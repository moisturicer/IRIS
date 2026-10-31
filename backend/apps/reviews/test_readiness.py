"""
Readiness on record detail (ADR-032 §10 Amendment, IR-679; built in IR-681).

Real workflow services and the record HTTP seam. Every scenario also checks
the contract's invariants: `ready` exactly when a Decision would be
accepted, and a blocker item for every refusal the decision block names.
"""

from django.urls import reverse

from apps.documents.models import DocumentRequest
from apps.reviews import seats
from apps.reviews.models import RecordAssignment
from core.enums import AssignmentState, Party
from core.permissions import may_read_review

from .test_decisions import COMMENT, DecisionTestBase


def rdco_with_ierc_asking(test):
    """RDCO holds the record and sent it to IERC, whose reviewer asked the author for a revision."""
    record = test.at_rdco()
    response = test.route(record, test.rdco, [{"party": Party.IERC}])
    test.assertEqual(response.status_code, 200, response.data)
    test.opened_seat(record, Party.IERC, test.ierc)
    return record, test.asked(record, test.ierc)


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

    def test_an_open_ierc_revision_request_blocks_the_decider_and_names_who_asked_and_when(self):
        # IR-682's first criterion names the Adviser, but an Adviser can no
        # longer decide once the record has gone to an office, and IERC never
        # holds it before then. RDCO is the party that decides here.
        record, request = rdco_with_ierc_asking(self)
        readiness = self.readiness(record, self.rdco)

        self.assertEqual(readiness["verdict"], "blocked")
        blockers = [i for i in readiness["items"] if i["severity"] == "blocker"]
        self.assertEqual([i["kind"] for i in blockers], ["revision_request"])
        item = blockers[0]
        self.assertEqual(item["party"], Party.IERC)
        self.assertIn("IERC", item["label"])
        self.assertEqual(item["actor_name"], self.ierc.get_full_name())
        self.assertEqual(item["since"], request.created_at.isoformat())
        # Only IERC's own seat holders may withdraw it, so RDCO is offered nothing.
        self.assertIsNone(item["action"])


class ReadinessExplainsEveryRefusalTests(DecisionTestBase):
    """
    The property ADR-032 §10 Amendment asks for: across the states these tests
    build, `decide/` is accepted exactly when readiness said `ready`, and a
    refused Decision was always explained by a blocker readiness already showed.
    """

    def readiness_then_decide(self, record, viewer):
        self.client.force_authenticate(viewer)
        readiness = self.client.get(reverse("record-detail", args=[record.pk])).data["readiness"]
        response = self.decide(record, viewer, "publish", COMMENT)
        return readiness, response

    def states(self):
        def unopened_adviser():
            record = self.new_model()
            self.adviser_seat(record, opened=False)
            return record, self.adviser

        def rdco_asked():
            record = self.at_rdco()
            self.asked(record, self.rdco)
            return record, self.rdco

        def ierc_asked():
            return rdco_with_ierc_asking(self)[0], self.rdco

        def ierc_document_request():
            record = self.at_rdco()
            self.route(record, self.rdco, [{"party": Party.IERC}])
            self.opened_seat(record, Party.IERC, self.ierc)
            DocumentRequest.objects.create(
                record=record, party=Party.IERC, assignment=self.assignment(record, Party.IERC),
                requested_by=self.ierc, message="Signed consent forms, please.",
            )
            return record, self.rdco

        def unopened_second_rdco_seat():
            record = self.at_rdco()
            rdco = RecordAssignment.objects.get(
                record=record, party=Party.RDCO, state=AssignmentState.ACTIVE,
            )
            seats.add_reviewer(rdco, self.rdco, self.rdco2)
            return record, self.rdco2

        return {
            "opened adviser": lambda: (self.at_adviser(), self.adviser),
            "unopened adviser": unopened_adviser,
            "opened rdco": lambda: (self.at_rdco(), self.rdco),
            "rdco asked for a revision": rdco_asked,
            "ierc asked for a revision": ierc_asked,
            "ierc asked for a document": ierc_document_request,
            "unopened second rdco seat": unopened_second_rdco_seat,
        }

    def test_a_refused_decision_is_always_explained_by_a_blocker_already_shown(self):
        refused = 0
        for name, build in self.states().items():
            with self.subTest(state=name):
                record, viewer = build()
                readiness, response = self.readiness_then_decide(record, viewer)
                accepted = response.status_code == 200
                self.assertEqual(accepted, readiness["verdict"] == "ready", response.data)
                if not accepted:
                    refused += 1
                    self.assertTrue(
                        any(i["severity"] == "blocker" and i["label"] for i in readiness["items"]),
                        f"{name}: refused with {response.data} and no blocker shown",
                    )
        # The property means nothing unless some states were refused.
        self.assertGreaterEqual(refused, 3)
