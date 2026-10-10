"""
Adviser-first entry, accept & route, and onward routing into pools (IR-261).

ADR-032 §1, §3, §4, at the REST seam IR-255 confirmed. One class per
acceptance criterion. Records reach the new model through
`routing.enter_at_adviser`, which is how they get there until IR-260 makes
submission call it (decided 2026-10-07).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews import routing
from apps.reviews.models import (
    RecordAssignment,
    RecordClearance,
    Review,
    ReviewerSeat,
    RoutingEvent,
)
from core.enums import (
    AssignmentState,
    ClearanceStatus,
    Party,
    PipelineStatus,
    RecordTypeName,
    ReviewDecision,
    RoleName,
    SeatSource,
    SeatState,
)

from .workflow_test_helpers import make_user


def accept_url(record):
    return reverse("record-accept-and-route", args=[record.pk])


def route_url(record):
    return reverse("record-route", args=[record.pk])


def options_url(record):
    return reverse("record-route-options", args=[record.pk])


class RoutingTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("route-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = make_user("route-adviser@cit.edu", RoleName.ADVISER)
        cls.itso = make_user("route-itso@cit.edu", RoleName.ITSO)
        cls.itso2 = make_user("route-itso2@cit.edu", RoleName.ITSO)
        cls.ierc = make_user("route-ierc@cit.edu", RoleName.IERC)
        cls.ktto = make_user("route-ktto@cit.edu", RoleName.KTTO)
        cls.rdco = make_user("route-rdco@cit.edu", RoleName.RDCO)

    def make_record(self, type_name=RecordTypeName.THESIS_RESEARCH, **extra):
        record = Record.objects.create(
            title=f"Routing {type_name}",
            abstract="A" * 40,
            record_type=RecordType.objects.get_or_create(name=type_name)[0],
            added_by=self.owner,
            pipeline_status=PipelineStatus.DRAFT,
            adviser=self.adviser,
            **extra,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def new_model(self, type_name=RecordTypeName.THESIS_RESEARCH, **extra):
        record = self.make_record(type_name, **extra)
        routing.enter_at_adviser(record, self.owner)
        return record

    def post(self, url, as_user, body):
        self.client.force_authenticate(as_user)
        return self.client.post(url, body, format="json")

    def accept(self, record, to, reason="Possible patentable mechanism.", as_user=None):
        return self.post(accept_url(record), as_user or self.adviser, {"to": to, "reason": reason})

    def route(self, record, as_user, to, reason="Commercial potential."):
        return self.post(route_url(record), as_user, {"to": to, "reason": reason})

    def active(self, record):
        return set(
            RecordAssignment.objects.filter(record=record, state=AssignmentState.ACTIVE)
            .values_list("party", flat=True)
        )

    def seat(self, record, party, reviewer):
        assignment = RecordAssignment.objects.get(
            record=record, party=party, state=AssignmentState.ACTIVE,
        )
        return ReviewerSeat.objects.create(
            assignment=assignment, reviewer=reviewer, source=SeatSource.CLAIMED,
        )

    def accepted_to(self, record, *parties):
        response = self.accept(record, [{"party": p} for p in parties])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response


# --- entry -------------------------------------------------------------------------

class EntryTests(RoutingTestBase):

    def test_a_new_model_thesis_enters_at_its_adviser_with_an_entry_seat(self):
        record = self.new_model()

        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        self.assertEqual(self.active(record), {Party.ADVISER})
        self.assertFalse(RecordAssignment.objects.filter(record=record, party=Party.INTAKE).exists())
        seat = ReviewerSeat.objects.get(assignment__record=record)
        self.assertEqual((seat.reviewer, seat.source), (self.adviser, SeatSource.ENTRY))

        self.client.force_authenticate(self.owner)
        tracker = self.client.get(reverse("record-tracker", args=[record.pk])).data
        self.assertEqual(tracker["workflow_state"], "submitted")

    def test_an_adviser_who_owns_the_record_cannot_be_its_adviser(self):
        """ADR-032 §1: nobody reviews their own submission."""
        record = self.make_record()
        RecordOwner.objects.create(record=record, user=self.adviser)
        with self.assertRaises(routing.RoutingError):
            routing.enter_at_adviser(record, self.owner)
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)

    def test_only_a_draft_enters(self):
        record = self.new_model()
        with self.assertRaises(routing.RoutingError):
            routing.enter_at_adviser(record, self.owner)
        self.assertEqual(RecordAssignment.objects.filter(record=record).count(), 1)

    def test_a_record_with_no_adviser_cannot_enter(self):
        record = self.make_record()
        record.adviser = None
        record.save(update_fields=["adviser"])
        with self.assertRaises(routing.RoutingError):
            routing.enter_at_adviser(record, self.owner)


# --- accept & route ------------------------------------------------------------------

class AcceptAndRouteTests(RoutingTestBase):

    def test_the_adviser_accepts_and_routes_to_two_offices(self):
        record = self.new_model()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.accepted_to(record, Party.ITSO, Party.IERC)

        # Both offices hold it, in their pools.
        self.assertEqual(self.active(record), {Party.ITSO, Party.IERC})
        for party in (Party.ITSO, Party.IERC):
            assignment = RecordAssignment.objects.get(
                record=record, party=party, state=AssignmentState.ACTIVE,
            )
            self.assertFalse(assignment.seats.exists(), f"{party} should be a pool")
        # One movement, Adviser -> ITSO + IERC, on the tracker it answers with.
        # (The history also starts with the submitter's movement in, to the
        # Adviser, which `enter_at_adviser` records.)
        from_adviser = [
            m for m in response.data["routing_history"] if m["from"] == Party.ADVISER
        ]
        self.assertEqual(len(from_adviser), 1)
        self.assertEqual(set(from_adviser[0]["to"]), {Party.ITSO, Party.IERC})
        self.assertEqual(
            [(m["from"], m["to"]) for m in response.data["routing_history"]],
            [(None, [Party.ADVISER]), (Party.ADVISER, from_adviser[0]["to"])],
        )
        # The Adviser's turn is over, and the record is still in review.
        adviser = RecordAssignment.objects.get(record=record, party=Party.ADVISER)
        self.assertEqual(adviser.state, AssignmentState.COMPLETED)
        self.assertEqual(
            ReviewerSeat.objects.get(assignment=adviser).state, SeatState.DONE,
        )
        record.refresh_from_db()
        self.assertEqual(record.pipeline_status, PipelineStatus.IN_REVIEW)
        # The acceptance is the Adviser's review.
        review = Review.objects.get(record=record)
        self.assertEqual(
            (review.stage, review.status, review.reviewed_by),
            (Party.ADVISER, ReviewDecision.APPROVED, self.adviser),
        )
        # Each office's clearance is pending.
        self.assertEqual(
            dict(RecordClearance.objects.filter(record=record).values_list("office", "status")),
            {Party.ITSO: ClearanceStatus.PENDING, Party.IERC: ClearanceStatus.PENDING},
        )
        # Members of both offices, and the owner, are notified.
        for role in (RoleName.ITSO, RoleName.IERC):
            self.assertTrue(
                Notification.objects.filter(record=record, broadcast_to_role__name=role).exists(),
                f"{role} was not notified",
            )
        self.assertTrue(Notification.objects.filter(record=record, recipient=self.owner).exists())

    def test_a_nominee_is_seated(self):
        record = self.new_model()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.accept(record, [{"party": Party.ITSO, "nominee": self.itso.pk}])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        seat = ReviewerSeat.objects.get(assignment__record=record, assignment__party=Party.ITSO)
        self.assertEqual(
            (seat.reviewer, seat.source, seat.assigned_by),
            (self.itso, SeatSource.NOMINATED, self.adviser),
        )
        self.assertTrue(Notification.objects.filter(record=record, recipient=self.itso).exists())
        # It went to the nominee, not the pool: ITSO is not told its pool has work.
        self.assertFalse(
            Notification.objects.filter(record=record, broadcast_to_role__name=RoleName.ITSO).exists()
        )

    def test_a_nominee_who_does_not_staff_the_office_is_refused_and_nothing_is_written(self):
        record = self.new_model()

        response = self.accept(record, [{"party": Party.ITSO, "nominee": self.ierc.pk}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(self.active(record), {Party.ADVISER})
        self.assertFalse(Review.objects.filter(record=record).exists())

    def test_only_the_records_adviser_may_accept(self):
        record = self.new_model()
        self.assertEqual(self.accept(record, [{"party": Party.ITSO}], as_user=self.owner).status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.accept(record, [{"party": Party.ITSO}], as_user=self.itso).status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_the_adviser_accepts_once(self):
        record = self.new_model()
        self.accepted_to(record, Party.ITSO)
        self.assertEqual(self.accept(record, [{"party": Party.KTTO}]).status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_a_record_the_caller_cannot_see_is_a_404(self):
        record = self.new_model()
        stranger = make_user("route-stranger@cit.edu", RoleName.ADVISER)
        self.assertEqual(self.accept(record, [{"party": Party.ITSO}], as_user=stranger).status_code,
                         status.HTTP_404_NOT_FOUND)


# --- onward routing ---------------------------------------------------------------------

class OnwardRoutingTests(RoutingTestBase):

    def setUp(self):
        self.record = self.new_model()
        self.accepted_to(self.record, Party.ITSO)
        self.itso_seat = self.seat(self.record, Party.ITSO, self.itso)

    def test_an_itso_seat_holder_routes_to_ktto_and_keeps_its_own_turn(self):
        response = self.route(self.record, self.itso, [{"party": Party.KTTO}])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.active(self.record), {Party.ITSO, Party.KTTO})
        self.assertEqual(
            RoutingEvent.objects.filter(record=self.record, from_party=Party.ITSO).count(), 1,
        )

    def test_routing_to_an_office_that_holds_it_opens_no_second_assignment(self):
        self.route(self.record, self.itso, [{"party": Party.KTTO}])

        again = self.route(self.record, self.itso, [{"party": Party.KTTO}])
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST, again.data)

        self.ktto2 = make_user("route-ktto2@cit.edu", RoleName.KTTO)
        with_nominee = self.route(self.record, self.itso, [{"party": Party.KTTO, "nominee": self.ktto2.pk}])
        self.assertEqual(with_nominee.status_code, status.HTTP_200_OK, with_nominee.data)
        self.assertEqual(
            RecordAssignment.objects.filter(record=self.record, party=Party.KTTO).count(), 1,
        )
        self.assertTrue(
            ReviewerSeat.objects.filter(
                assignment__record=self.record, assignment__party=Party.KTTO,
                reviewer=self.ktto2, source=SeatSource.NOMINATED,
            ).exists()
        )

    def test_routing_to_an_office_that_already_cleared_keeps_its_clearance(self):
        # IERC reviewed earlier and cleared; its turn is over.
        ierc_turn = RecordAssignment.objects.create(
            record=self.record, party=Party.IERC, state=AssignmentState.COMPLETED,
        )
        RecordClearance.objects.create(
            record=self.record, office=Party.IERC, status=ClearanceStatus.CLEARED,
            reviewed_by=self.ierc,
        )

        response = self.route(self.record, self.itso, [{"party": Party.IERC}])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(Party.IERC, self.active(self.record))
        self.assertEqual(
            RecordClearance.objects.get(record=self.record, office=Party.IERC).status,
            ClearanceStatus.CLEARED,
        )
        ierc_turn.refresh_from_db()
        self.assertEqual(ierc_turn.state, AssignmentState.COMPLETED)

    def test_an_rdco_seat_holder_routes_to_an_office(self):
        RecordAssignment.objects.create(record=self.record, party=Party.RDCO)
        self.seat(self.record, Party.RDCO, self.rdco)

        response = self.route(self.record, self.rdco, [{"party": Party.KTTO}])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(Party.KTTO, self.active(self.record))


# --- refusals --------------------------------------------------------------------------

class RefusalTests(RoutingTestBase):

    def setUp(self):
        self.record = self.new_model()

    def test_a_user_without_a_seat_on_the_routing_party_is_refused(self):
        self.accepted_to(self.record, Party.ITSO)  # ITSO's pool: nobody seated
        response = self.route(self.record, self.itso, [{"party": Party.KTTO}])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_targets_outside_the_graph_are_refused(self):
        for target in (Party.ADVISER, Party.RDCO, Party.INTAKE, "nonsense"):
            with self.subTest(target=target):
                response = self.accept(self.record, [{"party": target}])
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

        self.accepted_to(self.record, Party.ITSO)
        self.seat(self.record, Party.ITSO, self.itso)
        own = self.route(self.record, self.itso, [{"party": Party.ITSO}])
        self.assertEqual(own.status_code, status.HTTP_400_BAD_REQUEST, own.data)

    def test_a_missing_reason_or_no_target_is_refused(self):
        self.assertEqual(self.accept(self.record, [{"party": Party.ITSO}], reason="  ").status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.accept(self.record, []).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.active(self.record), {Party.ADVISER})

    def test_routing_a_proposal_is_refused(self):
        proposal = self.new_model(RecordTypeName.PROPOSAL)
        response = self.accept(proposal, [{"party": Party.ITSO}])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(self.active(proposal), {Party.ADVISER})

    def test_who_is_asked_before_what(self):
        """Someone who could never route it is a 403, whatever the record's state."""
        proposal = self.new_model(RecordTypeName.PROPOSAL)
        self.assertEqual(
            self.route(proposal, self.itso, [{"party": Party.KTTO}]).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_a_record_not_in_review_is_refused(self):
        """IR-274: this was asked of a record still holding a fixed-pipeline status. Those statuses are gone; the refusal they exercised -- a record not in review -- is asked of a published record instead."""
        legacy = self.make_record(requested_itso=True)
        legacy.pipeline_status = PipelineStatus.PUBLISHED
        legacy.save(update_fields=["pipeline_status"])
        RecordAssignment.objects.create(record=legacy, party=Party.ITSO)
        self.seat(legacy, Party.ITSO, self.itso)

        response = self.route(legacy, self.itso, [{"party": Party.KTTO}])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertNotIn(Party.KTTO, self.active(legacy))


# --- what Paper View reads ------------------------------------------------------------

class RoutingOptionsTests(RoutingTestBase):

    def test_the_adviser_sees_three_offices_their_members_and_the_authors_hint(self):
        record = self.new_model(requested_itso=True)
        self.client.force_authenticate(self.adviser)

        data = self.client.get(options_url(record)).data

        self.assertEqual((data["from_party"], data["accept"]), (Party.ADVISER, True))
        by_party = {t["party"]: t for t in data["targets"]}
        self.assertEqual(set(by_party), {Party.ITSO, Party.IERC, Party.KTTO})
        self.assertEqual(
            {m["id"] for m in by_party[Party.ITSO]["members"]}, {self.itso.pk, self.itso2.pk},
        )
        self.assertIsNotNone(by_party[Party.ITSO]["author_hint"])
        self.assertIsNone(by_party[Party.IERC]["author_hint"])

    def test_someone_who_cannot_route_gets_no_picklist(self):
        record = self.new_model()
        self.client.force_authenticate(self.itso)
        self.assertEqual(self.client.get(options_url(record)).status_code, status.HTTP_403_FORBIDDEN)

    def test_record_detail_says_what_to_offer(self):
        record = self.new_model()
        detail = reverse("record-detail", args=[record.pk])

        self.client.force_authenticate(self.adviser)
        self.assertEqual(
            self.client.get(detail).data["routing"], {"accept_and_route": True, "route_as": None},
        )

        self.accepted_to(record, Party.ITSO)
        self.seat(record, Party.ITSO, self.itso)
        self.client.force_authenticate(self.adviser)
        self.assertFalse(self.client.get(detail).data["routing"]["accept_and_route"])
        self.client.force_authenticate(self.itso)
        self.assertEqual(self.client.get(detail).data["routing"]["route_as"], Party.ITSO)
