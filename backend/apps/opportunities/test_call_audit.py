"""
IR-763: every act on a Call is audited (ADR-050 decision 15; owner's
decisions of 2026-11-15 on the card).

Each case goes through the HTTP API, the seam RDCO and an Adviser use, and
reads the event back from the Audit Log's own rows.
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.audit.models import AuditEvent

from .models import Opportunity
from .test_call_review import CallReviewTestCase, payload
from .tasks import remove_lapsed_requests
from .test_lapsed_requests import JUST_AFTER_MIDNIGHT_16TH_MANILA
from .tests import an_area, make_opportunity, make_user


def events(event_type):
    return list(AuditEvent.objects.filter(event_type=event_type).order_by("id"))


class PostedTests(CallReviewTestCase):
    def test_posting_records_who_posted_and_a_full_copy(self):
        area = an_area()
        response = self.post_as(self.adviser, title="ICACSIS", areas=[area.pk], registration_fee="PHP 2,500")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        call = Opportunity.objects.get(title="ICACSIS")

        [event] = events("CALL_POSTED")
        self.assertEqual(event.user_id, self.adviser.pk)
        self.assertIsNone(event.record_id)
        copy = event.metadata["call"]
        self.assertEqual(copy["id"], call.pk)
        self.assertEqual(copy["title"], "ICACSIS")
        self.assertEqual(copy["status"], "pending")
        self.assertEqual(copy["registration_fee"], "PHP 2,500")
        self.assertEqual(copy["areas"], [{"id": area.pk, "name": area.name}])
        self.assertEqual(copy["due_date"], payload()["due_date"])
        self.assertEqual(copy["posted_by"], self.adviser.pk)

    def test_rdcos_call_is_recorded_as_posted_confirmed(self):
        self.post_as(self.rdco, title="RDCO's call")
        [event] = events("CALL_POSTED")
        self.assertEqual((event.user_id, event.metadata["call"]["status"]), (self.rdco.pk, "confirmed"))

    def test_a_refused_post_records_nothing(self):
        yesterday = str(timezone.localdate() - timezone.timedelta(days=1))
        response = self.post_as(self.adviser, due_date=yesterday)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(events("CALL_POSTED"), [])


class EditedTests(CallReviewTestCase):
    def patch(self, user, call, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).patch(self.detail(call), data, format="json")

    def test_an_edit_records_each_changed_field_old_and_new_including_featured(self):
        call = make_opportunity(posted_by=self.rdco, title="ICACSIS", location="Manila")
        response = self.patch(self.rdco, call, title="ICACSIS 2027", is_featured=True, location="Manila")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        [event] = events("CALL_EDITED")
        self.assertEqual(event.user_id, self.rdco.pk)
        self.assertEqual(event.metadata["call_id"], call.pk)
        self.assertEqual(event.metadata["title"], "ICACSIS 2027")
        self.assertEqual(event.metadata["changes"], {
            "title":       {"old": "ICACSIS", "new": "ICACSIS 2027"},
            "is_featured": {"old": False, "new": True},
        })

    def test_changed_areas_are_recorded_as_ids_and_names(self):
        old, new = an_area("Computing"), an_area("Engineering")
        call = make_opportunity(posted_by=self.rdco)
        call.areas.set([old])
        self.patch(self.rdco, call, areas=[new.pk])
        [event] = events("CALL_EDITED")
        self.assertEqual(event.metadata["changes"]["areas"], {
            "old": [{"id": old.pk, "name": "Computing"}],
            "new": [{"id": new.pk, "name": "Engineering"}],
        })

    def test_an_advisers_edit_that_sends_a_call_back_records_the_status_change(self):
        call = make_opportunity(posted_by=self.adviser, title="ICACSIS")
        self.patch(self.adviser, call, location="Online")
        [event] = events("CALL_EDITED")
        self.assertEqual(event.user_id, self.adviser.pk)
        self.assertEqual(event.metadata["changes"]["status"], {"old": "confirmed", "new": "pending"})
        self.assertEqual(event.metadata["changes"]["location"]["new"], "Online")

    def test_resubmitting_a_rejected_call_records_the_cleared_reason(self):
        call = self.adviser_call(status="rejected", review_reason="Broken link")
        self.patch(self.adviser, call, external_url="https://example.org/fixed")
        changes = events("CALL_EDITED")[0].metadata["changes"]
        self.assertEqual(changes["status"], {"old": "rejected", "new": "pending"})
        self.assertEqual(changes["review_reason"], {"old": "Broken link", "new": ""})

    def test_an_edit_that_changes_nothing_records_nothing(self):
        call = make_opportunity(posted_by=self.rdco, title="ICACSIS")
        self.patch(self.rdco, call, title="ICACSIS")
        self.assertEqual(events("CALL_EDITED"), [])

    def test_a_refused_edit_records_nothing(self):
        call = self.adviser_call()
        yesterday = str(timezone.localdate() - timezone.timedelta(days=1))
        response = self.patch(self.adviser, call, due_date=yesterday)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(events("CALL_EDITED"), [])


class DeletedTests(CallReviewTestCase):
    def delete(self, user, call):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).delete(self.detail(call))

    def test_a_delete_records_the_deleter_and_a_copy_with_no_reason(self):
        call = self.adviser_call(title="ICACSIS")
        response = self.delete(self.adviser, call)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        [event] = events("CALL_DELETED")
        self.assertEqual(event.user_id, self.adviser.pk)
        self.assertIsNone(event.metadata["reason"])
        self.assertEqual(
            (event.metadata["call"]["id"], event.metadata["call"]["title"], event.metadata["call"]["status"]),
            (call.pk, "ICACSIS", "pending"),
        )

    def test_rdcos_delete_of_a_colleagues_call_records_rdco(self):
        colleague = make_user("rdco.two@cit.edu", "RDCO")
        call = make_opportunity(posted_by=colleague)
        self.delete(self.rdco, call)
        [event] = events("CALL_DELETED")
        self.assertEqual((event.user_id, event.metadata["call"]["posted_by"]), (self.rdco.pk, colleague.pk))

    def test_a_refused_delete_records_nothing(self):
        response = self.delete(self.rdco, self.adviser_call())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(events("CALL_DELETED"), [])


class DecidedTests(CallReviewTestCase):
    def test_a_confirmation_records_rdco_and_names_the_call(self):
        call = self.adviser_call(title="ICACSIS")
        self.assertEqual(self.decide(self.rdco, call, "confirm").status_code, status.HTTP_200_OK)
        [event] = events("CALL_CONFIRMED")
        self.assertEqual(event.user_id, self.rdco.pk)
        self.assertEqual(event.metadata, {"call_id": call.pk, "title": "ICACSIS"})

    def test_a_rejection_records_rdcos_reason(self):
        call = self.adviser_call(title="ICACSIS")
        self.decide(self.rdco, call, "reject", reason="The link is broken.")
        [event] = events("CALL_REJECTED")
        self.assertEqual(event.user_id, self.rdco.pk)
        self.assertEqual(
            event.metadata, {"call_id": call.pk, "title": "ICACSIS", "reason": "The link is broken."},
        )

    def test_a_refused_decision_records_nothing(self):
        call = self.adviser_call()
        stale = call.updated_at - timezone.timedelta(seconds=5)
        for act, data in (("confirm", {}), ("reject", {"reason": "No"})):
            with self.subTest(act):
                response = self.decide(self.rdco, call, act, seen=stale, **data)
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(events("CALL_CONFIRMED") + events("CALL_REJECTED"), [])


class RemovedTests(CallReviewTestCase):
    def remove(self, user, call, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).post(reverse("opportunity-remove", args=[call.pk]), data, format="json")

    def test_a_removal_records_rdco_its_reason_and_a_copy(self):
        call = make_opportunity(posted_by=self.adviser, title="ICACSIS")
        response = self.remove(self.rdco, call, reason="Predatory publisher.")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        [event] = events("CALL_REMOVED")
        self.assertEqual(event.user_id, self.rdco.pk)
        self.assertEqual(event.metadata["reason"], "Predatory publisher.")
        self.assertEqual((event.metadata["call"]["id"], event.metadata["call"]["title"]), (call.pk, "ICACSIS"))
        self.assertEqual(events("CALL_DELETED"), [])

    def test_a_refused_removal_records_nothing(self):
        response = self.remove(self.rdco, make_opportunity(posted_by=self.adviser))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(events("CALL_REMOVED"), [])


class LapsedTests(TestCase):
    def setUp(self):
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        clock = patch("django.utils.timezone.now", return_value=JUST_AFTER_MIDNIGHT_16TH_MANILA)
        clock.start()
        self.addCleanup(clock.stop)

    def test_each_lapsed_request_is_recorded_with_no_actor_and_a_copy(self):
        waiting = make_opportunity(
            title="Waiting", due_date=date(2026, 11, 15), status="pending", posted_by=self.adviser,
        )
        make_opportunity(
            title="Rejected", due_date=date(2026, 11, 15), status="rejected", posted_by=self.adviser,
            review_reason="Broken link",
        )
        make_opportunity(
            title="Confirmed", due_date=date(2026, 11, 15), start_date=date(2026, 11, 20),
            status="confirmed", posted_by=self.adviser,
        )

        with self.captureOnCommitCallbacks(execute=True):
            remove_lapsed_requests()
            remove_lapsed_requests()

        lapsed = events("CALL_LAPSED")
        self.assertEqual(sorted(e.metadata["call"]["title"] for e in lapsed), ["Rejected", "Waiting"])
        self.assertEqual({e.user_id for e in lapsed}, {None})
        [copy] = [e.metadata["call"] for e in lapsed if e.metadata["call"]["id"] == waiting.pk]
        self.assertEqual((copy["due_date"], copy["posted_by"]), ("2026-11-15", self.adviser.pk))
        self.assertEqual(events("CALL_DELETED"), [])


class SameTransactionTests(CallReviewTestCase):
    def test_an_act_that_fails_after_its_event_leaves_neither(self):
        """The event is inside the act's transaction: a failure after it rolls both back."""
        from .audit import confirmed as write_the_event

        def write_then_fail(call, *, by):
            write_the_event(call, by=by)
            raise RuntimeError("the act failed after its event was written")

        call = self.adviser_call()
        with patch("apps.opportunities.review.audit.confirmed", side_effect=write_then_fail):
            with self.assertRaises(RuntimeError):
                self.decide(self.rdco, call, "confirm")

        self.assertEqual(events("CALL_CONFIRMED"), [])
        call.refresh_from_db()
        self.assertEqual(call.status, "pending")


class CopyCoversEveryFieldTests(TestCase):
    def test_a_copy_holds_every_field_a_call_has(self):
        """A field added to Opportunity must reach the copy ADR-050 decision 15 promises."""
        from .audit import COPIED_FIELDS

        fields = {field.name for field in Opportunity._meta.get_fields() if field.concrete}
        self.assertEqual(set(COPIED_FIELDS), fields)
