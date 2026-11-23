"""
IR-1289 (ADR-073 decision 3, amended): the person who asked hears what became
of it.

- A role request saved, or a role changed through `User.assign_role`, tells
  that person `account` on their own channel, and nobody else.
- A Call saved or removed tells its poster `calls`, and nobody else.

Through a recorder: CI has no Redis.
"""
from django.test import TestCase

from apps.accounts.models import Role, RoleRequest
from apps.accounts.services import approve_role_request, decline_role_request
from apps.live import channels as ch
from apps.live.publish import use_publisher
from apps.opportunities import review
from apps.opportunities.tests import make_opportunity
from apps.tests.test_authorization_matrix import make_user
from core.enums import CallStatus, RoleName

from .test_live import Recorder


class RequestHintTests(TestCase):
    def setUp(self):
        self.asker = make_user("live-asker@cit.edu")
        self.adviser = make_user("live-poster@cit.edu", RoleName.ADVISER)
        self.rdco = make_user("live-rdco@cit.edu", RoleName.RDCO)
        self.bystander = make_user("live-bystander@cit.edu", RoleName.STUDENT)

    def told(self, write, topic):
        """The channels told exactly `[topic]` while `write` ran and committed."""
        recorder = Recorder()
        with use_publisher(recorder), self.captureOnCommitCallbacks(execute=True):
            write()
        return sorted(channel for channel, topics in recorder.sent if topics == [topic])

    # --- account ------------------------------------------------------------------

    def asked(self):
        role = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        return RoleRequest.objects.create(user=self.asker, requested_role=role)

    def test_asking_tells_the_asker_only(self):
        self.assertEqual(self.told(self.asked, ch.ACCOUNT), [ch.user_channel(self.asker.pk)])

    def test_approving_tells_the_asker_and_nobody_else(self):
        request = self.asked()
        told = self.told(lambda: approve_role_request(request, reviewed_by=self.rdco), ch.ACCOUNT)
        # The role change and the decision each tell them; their tabs coalesce it.
        self.assertEqual(set(told), {ch.user_channel(self.asker.pk)})

    def test_declining_tells_the_asker(self):
        request = self.asked()
        told = self.told(lambda: decline_role_request(request, reviewed_by=self.rdco), ch.ACCOUNT)
        self.assertEqual(told, [ch.user_channel(self.asker.pk)])

    def test_an_admin_s_role_change_tells_that_person(self):
        adviser = Role.objects.get_or_create(name=RoleName.ADVISER)[0]
        told = self.told(lambda: self.bystander.assign_role(adviser), ch.ACCOUNT)
        self.assertEqual(told, [ch.user_channel(self.bystander.pk)])

    # --- calls ----------------------------------------------------------------------

    def test_confirming_rejecting_and_removing_a_call_tell_its_poster_only(self):
        for act in ("confirm", "reject", "remove"):
            with self.subTest(act=act):
                call = make_opportunity(posted_by=self.adviser, status=CallStatus.PENDING)

                def decide(call=call, act=act):
                    if act == "confirm":
                        review.confirm(call.pk, by=self.rdco, seen=call.updated_at)
                    elif act == "reject":
                        review.reject(call.pk, by=self.rdco, seen=call.updated_at, reason="Wrong link.")
                    else:
                        review.remove(call.pk, by=self.rdco, reason="Duplicate.")

                told = self.told(decide, ch.CALLS)
                self.assertEqual(set(told), {ch.user_channel(self.adviser.pk)})

    def test_a_call_nobody_posted_tells_nobody(self):
        self.assertEqual(self.told(lambda: make_opportunity(), ch.CALLS), [])
