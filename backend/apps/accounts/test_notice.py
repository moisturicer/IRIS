"""
The data notice and a person's answer to it (ADR-054 decisions 1-4 and 17, IR-789).

Tested at the HTTP boundary with real tokens, because the thing under test is
a server-side block: a screen that hides the app proves nothing. The suite gives
every new user a Yes (`conftest.py`); `make_unanswered` undoes that where a test
is about the unanswered state, which is how every real account starts.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.accounts import notice
from apps.accounts.models import DataNotice, NoticeAnswer, User
from apps.accounts.tests import make_unanswered, make_user
from apps.audit.models import AuditEvent
from core.enums import RoleName

PASSWORD = "pw12345!"
LOGIN = "/api/v1/auth/login/"
NOTICE = "/api/v1/auth/notice/"
ANSWER = "/api/v1/auth/notice/answer/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/users/me/"


def publish(number, **extra):
    """A newer notice, as IR-790 will publish one."""
    return DataNotice.objects.create(
        number=number, title=f"Notice {number}", subtitle="", sections=[{"title": "T", "body": "B"}],
        **extra,
    )


def sign_in(email):
    response = APIClient().post(LOGIN, {"email": email, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def bearer(tokens):
    return {"HTTP_AUTHORIZATION": f"Bearer {tokens['access']}"}


class TheNoticeLivesInTheDatabaseTests(TestCase):
    def test_version_one_exists_from_the_text_the_frontend_carried(self):
        first = DataNotice.objects.get(number=1)
        self.assertEqual(first.title, "DPA Consent Registry (RA 10173)")
        titles = [section["title"] for section in first.sections]
        self.assertIn("3. External AI processing", titles)
        self.assertIn("4. Your rights under RA 10173", titles)
        # DataNotice.tsx, the interim registration notice, is carried too.
        self.assertIn("Interim notice", titles)
        self.assertEqual(titles, [
            "Interim notice", "Notice review status",
            "Republic Act No. 10173 (Data Privacy Act of 2012) Terms", "1. What we collect",
            "2. How your submission is used", "3. External AI processing",
            "4. Your rights under RA 10173", "Consent Confirmation",
        ])
        self.assertEqual(first.subtitle, "Cebu Institute of Technology - University Technology Transfer Office")
        self.assertEqual(DataNotice.current().number, DataNotice.objects.order_by("-number").first().number)

    def test_the_current_notice_is_the_highest_number(self):
        publish(2)
        self.assertEqual(DataNotice.current().number, 2)
        self.assertEqual(notice.current_notice_number(), 2)

    def test_a_published_notice_is_never_edited(self):
        first = DataNotice.objects.get(number=1)
        first.title = "Changed afterwards"
        with self.assertRaises(ValueError):
            first.save()

    def test_numbers_are_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            publish(1)

    def test_the_notice_is_public_for_registration_and_carries_no_personal_fields(self):
        response = self.client.get(NOTICE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], DataNotice.current().number)
        self.assertNotIn("answer", response.data)
        self.assertNotIn("answer_required", response.data)


class AnAnswerIsStoredTests(APITestCase):
    def setUp(self):
        self.user = make_unanswered(make_user("answers@cit.edu", RoleName.STUDENT))
        self.client.force_authenticate(self.user)
        self.version = DataNotice.current().number

    def answer(self, **body):
        payload = {"notice_version": self.version, "agree_dpa": True, "ai_consent": True, **body}
        return self.client.post(ANSWER, payload, format="json")

    def test_a_yes_records_the_version_the_time_and_both_answers(self):
        before = timezone.now()
        response = self.answer(ai_consent=True)

        self.assertEqual(response.status_code, 201, response.content)
        row = NoticeAnswer.objects.get(user=self.user)
        self.assertEqual((row.notice.number, row.agreed_dpa, row.ai_consent), (self.version, True, True))
        self.assertGreaterEqual(row.answered_at, before)
        self.user.refresh_from_db()
        self.assertEqual(self.user.answered_notice_version, self.version)
        self.assertIs(self.user.ai_consent, True)
        self.assertEqual(self.user.notice_answered_at, row.answered_at)
        self.assertFalse(response.data["answer_required"])

    def test_a_no_is_a_complete_answer_and_the_account_stays_normal(self):
        response = self.answer(ai_consent=False)

        self.assertEqual(response.status_code, 201, response.content)
        self.user.refresh_from_db()
        self.assertIs(self.user.ai_consent, False)
        self.assertTrue(self.user.is_active)
        self.assertFalse(notice.requires_answer(self.user))
        # Normal means every endpoint, not only the notice ones.
        self.assertEqual(self.client.get(ME).status_code, 200)

    def test_the_history_keeps_every_answer_including_a_change_to_the_same_version(self):
        self.answer(ai_consent=True)
        self.answer(ai_consent=False)

        rows = list(NoticeAnswer.objects.filter(user=self.user).order_by("id"))
        self.assertEqual([r.ai_consent for r in rows], [True, False])
        self.user.refresh_from_db()
        self.assertIs(self.user.ai_consent, False)

    def test_both_answers_are_required_and_neither_has_a_default(self):
        for missing in ("agree_dpa", "ai_consent", "notice_version"):
            with self.subTest(missing=missing):
                payload = {"notice_version": self.version, "agree_dpa": True, "ai_consent": True}
                del payload[missing]
                response = self.client.post(ANSWER, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(missing, response.data)
        self.assertFalse(NoticeAnswer.objects.filter(user=self.user).exists())

    def test_a_missing_ai_answer_in_a_form_post_is_still_missing_not_no(self):
        response = self.client.post(ANSWER, {"notice_version": self.version, "agree_dpa": "true"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("ai_consent", response.data)

    def test_the_data_privacy_agreement_must_be_agreed(self):
        response = self.answer(agree_dpa=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("agree_dpa", response.data)
        self.assertFalse(NoticeAnswer.objects.filter(user=self.user).exists())

    def test_the_stored_answer_is_always_an_agreement(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            NoticeAnswer.objects.create(
                user=self.user, notice=DataNotice.current(), agreed_dpa=False, ai_consent=True,
            )

    def test_history_is_never_edited(self):
        self.answer()
        row = NoticeAnswer.objects.get(user=self.user)
        row.ai_consent = False
        with self.assertRaises(ValueError):
            row.save()

    def test_answering_is_audited_with_the_previous_answer(self):
        self.answer(ai_consent=True)
        self.answer(ai_consent=False)

        events = list(AuditEvent.objects.filter(event_type=AuditEvent.NOTICE_ANSWERED, user=self.user).order_by("id"))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].metadata, {
            "notice_version": self.version, "ai_consent": True,
            "previous_notice_version": None, "previous_ai_consent": None,
        })
        self.assertEqual(events[1].metadata, {
            "notice_version": self.version, "ai_consent": False,
            "previous_notice_version": self.version, "previous_ai_consent": True,
        })

    def test_the_discoverable_setting_is_not_touched(self):
        # ADR-032 §8 keeps it its own decision. The only fields an answer writes:
        before = {f.name: getattr(self.user, f.name) for f in User._meta.concrete_fields}
        self.answer(ai_consent=False)
        self.user.refresh_from_db()
        after = {f.name: getattr(self.user, f.name) for f in User._meta.concrete_fields}
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(
            changed, {"answered_notice_version", "ai_consent", "notice_answered_at", "consent_given"},
        )


class AStaleNoticeIsRefusedTests(APITestCase):
    def setUp(self):
        self.user = make_unanswered(make_user("stale@cit.edu", RoleName.STUDENT))
        self.client.force_authenticate(self.user)

    def test_answering_an_older_version_is_refused_with_the_current_notice(self):
        shown = DataNotice.current().number
        newer = publish(shown + 1)

        response = self.client.post(
            ANSWER, {"notice_version": shown, "agree_dpa": True, "ai_consent": True}, format="json",
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["code"], "notice_stale")
        self.assertEqual(response.data["notice"]["version"], newer.number)
        self.assertEqual(response.data["notice"]["title"], newer.title)
        self.assertFalse(NoticeAnswer.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.answered_notice_version)

    def test_a_version_the_server_never_showed_is_refused_the_same_way(self):
        shown = DataNotice.current().number
        response = self.client.post(
            ANSWER, {"notice_version": shown + 5, "agree_dpa": True, "ai_consent": False}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["notice"]["version"], shown)

    def test_a_refused_stale_answer_writes_no_audit_event(self):
        shown = DataNotice.current().number
        publish(shown + 1)
        self.client.post(ANSWER, {"notice_version": shown, "agree_dpa": True, "ai_consent": True}, format="json")
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.NOTICE_ANSWERED).exists())


class RegistrationAsksBothTests(APITestCase):
    url = reverse("auth-register")

    def payload(self, **extra):
        return {
            "email": "newcomer@cit.edu", "first_name": "New", "last_name": "Comer",
            "password": "Kalamansi-Tide-42", "confirm_password": "Kalamansi-Tide-42",
            "notice_version": DataNotice.current().number, "agree_dpa": True, "ai_consent": True,
            **extra,
        }

    def post(self, **extra):
        data = self.payload(**extra)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post(self.url, data, format="json")

    def test_registering_with_yes_records_the_first_answer(self):
        response = self.post(ai_consent=True)
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email="newcomer@cit.edu")
        self.assertEqual(user.answered_notice_version, DataNotice.current().number)
        self.assertIs(user.ai_consent, True)
        self.assertEqual(NoticeAnswer.objects.filter(user=user).count(), 1)
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.NOTICE_ANSWERED, user=user).exists())

    def test_registering_with_no_still_gives_a_normal_account(self):
        response = self.post(ai_consent=False)
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email="newcomer@cit.edu")
        self.assertIs(user.ai_consent, False)
        self.assertTrue(user.is_active)
        self.assertFalse(notice.requires_answer(user))

    def test_the_ai_answer_has_no_default(self):
        response = self.post(ai_consent=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn("ai_consent", response.data)
        self.assertFalse(User.objects.filter(email="newcomer@cit.edu").exists())

    def test_the_data_privacy_agreement_is_required(self):
        for value in (False, None):
            with self.subTest(value=value):
                response = self.post(agree_dpa=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("agree_dpa", response.data)
        self.assertFalse(User.objects.filter(email="newcomer@cit.edu").exists())

    def test_the_old_single_box_no_longer_registers_anyone(self):
        data = self.payload()
        for key in ("notice_version", "agree_dpa", "ai_consent"):
            del data[key]
        data["consent_given"] = True
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@cit.edu").exists())

    def test_a_notice_published_while_the_form_was_open_is_refused_with_it(self):
        shown = DataNotice.current().number
        publish(shown + 1)
        response = self.post(notice_version=shown)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["notice"]["version"], shown + 1)
        self.assertFalse(User.objects.filter(email="newcomer@cit.edu").exists())


class NobodyUsesIrisWithoutAnsweringTests(APITestCase):
    """ADR-054 decision 3, enforced for every account the server knows."""

    def account(self, email, role_name, **extra):
        return make_unanswered(make_user(email, role_name, **extra))

    def users(self):
        admin = self.account("blocked-admin@cit.edu", None, is_staff=True, is_superuser=True)
        return {
            "student": self.account("blocked-student@cit.edu", RoleName.STUDENT),
            "adviser": self.account("blocked-adviser@cit.edu", RoleName.ADVISER),
            "rdco": self.account("blocked-rdco@cit.edu", RoleName.RDCO),
            "itso": self.account("blocked-itso@cit.edu", RoleName.ITSO),
            "ierc": self.account("blocked-ierc@cit.edu", RoleName.IERC),
            "ktto": self.account("blocked-ktto@cit.edu", RoleName.KTTO),
            "sysadmin": self.account("blocked-sysadmin@cit.edu", RoleName.SYSTEM_ADMIN),
            "superuser": admin,
        }

    def test_every_other_request_answers_notice_acceptance_required(self):
        for label, user in self.users().items():
            with self.subTest(account=label):
                tokens = sign_in(user.email)
                self.assertTrue(tokens["notice_answer_required"])
                for url in (ME, reverse("record-list"), reverse("user-advisers"), reverse("audit-list")):
                    response = APIClient().get(url, **bearer(tokens))
                    self.assertEqual(response.status_code, 403, (url, response.content))
                    self.assertEqual(response.json()["code"], "notice_acceptance_required")

    def test_a_write_is_refused_the_same_way(self):
        user = self.account("blocked-writer@cit.edu", RoleName.STUDENT)
        tokens = sign_in(user.email)
        response = APIClient().patch(ME, {"first_name": "Sneaky"}, format="json", **bearer(tokens))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "notice_acceptance_required")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Test")

    def test_the_person_can_read_the_notice_answer_it_and_sign_out(self):
        user = self.account("allowed@cit.edu", RoleName.STUDENT)
        tokens = sign_in(user.email)
        client = APIClient()

        read = client.get(NOTICE, **bearer(tokens))
        self.assertEqual(read.status_code, 200)
        self.assertTrue(read.json()["answer_required"])
        self.assertIsNone(read.json()["answer"])

        answered = client.post(
            ANSWER, {"notice_version": read.json()["version"], "agree_dpa": True, "ai_consent": False},
            format="json", **bearer(tokens),
        )
        self.assertEqual(answered.status_code, 201, answered.content)
        # Answered with the same token: the next request goes through at once.
        self.assertEqual(client.get(ME, **bearer(tokens)).status_code, 200)

    def test_signing_out_works_while_unanswered(self):
        user = self.account("leaving@cit.edu", RoleName.STUDENT)
        tokens = sign_in(user.email)
        response = APIClient().post(LOGOUT, {"refresh": tokens["refresh"]}, format="json", **bearer(tokens))
        self.assertEqual(response.status_code, 200, response.content)

    def test_refreshing_a_token_is_not_blocked(self):
        user = self.account("refresher@cit.edu", RoleName.STUDENT)
        tokens = sign_in(user.email)
        response = APIClient().post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def test_publishing_a_new_notice_blocks_someone_who_answered_the_old_one(self):
        user = make_user("was-fine@cit.edu", RoleName.STUDENT)
        tokens = sign_in(user.email)
        self.assertEqual(APIClient().get(ME, **bearer(tokens)).status_code, 200)

        publish(DataNotice.current().number + 1)

        response = APIClient().get(ME, **bearer(tokens))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "notice_acceptance_required")
        self.assertEqual(response.json()["notice_version"], DataNotice.current().number)

    def test_a_blocked_person_answers_the_new_notice_and_is_through(self):
        user = make_user("catches-up@cit.edu", RoleName.RDCO)
        tokens = sign_in(user.email)
        newer = publish(DataNotice.current().number + 1)

        answered = APIClient().post(
            ANSWER, {"notice_version": newer.number, "agree_dpa": True, "ai_consent": True},
            format="json", **bearer(tokens),
        )

        self.assertEqual(answered.status_code, 201, answered.content)
        self.assertEqual(APIClient().get(ME, **bearer(tokens)).status_code, 200)

    def test_an_unauthenticated_request_is_refused_as_before_not_as_a_notice_block(self):
        response = APIClient().get(ME)
        self.assertEqual(response.status_code, 401)


class ALastAnswerStandsTests(TestCase):
    def test_publishing_a_new_notice_changes_nobodys_stored_answer(self):
        graduate = make_user("graduate@cit.edu", RoleName.STUDENT)
        notice.answer_notice(graduate, notice_version=DataNotice.current().number, ai_consent=False)
        answered = DataNotice.current().number

        publish(answered + 1)
        publish(answered + 2)

        graduate.refresh_from_db()
        self.assertEqual(graduate.answered_notice_version, answered)
        self.assertIs(graduate.ai_consent, False)
        self.assertEqual(graduate.notice_answered_at, NoticeAnswer.objects.get(user=graduate).answered_at)
        # They must answer to *use* IRIS again, but what they said stands until then.
        self.assertTrue(notice.requires_answer(graduate))

    def test_existing_accounts_start_unanswered_never_as_having_accepted(self):
        # `bulk_create` sends no signal, so this is the model's own starting state
        # -- the state migration 0019 leaves every account that predates it in.
        legacy = User.objects.bulk_create([
            User(email="legacy@cit.edu", first_name="L", last_name="G", consent_given=True),
        ])[0]
        legacy.refresh_from_db()
        self.assertIsNone(legacy.answered_notice_version)
        self.assertIsNone(legacy.ai_consent)
        self.assertIsNone(legacy.notice_answered_at)
        self.assertTrue(notice.requires_answer(legacy))

    def test_no_notice_yet_blocks_nobody(self):
        DataNotice.objects.all().delete()
        self.assertFalse(notice.requires_answer(make_unanswered(make_user("early@cit.edu"))))
