"""
RDCO hears of a role request once the person has verified their email (IR-784,
ADR-051 decision 20). Every case goes through the real activation link over HTTP.
"""
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, RoleRequest, User
from apps.notifications.models import Notification
from core.enums import RequestStatus, RoleName


class RoleRequestNotificationTests(APITestCase):
    def setUp(self):
        self.rdco = Role.objects.get_or_create(name=RoleName.RDCO)[0]
        self.student = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        self.adviser = Role.objects.get_or_create(name=RoleName.ADVISER)[0]

    def signup(self, email="new@cit.edu", requested=None):
        user = User.objects.create_user(
            email=email, password="pw12345!", first_name="New", last_name="Person",
            is_verified=False,
        )
        RoleRequest.objects.create(user=user, requested_role=requested or self.student)
        return user

    def link(self, user):
        return reverse("auth-activate", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        })

    def broadcasts(self):
        return Notification.objects.filter(broadcast_to_role=self.rdco)

    def test_verifying_notifies_rdco_once(self):
        user = self.signup()
        self.assertEqual(self.broadcasts().count(), 0)

        response = self.client.get(self.link(user))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        sent = self.broadcasts().get()
        self.assertEqual(sent.sender, user)
        self.assertIsNone(sent.recipient)
        self.assertEqual(sent.notif_type.name, "Role Request - Student")
        self.assertIn("New Person requested the Student role.", sent.message)

    def test_an_adviser_request_uses_the_adviser_notification_type(self):
        user = self.signup("adv@cit.edu", requested=self.adviser)
        self.client.get(self.link(user))
        self.assertEqual(self.broadcasts().get().notif_type.name, "Role Request - Adviser")

    def test_signing_up_without_verifying_alerts_nobody(self):
        self.signup()
        self.assertEqual(self.broadcasts().count(), 0)

    def test_a_bad_token_verifies_nobody_and_alerts_nobody(self):
        user = self.signup()
        url = reverse("auth-activate", kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": "not-a-real-token",
        })

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertFalse(user.is_verified)
        self.assertEqual(self.broadcasts().count(), 0)

    def test_repeating_the_link_sends_no_second_notification(self):
        user = self.signup()
        url = self.link(user)

        first = self.client.get(url)
        second = self.client.get(url)
        third = self.client.get(url)

        self.assertEqual(
            [first.status_code, second.status_code, third.status_code], [status.HTTP_200_OK] * 3,
        )
        self.assertEqual(self.broadcasts().count(), 1)

    def test_an_account_with_no_pending_request_is_verified_without_a_notice(self):
        user = User.objects.create_user(
            email="norequest@cit.edu", password="pw12345!", first_name="No", last_name="Request",
            is_verified=False,
        )

        response = self.client.get(self.link(user))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertEqual(self.broadcasts().count(), 0)

    def test_a_decided_request_is_not_announced_as_new(self):
        user = self.signup()
        RoleRequest.objects.filter(user=user).update(status=RequestStatus.APPROVED)

        self.client.get(self.link(user))

        self.assertEqual(self.broadcasts().count(), 0)

    def test_the_two_empty_email_tasks_are_gone_and_the_mail_task_remains(self):
        from apps.accounts import tasks

        self.assertFalse(hasattr(tasks, "send_verification_email_task"))
        self.assertFalse(hasattr(tasks, "send_role_request_email_task"))
        self.assertTrue(callable(tasks.send_email_task))
