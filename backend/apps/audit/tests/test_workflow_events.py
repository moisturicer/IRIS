"""
Workflow audit events (IR-144, ADR-011).

The evaluation's turnaround and preserved-clearance metrics have no other
source, and an event missed in the pilot cannot be reconstructed. One class
per acceptance criterion. Every event is read back through `GET /audit/`, the
export the evaluation uses, never from the table directly.

Records reach the workflow through the same REST seam and helpers as
`apps/reviews/test_*.py`, so these tests drive the real services.
"""

import json
from unittest.mock import patch

from django.db import connection, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from apps.documents.testing import real_pdf_bytes
from apps.documents.models import DocumentRequest, DocumentRequestItem, UploadSlot
from apps.records.models import Record
from apps.reviews.models import RecordAssignment, ResubmissionRequest, ReviewerSeat
from apps.reviews.test_decisions import DecisionTestBase
from apps.reviews.test_new_version import RESTART_ALL, NewVersionTestBase, _pdf
from core.enums import (
    AssignmentState,
    Party,
    PipelineStatus,
    RecordTypeName,
)

AUDIT = "/api/v1/audit/"
SUBMIT_DOCUMENT = "/api/v1/documents/submit/"

#: Every type IR-144 adds. Other audit rows (an upload, a record access) are
#: written beside them and are not what these tests are about.
WORKFLOW_TYPES = frozenset({
    AuditEvent.SUBMITTED, AuditEvent.ROUTED, AuditEvent.ASSIGNMENT_CLOSED,
    AuditEvent.DECISION_RECORDED, AuditEvent.PUBLISHED, AuditEvent.RESUBMISSION_REQUESTED,
    AuditEvent.REVISION_REQUEST_WITHDRAWN, AuditEvent.RESUBMITTED,
    AuditEvent.CLEARANCE_PRESERVED, AuditEvent.SEAT_CLAIMED, AuditEvent.SEAT_ASSIGNED,
    AuditEvent.SEAT_NOMINATED, AuditEvent.SEAT_REASSIGNED, AuditEvent.SEAT_WITHDRAWN,
    AuditEvent.REVIEWER_ADDED, AuditEvent.SEAT_OPENED, AuditEvent.RECORD_WITHDRAWN,
    AuditEvent.DOCUMENT_REQUESTED, AuditEvent.DOCUMENT_REQUEST_FULFILLED,
    AuditEvent.DOCUMENT_REQUEST_ACCEPTED, AuditEvent.DOCUMENT_REQUEST_REJECTED,
    AuditEvent.DOCUMENT_REQUEST_WITHDRAWN,
})
DOCUMENT_TYPES = frozenset(t for t in WORKFLOW_TYPES if t.startswith("DOCUMENT_REQUEST"))
REVISION_TYPES = frozenset({
    AuditEvent.RESUBMISSION_REQUESTED, AuditEvent.REVISION_REQUEST_WITHDRAWN,
    AuditEvent.RESUBMITTED, AuditEvent.CLEARANCE_PRESERVED,
})

FINDING = "Consent forms do not cover minors."
REJECTION = "The study duplicates a thesis already published in 2023."


def _fail_insert(*args, **kwargs):
    """A real database error: on PostgreSQL it aborts the open transaction."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1/0")


class AuditTestBase(NewVersionTestBase, DecisionTestBase):

    # --- reading the log, as the evaluation will -------------------------------

    def events(self, record, *types):
        """`record`'s workflow events through `GET /audit/`, oldest first."""
        self.client.force_authenticate(self.rdco)
        response = self.client.get(AUDIT, {"record": record.pk, "page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = sorted(response.data["results"], key=lambda row: row["id"])
        wanted = set(types) or WORKFLOW_TYPES
        return [row for row in rows if row["event_type"] in wanted]

    def one(self, record, event_type):
        rows = self.events(record, event_type)
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def types(self, record):
        return [row["event_type"] for row in self.events(record)]

    # --- driving the workflow ---------------------------------------------------

    def ok(self, response, code=None):
        expected = (code,) if code else (status.HTTP_200_OK, status.HTTP_201_CREATED)
        self.assertIn(response.status_code, expected, getattr(response, "data", response))
        return response

    def open_seat(self, seat, user):
        return self.ok(self.post(reverse("seat-open", args=[seat.pk]), user, {}))

    def claim(self, record, party, user):
        assignment = self.assignment(record, party)
        response = self.ok(self.post(reverse("assignment-claim", args=[assignment.pk]), user, {}))
        return ReviewerSeat.objects.get(pk=response.data["id"])

    def claimed_and_opened(self, record, party, user):
        seat = self.claim(record, party, user)
        self.open_seat(seat, user)
        return seat

    def ask_for_documents(self, record, user, items, message="Please send these."):
        self.client.force_authenticate(user)
        response = self.client.post(
            reverse("record-document-requests", args=[record.pk]),
            {"message": message, "items": items}, format="json",
        )
        return self.ok(response, status.HTTP_201_CREATED).data

    def upload(self, record, **target):
        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                SUBMIT_DOCUMENT,
                {"record": record.pk, "file": _pdf(real_pdf_bytes(b"requested"), "form.pdf"), **target},
                format="multipart",
            )
        return self.ok(response, status.HTTP_201_CREATED)

    def item_decision(self, item_id, user, body):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"/api/v1/document-request-items/{item_id}/", body, format="json",
            )
        return self.ok(response, status.HTTP_200_OK)

    def withdraw_documents(self, request_id, user):
        self.client.force_authenticate(user)
        response = self.client.patch(
            f"/api/v1/document-requests/{request_id}/", {"action": "withdraw"}, format="json",
        )
        return self.ok(response, status.HTTP_200_OK)

    def submit_via_api(self, record):
        response = self.post(reverse("record-submit", args=[record.pk]), self.owner,
                             {"dpa_accepted": True})
        return self.ok(response, status.HTTP_200_OK)

    def ethics_slot(self, record):
        return UploadSlot.objects.get_or_create(
            name="Ethics Clearance", record_type=record.record_type, record=None,
        )[0]


# --- AC: every type is emitted from the write it describes ------------------------------

class EntryAndRoutingTests(AuditTestBase):

    def test_submitting_writes_submitted_naming_the_adviser_and_version_one(self):
        record = self.make_record()

        self.submit_via_api(record)

        row = self.one(record, AuditEvent.SUBMITTED)
        self.assertEqual(row["user"], self.owner.pk)
        self.assertEqual(row["metadata"], {"to_party": Party.ADVISER, "version": 1})

    def test_accept_and_route_records_the_verdict_closes_the_adviser_and_routes(self):
        record = self.new_model()
        self.adviser_seat(record)

        self.accepted_to(record, Party.ITSO, Party.IERC)

        self.assertEqual(
            self.types(record)[1:],  # after SUBMITTED
            ["DECISION_RECORDED", "ASSIGNMENT_CLOSED", "ROUTED", "ROUTED"],
        )
        decision = self.one(record, AuditEvent.DECISION_RECORDED)
        self.assertEqual(decision["user"], self.adviser.pk)
        self.assertEqual(
            {k: decision["metadata"][k] for k in ("party", "outcome", "final", "version")},
            {"party": Party.ADVISER, "outcome": "accepted_and_routed", "final": False, "version": 1},
        )
        closed = self.one(record, AuditEvent.ASSIGNMENT_CLOSED)["metadata"]
        self.assertEqual((closed["party"], closed["how"]), (Party.ADVISER, "completed"))
        routed = [row["metadata"] for row in self.events(record, AuditEvent.ROUTED)]
        self.assertEqual(
            sorted((m["from_party"], m["to_party"], m["opened"], m["hand_back"]) for m in routed),
            [(Party.ADVISER, Party.IERC, True, False), (Party.ADVISER, Party.ITSO, True, False)],
        )
        self.assertEqual(len({m["group"] for m in routed}), 1, "one movement, one group")

    def test_a_nominee_is_named_on_the_route_and_seated_as_nominated(self):
        record = self.new_model()
        self.adviser_seat(record)

        self.ok(self.accept(record, [{"party": Party.ITSO, "nominee": self.itso.pk}]))

        self.assertEqual(self.one(record, AuditEvent.ROUTED)["metadata"]["nominee"], self.itso.pk)
        nominated = self.one(record, AuditEvent.SEAT_NOMINATED)
        self.assertEqual(nominated["user"], self.adviser.pk)
        self.assertEqual(
            (nominated["metadata"]["party"], nominated["metadata"]["reviewer"]),
            (Party.ITSO, self.itso.pk),
        )

    def test_routing_to_a_party_already_holding_the_record_starts_no_clock(self):
        record = self.routed(Party.ITSO)
        self.claimed_and_opened(record, Party.ITSO, self.itso)
        self.ok(self.route(record, self.itso, [{"party": Party.IERC}]))

        self.ok(self.route(record, self.itso, [{"party": Party.IERC, "nominee": self.ierc.pk}]))

        to_ierc = [
            row["metadata"]["opened"] for row in self.events(record, AuditEvent.ROUTED)
            if row["metadata"]["to_party"] == Party.IERC
        ]
        self.assertEqual(to_ierc, [True, False])

    def test_the_hand_back_to_rdco_is_a_routing_movement_nobody_made(self):
        record = self.routed(Party.ITSO)
        self.claimed_and_opened(record, Party.ITSO, self.itso)

        self.cleared(record, self.itso)

        hand_back = self.events(record, AuditEvent.ROUTED)[-1]
        self.assertIsNone(hand_back["user"])
        self.assertEqual(
            {k: hand_back["metadata"][k] for k in ("from_party", "to_party", "opened", "hand_back")},
            {"from_party": Party.ITSO, "to_party": Party.RDCO, "opened": True, "hand_back": True},
        )


class OfficeVerdictTests(AuditTestBase):

    def test_a_clearance_is_recorded_and_the_office_closes(self):
        record = self.routed(Party.ITSO)
        self.claimed_and_opened(record, Party.ITSO, self.itso)

        self.cleared(record, self.itso, "No patent concerns.")

        verdict = self.events(record, AuditEvent.DECISION_RECORDED)[-1]
        self.assertEqual(verdict["user"], self.itso.pk)
        self.assertEqual(
            (verdict["metadata"]["party"], verdict["metadata"]["outcome"], verdict["metadata"]["final"]),
            (Party.ITSO, "cleared", False),
        )
        closed = self.events(record, AuditEvent.ASSIGNMENT_CLOSED)[-1]["metadata"]
        self.assertEqual((closed["party"], closed["how"]), (Party.ITSO, "completed"))

    def test_a_finding_records_its_outcome_and_never_its_text(self):
        record = self.routed(Party.ITSO)
        self.claimed_and_opened(record, Party.ITSO, self.itso)

        self.found(record, self.itso, FINDING)

        verdict = self.events(record, AuditEvent.DECISION_RECORDED)[-1]
        self.assertEqual(verdict["metadata"]["outcome"], "finding")
        for row in self.events(record):
            self.assertNotIn(FINDING, json.dumps(row["metadata"]))


class DecisionTests(AuditTestBase):
    """AC: `DECISION_RECORDED` for every decision; `PUBLISHED` only when it goes public."""

    def final(self, record):
        return self.events(record, AuditEvent.DECISION_RECORDED)[-1]

    def test_publish_writes_the_decision_and_published(self):
        record = self.at_adviser()

        self.decided(record, self.adviser, "publish")

        self.assertEqual(
            {k: self.final(record)["metadata"][k] for k in ("party", "outcome", "final", "version")},
            {"party": Party.ADVISER, "outcome": "publish", "final": True, "version": 1},
        )
        published = self.one(record, AuditEvent.PUBLISHED)
        self.assertEqual(published["user"], self.adviser.pk)
        self.assertEqual(published["metadata"], {"party": Party.ADVISER, "version": 1})

    def test_keep_unlisted_writes_the_decision_only(self):
        record = self.at_rdco()

        self.decided(record, self.rdco, "keep_unlisted")

        self.assertEqual(self.final(record)["metadata"]["outcome"], "keep_unlisted")
        self.assertEqual(self.events(record, AuditEvent.PUBLISHED), [])

    def test_reject_writes_the_decision_only_and_never_the_reason(self):
        record = self.at_adviser()

        self.decided(record, self.adviser, "reject", REJECTION)

        self.assertEqual(self.final(record)["metadata"]["outcome"], "reject")
        self.assertEqual(self.events(record, AuditEvent.PUBLISHED), [])
        for row in self.events(record):
            self.assertNotIn(REJECTION, json.dumps(row["metadata"]))

    def test_accepting_a_proposal_writes_the_decision_only(self):
        record = self.at_adviser(RecordTypeName.PROPOSAL)

        self.decided(record, self.adviser, "accept")

        self.assertEqual(self.final(record)["metadata"]["outcome"], "accept")
        self.assertEqual(self.events(record, AuditEvent.PUBLISHED), [])

    def test_a_decision_closes_the_other_turns_and_withdraws_open_document_requests(self):
        record = self.at_rdco()
        self.ok(self.route(record, self.rdco, [{"party": Party.KTTO}]))
        asked = self.ask_for_documents(record, self.rdco, [{"label": "Signed licence"}])

        self.decided(record, self.rdco, "publish")

        review = self.final(record)["metadata"]["review"]
        closed = {
            row["metadata"]["party"]: row["metadata"]
            for row in self.events(record, AuditEvent.ASSIGNMENT_CLOSED)
            if row["metadata"]["decision"] == review
        }
        self.assertEqual(
            {party: m["how"] for party, m in closed.items()},
            {Party.RDCO: "completed", Party.KTTO: "closed_by_decision"},
        )
        withdrawn = self.one(record, AuditEvent.DOCUMENT_REQUEST_WITHDRAWN)["metadata"]
        self.assertEqual(
            (withdrawn["request"], withdrawn["party"], withdrawn["closed_by"], withdrawn["closed_by_decision"]),
            (asked["id"], Party.RDCO, "decision", True),
        )


class RevisionTests(AuditTestBase):

    def test_a_revision_request_carries_its_party_and_reason(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)

        request = self.asked(record, self.ierc, "Add the assent form.")

        row = self.one(record, AuditEvent.RESUBMISSION_REQUESTED)
        self.assertEqual(row["user"], self.ierc.pk)
        self.assertEqual(
            row["metadata"],
            {"party": Party.IERC, "request": request.pk, "reason": "Add the assent form.", "version": 1},
        )

    def test_withdrawing_it_is_recorded(self):
        record = self.routed(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = self.asked(record, self.ierc)

        self.ok(self.withdraw(record, self.ierc, request.pk))

        row = self.one(record, AuditEvent.REVISION_REQUEST_WITHDRAWN)
        self.assertEqual(
            row["metadata"],
            {"party": Party.IERC, "request": request.pk, "closed_by": "requesting_party"},
        )


class ResubmissionTests(AuditTestBase):
    """AC: `RESUBMITTED` carries the policy and parties; one `CLEARANCE_PRESERVED` per kept office."""

    def test_clearance_aware_keeps_itso_and_resets_ierc(self):
        record = self.itso_cleared_and_ierc_asked()
        request = ResubmissionRequest.objects.get(record=record)
        self.edit_title(record)

        self.submitted(record)

        row = self.one(record, AuditEvent.RESUBMITTED)
        self.assertEqual(row["user"], self.owner.pk)
        self.assertEqual(row["metadata"], {
            "version": 2,
            "policy": "clearance_aware",
            "requests": [request.pk],
            "rereview_parties": [Party.IERC],
            "reset_parties": [Party.IERC],
            "preserved_parties": [Party.ITSO],
        })
        preserved = self.events(record, AuditEvent.CLEARANCE_PRESERVED)
        self.assertEqual(
            [row["metadata"] for row in preserved],
            [{"party": Party.ITSO, "version": 2, "policy": "clearance_aware"}],
        )

    @override_settings(WORKFLOW_TABLE=RESTART_ALL)
    def test_restart_all_preserves_nothing_and_names_its_policy(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)

        self.submitted(record)

        metadata = self.one(record, AuditEvent.RESUBMITTED)["metadata"]
        self.assertEqual(metadata["policy"], "restart_all")
        self.assertEqual(metadata["reset_parties"], [Party.IERC, Party.ITSO])
        # ITSO had cleared, so it reviews again (ADR-032 §5, IR-632 amendment).
        self.assertEqual(metadata["rereview_parties"], [Party.ITSO, Party.IERC])
        self.assertEqual(metadata["preserved_parties"], [])
        self.assertEqual(self.events(record, AuditEvent.CLEARANCE_PRESERVED), [])


class SeatTests(AuditTestBase):

    def test_claim_assign_reassign_withdraw_and_add_are_each_recorded(self):
        record = self.routed(Party.ITSO)
        assignment = self.assignment(record, Party.ITSO)
        coordinator = self.itso_coordinator

        claimed = self.claim(record, Party.ITSO, self.itso)
        assigned = self.ok(self.post(
            reverse("assignment-assign", args=[assignment.pk]), coordinator,
            {"reviewer": self.itso2.pk},
        )).data
        reassigned = self.ok(self.post(
            reverse("seat-reassign", args=[assigned["id"]]), coordinator,
            {"reviewer": coordinator.pk, "reason": "Workload"},
        )).data
        self.ok(self.post(reverse("seat-withdraw", args=[reassigned["id"]]), coordinator, {}))
        added = self.ok(self.post(
            reverse("assignment-add-reviewer", args=[assignment.pk]), self.itso,
            {"reviewer": self.itso2.pk},
        )).data

        seat_rows = [
            row for row in self.events(record)
            if row["event_type"].startswith("SEAT_") or row["event_type"] == "REVIEWER_ADDED"
        ]
        self.assertEqual(
            [(row["event_type"], row["user"], row["metadata"]["seat"], row["metadata"]["reviewer"])
             for row in seat_rows],
            [
                ("SEAT_CLAIMED", self.itso.pk, claimed.pk, self.itso.pk),
                ("SEAT_ASSIGNED", coordinator.pk, assigned["id"], self.itso2.pk),
                ("SEAT_REASSIGNED", coordinator.pk, reassigned["id"], coordinator.pk),
                ("SEAT_WITHDRAWN", coordinator.pk, reassigned["id"], coordinator.pk),
                ("REVIEWER_ADDED", self.itso.pk, added["id"], self.itso2.pk),
            ],
        )
        self.assertEqual(
            (seat_rows[2]["metadata"]["previous_seat"], seat_rows[2]["metadata"]["previous_reviewer"],
             seat_rows[2]["metadata"]["reason"]),
            (assigned["id"], self.itso2.pk, "Workload"),
        )
        self.assertTrue(all(row["metadata"]["party"] == Party.ITSO for row in seat_rows))

    def test_only_the_first_open_is_recorded(self):
        record = self.routed(Party.ITSO)
        seat = self.claim(record, Party.ITSO, self.itso)

        self.open_seat(seat, self.itso)
        self.open_seat(seat, self.itso)

        row = self.one(record, AuditEvent.SEAT_OPENED)
        self.assertEqual(
            (row["user"], row["metadata"]["seat"], row["metadata"]["party"]),
            (self.itso.pk, seat.pk, Party.ITSO),
        )


class RecordWithdrawnTests(AuditTestBase):

    def test_deleting_a_record_in_review_records_what_it_withdrew(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.claimed_and_opened(record, Party.IERC, self.ierc)
        asked = self.ask_for_documents(record, self.ierc, [{"label": "Consent form"}])
        revision = self.asked(record, self.ierc)

        self.client.force_authenticate(self.owner)
        self.ok(self.client.delete(reverse("record-detail", args=[record.pk])),
                status.HTTP_204_NO_CONTENT)

        withdrawn = self.one(record, AuditEvent.RECORD_WITHDRAWN)
        self.assertEqual(withdrawn["user"], self.owner.pk)
        self.assertEqual(
            withdrawn["metadata"],
            {"version": 1, "closed_parties": [Party.IERC, Party.ITSO]},
        )
        closed = {
            row["metadata"]["party"]: row["metadata"]["how"]
            for row in self.events(record, AuditEvent.ASSIGNMENT_CLOSED)
            if row["metadata"]["party"] != Party.ADVISER
        }
        self.assertEqual(closed, {Party.ITSO: "withdrawn", Party.IERC: "withdrawn"})
        self.assertEqual(
            self.one(record, AuditEvent.REVISION_REQUEST_WITHDRAWN)["metadata"],
            {"party": Party.IERC, "request": revision.pk, "closed_by": "record_withdrawn"},
        )
        documents = self.one(record, AuditEvent.DOCUMENT_REQUEST_WITHDRAWN)["metadata"]
        self.assertEqual(
            (documents["request"], documents["closed_by"], documents["closed_by_decision"]),
            (asked["id"], "record_withdrawn", False),
        )

    def test_deleting_a_draft_writes_no_withdrawal(self):
        record = self.make_record()

        self.client.force_authenticate(self.owner)
        self.ok(self.client.delete(reverse("record-detail", args=[record.pk])),
                status.HTTP_204_NO_CONTENT)

        self.assertEqual(self.events(record), [])


class DocumentRequestTests(AuditTestBase):
    """AC: party, request id and item ids/labels on each; the rejection carries its reason."""

    def test_the_whole_document_request_lifecycle_is_recorded(self):
        record = self.routed(Party.IERC)
        ethics = self.ethics_slot(record)
        asked = self.ask_for_documents(
            record, self.ierc, [{"label": "Consent form"}, {"slot": ethics.pk}],
            message="The consent forms are missing.",
        )
        consent, ethics_item = asked["items"]
        items = [
            {"id": consent["id"], "label": "Consent form"},
            {"id": ethics_item["id"], "label": "Ethics Clearance"},
        ]

        requested = self.one(record, AuditEvent.DOCUMENT_REQUESTED)
        self.assertEqual(requested["user"], self.ierc.pk)
        self.assertEqual(requested["metadata"], {
            "party": Party.IERC, "request": asked["id"], "items": items,
            "message": "The consent forms are missing.",
        })

        # One answered through `request_item`, the other by an ordinary slot
        # upload (IR-346): fulfilled once, when the last one arrives.
        self.upload(record, request_item=consent["id"])
        self.assertEqual(self.events(record, AuditEvent.DOCUMENT_REQUEST_FULFILLED), [])
        self.upload(record, slot=ethics.pk)
        fulfilled = self.one(record, AuditEvent.DOCUMENT_REQUEST_FULFILLED)
        self.assertEqual(fulfilled["user"], self.owner.pk)
        self.assertEqual(
            fulfilled["metadata"], {"party": Party.IERC, "request": asked["id"], "items": items},
        )

        self.item_decision(consent["id"], self.ierc, {"action": "accept"})
        self.assertEqual(
            self.one(record, AuditEvent.DOCUMENT_REQUEST_ACCEPTED)["metadata"],
            {"party": Party.IERC, "request": asked["id"], "items": [items[0]]},
        )

        self.item_decision(ethics_item["id"], self.ierc, {"action": "reject", "reason": "Unsigned."})
        rejected = self.one(record, AuditEvent.DOCUMENT_REQUEST_REJECTED)
        self.assertEqual(rejected["user"], self.ierc.pk)
        self.assertEqual(rejected["metadata"], {
            "party": Party.IERC, "request": asked["id"], "items": [items[1]], "reason": "Unsigned.",
        })

        self.withdraw_documents(asked["id"], self.ierc)
        self.assertEqual(
            self.one(record, AuditEvent.DOCUMENT_REQUEST_WITHDRAWN)["metadata"],
            {
                "party": Party.IERC, "request": asked["id"], "items": items,
                "closed_by": "requesting_party", "closed_by_decision": False,
            },
        )


    def test_a_request_item_upload_that_answers_the_last_item_fulfils_the_request(self):
        record = self.routed(Party.IERC)
        asked = self.ask_for_documents(record, self.ierc, [{"label": "Consent form"}])
        [item] = asked["items"]

        self.upload(record, request_item=item["id"])

        self.assertEqual(
            self.one(record, AuditEvent.DOCUMENT_REQUEST_FULFILLED)["metadata"],
            {
                "party": Party.IERC, "request": asked["id"],
                "items": [{"id": item["id"], "label": "Consent form"}],
            },
        )


# --- AC: kept apart (ADR-022) -------------------------------------------------------------

class KeptApartTests(AuditTestBase):

    def test_a_document_request_writes_no_revision_event(self):
        record = self.routed(Party.IERC)
        asked = self.ask_for_documents(record, self.ierc, [{"label": "Consent form"}])
        self.upload(record, request_item=asked["items"][0]["id"])

        self.assertTrue(self.events(record, *DOCUMENT_TYPES))
        self.assertEqual(self.events(record, *REVISION_TYPES), [])

    def test_a_revision_and_its_new_version_write_no_document_event(self):
        record = self.itso_cleared_and_ierc_asked()
        self.edit_title(record)
        self.submitted(record)

        self.assertTrue(self.events(record, *REVISION_TYPES))
        self.assertEqual(self.events(record, *DOCUMENT_TYPES), [])


# --- AC: inside the transaction -----------------------------------------------------------

class TransactionTests(AuditTestBase):

    def test_a_rolled_back_decision_leaves_no_event(self):
        record = self.at_adviser()
        before = self.types(record)

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaisesRegex(RuntimeError, "outer rollback"):
                with transaction.atomic():
                    self.decided(record, self.adviser, "publish")
                    self.assertIn("PUBLISHED", self.types(record))
                    raise RuntimeError("outer rollback")

        self.assertEqual(self.types(record), before)

    def test_a_rolled_back_route_leaves_no_event(self):
        record = self.new_model()
        self.adviser_seat(record)
        before = self.types(record)

        with self.assertRaisesRegex(RuntimeError, "outer rollback"):
            with transaction.atomic():
                self.accepted_to(record, Party.ITSO)
                raise RuntimeError("outer rollback")

        self.assertEqual(self.types(record), before)

    def test_a_refused_act_writes_nothing(self):
        record = self.new_model()
        self.adviser_seat(record)
        before = self.types(record)

        refused = self.accept(record, [{"party": Party.ITSO}], reason="")
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        not_the_decider = self.decide(record, self.itso, "publish")
        self.assertIn(
            not_the_decider.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

        self.assertEqual(self.types(record), before)


# --- AC: an audit failure never breaks the workflow action ----------------------------------

class AuditFailureTests(AuditTestBase):

    def test_the_savepoint_keeps_the_surrounding_transaction_usable(self):
        record = self.make_record()
        with self.assertLogs("apps.audit.services", level="ERROR") as logs:
            with transaction.atomic():
                with patch.object(AuditEvent, "save", _fail_insert):
                    create_audit_event(AuditEvent.SUBMITTED, self.owner, record=record)
                # Without the savepoint PostgreSQL refuses every statement from here.
                self.assertTrue(Record.objects.filter(pk=record.pk).exists())
        self.assertIn(f"SUBMITTED for record {record.pk}", logs.output[0])

    def test_a_workflow_transition_succeeds_when_its_events_cannot_be_written(self):
        record = self.new_model()
        self.adviser_seat(record)
        before = AuditEvent.objects.filter(record=record).count()

        with patch.object(AuditEvent, "save", _fail_insert):
            with self.assertLogs("apps.audit.services", level="ERROR") as logs:
                response = self.accept(record, [{"party": Party.ITSO}])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            RecordAssignment.objects.get(record=record, party=Party.ITSO).state,
            AssignmentState.ACTIVE,
        )
        self.assertEqual(
            RecordAssignment.objects.get(record=record, party=Party.ADVISER).state,
            AssignmentState.COMPLETED,
        )
        self.assertEqual(AuditEvent.objects.filter(record=record).count(), before)
        self.assertTrue(any(
            "DECISION_RECORDED" in line and f"record {record.pk}" in line and "ERROR" in line
            for line in logs.output
        ), logs.output)

    def test_a_document_request_succeeds_when_its_event_cannot_be_written(self):
        record = self.routed(Party.IERC)
        before = AuditEvent.objects.filter(record=record).count()

        with patch.object(AuditEvent, "save", _fail_insert):
            with self.assertLogs("apps.audit.services", level="ERROR") as logs:
                asked = self.ask_for_documents(record, self.ierc, [{"label": "Consent form"}])

        self.assertTrue(DocumentRequest.objects.filter(pk=asked["id"]).exists())
        self.assertEqual(DocumentRequestItem.objects.filter(request_id=asked["id"]).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(record=record).count(), before)
        self.assertTrue(any(
            "DOCUMENT_REQUESTED" in line and f"record {record.pk}" in line for line in logs.output
        ), logs.output)


# --- AC: turnaround and the preserved-clearance count from GET /audit/ alone -----------------

class MetricsFromTheExportTests(AuditTestBase):
    """
    One Thesis through its whole life, then ADR-011's metrics computed from the
    `GET /audit/` rows and nothing else, as `docs/evaluation/AUDIT_EXPORT.md`
    describes. The workflow tables are read only afterwards, to check them.
    """

    def clocks(self, rows):
        """
        Per-party turnaround as AUDIT_EXPORT.md writes it: a clock starts when a
        party is handed work and stops when its assignment closes. Returns
        `(party, duration)` in the order the clocks stopped.
        """
        started, clocks = {}, []
        for row in rows:
            at, m = parse_datetime(row["created_at"]), row["metadata"]
            if row["event_type"] == AuditEvent.SUBMITTED:
                started[m["to_party"]] = at
            elif row["event_type"] == AuditEvent.ROUTED and m["opened"]:
                started[m["to_party"]] = at
            elif row["event_type"] == AuditEvent.RESUBMITTED:
                for party in m["rereview_parties"]:
                    started.setdefault(party, at)
            elif row["event_type"] == AuditEvent.ASSIGNMENT_CLOSED:
                clocks.append((m["party"], at - started.pop(m["party"])))
        self.assertEqual(started, {}, "every clock that started stopped")
        return clocks

    @override_settings(WORKFLOW_TABLE=RESTART_ALL)
    def test_a_reopened_office_gets_a_second_clock_under_restart_all(self):
        # IR-632: ITSO cleared, IERC asked; the new version reopens ITSO, whose
        # second turn is timed from RESUBMITTED to its second close.
        record = self.make_record(abstract_file=_pdf(b"%PDF-1.7 v1"))
        self.submit_via_api(record)
        adviser_seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.adviser)
        self.open_seat(adviser_seat, self.adviser)
        self.accepted_to(record, Party.ITSO, Party.IERC)
        self.claimed_and_opened(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.claimed_and_opened(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.edit_title(record)
        self.submitted(record)
        self.cleared(record, self.itso)
        self.cleared(record, self.ierc)
        self.claimed_and_opened(record, Party.RDCO, self.rdco)
        self.decided(record, self.rdco, "publish")
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)

        clocks = self.clocks(self.events(record))
        itso = [duration for party, duration in clocks if party == Party.ITSO]
        self.assertEqual(len(itso), 2, "ITSO's first turn and its reopened one")
        ierc = [duration for party, duration in clocks if party == Party.IERC]
        self.assertEqual(len(ierc), 1, "IERC asked, so its one clock kept running")

        # The second clock runs from the new version to ITSO's second close.
        resubmitted_at = parse_datetime(self.one(record, AuditEvent.RESUBMITTED)["created_at"])
        assignment = RecordAssignment.objects.get(record=record, party=Party.ITSO)
        self.assertLess(
            abs((resubmitted_at + itso[1] - assignment.closed_at).total_seconds()), 1.0,
        )

    def test_turnaround_and_preserved_clearances_are_computable_from_the_rows(self):
        record = self.make_record(abstract_file=_pdf(b"%PDF-1.7 v1"))
        self.submit_via_api(record)
        adviser_seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.adviser)
        self.open_seat(adviser_seat, self.adviser)
        self.accepted_to(record, Party.ITSO, Party.IERC)
        self.claimed_and_opened(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)
        self.claimed_and_opened(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.edit_title(record)
        self.submitted(record)
        self.cleared(record, self.ierc)
        self.claimed_and_opened(record, Party.RDCO, self.rdco)
        self.decided(record, self.rdco, "publish")
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)

        clocks = self.clocks(self.events(record))
        turnaround = dict(clocks)
        self.assertEqual(len(clocks), len(turnaround), "one clock per party")
        self.assertEqual(set(turnaround), {Party.ADVISER, Party.ITSO, Party.IERC, Party.RDCO})

        # The author's share of IERC's clock: from its request to the new version.
        asked_at = parse_datetime(self.one(record, AuditEvent.RESUBMISSION_REQUESTED)["created_at"])
        resubmitted_at = parse_datetime(self.one(record, AuditEvent.RESUBMITTED)["created_at"])
        self.assertLess(resubmitted_at - asked_at, turnaround[Party.IERC])

        # Total turnaround: submission to the final decision.
        total = (
            parse_datetime(self.one(record, AuditEvent.PUBLISHED)["created_at"])
            - parse_datetime(self.one(record, AuditEvent.SUBMITTED)["created_at"])
        )
        self.assertTrue(all(t <= total for t in turnaround.values()))

        # The preserved-clearance count: one row per office kept.
        preserved = [row["metadata"]["party"] for row in self.events(record, AuditEvent.CLEARANCE_PRESERVED)]
        self.assertEqual(preserved, [Party.ITSO])

        # Checked against the workflow tables: each clock matches its assignment.
        for party, duration in turnaround.items():
            assignment = RecordAssignment.objects.get(record=record, party=party)
            recorded = assignment.closed_at - assignment.opened_at
            self.assertLess(abs((duration - recorded).total_seconds()), 1.0, party)
