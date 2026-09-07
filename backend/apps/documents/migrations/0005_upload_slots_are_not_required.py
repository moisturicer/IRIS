"""Stop the system asserting a document requirement nobody can justify (IR-118).

`0003_seed_upload_slots` seeded 39 slots, 37 of them `is_required=True`. Three
things are wrong with that, and none is a UI problem:

1.  **The required set is unsatisfiable.** A Thesis/Research submission requires
    Patent Draft AND Utility Model AND Industrial Design AND Trademark AND
    Copyright, at once. Those are *alternative* IP protections; no single work
    holds all five.

2.  **Several are office outputs, not submitter inputs.** A Patent Search Report
    and a Patent Draft are products of KTTO's work *after* a disclosure is
    filed. A student cannot attach them at submission because they do not exist
    yet.

3.  **Ethics Clearance is unconditional**, which contradicts
    `Record.requires_ethics_review` being a per-record question under ADR-018 --
    the whole point of which is that IERC's involvement is not implied by type.

Read together, the seeded list is a faithful description of what a *completed*
disclosure file eventually contains -- a lifecycle checklist -- entered into the
one dimension the schema had, which is submission-time requirement keyed on
record type. The SRS (FR-M2-01 SS3.2.2.1) describes the dimension it actually
needs: per-department templates and per-office, stage-gated checklists with
conditional rules. None of that exists.

**So this migration removes the claim and keeps the vocabulary.** The slot names
are real and useful -- they are the upload targets an office will eventually ask
for. What is not real is that any of them is required to submit, and a red
"Required" badge on a form a student cannot produce teaches people to disregard
the interface.

Under ADR-018 (accepted 2026-09-07) documents are requested by the office that
needs them, at the stage it needs them. Until an office states its real list,
the honest default is that nothing beyond the manuscript is required, which is
already what the submission wizard does (`UploadsStep`'s `hideSlots`).

Reversible: `is_required` is restored to the exact values `0003` seeded, so a
downgrade reproduces the previous state rather than approximating it.
"""

from django.db import migrations

# (slot_name, record_type_name) pairs that 0003 seeded with is_required=False.
# Everything else it seeded was True, so the reverse can be exact rather than
# a blanket flip -- see the module docstring.
ORIGINALLY_OPTIONAL = {
    ("Commercialization Initial Assessment", "Proposal"),
    ("Community Extension Initial Assessment", "Proposal"),
    ("Commercialization Initial Assessment", "Project"),
    ("Community Extension Initial Assessment", "Project"),
}


def drop_the_requirement(apps, schema_editor):
    UploadSlot = apps.get_model("documents", "UploadSlot")
    UploadSlot.objects.update(is_required=False)


def restore_the_requirement(apps, schema_editor):
    UploadSlot = apps.get_model("documents", "UploadSlot")
    for slot in UploadSlot.objects.select_related("record_type"):
        rt_name = slot.record_type.name if slot.record_type else ""
        slot.is_required = (slot.name, rt_name) not in ORIGINALLY_OPTIONAL
        slot.save(update_fields=["is_required"])


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0004_pdfextraction_structure"),
    ]

    operations = [
        migrations.RunPython(drop_the_requirement, restore_the_requirement),
    ]
