"""
Durable recovery mail (ADR-045 §6, IR-642), at the worker boundary.

The request commits an intent and only then hands its id to the broker. The
worker -- `deliver_recovery_intent` -- issues a token and sends; the
dispatcher re-enqueues anything due that a lost message or crashed hook left
behind. These tests drive both directly, with Django's mail outbox as the SMTP
server and `EmailMessage.send` patched where a failure is the point.
"""

import logging
import smtplib
import os
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.mail import EmailMessage
from django.db import transaction

from apps.accounts.models import (
    RecoveryBucket, RecoveryGeneration, RecoveryIntent, RecoveryToken, User,
)
from apps.accounts.recovery.delivery import deliver_recovery_intent, dispatch_recovery_intents
from apps.audit.models import AuditEvent

from .test_password_recovery import CONFIRM, GENERIC_202, NEW, OLD, RecoveryTestCase

REAL_SEND = EmailMessage.send


def intent():
    return RecoveryIntent.objects.get(purpose="password_reset")


class EnqueueTests(RecoveryTestCase):
    def test_a_fresh_worker_registers_recovery_tasks(self):
        result = subprocess.run(
            [sys.executable, "-c", (
                "import django; django.setup(); from config.celery import app; "
                "app.loader.import_default_modules(); "
                "assert 'apps.accounts.recovery.tasks.deliver_recovery_intent_task' in app.tasks; "
                "assert 'apps.accounts.recovery.tasks.dispatch_recovery_intents' in app.tasks"
            )], env=dict(os.environ), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_intent_is_enqueued_only_after_the_request_commits(self):
        with patch("apps.accounts.recovery.service.enqueue") as enqueue:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.request_reset()
            enqueue.assert_not_called()
            for callback in callbacks:
                callback()
        enqueue.assert_called_once_with(intent().pk)

    def test_a_rolled_back_admission_leaves_nothing_to_send(self):
        from apps.accounts.recovery.service import admit_request

        with patch("apps.accounts.recovery.service.enqueue") as enqueue:
            try:
                with transaction.atomic():
                    admit_request("password_reset", "reader@cit.edu")
                    raise RuntimeError("the request failed after admission")
            except RuntimeError:
                pass
        enqueue.assert_not_called()
        self.assertFalse(RecoveryIntent.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.RECOVERY_REQUESTED).exists())

    def test_a_broker_outage_still_answers_202_and_the_dispatcher_recovers_the_intent(self):
        with patch("apps.accounts.recovery.tasks.deliver_recovery_intent_task.apply_async",
                   side_effect=ConnectionError("broker down")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.request_reset()
        self.assertEqual((response.status_code, response.json()), (202, GENERIC_202))

        with patch("apps.accounts.recovery.service.enqueue") as enqueue:
            self.assertEqual(dispatch_recovery_intents(), 1)
        enqueue.assert_called_once_with(intent().pk)


class IssueTests(RecoveryTestCase):
    def test_running_the_worker_twice_issues_one_token_and_sends_one_email(self):
        self.request_reset()
        deliver_recovery_intent(str(intent().pk))
        deliver_recovery_intent(str(intent().pk))
        self.assertEqual(RecoveryToken.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_delayed_older_intent_cannot_issue_after_a_newer_request(self):
        self.request_reset()
        older = intent().pk
        self.clock.advance(seconds=61)
        self.request_reset()
        deliver_recovery_intent(str(older))
        self.assertEqual(RecoveryIntent.objects.get(pk=older).status, "superseded")
        self.assertFalse(RecoveryToken.objects.exists())

    def test_an_intent_issues_until_ten_minutes_after_admission_and_not_at(self):
        self.request_reset()
        self.clock.advance(seconds=599)
        deliver_recovery_intent(str(intent().pk))
        self.assertEqual(len(mail.outbox), 1)

        mail.outbox.clear()
        self.clock.advance(seconds=61)
        self.request_reset()
        newer = RecoveryIntent.objects.get(status="pending")
        self.clock.advance(seconds=600)
        deliver_recovery_intent(str(newer.pk))
        newer.refresh_from_db()
        self.assertEqual((newer.status, newer.address_encrypted), ("expired", ""))
        self.assertEqual(mail.outbox, [])

    def test_the_dispatcher_expires_stale_pending_intents(self):
        self.request_reset()
        self.clock.advance(seconds=600)
        with patch("apps.accounts.recovery.service.enqueue"):
            dispatch_recovery_intents()
        self.assertEqual(intent().status, "expired")


class SendTests(RecoveryTestCase):
    def test_repeated_worker_crashes_cannot_exceed_four_attempts(self):
        self.request_reset()
        with patch.object(EmailMessage, "send", side_effect=KeyboardInterrupt) as send:
            for _ in range(4):
                with self.assertRaises(KeyboardInterrupt):
                    self.deliver()
                self.clock.advance(seconds=121)
            self.deliver()
        self.assertEqual(send.call_count, 4)
        self.assertEqual(intent().status, "failed")
        self.assertEqual(intent().payload_encrypted, "")

    def failing(self, *errors):
        """`EmailMessage.send` raising each of ``errors`` in turn, then sending."""
        queue = list(errors)

        def send(message, fail_silently=False):
            if queue:
                raise queue.pop(0)
            return REAL_SEND(message, fail_silently=fail_silently)

        return patch.object(EmailMessage, "send", send)

    def deliver(self):
        with patch("apps.accounts.recovery.service.enqueue"):
            deliver_recovery_intent(str(intent().pk))

    def test_transient_failures_retry_at_30_120_and_300_seconds_with_the_same_link(self):
        self.request_reset()
        with self.failing(OSError(), smtplib.SMTPServerDisconnected(), TimeoutError()):
            self.deliver()
            for wait in (30, 120, 300):
                self.clock.advance(seconds=wait - 1)
                self.deliver()
                self.assertEqual(intent().attempts, (30, 120, 300).index(wait) + 1, "not due yet")
                self.clock.advance(seconds=1)
                self.deliver()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(intent().status, "sent")
        self.assertEqual(RecoveryToken.objects.count(), 1)
        sent = AuditEvent.objects.get(event_type=AuditEvent.RECOVERY_EMAIL_SENT)
        self.assertEqual(sent.metadata["attempt"], 4)

    def test_four_transient_failures_give_up_and_audit_it(self):
        self.request_reset()
        with self.failing(*[OSError()] * 4), self.assertLogs("apps.accounts.recovery", "ERROR"):
            self.deliver()
            for wait in (30, 120, 300):
                self.clock.advance(seconds=wait)
                self.deliver()
        self.assertEqual((intent().status, intent().payload_encrypted), ("failed", ""))
        failed = AuditEvent.objects.get(event_type=AuditEvent.RECOVERY_EMAIL_FAILED)
        self.assertEqual((failed.metadata["reason"], failed.metadata["attempt"]), ("attempts_exhausted", 4))
        self.assertEqual(mail.outbox, [])

    def test_a_permanent_rejection_stops_at_once(self):
        self.request_reset()
        refused = smtplib.SMTPRecipientsRefused({"reader@cit.edu": (550, b"no such user")})
        with self.failing(refused), self.assertLogs("apps.accounts.recovery", "ERROR"):
            self.deliver()
        self.assertEqual(intent().status, "failed")
        self.assertEqual(AuditEvent.objects.get(event_type=AuditEvent.RECOVERY_EMAIL_FAILED)
                         .metadata["reason"], "rejected")

    def test_a_link_used_or_replaced_before_a_retry_is_never_sent(self):
        self.request_reset()
        with self.failing(OSError()):
            self.deliver()
        RecoveryToken.objects.update(revoked_at=self.clock())
        self.clock.advance(seconds=30)
        self.deliver()
        self.assertEqual((intent().status, intent().payload_encrypted), ("withdrawn", ""))
        self.assertEqual(mail.outbox, [])

    def test_a_crashed_worker_is_retried_by_the_dispatcher_after_its_lease(self):
        self.request_reset()
        with patch.object(EmailMessage, "send", side_effect=KeyboardInterrupt):
            try:
                self.deliver()
            except KeyboardInterrupt:
                pass  # the worker process died mid-send
        with patch("apps.accounts.recovery.service.enqueue") as enqueue:
            self.assertEqual(dispatch_recovery_intents(), 0, "still leased")
            self.clock.advance(seconds=121)
            self.assertEqual(dispatch_recovery_intents(), 1)
        self.deliver()
        self.assertEqual(len(mail.outbox), 1)

    def test_the_payload_is_deleted_once_sent(self):
        self.request_reset()
        self.deliver()
        self.assertEqual((intent().address_encrypted, intent().payload_encrypted), ("", ""))


class AfterResetTests(RecoveryTestCase):
    def reset(self):
        token = self.emailed_token()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            with patch("apps.accounts.recovery.service.enqueue"):
                self.assertEqual(self.confirm(token).status_code, 200)

    def test_a_password_changed_notice_follows_the_reset(self):
        self.reset()
        notice = RecoveryIntent.objects.get(purpose="password_changed")
        deliver_recovery_intent(str(notice.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@cit.edu"])
        self.assertNotIn("#token=", mail.outbox[0].body)

    def test_a_notice_that_cannot_be_recorded_does_not_undo_the_reset(self):
        with patch("apps.accounts.recovery.service.RecoveryIntent.objects.create",
                   side_effect=RuntimeError("down")), self.assertLogs("apps.accounts.recovery", "ERROR"):
            from apps.accounts.recovery.service import notify_password_changed
            notify_password_changed(self.user.pk)
        self.reset()
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(NEW))

    def test_records_are_purged_after_seven_days(self):
        self.reset()
        self.clock.advance(days=7, minutes=31)
        with patch("apps.accounts.recovery.service.enqueue"):
            dispatch_recovery_intents()
        self.assertFalse(RecoveryToken.objects.exists())
        self.assertFalse(RecoveryIntent.objects.filter(purpose="password_reset").exists())

    def test_counters_for_addresses_and_recipients_nobody_uses_any_more_are_purged(self):
        # Spraying addresses must not grow storage without bound (§6): once
        # their attempts and intents are gone, so are the rows keyed by them.
        for i in range(3):
            self.request_reset(f"stranger{i}@cit.edu", ip=f"10.0.1.{i}")
        self.assertTrue(RecoveryBucket.objects.exists())
        self.assertTrue(RecoveryGeneration.objects.exists())
        self.clock.advance(days=8)
        with patch("apps.accounts.recovery.service.enqueue"):
            dispatch_recovery_intents()
        self.assertFalse(RecoveryBucket.objects.exists())
        self.assertFalse(RecoveryGeneration.objects.exists())

        # And nothing about the purge stops the next request.
        self.assertEqual(self.request_reset("stranger0@cit.edu", ip="10.0.1.0").json(), GENERIC_202)


class RedactionTests(RecoveryTestCase):
    def test_no_address_token_or_password_reaches_audit_or_logs(self):
        with self.assertLogs("apps", logging.DEBUG) as logs:
            logging.getLogger("apps").debug("start")
            with patch("apps.accounts.recovery.service.enqueue"):
                self.request_reset()
                self.request_reset("nobody@cit.edu", ip="10.0.0.2")
            self.run_workers()
            token = self.token_from(mail.outbox[0])
            self.confirm("x" * 43)
            self.confirm(token, new="qwertyuiop")
            self.confirm(token)
        secrets = ["reader@cit.edu", "nobody@cit.edu", token, NEW, OLD, "qwertyuiop"]
        audit = [str(event.metadata) for event in AuditEvent.objects.all()]
        self.assertTrue(audit)
        for text in audit + logs.output:
            for secret in secrets:
                self.assertNotIn(secret, text)
        allowed = {"purpose", "outcome", "correlation_id", "reason", "attempt"}
        for event in AuditEvent.objects.all():
            self.assertLessEqual(set(event.metadata), allowed, event.event_type)

    def test_the_broker_carries_only_the_intent_id(self):
        with patch("apps.accounts.recovery.tasks.deliver_recovery_intent_task.apply_async") as send:
            with self.captureOnCommitCallbacks(execute=True):
                self.request_reset()
        self.assertEqual(send.call_args.kwargs["args"], [str(intent().pk)])

    def test_the_link_is_on_the_configured_origin_with_the_token_in_the_fragment(self):
        from django.test import override_settings

        # The hostile Host is allowed, so the request reaches the view and the
        # test proves the link ignores it rather than Django refusing it first.
        with override_settings(FRONTEND_URL="https://iris.example.edu",
                               ALLOWED_HOSTS=["testserver", "evil.example.com"]):
            self.request_reset(HTTP_HOST="evil.example.com")
            self.run_workers()
        body = mail.outbox[0].body
        self.assertIn("https://iris.example.edu/password/reset#token=", body)
        self.assertNotIn("evil.example.com", body)
        self.assertIn(" UTC.", body)
        self.assertIn("If you did not request this, ignore this email.", body)
        self.assertIn("RDCO or your department administrator", body)

    def test_the_stored_token_is_a_digest(self):
        token = self.emailed_token()
        stored = RecoveryToken.objects.get()
        self.assertNotEqual(stored.digest, token)
        self.assertEqual(len(stored.digest), 64)
        self.assertNotIn(token, str(list(RecoveryIntent.objects.values())))
        self.assertTrue(OLD)  # the account is untouched until a confirm
        self.assertEqual(self.client.post(CONFIRM, {}, format="json").status_code, 400)
