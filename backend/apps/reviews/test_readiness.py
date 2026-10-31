"""
Readiness on record detail (ADR-032 §10 Amendment, IR-679; built in IR-681).

Real workflow services and the record HTTP seam. Every scenario also checks
the contract's invariants: `ready` exactly when a Decision would be
accepted, and a blocker item for every refusal the decision block names.
"""

from apps.documents.models import DocumentRequest
from core.enums import Party
from core.permissions import may_read_review

from .test_decisions import COMMENT, DecisionTestBase


class ReadinessTests(DecisionTestBase):

    def readiness(self, record, as_user):
        payload = self.detail(record, as_user)
        readiness, decision = payload["readiness"], payload["decision"]
        if readiness is not None:
            self.assertEqual(
                readiness["verdict"] == "ready",
                bool(decision["outcomes"]) and decision["blocked"] is None,
            )
            if decision["outcomes"] and decision["blocked"]:
                self.assertTrue(any(i["severity"] == "blocker" for i in readiness["items"]))
            self.assertTrue(readiness["headline"])
            for item in readiness["items"]:
                self.assertTrue(item["label"])
                if item["kind"] != "due_date":
                    self.assertIsNone(item["paused"])
        return readiness

    def kinds(self, readiness, severity=None):
        return [i["kind"] for i in readiness["items"] if severity in (None, i["severity"])]

    def test_an_opened_adviser_is_ready_and_the_decision_is_accepted(self):
        record = self.at_adviser()
        readiness = self.readiness(record, self.adviser)
        self.assertEqual(readiness["verdict"], "ready")
        self.assertEqual(self.kinds(readiness, "blocker"), [])
        self.decided(record, self.adviser, "publish", COMMENT)

    def test_an_unopened_seat_is_a_blocker_that_offers_open_review(self):
        record = self.new_model()
        seat = self.adviser_seat(record, opened=False)
        readiness = self.readiness(record, self.adviser)
        self.assertEqual(readiness["verdict"], "blocked")
        item = readiness["items"][0]
        self.assertEqual((item["kind"], item["severity"]), ("open_review", "blocker"))
        self.assertEqual(item["action"], {"kind": "open_review", "target": str(seat.pk)})

    def test_a_revision_request_blocks_rdco_and_only_its_own_office(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = self.asked(record, self.ierc)

        mine = self.readiness(record, self.ierc)
        self.assertEqual(mine["verdict"], "blocked")
        item = next(i for i in mine["items"] if i["kind"] == "revision_request")
        self.assertEqual(item["severity"], "blocker")
        self.assertEqual(item["action"], {"kind": "withdraw_revision", "target": str(request.pk)})
        self.assertEqual(item["actor_name"], self.ierc.get_full_name())
        self.assertIsNotNone(item["since"])

        other = self.readiness(record, self.itso)
        self.assertEqual(other["verdict"], "waiting_on_you")
        item = next(i for i in other["items"] if i["kind"] == "revision_request")
        self.assertEqual((item["severity"], item["action"]), ("info", None))
        self.assertIn("party_reviewing", self.kinds(other, "info"))

    def test_a_blocked_rdco_decision_names_every_refusal(self):
        record = self.at_rdco()
        self.assertEqual(self.ask(record, self.rdco).status_code, 200)
        readiness = self.readiness(record, self.rdco)
        self.assertEqual(readiness["verdict"], "blocked")
        self.assertIn("revision_request", self.kinds(readiness, "blocker"))

    def test_an_office_own_document_request_blocks_it_and_informs_the_others(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = DocumentRequest.objects.create(
            record=record, party=Party.IERC, assignment=self.assignment(record, Party.IERC),
            requested_by=self.ierc, message="Signed consent forms, please.",
        )
        mine = self.readiness(record, self.ierc)
        self.assertEqual(mine["verdict"], "blocked")
        item = next(i for i in mine["items"] if i["kind"] == "document_request")
        self.assertEqual(item["severity"], "blocker")
        self.assertEqual(item["action"], {"kind": "open_documents", "target": str(request.pk)})
        other = self.readiness(record, self.itso)
        self.assertEqual(other["verdict"], "waiting_on_you")
        self.assertIn("document_request", self.kinds(other, "info"))

    def test_an_unclaimed_pool_is_information_with_claim_for_its_members(self):
        record = self.routed(Party.ITSO)
        assignment = self.assignment(record, Party.ITSO)
        pool = self.readiness(record, self.itso)
        self.assertEqual(pool["verdict"], "waiting_on_you")
        item = next(i for i in pool["items"] if i["kind"] == "pool_unclaimed")
        self.assertEqual(item["severity"], "info")
        self.assertEqual(item["action"], {"kind": "claim", "target": str(assignment.pk)})

    def test_not_disclosed_to_a_viewer_who_may_not_read_the_review(self):
        record = self.routed(Party.ITSO)
        for viewer in (self.ktto, self.ierc, self.owner, self.itso):
            with self.subTest(viewer=viewer.email):
                readable = may_read_review(viewer, record)
                readiness = self.readiness(record, viewer)
                self.assertEqual(readiness is None, not readable)
        self.assertIsNone(self.readiness(record, self.ktto))
