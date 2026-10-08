"""
My Reviews: a reviewer's own seats plus their office's pool, as To review, In
review and Done (IR-268).

ADR-032 §9 and its 2026-10-08 Amendment, at the REST seam the card names ("API
tests per role and per tab"): `GET /api/v1/reviews/mine/`. One class per
acceptance criterion, then the decisions settled in the 2026-10-08 grilling.
New-model records reach their state through routing, as in `test_routing.py`;
old-pipeline records are parked at a stage, as the legacy queue tests do.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, RecordClearance, Review, ReviewerSeat
from core.enums import (
    AssignmentState,
    Party,
    PipelineStatus,
    RecordTypeName,
    RoleName,
    SeatSource,
    SeatState,
)

from .test_routing import RoutingTestBase
from .test_workflow_characterisation import make_user

MINE = "/api/v1/reviews/mine/"


class MyReviewsTestBase(RoutingTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.itso_coordinator = make_user("mine-itso-coord@cit.edu", RoleName.ITSO)
        cls.itso_coordinator.is_office_coordinator = True
        cls.itso_coordinator.save(update_fields=["is_office_coordinator"])
        cls.adviser2 = make_user("mine-adviser2@cit.edu", RoleName.ADVISER)

    def mine(self, as_user, **params):
        self.client.force_authenticate(as_user)
        return self.client.get(MINE, params)

    def page(self, as_user, **params):
        response = self.mine(as_user, **params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def rows(self, as_user, **params):
        return self.page(as_user, **params)["rows"]

    def keys(self, as_user, **params):
        """(record id, party, kind) for each row: what the row is, not how it looks."""
        return {(r["record"], r["party"], r["kind"]) for r in self.rows(as_user, **params)}

    def routed(self, *parties, type_name=RecordTypeName.THESIS_RESEARCH):
        record = self.new_model(type_name)
        self.accepted_to(record, *parties)
        return record

    def assignment(self, record, party):
        return RecordAssignment.objects.get(record=record, party=party, state=AssignmentState.ACTIVE)

    def opened(self, seat):
        seat.state = SeatState.IN_REVIEW
        seat.opened_at = timezone.now()
        seat.save(update_fields=["state", "opened_at"])
        return seat

    def done_seat(self, record, when):
        """`self.itso`'s finished seat on a closed ITSO assignment of `record`."""
        assignment = RecordAssignment.objects.create(
            record=record, party=Party.ITSO, state=AssignmentState.COMPLETED,
        )
        return ReviewerSeat.objects.create(
            assignment=assignment, reviewer=self.itso, source=SeatSource.CLAIMED,
            state=SeatState.DONE, done_at=when,
        )

    def legacy(self, pipeline_status, **extra):
        """An old-pipeline record parked at `pipeline_status`."""
        record = Record.objects.create(
            title=f"Legacy at {pipeline_status}",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.PROJECT)[0],
            added_by=self.owner,
            pipeline_status=pipeline_status,
            adviser=self.adviser,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record


# --- AC: To review --------------------------------------------------------------------

class ToReviewTests(MyReviewsTestBase):

    def test_an_itso_member_sees_their_unopened_seat_and_itsos_pool_only(self):
        seated = self.routed(Party.ITSO)
        self.seat(seated, Party.ITSO, self.itso)
        pool = self.routed(Party.ITSO)
        colleagues = self.routed(Party.ITSO)
        self.seat(colleagues, Party.ITSO, self.itso2)
        ierc_pool = self.routed(Party.IERC)

        self.assertEqual(
            self.keys(self.itso, tab="to_review"),
            {(seated.pk, "itso", "seat"), (pool.pk, "itso", "pool")},
        )
        self.assertNotIn(ierc_pool.pk, {r["record"] for r in self.rows(self.itso, tab="to_review")})

    def test_a_pool_row_carries_its_assignment_and_offers_claim_to_a_member(self):
        record = self.routed(Party.ITSO)
        row = self.rows(self.itso, tab="to_review")[0]

        self.assertEqual(row["assignment"], self.assignment(record, Party.ITSO).pk)
        self.assertIsNone(row["seat"])
        self.assertTrue(row["can_claim"])
        self.assertFalse(row["can_assign"])

    def test_a_coordinator_is_also_offered_assign_on_a_pool_row(self):
        self.routed(Party.ITSO)
        row = self.rows(self.itso_coordinator, tab="to_review")[0]
        self.assertTrue(row["can_claim"])
        self.assertTrue(row["can_assign"])

    def test_a_routed_row_says_who_routed_it_and_why(self):
        self.routed(Party.ITSO)
        row = self.rows(self.itso, tab="to_review")[0]
        self.assertEqual(row["routed_by"], self.adviser.get_full_name())
        self.assertEqual(row["routed_reason"], "Possible patentable mechanism.")
        self.assertIsNotNone(row["waiting_since"])

    def test_an_opened_seat_is_not_in_to_review(self):
        record = self.routed(Party.ITSO)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        self.assertEqual(self.rows(self.itso, tab="to_review"), [])

    def test_to_review_is_the_default_tab(self):
        self.routed(Party.ITSO)
        self.assertEqual(len(self.rows(self.itso)), 1)


# --- AC: Adviser --------------------------------------------------------------------------

class AdviserTests(MyReviewsTestBase):

    def test_an_adviser_sees_a_record_only_through_their_own_seat(self):
        record = self.new_model()

        rows = self.rows(self.adviser, tab="to_review")
        self.assertEqual([(r["record"], r["party"], r["kind"]) for r in rows],
                         [(record.pk, "adviser", "seat")])
        self.assertEqual(rows[0]["submitted_by"], self.owner.get_full_name())
        self.assertIsNone(rows[0]["routed_by"])
        self.assertEqual(self.rows(self.adviser2, tab="to_review"), [])

    def test_an_adviser_has_no_pool(self):
        """The Adviser is not an office, so nothing is ever theirs to claim."""
        self.new_model()
        for row in self.rows(self.adviser2, tab="to_review"):
            self.assertNotEqual(row["kind"], "pool")


# --- AC: In review ------------------------------------------------------------------------

class InReviewTests(MyReviewsTestBase):

    def test_an_opened_seat_appears_in_review(self):
        record = self.routed(Party.ITSO)
        seat = self.opened(self.seat(record, Party.ITSO, self.itso))

        rows = self.rows(self.itso, tab="in_review")
        self.assertEqual([(r["record"], r["seat"]) for r in rows], [(record.pk, seat.pk)])
        self.assertIsNone(rows[0]["waiting_on"])

    def test_an_open_revision_request_reports_waiting_on_author_and_stays(self):
        record = self.routed(Party.ITSO)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        response = self.post(
            reverse("record-request-revision", args=[record.pk]), self.itso,
            {"reason": "Clarify the claims."},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        rows = self.rows(self.itso, tab="in_review")
        self.assertEqual([r["record"] for r in rows], [record.pk])
        self.assertEqual(rows[0]["waiting_on"], "author")
        self.assertEqual(self.rows(self.itso, tab="done"), [])

    def test_waiting_on_is_record_level_and_author_wins_over_document(self):
        """Settled 2026-10-08: any party's open request counts."""
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        self.opened(self.seat(record, Party.IERC, self.ierc))
        response = self.post(
            reverse("record-document-requests", args=[record.pk]), self.ierc,
            {"message": "The consent forms.", "items": [{"label": "Consent forms"}]},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self.rows(self.itso, tab="in_review")[0]["waiting_on"], "document")

        response = self.post(
            reverse("record-request-revision", args=[record.pk]), self.ierc,
            {"reason": "Clarify the consent process."},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.rows(self.itso, tab="in_review")[0]["waiting_on"], "author")


# --- AC: Done -----------------------------------------------------------------------------

class DoneTests(MyReviewsTestBase):

    def office_review(self, record, as_user, outcome, comment="A reason."):
        response = self.post(
            reverse("record-office-review", args=[record.pk]), as_user,
            {"outcome": outcome, "comment": comment},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def legacy_review(self, record, by, stage, decision):
        """A decision from before IR-415: no assignment, so no seat behind it."""
        return Review.objects.create(record=record, reviewed_by=by, stage=stage, status=decision)

    def test_a_completed_seat_appears_with_its_outcome(self):
        record = self.routed(Party.ITSO)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        self.office_review(record, self.itso, "cleared")

        rows = self.rows(self.itso, tab="done")
        self.assertEqual([(r["record"], r["kind"], r["outcome"]) for r in rows],
                         [(record.pk, "seat", "cleared")])
        self.assertEqual(rows[0]["outcome_label"], "Cleared")
        self.assertIsNotNone(rows[0]["decided_at"])

    def test_the_outcome_filter_narrows_done_and_never_the_counts(self):
        cleared = self.routed(Party.ITSO)
        self.opened(self.seat(cleared, Party.ITSO, self.itso))
        self.office_review(cleared, self.itso, "cleared")
        found = self.routed(Party.ITSO)
        self.opened(self.seat(found, Party.ITSO, self.itso))
        self.office_review(found, self.itso, "finding")

        page = self.page(self.itso, tab="done", outcome="finding")
        self.assertEqual([(r["record"], r["outcome"]) for r in page["rows"]], [(found.pk, "finding")])
        self.assertEqual(page["counts"]["done"], 2)
        self.assertEqual(
            {r["record"] for r in self.rows(self.itso, tab="done", outcome="cleared")}, {cleared.pk},
        )

    def test_an_advisers_accept_and_route_is_accepted(self):
        record = self.routed(Party.ITSO)
        rows = self.rows(self.adviser, tab="done")
        self.assertEqual([(r["record"], r["party"], r["outcome"]) for r in rows],
                         [(record.pk, "adviser", "accepted")])
        self.assertEqual(self.rows(self.adviser, tab="done", outcome="accepted")[0]["record"], record.pk)

    def test_old_pipeline_history_without_a_seat_is_done(self):
        """Settled 2026-10-08 (Q10): the seat backfill never seated these."""
        record = self.legacy(PipelineStatus.PARALLEL_REVIEW)
        self.legacy_review(record, self.itso, "itso", "approved")

        rows = self.rows(self.itso, tab="done")
        self.assertEqual([(r["record"], r["kind"], r["outcome"]) for r in rows],
                         [(record.pk, "review", "cleared")])

    def test_an_old_decline_is_revision_requested_and_only_under_all(self):
        record = self.legacy(PipelineStatus.DECLINED)
        self.legacy_review(record, self.itso, "itso", "declined")

        rows = self.rows(self.itso, tab="done")
        self.assertEqual([(r["record"], r["outcome"]) for r in rows], [(record.pk, "revision_requested")])
        for outcome in ("cleared", "finding", "accepted", "rejected", "published"):
            with self.subTest(outcome=outcome):
                self.assertEqual(self.rows(self.itso, tab="done", outcome=outcome), [])

    def test_a_final_approval_that_published_the_record_is_published(self):
        record = self.legacy(PipelineStatus.PUBLISHED)
        self.legacy_review(record, self.rdco, "rdco", "approved")
        self.assertEqual(self.rows(self.rdco, tab="done")[0]["outcome"], "published")
        self.assertEqual(len(self.rows(self.rdco, tab="done", outcome="published")), 1)
        self.assertEqual(self.rows(self.rdco, tab="done", outcome="accepted"), [])

    def test_an_intake_decision_is_rdcos(self):
        record = self.legacy(PipelineStatus.ITSO_REVIEW)
        self.legacy_review(record, self.rdco, "rdco_intake", "approved")
        row = self.rows(self.rdco, tab="done")[0]
        self.assertEqual((row["party"], row["party_label"], row["outcome"]), ("rdco", "RDCO Intake", "accepted"))

    def test_a_seat_done_without_a_verdict_of_its_own_has_no_outcome(self):
        record = self.routed(Party.ITSO)
        seat = self.opened(self.seat(record, Party.ITSO, self.itso))
        seat.state = SeatState.DONE
        seat.done_at = timezone.now()
        seat.save(update_fields=["state", "done_at"])

        row = self.rows(self.itso, tab="done")[0]
        self.assertIsNone(row["outcome"])
        self.assertEqual(row["outcome_label"], "Completed by your office")
        self.assertEqual(self.rows(self.itso, tab="done", outcome="cleared"), [])

    def test_two_review_rounds_are_two_done_rows(self):
        record = self.routed(Party.ITSO)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        self.office_review(record, self.itso, "cleared")
        rdco = self.assignment(record, Party.RDCO)
        ReviewerSeat.objects.create(assignment=rdco, reviewer=self.rdco, source=SeatSource.CLAIMED)
        response = self.route(record, self.rdco, [{"party": Party.ITSO}])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.opened(self.seat(record, Party.ITSO, self.itso))
        self.office_review(record, self.itso, "finding")

        outcomes = [r["outcome"] for r in self.rows(self.itso, tab="done")]
        self.assertEqual(outcomes, ["finding", "cleared"])

    def test_done_is_paged_newest_first(self):
        records = []
        now = timezone.now()
        for i in range(51):
            record = self.legacy(PipelineStatus.PUBLISHED)
            review = self.legacy_review(record, self.itso, "itso", "approved")
            Review.objects.filter(pk=review.pk).update(created_at=now - timezone.timedelta(minutes=i))
            records.append(record.pk)

        first = self.page(self.itso, tab="done")
        self.assertEqual([r["record"] for r in first["rows"]], records[:50])
        self.assertIsNotNone(first["next"])
        self.assertEqual(first["counts"]["done"], 51)
        second = self.page(self.itso, tab="done", cursor=first["next"])
        self.assertEqual([r["record"] for r in second["rows"]], records[50:])
        self.assertIsNone(second["next"])


    def test_done_pages_across_seats_and_seatless_reviews_as_one_list(self):
        """Settled 2026-10-08 (Q16): one ordering key across both sources."""
        now = timezone.now()
        expected = []
        for i in range(60):
            record = self.legacy(PipelineStatus.PUBLISHED)
            when = now - timezone.timedelta(minutes=i)
            if i % 2:
                review = self.legacy_review(record, self.itso, "itso", "approved")
                Review.objects.filter(pk=review.pk).update(created_at=when)
            else:
                self.done_seat(record, when)
            expected.append(record.pk)

        first = self.page(self.itso, tab="done")
        second = self.page(self.itso, tab="done", cursor=first["next"])
        self.assertEqual([r["record"] for r in first["rows"] + second["rows"]], expected)
        self.assertEqual(len(first["rows"]), 50)
        self.assertIsNone(second["next"])


# --- AC: Coordinator ----------------------------------------------------------------------

class CoordinatorTests(MyReviewsTestBase):

    def test_a_coordinator_lists_every_seat_in_their_office_with_its_holder(self):
        mine = self.routed(Party.ITSO)
        self.seat(mine, Party.ITSO, self.itso)
        theirs = self.routed(Party.ITSO)
        self.opened(self.seat(theirs, Party.ITSO, self.itso2))
        pool = self.routed(Party.ITSO)
        self.routed(Party.IERC)

        to_review = self.rows(self.itso_coordinator, tab="to_review", office="itso")
        self.assertEqual(
            {(r["record"], r["kind"], r["holder_name"]) for r in to_review},
            {(mine.pk, "seat", self.itso.get_full_name()), (pool.pk, "pool", None)},
        )
        in_review = self.rows(self.itso_coordinator, tab="in_review", office="itso")
        self.assertEqual([(r["record"], r["holder"]) for r in in_review], [(theirs.pk, self.itso2.pk)])

    def test_the_office_view_narrows_the_counts(self):
        record = self.routed(Party.ITSO)
        self.seat(record, Party.ITSO, self.itso)
        mine_view = self.page(self.itso_coordinator)["counts"]
        office_view = self.page(self.itso_coordinator, office="itso")["counts"]
        self.assertEqual((mine_view["to_review"], office_view["to_review"]), (0, 1))

    def test_a_non_coordinator_is_refused_the_office_parameter(self):
        self.assertEqual(self.mine(self.itso, office="itso").status_code, status.HTTP_403_FORBIDDEN)

    def test_a_coordinator_is_refused_another_office(self):
        for office in ("ierc", "nonsense"):
            with self.subTest(office=office):
                response = self.mine(self.itso_coordinator, office=office)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_an_old_pipeline_row_in_the_office_view_offers_no_assign(self):
        record = self.legacy(PipelineStatus.ITSO_REVIEW)
        RecordClearance.objects.create(record=record, office="itso", status="pending")

        rows = self.rows(self.itso_coordinator, office="itso")
        self.assertEqual([(r["record"], r["kind"], r["can_assign"]) for r in rows],
                         [(record.pk, "legacy", False)])


# --- AC: Old pipeline -----------------------------------------------------------------------

class OldPipelineTests(MyReviewsTestBase):

    def test_old_pipeline_records_appear_where_the_old_queue_put_them(self):
        itso_stage = self.legacy(PipelineStatus.ITSO_REVIEW)
        for office in ("itso", "ierc", "ktto"):
            RecordClearance.objects.create(record=itso_stage, office=office, status="pending")
        intake = self.legacy(PipelineStatus.RDCO_INTAKE)
        proposal = self.legacy(PipelineStatus.ADVISER_REVIEW)

        def legacy_rows(user):
            return {r["record"] for r in self.rows(user, tab="to_review") if r["kind"] == "legacy"}

        self.assertEqual(legacy_rows(self.itso), {itso_stage.pk})
        self.assertEqual(legacy_rows(self.ktto), {itso_stage.pk})
        # IERC holds a pending clearance at itso_review, and may not act there yet.
        self.assertEqual(legacy_rows(self.ierc), set())
        self.assertEqual(legacy_rows(self.rdco), {intake.pk})
        self.assertEqual(legacy_rows(self.adviser), {proposal.pk})
        self.assertEqual(legacy_rows(self.adviser2), set())

    def test_a_legacy_row_names_its_stage_and_is_never_in_review(self):
        self.legacy(PipelineStatus.RDCO_INTAKE)
        row = self.rows(self.rdco, tab="to_review")[0]
        self.assertEqual(row["stage_label"], "RDCO Intake Review")
        self.assertEqual(row["party_label"], "RDCO")
        self.assertFalse(row["can_claim"])
        self.assertEqual(self.rows(self.rdco, tab="in_review"), [])

    def test_a_student_has_empty_tabs(self):
        self.legacy(PipelineStatus.RDCO_INTAKE)
        page = self.page(self.owner)
        self.assertEqual(page["rows"], [])
        self.assertEqual(page["counts"], {"to_review": 0, "in_review": 0, "done": 0})


# --- Settled 2026-10-08: the contract -------------------------------------------------------

class ContractTests(MyReviewsTestBase):

    def test_every_tab_is_counted_on_every_call(self):
        to_review = self.routed(Party.ITSO)
        self.seat(to_review, Party.ITSO, self.itso)
        in_review = self.routed(Party.ITSO)
        self.opened(self.seat(in_review, Party.ITSO, self.itso))
        self.routed(Party.ITSO)

        for tab in ("to_review", "in_review", "done"):
            with self.subTest(tab=tab):
                self.assertEqual(self.page(self.itso, tab=tab)["counts"],
                                 {"to_review": 2, "in_review": 1, "done": 0})

    def test_a_parameter_it_cannot_read_is_a_400(self):
        for params in ({"tab": "awaiting"}, {"tab": "done", "outcome": "approved"},
                       {"tab": "done", "outcome": "revision_requested"},
                       {"tab": "done", "cursor": "not-a-cursor"}):
            with self.subTest(params=params):
                self.assertEqual(self.mine(self.itso, **params).status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(MINE).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_query_count_does_not_grow_with_the_rows(self):
        """Settled 2026-10-08: more rows must never mean more queries."""
        def build(n):
            for _ in range(n):
                self.seat(self.routed(Party.ITSO), Party.ITSO, self.itso)
                self.routed(Party.ITSO)
                legacy = self.legacy(PipelineStatus.ITSO_REVIEW)
                RecordClearance.objects.create(record=legacy, office="itso", status="pending")
                done = self.legacy(PipelineStatus.PUBLISHED)
                Review.objects.create(record=done, reviewed_by=self.itso, stage="itso", status="approved")
                self.done_seat(self.legacy(PipelineStatus.PUBLISHED), timezone.now())

        def queries(tab):
            self.client.force_authenticate(self.itso)
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(MINE, {"tab": tab}).status_code, status.HTTP_200_OK)
            return len(ctx)

        build(1)
        small = {tab: queries(tab) for tab in ("to_review", "done")}
        build(5)
        large = {tab: queries(tab) for tab in ("to_review", "done")}
        self.assertEqual(small, large)


# --- Settled 2026-10-08: the Assign picklist ----------------------------------------------------

class AssignOptionsTests(MyReviewsTestBase):

    def url(self, assignment):
        return reverse("assignment-assign", args=[assignment.pk])

    def test_a_coordinator_is_offered_their_offices_members(self):
        assignment = self.assignment(self.routed(Party.ITSO), Party.ITSO)
        self.client.force_authenticate(self.itso_coordinator)
        response = self.client.get(self.url(assignment))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ids = {m["id"] for m in response.data["members"]}
        self.assertTrue({self.itso.pk, self.itso2.pk, self.itso_coordinator.pk} <= ids)
        self.assertNotIn(self.ierc.pk, ids)

    def test_a_member_who_is_not_a_coordinator_is_refused(self):
        assignment = self.assignment(self.routed(Party.ITSO), Party.ITSO)
        self.client.force_authenticate(self.itso)
        self.assertEqual(self.client.get(self.url(assignment)).status_code, status.HTTP_403_FORBIDDEN)

    def test_someone_who_cannot_see_the_record_gets_not_found(self):
        assignment = self.assignment(self.routed(Party.ITSO), Party.ITSO)
        self.client.force_authenticate(make_user("mine-stranger@cit.edu", RoleName.STUDENT))
        self.assertEqual(self.client.get(self.url(assignment)).status_code, status.HTTP_404_NOT_FOUND)
