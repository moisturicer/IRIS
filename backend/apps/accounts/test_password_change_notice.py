"""
A password change made while signed in sends the owner the same notice a reset
sends (IR-820, ASVS 2.2.3 and 2.5.5).

Before this, `ChangePasswordView` wrote an audit event and told no one, so a
change made from a stolen session went unreported. The notice is written after
the change commits and is best effort, exactly as after a reset: failing to
record or send it can never undo the new password.
"""

from unittest.mock import patch

from django.core import mail
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import RecoveryIntent, RecoveryPurpose, User
from apps.accounts.recovery.delivery import deliver_recovery_intent

LOGIN = "/api/v1/auth/login/"
CHANGE = "/api/v1/auth/password/change/"
EMAIL = "changer@cit.edu"
OLD = "Original-pass-1"
NEW = "Brand-new-pass-2"


class PasswordChangeNoticeTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(email=EMAIL, password=OLD, first_name="C", last_name="H",
                                             is_verified=True)
        signed_in = APIClient().post(LOGIN, {"email": EMAIL, "password": OLD}, format="json")
        self.assertEqual(signed_in.status_code, 200, signed_in.content)
        self.access = signed_in.json()["access"]

    def change(self, old=OLD, new=NEW):
        return APIClient().post(CHANGE, {"old_password": old, "new_password": new}, format="json",
                                HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def notices(self):
        return RecoveryIntent.objects.filter(purpose=RecoveryPurpose.PASSWORD_CHANGED, user=self.user)

    def test_a_change_emails_the_owner_the_reset_notice_after_it_commits(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.change()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.notices().count(), 1)

        for intent_id in self.notices().values_list("id", flat=True):
            deliver_recovery_intent(str(intent_id))
        self.assertEqual(len(mail.outbox), 1)
        notice = mail.outbox[0]
        self.assertEqual(notice.to, [EMAIL])
        self.assertEqual(notice.subject, "Your IRIS password was changed")
        self.assertNotIn(NEW, notice.body)

    def test_nothing_is_sent_before_the_change_commits(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.change()
        self.assertFalse(self.notices().exists())
        self.assertEqual(len(callbacks), 1)

    def test_a_refused_change_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.change(old="Not-the-password-9")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.notices().exists())
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(OLD))

    def test_failing_to_record_the_notice_cannot_undo_the_change(self):
        with patch.object(RecoveryIntent.objects, "create", side_effect=RuntimeError("database hiccup")), \
                self.captureOnCommitCallbacks(execute=True):
            response = self.change()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(NEW))
        self.assertFalse(self.notices().exists())
