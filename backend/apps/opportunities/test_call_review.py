"""
IR-762: an Adviser's Call waits for RDCO to confirm it, and only RDCO features
a Call (ADR-050 decisions 8-12, as amended 2026-11-15).

Every case goes through the HTTP API, the seam a client and RDCO use.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification

from .models import Opportunity
from .tests import an_area, make_opportunity, make_user


def payload(**overrides):
    fields = {
        "opportunity_type": Opportunity.TYPE_CONFERENCE,
        "title":            "Conference on Capstone Research",
        "description":      "Full papers on capstone research.",
        "due_date":         str(timezone.localdate() + timedelta(days=14)),
        "location":         "Cebu City, Philippines",
        "areas":            [an_area().pk],
        "external_url":     "https://example.org/capstone",
    }
    fields.update(overrides)
    return fields


class CallReviewTestCase(APITestCase):
    def setUp(self):
        self.rdco = make_user("rdco@cit.edu", "RDCO")
        self.adviser = make_user("adviser@cit.edu", "Adviser")
        self.other_adviser = make_user("other.adviser@cit.edu", "Adviser")
        self.student = make_user("student@cit.edu", "Student")

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def post_as(self, user, **overrides):
        # Notices go out on commit; run them, since a test never commits.
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).post(reverse("opportunity-list"), payload(**overrides), format="json")

    def board_titles(self, user):
        response = self.as_user(user).get(reverse("opportunity-list"))
        return {row["title"] for row in response.data["results"]}

    def detail(self, call):
        return reverse("opportunity-detail", args=[call.pk])

    def decide(self, user, call, act, seen=None, **data):
        """RDCO's decision names the version it saw: by default, the Call as it is now."""
        if seen is None:
            seen = Opportunity.objects.get(pk=call.pk).updated_at
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).post(
                reverse(f"opportunity-{act}", args=[call.pk]),
                {"updated_at": seen.isoformat(), **data}, format="json",
            )

    def adviser_call(self, **overrides):
        """An Adviser's Call, waiting for RDCO."""
        return make_opportunity(
            title=overrides.pop("title", "Adviser's call"), posted_by=self.adviser,
            status=overrides.pop("status", "pending"), **overrides,
        )


class StartingStatusTests(CallReviewTestCase):
    def test_rdcos_call_is_confirmed_at_once(self):
        response = self.post_as(self.rdco, title="RDCO's call")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "confirmed")
        self.assertIn("RDCO's call", self.board_titles(self.student))

    def test_an_advisers_call_waits_off_the_board(self):
        response = self.post_as(self.adviser, title="Adviser's call")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["status_label"], "Waiting for RDCO")
        for viewer in (self.student, self.adviser, self.rdco):
            self.assertNotIn("Adviser's call", self.board_titles(viewer))

    def test_status_cannot_be_chosen_by_the_client(self):
        response = self.post_as(self.adviser, status="confirmed")
        self.assertEqual(response.data["status"], "pending")


class WhoSeesWhatTests(CallReviewTestCase):
    def test_a_waiting_call_is_visible_to_its_adviser_and_rdco_only(self):
        call = self.adviser_call()
        for viewer in (self.adviser, self.rdco):
            with self.subTest(viewer.email):
                self.assertEqual(self.as_user(viewer).get(self.detail(call)).status_code, status.HTTP_200_OK)
        for viewer in (self.student, self.other_adviser):
            with self.subTest(viewer.email):
                self.assertEqual(self.as_user(viewer).get(self.detail(call)).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_missing_call_and_a_hidden_one_answer_alike(self):
        hidden = self.as_user(self.student).get(self.detail(self.adviser_call()))
        missing = self.as_user(self.student).get(reverse("opportunity-detail", args=[999999]))
        self.assertEqual((hidden.status_code, hidden.data), (missing.status_code, missing.data))

    def test_the_calendar_serves_confirmed_calls_only(self):
        call = self.adviser_call()
        for viewer in (self.adviser, self.rdco, self.student):
            with self.subTest(viewer.email):
                response = self.as_user(viewer).get(reverse("opportunity-calendar", args=[call.pk]))
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class QueueTests(CallReviewTestCase):
    def queue(self, user):
        return self.as_user(user).get(reverse("opportunity-requests"))

    def test_rdcos_queue_lists_waiting_calls_only(self):
        self.adviser_call(title="Waiting")
        self.adviser_call(title="Rejected", status="rejected")
        make_opportunity(title="Confirmed", posted_by=self.adviser)
        response = self.queue(self.rdco)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["title"] for row in response.data["results"]], ["Waiting"])

    def test_a_request_whose_deadline_passed_leaves_the_queue_before_the_job_runs(self):
        self.adviser_call(title="Lapsed", due_date=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.queue(self.rdco).data["results"], [])

    def test_only_rdco_reads_the_queue(self):
        for viewer in (self.adviser, self.student):
            with self.subTest(viewer.email):
                self.assertEqual(self.queue(viewer).status_code, status.HTTP_403_FORBIDDEN)


class MineTests(CallReviewTestCase):
    def mine(self, user):
        return self.as_user(user).get(reverse("opportunity-mine"))

    def test_a_poster_lists_their_own_calls_in_every_status(self):
        self.adviser_call(title="Waiting")
        self.adviser_call(title="Rejected", status="rejected", review_reason="Broken link")
        make_opportunity(title="Confirmed", posted_by=self.adviser)
        make_opportunity(title="Over", posted_by=self.adviser, due_date=timezone.localdate() - timedelta(days=5))
        make_opportunity(title="Someone else's", posted_by=self.other_adviser)

        rows = {row["title"]: row for row in self.mine(self.adviser).data["results"]}
        self.assertEqual(set(rows), {"Waiting", "Rejected", "Confirmed", "Over"})
        self.assertEqual(rows["Rejected"]["review_reason"], "Broken link")

    def test_only_a_poster_has_a_list_of_their_own(self):
        self.assertEqual(self.mine(self.student).status_code, status.HTTP_403_FORBIDDEN)


def notices(recipient, type_name):
    return list(
        Notification.objects.filter(recipient=recipient, notif_type__name=type_name)
        .values_list("message", flat=True)
    )


def rdco_notices(type_name="Call Request Submitted"):
    return Notification.objects.filter(broadcast_to_role__name="RDCO", notif_type__name=type_name)


class DecisionTests(CallReviewTestCase):

    def test_rdco_confirms_a_request_onto_the_board_and_the_adviser_is_told(self):
        call = self.adviser_call(title="ICACSIS")
        response = self.decide(self.rdco, call, "confirm")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "confirmed")
        self.assertIsNotNone(response.data["reviewed_at"])
        self.assertIn("ICACSIS", self.board_titles(self.student))
        self.assertEqual(
            notices(self.adviser, "Call Confirmed"),
            ['RDCO confirmed your call "ICACSIS". It is now on Calls & Conferences.'],
        )

    def test_a_rejection_needs_a_reason_which_the_adviser_receives(self):
        call = self.adviser_call(title="ICACSIS")
        refused = self.decide(self.rdco, call, "reject", reason="  ")
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", refused.data)

        response = self.decide(self.rdco, call, "reject", reason="The link goes to a parked domain.")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            (response.data["status"], response.data["review_reason"]),
            ("rejected", "The link goes to a parked domain."),
        )
        self.assertEqual(
            notices(self.adviser, "Call Rejected"),
            ['RDCO did not confirm your call "ICACSIS". Reason: The link goes to a parked domain.'],
        )
        # Still visible to its Adviser, with the reason; still hidden from others.
        self.assertEqual(self.as_user(self.adviser).get(self.detail(call)).data["review_reason"],
                         "The link goes to a parked domain.")
        self.assertEqual(self.as_user(self.student).get(self.detail(call)).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_stale_decision_is_refused(self):
        call = self.adviser_call()
        self.decide(self.rdco, call, "confirm")
        for act, data in (("confirm", {}), ("reject", {"reason": "Too late"})):
            with self.subTest(act):
                response = self.decide(self.rdco, call, act, **data)
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(response.data["detail"], "This Call isn't waiting for RDCO any more.")

    def test_only_rdco_decides(self):
        call = self.adviser_call()
        for act in ("confirm", "reject"):
            with self.subTest(act):
                response = self.decide(self.adviser, call, act, reason="x")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_decision_on_a_call_changed_since_rdco_opened_it_is_refused(self):
        """An Adviser may edit a waiting Call while RDCO reads it: RDCO never confirms unseen content."""
        call = self.adviser_call()
        seen = call.updated_at
        self.as_user(self.adviser).patch(self.detail(call), {"location": "Online"}, format="json")
        for act, data in (("confirm", {}), ("reject", {"reason": "Broken link"})):
            with self.subTest(act):
                response = self.decide(self.rdco, call, act, seen=seen, **data)
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(
                    response.data["detail"],
                    "This Call changed since you opened it. Open it again to see what changed.",
                )
        call.refresh_from_db()
        self.assertEqual(call.status, "pending")

    def test_a_decision_must_say_which_version_rdco_saw(self):
        response = self.as_user(self.rdco).post(reverse("opportunity-confirm", args=[self.adviser_call().pk]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("updated_at", response.data)

    def test_a_decision_on_a_call_rdco_cannot_find_is_a_404(self):
        response = self.as_user(self.rdco).post(reverse("opportunity-confirm", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RequestNoticeTests(CallReviewTestCase):
    def test_rdco_is_told_of_each_new_request(self):
        self.post_as(self.adviser, title="ICACSIS")
        notice = rdco_notices().get()
        self.assertEqual(notice.message, 'Test User asked RDCO to confirm the call "ICACSIS".')
        self.assertEqual(notice.sender, self.adviser)

    def test_rdcos_own_post_sends_no_request(self):
        self.post_as(self.rdco)
        self.assertFalse(rdco_notices().exists())

    def test_the_request_notice_settles_once_rdco_decides(self):
        """ADR-069: the notice asked RDCO to act, so it resolves when the request is decided."""
        self.post_as(self.adviser, title="ICACSIS")
        self.decide(self.rdco, Opportunity.objects.get(title="ICACSIS"), "confirm")

        listed = self.as_user(self.rdco).get(reverse("notification-list"))
        row = next(n for n in listed.data["results"] if n["message"].endswith('"ICACSIS".'))
        self.assertTrue(row["resolved_label"].startswith("Confirmed on "))


class EditTests(CallReviewTestCase):
    def patch(self, user, call, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).patch(self.detail(call), data, format="json")

    def confirmed_adviser_call(self, title="ICACSIS"):
        self.post_as(self.adviser, title=title)
        call = Opportunity.objects.get(title=title)
        self.decide(self.rdco, call, "confirm")
        return call

    def test_an_advisers_edit_returns_a_confirmed_call_to_rdco(self):
        call = self.confirmed_adviser_call()
        response = self.patch(self.adviser, call, location="Online")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "pending")
        self.assertNotIn("ICACSIS", self.board_titles(self.student))

        first, second = rdco_notices().order_by("id")
        self.assertTrue(first.resolved_label.startswith("Confirmed on "))
        self.assertEqual(second.message, 'Test User changed the call "ICACSIS" and asked RDCO to confirm it again.')
        self.assertIsNone(second.resolved_at)

    def test_rdcos_new_notice_names_the_call_as_edited(self):
        call = self.confirmed_adviser_call()
        self.patch(self.adviser, call, title="ICACSIS 2027")
        self.assertEqual(
            rdco_notices().order_by("id").last().message,
            'Test User changed the call "ICACSIS 2027" and asked RDCO to confirm it again.',
        )

    def test_an_adviser_may_move_a_passed_deadline_forward(self):
        call = make_opportunity(
            posted_by=self.adviser, due_date=timezone.localdate() - timedelta(days=3),
            start_date=timezone.localdate() + timedelta(days=10),
        )
        response = self.patch(self.adviser, call, due_date=str(timezone.localdate() + timedelta(days=7)))
        self.assertEqual((response.status_code, response.data["status"]), (status.HTTP_200_OK, "pending"))

    def test_an_advisers_edit_resubmits_a_rejected_call(self):
        call = self.adviser_call(title="ICACSIS", status="rejected", review_reason="Broken link")
        response = self.patch(self.adviser, call, external_url="https://example.org/fixed")
        self.assertEqual((response.data["status"], response.data["review_reason"]), ("pending", ""))
        self.assertEqual(rdco_notices().count(), 1)

    def test_editing_a_waiting_call_keeps_it_waiting_with_no_new_notice(self):
        call = self.adviser_call()
        response = self.patch(self.adviser, call, location="Online")
        self.assertEqual(response.data["status"], "pending")
        self.assertFalse(rdco_notices().exists())

    def test_rdcos_edits_never_change_a_calls_status(self):
        confirmed = self.confirmed_adviser_call()
        rejected = self.adviser_call(title="Rejected", status="rejected", review_reason="Broken link")
        self.assertEqual(self.patch(self.rdco, confirmed, location="Online").data["status"], "confirmed")
        response = self.patch(self.rdco, rejected, location="Online")
        self.assertEqual((response.data["status"], response.data["review_reason"]), ("rejected", "Broken link"))

    def test_a_request_that_changes_nothing_is_not_an_edit(self):
        call = self.confirmed_adviser_call()
        response = self.patch(self.adviser, call, location=call.location, is_featured=True)
        self.assertEqual(response.data["status"], "confirmed")
        self.assertIs(response.data["is_featured"], False)


class PastDeadlineTests(CallReviewTestCase):
    REFUSAL = "The paper deadline has passed. Use today's date or a later one."

    def yesterday(self):
        return str(timezone.localdate() - timedelta(days=1))

    def test_an_adviser_cannot_post_a_call_whose_deadline_has_passed(self):
        response = self.post_as(self.adviser, due_date=self.yesterday())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["due_date"], [self.REFUSAL])
        self.assertFalse(Opportunity.objects.exists())

    def test_a_deadline_of_today_is_accepted(self):
        response = self.post_as(self.adviser, due_date=str(timezone.localdate()))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_an_adviser_cannot_edit_a_call_once_its_deadline_has_passed(self):
        """Saving it would return it to RDCO, and the daily job would delete it."""
        call = make_opportunity(
            posted_by=self.adviser, due_date=timezone.localdate() - timedelta(days=3),
            start_date=timezone.localdate() + timedelta(days=10),
        )
        response = self.as_user(self.adviser).patch(self.detail(call), {"location": "Online"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["due_date"], [self.REFUSAL])

    def test_rdcos_dates_stay_unchecked(self):
        response = self.post_as(self.rdco, due_date=self.yesterday(),
                                start_date=str(timezone.localdate() + timedelta(days=5)))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class FeaturedTests(CallReviewTestCase):
    def patch(self, user, call, **data):
        return self.as_user(user).patch(self.detail(call), data, format="json")

    def test_featured_from_an_adviser_is_ignored(self):
        response = self.post_as(self.adviser, is_featured=True)
        self.assertIs(response.data["is_featured"], False)
        call = make_opportunity(posted_by=self.adviser, title="Confirmed")
        self.assertIs(self.patch(self.adviser, call, is_featured=True).data["is_featured"], False)

    def test_rdco_features_a_waiting_or_confirmed_call(self):
        for call in (self.adviser_call(title="Waiting"), make_opportunity(title="Confirmed")):
            with self.subTest(call.title):
                response = self.patch(self.rdco, call, is_featured=True)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIs(response.data["is_featured"], True)

    def test_rdco_cannot_feature_a_rejected_call(self):
        call = self.adviser_call(status="rejected", review_reason="Broken link")
        response = self.patch(self.rdco, call, is_featured=True)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["is_featured"], ["Only a waiting or confirmed Call can be featured."])

    def test_featured_does_not_move_a_call_up_the_board(self):
        today = timezone.localdate()
        make_opportunity(title="Later, featured", due_date=today + timedelta(days=40), is_featured=True)
        make_opportunity(title="Sooner", due_date=today + timedelta(days=1))
        rows = self.as_user(self.student).get(reverse("opportunity-list")).data["results"]
        self.assertEqual([row["title"] for row in rows], ["Sooner", "Later, featured"])


class RemovalTests(CallReviewTestCase):
    NEEDS_REASON = "An Adviser posted this Call. Remove it with a reason, which they receive."

    def delete(self, user, call):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).delete(self.detail(call))

    def remove(self, user, call, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_user(user).post(reverse("opportunity-remove", args=[call.pk]), data, format="json")

    def test_an_adviser_deletes_their_own_call_in_any_status(self):
        calls = [
            self.adviser_call(title="Waiting"),
            self.adviser_call(title="Rejected", status="rejected", review_reason="Broken link"),
            make_opportunity(title="Confirmed", posted_by=self.adviser),
        ]
        for call in calls:
            with self.subTest(call.title):
                self.assertEqual(self.delete(self.adviser, call).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Opportunity.objects.exists())

    def test_rdco_deletes_its_own_and_a_colleagues_call_without_a_reason(self):
        colleague = make_user("rdco.two@cit.edu", "RDCO")
        for call in (make_opportunity(posted_by=self.rdco), make_opportunity(posted_by=colleague),
                     make_opportunity(posted_by=None, title="Poster gone")):
            with self.subTest(call.title):
                self.assertEqual(self.delete(self.rdco, call).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(notif_type__name="Call Removed").exists())

    def test_rdco_cannot_delete_an_advisers_call_without_a_reason(self):
        call = make_opportunity(posted_by=self.adviser)
        response = self.delete(self.rdco, call)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], self.NEEDS_REASON)
        self.assertTrue(Opportunity.objects.filter(pk=call.pk).exists())

    def test_rdco_removes_an_advisers_call_with_a_reason_they_receive(self):
        call = make_opportunity(title="ICACSIS", posted_by=self.adviser)
        self.assertEqual(self.remove(self.rdco, call, reason="").status_code, status.HTTP_400_BAD_REQUEST)

        response = self.remove(self.rdco, call, reason="The conference was cancelled.")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Opportunity.objects.filter(pk=call.pk).exists())
        self.assertEqual(
            notices(self.adviser, "Call Removed"),
            ['RDCO removed your call "ICACSIS". Reason: The conference was cancelled.'],
        )

    def test_a_call_needing_no_reason_is_deleted_not_removed(self):
        call = make_opportunity(posted_by=self.rdco)
        response = self.remove(self.rdco, call, reason="Tidying up")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "This Call needs no reason. Delete it instead.")
        self.assertTrue(Opportunity.objects.filter(pk=call.pk).exists())

    def test_only_rdco_removes(self):
        call = make_opportunity(posted_by=self.other_adviser)
        self.assertEqual(self.remove(self.adviser, call, reason="Mine now").status_code, status.HTTP_403_FORBIDDEN)

    def test_rdcos_request_notice_settles_once_the_deadline_passes(self):
        """The request has left RDCO's queue, so its notice resolves before the job deletes it."""
        self.post_as(self.adviser, title="ICACSIS", due_date=str(timezone.localdate()))
        Opportunity.objects.filter(title="ICACSIS").update(due_date=timezone.localdate() - timedelta(days=1))
        self.as_user(self.rdco).get(reverse("notification-list"))
        self.assertEqual(rdco_notices().get().resolved_label, "No longer waiting")

    def test_rdcos_request_notice_settles_when_the_adviser_withdraws_it(self):
        self.post_as(self.adviser, title="ICACSIS")
        self.delete(self.adviser, Opportunity.objects.get(title="ICACSIS"))
        self.as_user(self.rdco).get(reverse("notification-list"))
        self.assertEqual(rdco_notices().get().resolved_label, "No longer waiting")


class CapabilityTests(CallReviewTestCase):
    """What the API tells each viewer they may do, so IR-765 compares no role names."""

    KEYS = ("can_edit", "can_delete", "can_remove", "can_confirm", "can_reject",
            "can_feature", "edit_returns_to_pending")

    def capabilities(self, viewer, call):
        data = self.as_user(viewer).get(self.detail(call)).data
        return {key: data[key] for key in self.KEYS}

    def expect(self, **true):
        return {key: key in true for key in self.KEYS}

    def test_rdco_on_a_waiting_request(self):
        self.assertEqual(
            self.capabilities(self.rdco, self.adviser_call()),
            self.expect(can_edit=1, can_remove=1, can_confirm=1, can_reject=1, can_feature=1),
        )

    def test_rdco_on_a_rejected_request(self):
        call = self.adviser_call(status="rejected", review_reason="Broken link")
        self.assertEqual(self.capabilities(self.rdco, call), self.expect(can_edit=1, can_remove=1))

    def test_rdco_on_its_own_call(self):
        call = make_opportunity(posted_by=self.rdco)
        self.assertEqual(self.capabilities(self.rdco, call), self.expect(can_edit=1, can_delete=1, can_feature=1))

    def test_the_adviser_on_their_confirmed_call(self):
        call = make_opportunity(posted_by=self.adviser)
        self.assertEqual(
            self.capabilities(self.adviser, call),
            self.expect(can_edit=1, can_delete=1, edit_returns_to_pending=1),
        )

    def test_the_adviser_on_their_waiting_call(self):
        self.assertEqual(self.capabilities(self.adviser, self.adviser_call()), self.expect(can_edit=1, can_delete=1))

    def test_the_adviser_may_still_edit_once_the_deadline_has_passed(self):
        """Moving the deadline forward is accepted; only a save keeping a past one is refused."""
        call = make_opportunity(
            posted_by=self.adviser, due_date=timezone.localdate() - timedelta(days=2),
            start_date=timezone.localdate() + timedelta(days=5),
        )
        self.assertEqual(
            self.capabilities(self.adviser, call),
            self.expect(can_edit=1, can_delete=1, edit_returns_to_pending=1),
        )

    def test_a_reader_may_do_nothing(self):
        call = make_opportunity(posted_by=self.adviser)
        for viewer in (self.student, self.other_adviser):
            with self.subTest(viewer.email):
                self.assertEqual(self.capabilities(viewer, call), self.expect())

    def test_a_lapsed_request_cannot_be_decided(self):
        call = self.adviser_call(due_date=timezone.localdate() - timedelta(days=1))
        caps = self.capabilities(self.rdco, call)
        self.assertEqual((caps["can_confirm"], caps["can_reject"]), (False, False))
        response = self.decide(self.rdco, call, "confirm")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_the_board_says_who_reviews_requests(self):
        for viewer, expected in ((self.rdco, True), (self.adviser, False), (self.student, False)):
            with self.subTest(viewer.email):
                data = self.as_user(viewer).get(reverse("opportunity-list")).data
                self.assertIs(data["can_review_requests"], expected)


class PersonalDataTests(CallReviewTestCase):
    def test_an_advisers_download_says_where_each_call_stands(self):
        from apps.accounts.personal_data.export import opportunities_posted

        self.adviser_call(title="Rejected", status="rejected", review_reason="Broken link")
        (row,) = opportunities_posted(self.adviser)
        self.assertEqual((row["status"], row["review_reason"]), ("rejected", "Broken link"))
