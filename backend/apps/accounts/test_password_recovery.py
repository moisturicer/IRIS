"""
Recover a forgotten password through email (IR-642, ADR-045).

Tested at the seams ADR-045 §9 names: the anonymous HTTP API with Django's
real mail outbox, the authenticated API for what a reset does to existing
credentials, and the worker boundary -- `deliver_recovery_intent` and the
periodic dispatcher. The suite's Celery broker is in-memory and executes
nothing, so a test runs the worker itself, exactly as a `celery-default`
process would after the request commits. That is also what proves the request
path sends no mail of its own.

The clock moved is `apps.accounts.recovery.clock.now` alone.
"""

import re
import threading
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import RecoveryIntent, User
from apps.accounts.recovery.delivery import deliver_recovery_intent

REQUEST = "/api/v1/auth/password/reset/request/"
CONFIRM = "/api/v1/auth/password/reset/confirm/"
LOGIN = "/api/v1/auth/login/"
OLD = "Original-pass-1"
NEW = "Brand-new-pass-2"

GENERIC_202 = {
    "code": "request_received",
    "detail": "If this address is eligible, an email will arrive shortly. "
              "You can try again after 60 seconds.",
    "retry_after": 60,
}
INVALID_LINK = {
    "code": "invalid_link",
    "detail": "This link is invalid or no longer available. Request a new email.",
}


class Clock:
    def __init__(self):
        self.at = timezone.now()

    def __call__(self):
        return self.at

    def advance(self, **kwargs):
        self.at += timedelta(**kwargs)


class RecoveryTestCase(APITestCase):
    def setUp(self):
        self.clock = Clock()
        patcher = patch("apps.accounts.recovery.clock.now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = self.make_user("reader@cit.edu")

    def make_user(self, email, **flags):
        flags.setdefault("is_verified", True)
        return User.objects.create_user(
            email=email, password=OLD, first_name="Rea", last_name="Der", **flags
        )

    def request_reset(self, email="reader@cit.edu", ip="10.0.0.1", **extra):
        return self.client.post(
            REQUEST, {"email": email}, format="json", REMOTE_ADDR=ip, **extra
        )

    def confirm(self, token, new=NEW, confirm=None, ip="10.0.0.1"):
        return self.client.post(
            CONFIRM,
            {"token": token, "new_password": new,
             "confirm_password": new if confirm is None else confirm},
            format="json", REMOTE_ADDR=ip,
        )

    def run_workers(self):
        """Every pending intent through the worker, as celery-default would."""
        for intent_id in RecoveryIntent.objects.values_list("id", flat=True):
            deliver_recovery_intent(str(intent_id))

    def token_from(self, message):
        match = re.search(r"/password/reset#token=([A-Za-z0-9_-]{43})\b", message.body)
        self.assertIsNotNone(match, message.body)
        return match.group(1)

    def emailed_token(self, email="reader@cit.edu"):
        self.assertEqual(self.request_reset(email).status_code, 202)
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)
        return self.token_from(mail.outbox[0])

    def login(self, password, email="reader@cit.edu"):
        return self.client.post(LOGIN, {"email": email, "password": password}, format="json")


class ResetJourneyTests(RecoveryTestCase):
    def test_request_email_link_confirm_then_only_the_new_password_signs_in(self):
        response = self.request_reset()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), GENERIC_202)
        self.assertEqual(mail.outbox, [], "the request path sends nothing itself")

        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@cit.edu"])
        token = self.token_from(mail.outbox[0])

        done = self.confirm(token)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json(), {
            "code": "password_reset",
            "detail": "Password updated. Sign in with your new password.",
        })
        self.assertEqual(self.login(OLD).status_code, 401)
        self.assertEqual(self.login(NEW).status_code, 200)


class RequestContractTests(RecoveryTestCase):
    """§2: one answer for every address; §1: who is actually sent mail."""

    def answer(self, response):
        return (response.status_code, response.json(), response["Cache-Control"], response.get("Retry-After"))

    def test_every_account_state_gets_the_identical_answer(self):
        self.make_user("locked@cit.edu", is_locked=True)
        self.make_user("inactive@cit.edu", is_active=False)
        self.make_user("unverified@cit.edu", is_verified=False)
        nopass = self.make_user("nopass@cit.edu")
        nopass.set_unusable_password()
        nopass.save()

        answers = {
            email: self.answer(self.request_reset(email, ip=f"10.0.1.{i}"))
            for i, email in enumerate([
                "reader@cit.edu", "nobody@cit.edu", "locked@cit.edu",
                "inactive@cit.edu", "unverified@cit.edu", "nopass@cit.edu",
            ])
        }
        for email, answer in answers.items():
            self.assertEqual(answer, (202, GENERIC_202, "no-store", None), email)

    def test_only_active_unlocked_accounts_with_a_password_are_sent_mail(self):
        self.make_user("locked@cit.edu", is_locked=True)
        self.make_user("inactive@cit.edu", is_active=False)
        self.make_user("unverified@cit.edu", is_verified=False)
        for i, email in enumerate(["nobody@cit.edu", "locked@cit.edu", "inactive@cit.edu",
                                   "unverified@cit.edu", "reader@cit.edu"]):
            self.request_reset(email, ip=f"10.0.2.{i}")
        self.run_workers()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["reader@cit.edu", "unverified@cit.edu"])

    def test_an_unknown_address_creates_no_account(self):
        self.request_reset("nobody@cit.edu")
        self.run_workers()
        self.assertFalse(User.objects.filter(email="nobody@cit.edu").exists())

    def test_the_domain_is_lowercased_and_the_local_part_kept(self):
        self.request_reset("  reader@CIT.EDU ")
        self.run_workers()
        self.assertEqual([m.to for m in mail.outbox], [["reader@cit.edu"]])

        mail.outbox.clear()
        self.clock.advance(seconds=61)
        self.request_reset("READER@cit.edu")
        self.run_workers()
        self.assertEqual(mail.outbox, [], "local-part case is not folded into a new identity rule")

    def test_an_invalid_or_missing_email_is_a_validation_error(self):
        for value in ["not-an-email", "", ("a" * 250) + "@cit.edu"]:
            response = self.request_reset(value)
            self.assertEqual(response.status_code, 400, value)
            self.assertEqual(response.json(), {"code": "validation_error",
                                               "errors": {"email": ["Enter a valid email address."]}})

        missing = self.client.post(REQUEST, {}, format="json")
        self.assertEqual(missing.json(), {"code": "validation_error",
                                          "errors": {"email": ["This field is required."]}})
        wrong_type = self.client.post(REQUEST, {"email": 7}, format="json")
        self.assertEqual(wrong_type.json()["errors"], {"email": ["Invalid value."]})
        extra = self.client.post(REQUEST, {"email": "reader@cit.edu", "role": "admin"}, format="json")
        self.assertEqual(extra.status_code, 400)
        self.assertEqual(extra.json()["errors"], {"role": ["Unknown field."]})

    def test_wrong_media_type_oversized_body_and_wrong_method(self):
        form = self.client.post(REQUEST, {"email": "reader@cit.edu"})
        self.assertEqual(form.status_code, 415)
        big = self.client.post(REQUEST, '{"email": "' + "a" * 5000 + '"}', content_type="application/json")
        self.assertEqual(big.status_code, 413)
        self.assertEqual(self.client.get(REQUEST).status_code, 405)
        self.run_workers()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(RecoveryIntent.objects.count(), 0)

    def test_an_authorization_header_is_ignored(self):
        response = self.request_reset(HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(response.status_code, 202)

    def test_the_request_path_never_reads_the_user_table(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            self.request_reset()
        user_table = User._meta.db_table
        self.assertFalse([q["sql"] for q in queries if f'"{user_table}"' in q["sql"]])


class ConsumptionTests(RecoveryTestCase):
    def test_a_verification_token_cannot_reset_a_password(self):
        from apps.accounts.models import RecoveryToken
        token = self.emailed_token()
        RecoveryToken.objects.update(purpose="email_verification")
        self.assertEqual(self.confirm(token).json(), INVALID_LINK)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))

    def test_a_completion_failure_rolls_back_password_token_audit_and_notice(self):
        from apps.accounts.models import RecoveryToken
        from apps.audit.models import AuditEvent
        token = self.emailed_token()
        with patch("apps.accounts.recovery.service.audit.record", side_effect=RuntimeError("fail")), \
                patch("apps.accounts.recovery.service.notify_password_changed") as notify:
            with self.assertRaises(RuntimeError):
                self.confirm(token)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))
        self.assertIsNone(RecoveryToken.objects.get().consumed_at)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.PASSWORD_RESET_COMPLETED).exists())
        notify.assert_not_called()

    """§2-§3: links are single use, short lived and judged against the account now."""

    def test_a_used_link_is_refused_and_the_password_stays_put(self):
        token = self.emailed_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        again = self.confirm(token, new="Another-pass-3")
        self.assertEqual((again.status_code, again.json()), (400, INVALID_LINK))
        self.assertEqual(self.login(NEW).status_code, 200)

    def test_malformed_unknown_and_wrong_type_tokens(self):
        for token in ["short", "x" * 43, "!" * 43, "a" * 44]:
            response = self.confirm(token)
            self.assertEqual((response.status_code, response.json()), (400, INVALID_LINK), token)
        wrong_type = self.client.post(CONFIRM, {"token": 5, "new_password": NEW, "confirm_password": NEW},
                                      format="json")
        self.assertEqual(wrong_type.json(), {"code": "validation_error", "errors": {"token": ["Invalid value."]}})
        self.assertEqual(self.login(OLD).status_code, 200)

    def test_the_link_expires_exactly_thirty_minutes_after_issue(self):
        token = self.emailed_token()
        self.clock.advance(seconds=1799)
        mismatch = self.confirm(token, new=NEW, confirm="mismatch")
        self.assertEqual(mismatch.json()["code"], "validation_error", "still valid one second before")
        self.clock.advance(seconds=1)
        self.assertEqual(self.confirm(token).json(), INVALID_LINK)
        self.assertEqual(self.login(OLD).status_code, 200)

    def test_a_newer_link_revokes_the_older_one(self):
        first = self.emailed_token()
        mail.outbox.clear()
        self.clock.advance(seconds=61)
        second = self.emailed_token()
        self.assertEqual(self.confirm(first).json(), INVALID_LINK)
        self.assertEqual(self.confirm(second).status_code, 200)

    def test_an_account_locked_or_deactivated_after_issue_cannot_use_its_link(self):
        for flags in ({"is_locked": True}, {"is_active": False}):
            with self.subTest(flags=flags):
                User.objects.filter(pk=self.user.pk).update(is_locked=False, is_active=True)
                mail.outbox.clear()
                self.clock.advance(seconds=61)
                token = self.emailed_token()
                User.objects.filter(pk=self.user.pk).update(**flags)
                self.assertEqual(self.confirm(token).json(), INVALID_LINK)
                self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))

    def test_a_changed_email_makes_the_link_unusable(self):
        token = self.emailed_token()
        User.objects.filter(pk=self.user.pk).update(email="moved@cit.edu")
        self.assertEqual(self.confirm(token).json(), INVALID_LINK)

    def test_restoring_an_old_email_does_not_restore_its_reset_link(self):
        token = self.emailed_token()
        original = self.user.email
        self.user.email = "changed@cit.edu"
        self.user.save(update_fields=["email"])
        self.user.email = original
        self.user.save(update_fields=["email"])
        self.assertEqual(self.confirm(token).json(), INVALID_LINK)

    def test_reset_changes_only_the_password(self):
        from apps.accounts.models import Role, RoleRequest
        role = Role.objects.get_or_create(name="Student")[0]
        RoleRequest.objects.create(user=self.user, requested_role=role)
        User.objects.filter(pk=self.user.pk).update(is_verified=False, consent_given=True)
        fields = ("is_verified", "is_locked", "is_active", "role", "is_staff",
                  "is_office_coordinator", "email", "consent_given")
        before = User.objects.filter(pk=self.user.pk).values(*fields).get()

        self.assertEqual(self.confirm(self.emailed_token()).status_code, 200)
        self.assertEqual(User.objects.filter(pk=self.user.pk).values(*fields).get(), before)
        self.assertEqual(RoleRequest.objects.get(user=self.user).status, "pending")

    def test_an_axes_lockout_neither_blocks_the_reset_nor_is_cleared_by_it(self):
        from axes.models import AccessAttempt
        AccessAttempt.objects.create(username="reader@cit.edu", ip_address="10.9.9.9",
                                     user_agent="t", failures_since_start=3)
        self.assertEqual(self.confirm(self.emailed_token()).status_code, 200)
        self.assertTrue(AccessAttempt.objects.filter(username="reader@cit.edu").exists())

    def test_the_response_never_carries_credentials(self):
        body = self.confirm(self.emailed_token()).json()
        self.assertEqual(set(body), {"code", "detail"})


class PasswordPolicyTests(RecoveryTestCase):
    """§4: the server's policy, every validator, and a refusal keeps the link."""

    def setUp(self):
        super().setUp()
        self.token = self.emailed_token()

    def errors(self, new, confirm=None):
        response = self.confirm(self.token, new=new, confirm=confirm)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["code"], "validation_error")
        return response.json()["errors"]

    def test_mismatch(self):
        self.assertEqual(self.errors(NEW, "Brand-new-pass-X"), {"confirm_password": ["Passwords do not match."]})

    def test_seven_and_129_characters_are_refused(self):
        self.assertIn("new_password", self.errors("Abcde1!"))
        self.assertEqual(self.errors("x" * 129), {"new_password": [
            "Ensure this field has no more than 128 characters."]})

    def test_128_characters_is_accepted(self):
        self.assertEqual(self.confirm(self.token, new="Qz7-" + "k" * 124).status_code, 200)

    def test_eight_characters_is_accepted(self):
        self.assertEqual(self.confirm(self.token, new="Qz7-kpWx").status_code, 200)

    def test_common_numeric_and_current_passwords(self):
        self.assertIn("new_password", self.errors("password"))
        self.assertIn("new_password", self.errors("83749201"))
        self.assertEqual(self.errors(OLD), {"new_password": ["Choose a different password."]})

    def test_a_refusal_leaves_the_link_usable_and_the_password_unchanged(self):
        self.errors("password")
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))
        self.assertEqual(self.confirm(self.token).status_code, 200)

    def test_passwords_are_not_trimmed(self):
        self.assertEqual(self.confirm(self.token, new="  Spaced-pass-9 ").status_code, 200)
        self.assertEqual(self.login("Spaced-pass-9").status_code, 401)
        self.assertEqual(self.login("  Spaced-pass-9 ").status_code, 200)


class LimitTests(RecoveryTestCase):
    """§5: shared sliding windows, measured from server time."""

    def rate_limited(self, response, retry_after):
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(response.json(), {"code": "rate_limited",
                                           "detail": "Too many requests. Try again later.",
                                           "retry_after": retry_after})
        self.assertEqual(response["Retry-After"], str(retry_after))

    def test_ten_requests_per_address_per_ten_minutes_and_the_cutoff_leaves_the_window(self):
        for i in range(10):
            self.assertEqual(self.request_reset(f"r{i}@cit.edu").status_code, 202)
        self.rate_limited(self.request_reset("r10@cit.edu"), 600)
        self.clock.advance(seconds=599)
        self.rate_limited(self.request_reset("r10@cit.edu"), 1)
        self.clock.advance(seconds=1)
        self.assertEqual(self.request_reset("r10@cit.edu").status_code, 202)

    def test_a_refused_request_is_not_counted(self):
        for i in range(10):
            self.request_reset(f"r{i}@cit.edu")
        for _ in range(5):
            self.request_reset("extra@cit.edu")
        self.clock.advance(seconds=600)
        self.assertEqual(self.request_reset("late@cit.edu").status_code, 202)

    def test_fifty_requests_per_address_per_day(self):
        for round_ in range(10):
            for i in range(5):
                self.assertEqual(self.request_reset(f"d{round_}-{i}@cit.edu").status_code, 202)
            self.clock.advance(seconds=600)
        self.rate_limited(self.request_reset("over@cit.edu"), 86400 - 6000)

    def test_malformed_bodies_count_toward_the_request_limit(self):
        # §5 counts request attempts by address: a body that is not JSON is
        # still an attempt, or it would be a free way past the counter.
        for _ in range(10):
            response = self.client.post(REQUEST, "{not json", content_type="application/json",
                                        REMOTE_ADDR="10.0.0.1")
            self.assertEqual(response.status_code, 400)
        self.rate_limited(self.request_reset("r@cit.edu"), 600)

    def test_addresses_are_counted_separately(self):
        for i in range(10):
            self.request_reset(f"r{i}@cit.edu", ip="10.0.0.1")
        self.assertEqual(self.request_reset("other@cit.edu", ip="10.0.0.2").status_code, 202)

    def test_bad_links_count_toward_the_confirmation_limit(self):
        for _ in range(30):
            self.assertEqual(self.confirm("x" * 43).status_code, 400)
        self.rate_limited(self.confirm("x" * 43), 600)

    def test_a_recipient_is_sent_one_email_per_cooldown_and_suppression_does_not_extend_it(self):
        self.request_reset(ip="10.0.3.1")
        self.clock.advance(seconds=30)
        suppressed = self.request_reset(ip="10.0.3.2")
        self.assertEqual((suppressed.status_code, suppressed.json()), (202, GENERIC_202))
        self.clock.advance(seconds=30)
        self.request_reset(ip="10.0.3.3")
        # Admitted at 0s and 60s: the suppressed one at 30s did not push the
        # cooldown out to 90s. Only the newer is still owed mail -- the older
        # was pending when it arrived, so it was superseded (§6).
        statuses = list(RecoveryIntent.objects.order_by("created_at").values_list("status", flat=True))
        self.assertEqual(statuses, ["superseded", "pending"])
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)

    def test_five_per_hour_and_ten_per_day_per_recipient(self):
        for i in range(6):
            self.request_reset(ip=f"10.0.4.{i}")
            self.clock.advance(seconds=61)
        self.assertEqual(RecoveryIntent.objects.count(), 5)
        self.clock.advance(seconds=3600)
        for i in range(6):
            self.request_reset(ip=f"10.0.5.{i}")
            self.clock.advance(seconds=61)
        self.assertEqual(RecoveryIntent.objects.count(), 10)

    def test_unknown_recipients_are_limited_exactly_like_known_ones(self):
        self.request_reset("nobody@cit.edu")
        self.request_reset("nobody@cit.edu", ip="10.0.0.9")
        self.assertEqual(RecoveryIntent.objects.count(), 1)

    def test_the_cooldown_is_shared_with_the_verification_purpose(self):
        from apps.accounts.models import RecoveryPurpose
        from apps.accounts.recovery.service import admit_request

        admit_request(RecoveryPurpose.EMAIL_VERIFICATION, "reader@cit.edu")
        self.request_reset()
        self.assertFalse(RecoveryIntent.objects.filter(purpose=RecoveryPurpose.PASSWORD_RESET).exists())

    def test_forwarded_addresses_are_believed_only_from_a_configured_proxy(self):
        from django.test import override_settings

        with override_settings(RECOVERY_TRUSTED_PROXIES=["10.0.0.254"]):
            for i in range(10):
                self.request_reset(f"p{i}@cit.edu", ip="10.0.0.254", HTTP_X_FORWARDED_FOR="203.0.113.7")
            self.rate_limited(self.request_reset("p@cit.edu", ip="10.0.0.254",
                                                 HTTP_X_FORWARDED_FOR="203.0.113.7"), 600)
            # Another client behind the same proxy is someone else.
            self.assertEqual(self.request_reset("q@cit.edu", ip="10.0.0.254",
                                                HTTP_X_FORWARDED_FOR="203.0.113.8").status_code, 202)
            # A client prepending a fake hop is still counted by its real one.
            self.rate_limited(self.request_reset("s@cit.edu", ip="10.0.0.254",
                                                 HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.7"), 600)

        # From an untrusted connection the header is ignored altogether.
        for i in range(10):
            self.request_reset(f"u{i}@cit.edu", ip="10.0.0.77", HTTP_X_FORWARDED_FOR=f"192.0.2.{i}")
        self.rate_limited(self.request_reset("u@cit.edu", ip="10.0.0.77",
                                             HTTP_X_FORWARDED_FOR="192.0.2.200"), 600)

    def test_a_counter_outage_fails_closed_for_every_address(self):
        from django.db import OperationalError

        with patch("apps.accounts.recovery.limits.admit", side_effect=OperationalError("down")):
            answers = [self.request_reset(email) for email in ("reader@cit.edu", "nobody@cit.edu")]
        for response in answers:
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"code": "temporarily_unavailable",
                                               "detail": "Unable to process this request. Try again later.",
                                               "retry_after": 60})
            self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(RecoveryIntent.objects.count(), 0)


class ConcurrentConsumptionTests(TransactionTestCase):
    """§3: real Postgres transactions on separate connections, released at once."""

    def setUp(self):
        self.user = User.objects.create_user(email="race@cit.edu", password=OLD,
                                             first_name="R", last_name="C", is_verified=True)

    def token(self):
        with patch("apps.accounts.recovery.service.enqueue"):
            from apps.accounts.recovery.service import admit_request
            admit_request("password_reset", "race@cit.edu")
        deliver_recovery_intent(str(RecoveryIntent.objects.get().pk))
        return re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body).group(1)

    def race(self, *calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(index, call):
            try:
                barrier.wait(10)
                results[index] = call()
            except Exception as exc:  # noqa: BLE001 -- reported below
                results[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        return results

    def test_two_consumers_of_one_link_have_exactly_one_winner(self):
        from apps.accounts.recovery import service

        token = self.token()

        def consume(password):
            def call():
                with patch("apps.accounts.recovery.service.enqueue"):
                    service.confirm_reset(token, password, password)
                return password
            return call

        results = self.race(consume("Winner-pass-111"), consume("Winner-pass-222"))
        winners = [r for r in results if isinstance(r, str)]
        losers = [r for r in results if isinstance(r, service.InvalidLink)]
        self.assertEqual((len(winners), len(losers)), (1, 1), results)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(winners[0]))

    def test_waiting_for_the_account_lock_does_not_extend_token_expiry(self):
        from rest_framework.test import APIClient
        from apps.accounts.models import RecoveryToken

        token = self.token()
        expires = RecoveryToken.objects.get().expires_at
        clock = Clock()
        clock.at = expires - timedelta(seconds=1)
        waiting = threading.Event()
        results = []

        def observe(execute, sql, params, many, context):
            if 'FOR UPDATE' in sql and 'accounts_user' in sql:
                waiting.set()
            return execute(sql, params, many, context)

        def consume():
            try:
                with connection.execute_wrapper(observe):
                    results.append(APIClient().post(CONFIRM, {
                        "token": token, "new_password": NEW, "confirm_password": NEW,
                    }, format="json"))
            finally:
                connection.close()

        with patch("apps.accounts.recovery.clock.now", clock):
            with transaction.atomic():
                User.objects.select_for_update().get(pk=self.user.pk)
                thread = threading.Thread(target=consume)
                thread.start()
                self.assertTrue(waiting.wait(10))
                clock.at = expires
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0].json(), INVALID_LINK)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))

    def test_duplicate_workers_send_one_link(self):
        from apps.accounts.recovery.service import admit_request
        from apps.accounts.models import RecoveryToken
        with patch("apps.accounts.recovery.service.enqueue"):
            admit_request("password_reset", self.user.email)
        intent_id = str(RecoveryIntent.objects.get().pk)
        results = self.race(*[lambda: deliver_recovery_intent(intent_id) for _ in range(2)])
        self.assertEqual(results, [None, None])
        self.assertEqual(RecoveryToken.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_the_ip_limit_is_atomic_across_connections(self):
        from rest_framework.test import APIClient
        with self.settings(RECOVERY_REQUEST_IP_10M=1), patch("apps.accounts.recovery.service.enqueue"):
            results = self.race(*[
                lambda: APIClient().post(REQUEST, {"email": "unknown@cit.edu"}, format="json").status_code
                for _ in range(2)
            ])
        self.assertEqual(sorted(results), [202, 429])

    def test_new_issuance_serializes_with_consuming_the_old_link(self):
        from apps.accounts.models import RecoveryAttempt
        from apps.accounts.recovery.service import admit_request
        from rest_framework.test import APIClient

        old = self.token()
        RecoveryAttempt.objects.all().delete()
        with patch("apps.accounts.recovery.service.enqueue"):
            admit_request("password_reset", self.user.email)
            intent_id = str(RecoveryIntent.objects.get(status="pending").pk)
            results = self.race(
                lambda: deliver_recovery_intent(intent_id),
                lambda: APIClient().post(CONFIRM, {"token": old, "new_password": NEW,
                                                   "confirm_password": NEW}, format="json").status_code,
            )
        self.assertIsNone(results[0])
        self.assertIn(results[1], (200, 400))
        latest = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body).group(1)
        response = APIClient().post(CONFIRM, {"token": latest, "new_password": "Third-pass-333",
                                              "confirm_password": "Third-pass-333"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
