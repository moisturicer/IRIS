"""
RDCO publishes a new data notice version by pasting it (IR-799).

ADR-051 decisions 16-17, as amended by ADR-063 decision 9: only RDCO
publishes and only RDCO reads every version, on Setup (IR-972); the System
Admin sees each publication in the Audit Log; anyone reads the current one. A version never changes. Tested at the HTTP boundary with real
tokens, because the sign-in block a publish triggers is enforced in
authentication, which `force_authenticate` would skip.
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts import notice
from apps.accounts.models import DataNotice, NoticeAnswer, User
from apps.accounts.tests import make_user
from apps.audit.models import AuditEvent
from core.enums import RoleName

PASSWORD = "pw12345!"
LOGIN = "/api/v1/auth/login/"
CURRENT = "/api/v1/auth/notice/"
ANSWER = "/api/v1/auth/notice/answer/"
VERSIONS = "/api/v1/auth/notice/versions/"
IMPACT = "/api/v1/auth/notice/versions/impact/"
ME = "/api/v1/users/me/"

#: Every role but RDCO, plus the role-less account. None may publish.
NOT_PUBLISHERS = [
    RoleName.STUDENT, RoleName.ADVISER, RoleName.KTTO, RoleName.ITSO,
    RoleName.IERC, RoleName.SYSTEM_ADMIN, None,
]


def client_for(user) -> APIClient:
    client = APIClient()
    response = client.post(LOGIN, {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
    return client


class PublishTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("rdco-publisher@cit.edu", RoleName.RDCO)
        self.client = client_for(self.rdco)
        self.base = DataNotice.current().number

    def publish(self, text="New notice.\n\nSecond paragraph.", based_on=None, client=None):
        return (client or self.client).post(
            VERSIONS, {"based_on_version": self.base if based_on is None else based_on, "text": text},
            format="json",
        )

    def test_rdco_publishes_the_next_version_which_is_current_at_once(self):
        response = self.publish("Line one.\r\nLine two.\n")

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["version"], self.base + 1)
        # Line endings normalized, line breaks kept, trailing whitespace dropped.
        self.assertEqual(body["text"], "Line one.\nLine two.")
        self.assertEqual(body["published_by"]["email"], self.rdco.email)
        current = APIClient().get(CURRENT).json()
        self.assertEqual(current["version"], self.base + 1)
        self.assertEqual(current["text"], "Line one.\nLine two.")

    def test_a_pasted_version_still_reaches_screens_that_render_sections(self):
        self.publish("Whole text.")

        current = APIClient().get(CURRENT).json()
        self.assertEqual(current["sections"], [{"title": "", "body": "Whole text."}])
        self.assertEqual(current["title"], notice.PASTED_NOTICE_TITLE)

    def test_html_is_stored_and_returned_as_the_characters_pasted(self):
        text = '<script>alert(1)</script> <a href="x">link</a> & 5 < 6'

        self.assertEqual(self.publish(text).status_code, 201)

        stored = DataNotice.current()
        self.assertEqual(stored.text, text)
        response = APIClient().get(CURRENT)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["text"], text)

    def test_blank_text_is_refused(self):
        for text in ["", "   ", "\n\n\t"]:
            with self.subTest(text=repr(text)):
                response = self.publish(text)
                self.assertEqual(response.status_code, 400)
                self.assertIn("text", response.json())
        self.assertEqual(DataNotice.current().number, self.base)

    def test_text_over_the_limit_is_refused(self):
        response = self.publish("x" * (notice.NOTICE_TEXT_MAX_LENGTH + 1))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DataNotice.current().number, self.base)
        self.assertEqual(self.publish("x" * notice.NOTICE_TEXT_MAX_LENGTH).status_code, 201)

    def test_version_one_as_text_fits_the_limit(self):
        first = DataNotice.objects.order_by("number").first()
        self.assertLess(len(first.display_text()), notice.NOTICE_TEXT_MAX_LENGTH)

    def test_a_stale_publish_is_refused_with_the_current_notice(self):
        other = make_user("rdco-other@cit.edu", RoleName.RDCO)
        other_client = client_for(other)
        self.assertEqual(self.publish("First paste.").status_code, 201)

        # The second person started from the same version and never saw the first
        # paste. The sign-in block stops them first, since there is a new notice ...
        blocked = self.publish("Second paste.", client=other_client)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], notice.ACCEPTANCE_REQUIRED_CODE)
        # ... and once they have answered it, their paste still names the old version.
        notice.answer_notice(other, notice_version=self.base + 1, ai_consent=True)
        response = self.publish("Second paste.", client=other_client)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], notice.STALE_NOTICE_CODE)
        self.assertEqual(response.json()["notice"]["version"], self.base + 1)
        self.assertEqual(DataNotice.current().text, "First paste.")

    def test_a_version_newer_than_any_published_is_refused_as_stale(self):
        response = self.publish(based_on=self.base + 5)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(DataNotice.current().number, self.base)

    def test_publishing_is_not_answering(self):
        self.assertEqual(self.publish().status_code, 201)

        self.rdco.refresh_from_db()
        self.assertEqual(self.rdco.answered_notice_version, self.base)
        self.assertFalse(NoticeAnswer.objects.filter(user=self.rdco, notice__number=self.base + 1).exists())
        # The publisher is blocked like everyone else until they answer it.
        blocked = self.client.get(ME)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], notice.ACCEPTANCE_REQUIRED_CODE)
        answered = self.client.post(
            ANSWER, {"notice_version": self.base + 1, "agree_dpa": True, "ai_consent": True}, format="json",
        )
        self.assertEqual(answered.status_code, 201, answered.content)
        self.assertEqual(self.client.get(ME).status_code, 200)

    def test_an_audit_event_names_the_version_and_the_publisher(self):
        text = "Audited notice."
        self.publish(text)

        event = AuditEvent.objects.get(event_type=AuditEvent.NOTICE_PUBLISHED)
        self.assertEqual(event.user_id, self.rdco.pk)
        self.assertEqual(event.metadata["notice_version"], self.base + 1)
        self.assertEqual(event.metadata["previous_notice_version"], self.base)
        self.assertEqual(event.metadata["characters"], len(text))
        self.assertNotIn(text, str(event.metadata))

    def test_a_refused_publish_writes_no_audit_event(self):
        self.publish("")
        self.publish(based_on=self.base + 5)

        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.NOTICE_PUBLISHED).exists())

    def test_no_other_role_can_publish(self):
        for role in NOT_PUBLISHERS:
            with self.subTest(role=role):
                user = make_user(f"not-publisher-{role or 'none'}@cit.edu".lower(), role)
                response = self.publish(client=client_for(user))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(APIClient().post(
            VERSIONS, {"based_on_version": self.base, "text": "x"}, format="json",
        ).status_code, 401)
        self.assertEqual(DataNotice.current().number, self.base)

    def test_there_is_no_edit_or_delete_route(self):
        self.publish()
        notice.answer_notice(self.rdco, notice_version=self.base + 1, ai_consent=True)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(VERSIONS, {"text": "changed"}, format="json")
                self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.get(f"{VERSIONS}{self.base + 1}/").status_code, 404)


class ReadVersionsTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("rdco-reader@cit.edu", RoleName.RDCO)
        self.base = DataNotice.current().number
        notice.publish_notice(self.rdco, based_on_version=self.base, text="Pasted.")
        # Publishing isn't answering: the publisher answers before reading on.
        notice.answer_notice(self.rdco, notice_version=self.base + 1, ai_consent=True)

    def answered(self, email, role):
        user = make_user(email, role)
        notice.answer_notice(user, notice_version=self.base + 1, ai_consent=True)
        return client_for(user)

    def test_rdco_lists_every_version_with_who_and_when(self):
        response = client_for(self.rdco).get(VERSIONS)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual([r["version"] for r in rows], list(range(self.base + 1, 0, -1)))
        self.assertEqual(rows[0]["published_by"]["email"], self.rdco.email)
        self.assertEqual(rows[0]["text"], "Pasted.")
        self.assertTrue(rows[0]["published_at"])
        # Version 1 came from a migration, published by nobody, readable as text.
        self.assertIsNone(rows[-1]["published_by"])
        self.assertTrue(rows[-1]["text"])

    def test_no_other_role_lists_the_versions(self):
        # The System Admin included (ADR-063 decision 9, IR-972): it reads each
        # publication in the Audit Log, which records who, when and which version.
        for role in NOT_PUBLISHERS:
            with self.subTest(role=role):
                client = self.answered(f"list-{role or 'none'}@cit.edu".lower(), role)
                self.assertEqual(client.get(VERSIONS).status_code, 403)
        self.assertEqual(APIClient().get(VERSIONS).status_code, 401)

    def test_anyone_reads_the_current_version_signed_in_or_not(self):
        self.assertEqual(APIClient().get(CURRENT).json()["version"], self.base + 1)
        student = self.answered("current-reader@cit.edu", RoleName.STUDENT)
        self.assertEqual(student.get(CURRENT).json()["version"], self.base + 1)


class ImpactTests(APITestCase):
    def test_rdco_sees_how_many_live_accounts_would_answer(self):
        rdco = make_user("rdco-impact@cit.edu", RoleName.RDCO)
        make_user("live@cit.edu", RoleName.STUDENT)
        make_user("inactive@cit.edu", RoleName.STUDENT, is_active=False)
        make_user("deleted@cit.edu", RoleName.STUDENT, deleted_at=timezone.now())

        response = client_for(rdco).get(IMPACT)

        self.assertEqual(response.status_code, 200)
        expected = User.objects.filter(is_active=True, deleted_at__isnull=True).count()
        self.assertEqual(response.json(), {
            "current_version": DataNotice.current().number, "accounts_to_answer": expected,
        })
        self.assertEqual(notice.accounts_to_answer(), expected)

    def test_only_rdco_sees_the_impact_count(self):
        for role in NOT_PUBLISHERS:
            with self.subTest(role=role):
                user = make_user(f"impact-{role or 'none'}@cit.edu".lower(), role)
                self.assertEqual(client_for(user).get(IMPACT).status_code, 403)
        self.assertEqual(APIClient().get(IMPACT).status_code, 401)


class VersionsNeverChangeTests(TestCase):
    """ADR-051 decision 17: no edit or delete in the database's normal paths."""

    def setUp(self):
        self.notice = DataNotice.current()

    def test_saving_an_existing_version_is_refused(self):
        self.notice.text = "changed"
        with self.assertRaises(ValueError):
            self.notice.save()

    def test_deleting_a_version_is_refused(self):
        with self.assertRaises(ValueError):
            self.notice.delete()
        with self.assertRaises(ValueError):
            DataNotice.objects.filter(pk=self.notice.pk).delete()

    def test_bulk_update_is_refused(self):
        with self.assertRaises(ValueError):
            DataNotice.objects.filter(pk=self.notice.pk).update(text="changed")
        self.assertTrue(DataNotice.objects.filter(pk=self.notice.pk, text=self.notice.text).exists())
