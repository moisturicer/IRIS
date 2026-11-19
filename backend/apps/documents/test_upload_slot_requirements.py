"""The starting Requirement labels, and that a label never blocks (ADR-063 decision 3, IR-971).

**Rewritten on purpose in IR-971.** IR-118 asserted that no slot may be
Required, because the `0003` seed marked 37 of 41 slots Required, nothing
enforced it, and the red badges asked students for documents they couldn't
produce. ADR-063 (accepted 2026-11-08) brings the label back under a rule that
keeps IR-118's point: **a label informs and never blocks submitting**. So the
property this file guards moves from "nothing is Required" to:

1. the labels are exactly ADR-063 decision 12's, as ADR-066 decisions 21-22
   amend it (the IP slots and the Commercialization Assessment leave the
   submission, so they stay Optional until IR-1062 removes them);
2. a submission with an empty Required slot is accepted;
3. no record type requires two alternative IP protections, and nothing
   requires the Patent Draft, an office's output (IR-118's two tells, kept).

The Proposal's Patent Search Report is Required: ADR-066 decision 22 keeps it
as the Proposal's own early check that the idea doesn't already exist, so it is
no longer counted as an office's output on a Proposal.
"""

from django.test import TestCase
from rest_framework import status

from apps.documents.models import UploadSlot
from apps.records.test_embargo import DraftBase
from core.enums import PipelineStatus

#: ADR-063 decision 12 as amended by ADR-066 decisions 21-22.
EXPECTED_REQUIRED = {
    ("Proposal", "Thesis Revision Form"),
    ("Proposal", "Patent Search Report"),
    ("Thesis / Research", "Community Extension"),
    ("Thesis / Research", "Publication / Conference Presentation / Both"),
    ("Thesis / Research", "Release Form"),
    ("Project", "Community Extension"),
    ("Project", "Publication / Conference Presentation / Both"),
    ("Project", "Release Form"),
}

#: Alternative IP protections. Requiring more than one of these at once is the
#: tell that a lifecycle checklist has been mistaken for a submission checklist.
MUTUALLY_EXCLUSIVE_IP = {
    "Patent Draft",
    "Utility Model",
    "Industrial Design",
    "Trademark",
    "Copyright",
}


def _seeded_required():
    return set(
        UploadSlot.objects.filter(is_required=True, record__isnull=True)
        .values_list("record_type__name", "name")
    )


class StartingLabelTests(TestCase):
    def test_the_seed_produced_slots(self):
        """Guards the rest of this suite: every assertion below passes
        vacuously against an empty table, which is how a broken seed would
        look like a clean bill of health."""
        self.assertGreater(UploadSlot.objects.count(), 0)

    def test_the_labels_are_decision_12s_as_adr_066_amends_it(self):
        self.assertEqual(_seeded_required(), EXPECTED_REQUIRED)

    def test_no_slot_leaving_the_submission_is_required(self):
        """ADR-066 decision 21: IP Application Status, the IP slots and the
        Commercialization Assessment leave Thesis / Research and Project."""
        leaving = MUTUALLY_EXCLUSIVE_IP | {
            "Intellectual Property Application Status", "Commercialization Assessment",
        }
        offenders = UploadSlot.objects.filter(
            is_required=True, name__in=leaving,
            record_type__name__in=["Thesis / Research", "Project"],
        )
        self.assertFalse(offenders.exists(), list(offenders.values_list("name", flat=True)))

    def test_the_patent_draft_is_never_demanded(self):
        """An office's output while it processes the disclosure."""
        self.assertFalse(UploadSlot.objects.filter(is_required=True, name="Patent Draft").exists())

    def test_no_record_type_requires_two_alternative_ip_protections(self):
        for slot in UploadSlot.objects.filter(is_required=True).select_related("record_type"):
            self.assertNotIn(slot.name, MUTUALLY_EXCLUSIVE_IP)

    def test_each_record_types_slots_are_numbered_in_order(self):
        """0025 keeps the order slots always showed in, numbered from 1."""
        for type_name in ("Proposal", "Thesis / Research", "Project"):
            positions = list(
                UploadSlot.objects.filter(record_type__name=type_name, record__isnull=True)
                .order_by("pk").values_list("position", flat=True)
            )
            self.assertEqual(positions, list(range(1, len(positions) + 1)), type_name)

    def test_the_slot_names_survive(self):
        names = set(UploadSlot.objects.values_list("name", flat=True))
        for expected in ("Ethics Clearance", "Patent Draft", "Release Form"):
            self.assertIn(expected, names)


class RequiredNeverBlocksTests(DraftBase):
    """ADR-063 decision 3: a Record with an empty Required slot is accepted."""

    def test_a_submission_with_every_required_slot_empty_is_accepted(self):
        required = UploadSlot.objects.filter(record_type=self.record_type, is_required=True)
        self.assertTrue(required.exists(), "the Thesis / Research type has no Required slot to leave empty")
        self.assertFalse(self.record.uploads.exists())

        response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.pipeline_status, PipelineStatus.IN_REVIEW)
