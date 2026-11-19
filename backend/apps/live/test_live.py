"""
ADR-073 (IR-1213): live-update hints.

Three seams:
- **Publishing**: a write publishes a hint on commit, to the channels the
  server picks, through a recorder (`use_publisher`); CI has no Redis.
- **The hub and the stream**: a hint dispatched to a channel reaches the
  streams registered on it and no other; a slow stream is closed.
- **The view**: who may open a stream, and that opening one records nothing.
"""
import json
from datetime import timedelta
from unittest import mock

import pytest
from asgiref.sync import async_to_sync
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import UserSession
from apps.accounts.sessions import start_session
from apps.live import channels as ch
from apps.live.publish import publish, use_publisher
from apps.live.stream import QUEUE_MAX, Hub, events, use_hub
from apps.live.views import live_stream
from apps.notifications.models import Notification, NotificationType
from apps.records.models import Record, RecordType
from apps.reviews.models import RecordAssignment
from apps.tests.test_authorization_matrix import make_user


class Recorder:
    def __init__(self):
        self.sent = []

    def __call__(self, channel, payload):
        self.sent.append((channel, json.loads(payload)["topics"]))


# --- publishing --------------------------------------------------------------------


@pytest.mark.db_required
class PublishingTests(TestCase):
    def setUp(self):
        self.reader = make_user("live-reader@cit.edu", "Student")
        self.adviser = make_user("live-adviser@cit.edu", "Adviser")
        kind = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        self.record = Record.objects.create(title="Live", record_type=kind, added_by=self.reader)
        self.notif_type = NotificationType.objects.get_or_create(name="live-test")[0]

    def recorded(self, write):
        recorder = Recorder()
        with use_publisher(recorder), self.captureOnCommitCallbacks(execute=True):
            write()
        return recorder.sent

    def test_a_notification_hints_its_recipient_with_the_record(self):
        sent = self.recorded(lambda: Notification.objects.create(
            recipient=self.reader, record=self.record, notif_type=self.notif_type))
        self.assertEqual(sent, [(
            ch.user_channel(self.reader.pk),
            sorted(["library", "notifications", "reviews", f"record:{self.record.pk}"]),
        )])

    def test_a_notification_without_a_record_hints_only_notifications(self):
        sent = self.recorded(lambda: Notification.objects.create(
            recipient=self.reader, notif_type=self.notif_type))
        self.assertEqual(sent, [(ch.user_channel(self.reader.pk), ["notifications"])])

    def test_a_broadcast_reaches_the_roles_channel(self):
        role = self.adviser.role
        sent = self.recorded(lambda: Notification.objects.create(
            broadcast_to_role=role, notif_type=self.notif_type))
        self.assertEqual(sent, [(ch.role_channel("Adviser"), ["notifications"])])

    def test_an_offices_pool_change_hints_the_office_with_no_record(self):
        sent = self.recorded(lambda: RecordAssignment.objects.create(record=self.record, party="itso"))
        self.assertEqual(sent, [(ch.role_channel("itso"), ["reviews"])])

    def test_an_advisers_assignment_hints_no_role(self):
        sent = self.recorded(lambda: RecordAssignment.objects.create(record=self.record, party="adviser"))
        self.assertEqual(sent, [])

    def test_a_download_request_hints_rdcos_queues(self):
        from apps.records.models import DownloadRequest
        sent = self.recorded(lambda: DownloadRequest.objects.create(record=self.record, requested_by=self.reader))
        self.assertIn((ch.role_channel("RDCO"), ["queues"]), sent)

    def test_nothing_is_sent_for_a_rolled_back_write(self):
        recorder = Recorder()
        with use_publisher(recorder):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                Notification.objects.create(recipient=self.reader, notif_type=self.notif_type)
        self.assertEqual(len(callbacks), 1)  # queued for commit, not sent
        self.assertEqual(recorder.sent, [])

    def test_publishing_is_off_without_a_publisher_when_disabled(self):
        with mock.patch("apps.live.publish._redis_send") as send, self.captureOnCommitCallbacks(execute=True):
            publish([ch.user_channel(self.reader.pk)], ["reviews"])
        send.assert_not_called()

    def test_a_failing_publisher_never_fails_the_write(self):
        def broken(channel, payload):
            raise ConnectionError("redis is down")
        with use_publisher(broken), self.captureOnCommitCallbacks(execute=True):
            Notification.objects.create(recipient=self.reader, notif_type=self.notif_type)
        self.assertTrue(Notification.objects.filter(recipient=self.reader).exists())


# --- the hub and the stream -----------------------------------------------------------


class HubAndStreamTests(SimpleTestCase):
    def test_a_hint_reaches_only_the_streams_on_its_channel(self):
        async def run():
            hub = Hub(listen=False)
            mine = hub.register(["live:user:1", "live:role:itso"])
            theirs = hub.register(["live:user:2"])
            hub.dispatch("live:user:1", '{"topics":["reviews"]}')
            hub.dispatch("live:role:itso", '{"topics":["reviews"]}')
            return mine.qsize(), theirs.qsize()
        self.assertEqual(async_to_sync(run)(), (2, 0))

    def test_unregistering_stops_delivery(self):
        async def run():
            hub = Hub(listen=False)
            queue = hub.register(["live:user:1"])
            hub.unregister(["live:user:1"], queue)
            hub.dispatch("live:user:1", "{}")
            return queue.qsize(), hub.stream_count
        self.assertEqual(async_to_sync(run)(), (0, 0))

    def test_a_stream_that_falls_behind_is_closed(self):
        async def run():
            hub = Hub(listen=False)
            queue = hub.register(["live:user:1"])
            for _ in range(QUEUE_MAX + 1):
                hub.dispatch("live:user:1", "{}")
            lines = [line async for line in events(queue, expires_at=10**12)]
            return queue.overflowed, lines
        overflowed, lines = async_to_sync(run)()
        self.assertTrue(overflowed)
        self.assertEqual(lines, [": connected\n\n"])

    def test_the_stream_sends_hints_and_pings_and_ends_with_its_token(self):
        clock = {"now": 1000.0}

        async def run():
            hub = Hub(listen=False)
            queue = hub.register(["live:user:1"])
            hub.dispatch("live:user:1", '{"topics":["reviews"]}')
            lines = []
            async for line in events(queue, expires_at=1000.05, ping=0.01, clock=lambda: clock["now"]):
                lines.append(line)
                if line.startswith(": ping"):
                    clock["now"] = 1001.0  # the token has expired
            return lines
        lines = async_to_sync(run)()
        self.assertEqual(lines[0], ": connected\n\n")
        self.assertEqual(lines[1], 'data: {"topics":["reviews"]}\n\n')
        self.assertEqual(lines[2], ": ping\n\n")
        self.assertEqual(len(lines), 3)


# --- the view ------------------------------------------------------------------------


@pytest.mark.db_required
class StreamViewTests(TestCase):
    def setUp(self):
        self.user = make_user("live-viewer@cit.edu", "ITSO")
        self.access = str(start_session(self.user).access_token)

    def request(self, token=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return RequestFactory().get("/api/v1/live/", **headers)

    def test_no_token_is_refused(self):
        response = async_to_sync(live_stream)(self.request())
        self.assertEqual(response.status_code, 401)

    def test_a_bad_token_is_refused(self):
        response = async_to_sync(live_stream)(self.request("not-a-token"))
        self.assertEqual(response.status_code, 401)

    def test_an_ended_session_is_refused(self):
        UserSession.objects.filter(user=self.user).update(ended_at=timezone.now(), ended_reason="logout")
        response = async_to_sync(live_stream)(self.request(self.access))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(json.loads(response.content)["code"], "session_ended")

    def test_an_idle_session_is_refused_and_opening_records_no_activity(self):
        before = timezone.now() - timedelta(minutes=31)
        UserSession.objects.filter(user=self.user).update(last_activity_at=before)
        response = async_to_sync(live_stream)(self.request(self.access))
        self.assertEqual(response.status_code, 401)
        session = UserSession.objects.get(user=self.user)
        # Read, never written: neither ended nor touched by the stream.
        self.assertIsNone(session.ended_at)
        self.assertEqual(session.last_activity_at, before)

    def test_a_stream_delivers_its_users_hints_and_unregisters_when_closed(self):
        hub = Hub(listen=False)

        async def run():
            response = await live_stream(self.request(self.access))
            stream = response.streaming_content
            first = await stream.__anext__()
            hub.dispatch(ch.user_channel(self.user.pk), '{"topics":["reviews"]}')
            hub.dispatch(ch.user_channel(self.user.pk + 1), '{"topics":["library"]}')
            second = await stream.__anext__()
            open_streams = hub.stream_count
            await stream.aclose()
            return response, first, second, open_streams

        with use_hub(hub):
            response, first, second, open_streams = async_to_sync(run)()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(first, b": connected\n\n")
        self.assertEqual(second, b'data: {"topics":["reviews"]}\n\n')
        self.assertEqual(open_streams, 1)
        self.assertEqual(hub.stream_count, 0)

    def test_the_stream_listens_on_its_users_and_roles_channels_only(self):
        self.assertEqual(ch.channels_for(self.user), [ch.user_channel(self.user.pk), "live:role:itso"])
