"""
Where a notification opens (IR-765).

A Call's notices carry no Record, so before IR-765 they had no Open button
and nowhere to go. The server now says where each one opens, in `target`, so
the screen guesses nothing from a type's name or the viewer's role.
"""
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.notifications import services as notify
from apps.opportunities.tests import make_opportunity, make_user


class CallNotificationTargetTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("target.rdco@cit.edu", "RDCO")
        self.adviser = make_user("target.adviser@cit.edu", "Adviser")
        self.call = make_opportunity(posted_by=self.adviser, title="ICCE 2027")

    def targets(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(reverse("notification-list"), {"page_size": 100})
        self.assertEqual(response.status_code, 200, response.content)
        return {n["notif_type_name"]: n["target"] for n in response.json()["results"]}

    def test_rdco_opens_its_call_requests_page(self):
        notify.notify_call_requested(self.call)
        self.assertEqual(self.targets(self.rdco), {"Call Request Submitted": "/rdco/call-requests"})

    def test_a_confirmed_call_opens_the_board(self):
        notify.notify_call_confirmed(self.call, confirmed_by=self.rdco)
        self.assertEqual(self.targets(self.adviser)["Call Confirmed"], "/opportunities")

    def test_a_rejected_removed_or_lapsed_call_opens_the_posters_own_calls(self):
        notify.notify_call_rejected(self.call, rejected_by=self.rdco, reason="Broken link.")
        notify.notify_call_removed(self.call, removed_by=self.rdco, reason="Duplicate.")
        notify.notify_call_lapsed(self.call)
        self.assertEqual(self.targets(self.adviser), {
            "Call Rejected": "/opportunities/mine",
            "Call Removed": "/opportunities/mine",
            "Call Request Lapsed": "/opportunities/mine",
        })

    def test_any_other_notice_names_no_target(self):
        from apps.notifications.models import Notification, NotificationType

        Notification.objects.create(
            recipient=self.adviser, notif_type=NotificationType.objects.get_or_create(name="Something Else")[0],
            message="Unrelated.",
        )
        self.assertEqual(self.targets(self.adviser), {"Something Else": None})
