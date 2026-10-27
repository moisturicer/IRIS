"""
A notification failure is logged, and mark-read only touches your own
notifications (IR-300).

Two defects survived the IR-260 cutover (the card numbers them D7 and D8,
after its original eight-defect list). D7: every notify function in
`services.py` swallowed its exception with a bare `pass`, so a dropped notice
left nothing in the logs. D8: `PATCH /notifications/<id>/read/` looked the id
up with no scope, so an unknown id was a 500 and anyone could mark someone
else's notification read. Both are driven through the HTTP API.

The scope the three endpoints share is `Notification.objects.visible_to(user)`.
A user with no role -- `admin@cit.edu` is one -- used to match
`broadcast_to_role IS NULL`, which is every direct notification; the shared
scope closes that as well.
"""

import ast
import inspect
from unittest import mock

from django.urls import reverse
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.notifications import services
from apps.notifications.models import Notification, NotificationRead, NotificationType
from apps.reviews.test_decisions import REASON, DecisionTestBase
from apps.reviews.workflow_test_helpers import make_user
from core.enums import PipelineStatus, RoleName

SERVICES_LOGGER = "apps.notifications.services"


def read_url(pk):
    return reverse("notification-read", args=[pk])


# --- D7: a failing notify function is logged, and the caller still succeeds -------

class NotifyFailureIsLoggedTests(DecisionTestBase):

    def test_a_failed_notice_leaves_the_decision_standing_and_logs_one_error(self):
        record = self.at_adviser()

        with mock.patch.object(
            Notification.objects, "create", side_effect=RuntimeError("boom"),
        ), self.assertLogs(SERVICES_LOGGER, level="ERROR") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                self.decided(record, self.adviser, "reject", REASON)

        self.assertEqual(len(logs.records), 1, [r.getMessage() for r in logs.records])
        logged = logs.records[0]
        self.assertEqual(logged.levelname, "ERROR")
        self.assertIn("notify_decided", logged.getMessage())
        self.assertTrue(
            logged.getMessage().endswith(f"for record {record.pk}"), logged.getMessage(),
        )
        self.assertIsNotNone(logged.exc_info, "the traceback must be kept")
        self.assertFalse(Notification.objects.filter(record=record).exists())
        # The notice runs on commit, after the response; what must stand is the
        # decision it was announcing.
        self.assertEqual(record.pipeline_status, PipelineStatus.REJECTED)


class NoSilentExceptTests(SimpleTestCase):

    def test_no_handler_in_services_swallows_without_logging(self):
        tree = ast.parse(inspect.getsource(services))
        silent = [
            handler.lineno
            for handler in ast.walk(tree)
            if isinstance(handler, ast.ExceptHandler)
            and all(isinstance(stmt, ast.Pass) for stmt in handler.body)
        ]
        self.assertEqual(silent, [], "except blocks whose only statement is `pass`")


# --- D8: mark-read resolves the id within the caller's own scope -----------------

class ScopeTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.me = make_user("notif-me@cit.edu", RoleName.STUDENT)
        cls.other = make_user("notif-other@cit.edu", RoleName.STUDENT)
        cls.roleless = User.objects.create_user(
            email="notif-roleless@cit.edu", password="TestPass123!",
            first_name="No", last_name="Role", is_verified=True,
        )
        cls.notif_type = NotificationType.objects.get_or_create(name="IR-300 test")[0]
        cls.mine = Notification.objects.create(
            recipient=cls.me, notif_type=cls.notif_type, message="mine",
        )
        cls.theirs = Notification.objects.create(
            recipient=cls.other, notif_type=cls.notif_type, message="theirs",
        )
        cls.to_students = Notification.objects.create(
            broadcast_to_role=cls.me.role, notif_type=cls.notif_type, message="students",
        )
        cls.to_rdco = Notification.objects.create(
            broadcast_to_role=make_user("notif-rdco@cit.edu", RoleName.RDCO).role,
            notif_type=cls.notif_type, message="rdco",
        )

    def mark(self, pk, as_user=None):
        self.client.force_authenticate(as_user or self.me)
        return self.client.patch(read_url(pk))

    def listed_ids(self, as_user):
        self.client.force_authenticate(as_user)
        response = self.client.get(reverse("notification-list"), {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return {row["id"] for row in rows}


class MarkReadScopeTests(ScopeTestBase):

    def test_an_unknown_id_is_404(self):
        missing = Notification.objects.order_by("-pk").first().pk + 1000

        self.assertEqual(self.mark(missing).status_code, status.HTTP_404_NOT_FOUND)

    def test_my_own_direct_notification_is_marked(self):
        self.assertEqual(self.mark(self.mine.pk).status_code, status.HTTP_200_OK)
        self.assertTrue(
            NotificationRead.objects.filter(notification=self.mine, user=self.me).exists()
        )

    def test_another_users_direct_notification_is_404_and_writes_nothing(self):
        response = self.mark(self.theirs.pk)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(NotificationRead.objects.filter(notification=self.theirs).exists())

    def test_a_broadcast_to_another_role_is_404(self):
        response = self.mark(self.to_rdco.pk)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(NotificationRead.objects.filter(notification=self.to_rdco).exists())

    def test_a_broadcast_to_my_role_is_marked(self):
        self.assertEqual(self.mark(self.to_students.pk).status_code, status.HTTP_200_OK)
        self.assertTrue(
            NotificationRead.objects.filter(notification=self.to_students, user=self.me).exists()
        )

    def test_a_user_with_no_role_cannot_reach_direct_notifications(self):
        response = self.mark(self.theirs.pk, as_user=self.roleless)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.listed_ids(self.roleless), set())


class OneScopeTests(ScopeTestBase):
    """List, mark-read and mark-all-read agree on what a user can see."""

    def test_the_list_shows_exactly_the_scope(self):
        self.assertEqual(
            self.listed_ids(self.me), {self.mine.pk, self.to_students.pk},
        )
        self.assertEqual(
            set(Notification.objects.visible_to(self.me).values_list("pk", flat=True)),
            {self.mine.pk, self.to_students.pk},
        )

    def test_mark_all_read_touches_only_the_scope(self):
        self.client.force_authenticate(self.me)
        response = self.client.post(reverse("notification-mark-all-read"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(NotificationRead.objects.values_list("notification_id", "user_id")),
            {(self.mine.pk, self.me.pk), (self.to_students.pk, self.me.pk)},
        )

    def test_mark_all_read_for_a_roleless_user_touches_nothing(self):
        self.client.force_authenticate(self.roleless)
        self.client.post(reverse("notification-mark-all-read"))

        self.assertFalse(NotificationRead.objects.exists())
