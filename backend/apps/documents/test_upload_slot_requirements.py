"""No seeded upload slot claims to be required (IR-118).

The seed in `0003` marked 37 of 41 slots `is_required=True`, including
combinations no single work can satisfy (Patent Draft *and* Utility Model *and*
Industrial Design *and* Trademark *and* Copyright) and documents that are
outputs of an office's work rather than a submitter's (Patent Search Report).
Nothing enforced any of it, so the only thing it did was put a red "Required"
badge on forms a student cannot produce.

This asserts the claim stays dropped. It is deliberately a property over the
whole table rather than a check on named rows: the point is not that *these*
slots are optional, it is that **the system does not assert a document
requirement it cannot justify**. A future seed that adds a required slot should
fail here and be argued for, not slip in.

Run:
    docker compose exec -T backend python manage.py test apps.documents.test_upload_slot_requirements
"""

from django.test import TestCase

from apps.documents.models import UploadSlot

#: Documents an office produces while processing a disclosure. A submitter
#: cannot attach these at submission because they do not exist yet -- if one
#: ever becomes required, the requirement is in the wrong place.
OFFICE_OUTPUTS = {"Patent Search Report", "Patent Draft"}

#: Alternative IP protections. Requiring more than one of these at once is the
#: tell that a lifecycle checklist has been mistaken for a submission checklist.
MUTUALLY_EXCLUSIVE_IP = {
    "Patent Draft",
    "Utility Model",
    "Industrial Design",
    "Trademark",
    "Copyright",
}


class UploadSlotRequirementTests(TestCase):
    def test_the_seed_produced_slots(self):
        """Guards the rest of this suite: every assertion below passes
        vacuously against an empty table, which is how a broken seed would
        look like a clean bill of health."""
        self.assertGreater(UploadSlot.objects.count(), 0)

    def test_no_slot_claims_to_be_required(self):
        required = list(
            UploadSlot.objects.filter(is_required=True).values_list("name", flat=True)
        )
        self.assertEqual(
            required,
            [],
            "A slot is marked required. Nothing in the codebase enforces "
            "is_required, so this only puts a red badge on the form. If an "
            "office has stated a real requirement, enforce it at submit and "
            "update this test deliberately (IR-118).",
        )

    def test_no_office_output_is_demanded_from_a_submitter(self):
        offenders = set(
            UploadSlot.objects.filter(
                is_required=True, name__in=OFFICE_OUTPUTS
            ).values_list("name", flat=True)
        )
        self.assertEqual(
            offenders,
            set(),
            "A document produced by an office while processing the disclosure "
            "is being required from the person submitting it.",
        )

    def test_no_record_type_requires_two_alternative_ip_protections(self):
        """The clearest signal that the list describes a finished file rather
        than a submission: a work has one IP protection, not five."""
        for slot in UploadSlot.objects.filter(is_required=True).select_related(
            "record_type"
        ):
            self.assertNotIn(slot.name, MUTUALLY_EXCLUSIVE_IP)

    def test_the_slot_names_survive(self):
        """Dropping the requirement must not drop the vocabulary -- these are
        the upload targets an office will ask for later, under ADR-018."""
        names = set(UploadSlot.objects.values_list("name", flat=True))
        for expected in ("Ethics Clearance", "Patent Draft", "Release Form"):
            self.assertIn(expected, names)
