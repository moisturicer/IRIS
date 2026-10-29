"""
What a submitter is told about their own record (IR-625).

One status line per record, the open requests waiting on the owner, and on
Record detail a history of each version and what was decided on it. Every
word is the server's: the frontend renders `submitter_status` as it comes.

**Seam: the records API**, through the tracker tests' drivers, plus the pure
`status_line` for the holder combinations the drivers cannot reach cheaply.
"""

import json

from apps.records.test_my_research_list import MyResearchListTestBase
from core.enums import Party, RecordTypeName, WorkflowState

from .submitter_status import OWNER_ACTION_STATES, status_line


class StatusLineTests(MyResearchListTestBase):

    def line(self, record):
        return self.mine()[record.pk]["submitter_status"]["line"]

    def test_a_submitted_record_is_with_the_adviser(self):
        self.assertEqual(self.line(self.submitted(RecordTypeName.THESIS_RESEARCH)), "With your Adviser")

    def test_a_record_in_parallel_review_names_the_offices_still_reviewing(self):
        self.assertEqual(self.line(self.at_parallel_review()), "In specialist review: IERC, KTTO")

    def test_a_revision_request_names_who_asked_and_says_it_is_on_the_owner(self):
        self.assertEqual(
            self.line(self.revision_requested()), "Revision requested by IERC: action needed",
        )

    def test_a_document_request_names_who_asked(self):
        self.assertEqual(
            self.line(self.document_requested()), "Documents requested by Adviser: action needed",
        )

    def test_a_draft_says_it_is_not_submitted(self):
        self.assertEqual(
            self.line(self.make_record(RecordTypeName.THESIS_RESEARCH)), "Draft: not yet submitted",
        )

    def test_rdco_holding_the_record_is_a_decision(self):
        line = status_line(
            record=None, workflow_state=WorkflowState.FINAL_REVIEW, holders=[Party.RDCO],
            revision_parties=[], document_parties=[],
        )
        self.assertEqual(line, "With RDCO for a decision")

    def test_the_list_and_detail_say_the_same_thing(self):
        records = self.one_of_each()
        rows = self.mine()
        for record in records:
            with self.subTest(record=record.pk):
                self.assertEqual(
                    rows[record.pk]["submitter_status"],
                    {k: v for k, v in self.detail(record)["submitter_status"].items() if k != "history"},
                )


class WaitingOnYouTests(MyResearchListTestBase):

    def waiting(self, record):
        return self.mine()[record.pk]["submitter_status"]["waiting_on_you"]

    def test_a_revision_request_is_one_item_answered_by_a_new_version(self):
        self.assertEqual(self.waiting(self.revision_requested()), [{
            "kind": "revision", "party": "ierc",
            "label": "Revision requested by IERC", "action_label": "Submit a new version",
        }])

    def test_a_document_request_is_one_item_answered_by_an_upload(self):
        self.assertEqual(self.waiting(self.document_requested()), [{
            "kind": "document", "party": "adviser",
            "label": "Documents requested by Adviser", "action_label": "Upload the documents",
        }])

    def test_a_record_only_in_review_waits_on_nobody(self):
        self.assertEqual(self.waiting(self.at_parallel_review()), [])

    def test_waiting_on_you_agrees_with_the_needs_action_states(self):
        """
        IR-534's My Library dot counts `awaiting_resubmission` and
        `awaiting_document`. A record waits on its owner exactly when its
        `workflow_state` is one of those, so the two never contradict.
        """
        self.one_of_each()
        for row in self.mine().values():
            with self.subTest(state=row["workflow_state"]):
                self.assertEqual(
                    bool(row["submitter_status"]["waiting_on_you"]),
                    row["workflow_state"] in OWNER_ACTION_STATES,
                )

    def test_no_reviewer_words_or_names_reach_the_owner(self):
        record = self.revision_requested()
        payload = json.dumps(self.detail(record)["submitter_status"])

        self.assertNotIn("consent procedure", payload)
        for reviewer in (self.adviser, self.itso, self.ierc):
            self.assertNotIn(reviewer.get_full_name(), payload)


class HistoryTests(MyResearchListTestBase):

    def test_each_version_lists_what_each_party_decided_on_it(self):
        record = self.revision_requested()
        history = self.detail(record)["submitter_status"]["history"]

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["number"], 1)
        self.assertEqual(history[0]["cause_label"], "Submission")
        self.assertTrue(history[0]["submitted_at"])
        self.assertEqual(
            [(d["label"], d["verdict_label"]) for d in history[0]["decisions"]],
            [("Adviser", "Approved"), ("ITSO", "Cleared"), ("IERC", "Revision requested")],
        )

    def test_a_version_nobody_has_decided_on_has_no_decisions(self):
        record = self.submitted(RecordTypeName.THESIS_RESEARCH)
        history = self.detail(record)["submitter_status"]["history"]

        self.assertEqual([(v["number"], v["decisions"]) for v in history], [(1, [])])

    def test_a_draft_has_no_history(self):
        record = self.make_record(RecordTypeName.THESIS_RESEARCH)
        self.assertEqual(self.detail(record)["submitter_status"]["history"], [])


class OwnerOnlyTests(MyResearchListTestBase):

    def test_a_reviewer_is_not_sent_the_owners_status(self):
        record = self.revision_requested()
        for viewer in (self.adviser, self.ierc):
            with self.subTest(viewer=viewer.email):
                self.assertIsNone(self.detail(record, viewer)["submitter_status"])
