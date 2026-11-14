"""
The starting Requirement list (ADR-063 decision 12, as amended by ADR-066; IR-971).

1. **Order.** Each record type's slots keep the order they have always shown in
   (by id), numbered from 1. The Manuscript is not a slot and always comes first.
2. **Labels.** Required where RDCO's requirements sheet says so, Optional
   otherwise. ADR-063 decision 12 also named Intellectual Property Application
   Status and the Commercialization Assessment Required on Thesis / Research and
   Project, and Patent Search Report on Project; ADR-066 decisions 21-22 take
   those off the submission (IR-1062 removes them), so they stay Optional here.
3. **Descriptions** start empty: RDCO writes them on Setup (IR-969, 2026-11-14).

A label never blocks submitting (ADR-063 decision 3). Reversing returns every
slot to Optional and position 0, which is what `0005` left.
"""
from django.db import migrations

#: (record type, slot): the Required labels, ADR-063 d12 as amended by ADR-066 d21-22.
REQUIRED = [
    ("Proposal", "Thesis Revision Form"),
    ("Proposal", "Patent Search Report"),
    ("Thesis / Research", "Community Extension"),
    ("Thesis / Research", "Publication / Conference Presentation / Both"),
    ("Thesis / Research", "Release Form"),
    ("Project", "Community Extension"),
    ("Project", "Publication / Conference Presentation / Both"),
    ("Project", "Release Form"),
]


def forwards(apps, schema_editor):
    UploadSlot = apps.get_model("documents", "UploadSlot")
    RecordType = apps.get_model("records", "RecordType")

    for record_type in RecordType.objects.all():
        slots = UploadSlot.objects.filter(record_type=record_type, record__isnull=True).order_by("pk")
        for position, slot in enumerate(slots, start=1):
            slot.position = position
            slot.save(update_fields=["position"])

    # "Optional otherwise": until Setup no screen set a label, so any Required
    # left on a type's slot is a seed's default (e.g. `seed_demo`'s demo slot),
    # never RDCO's choice. Ad-hoc slots are a request's, and are left alone.
    UploadSlot.objects.filter(record__isnull=True).update(is_required=False)
    for type_name, slot_name in REQUIRED:
        UploadSlot.objects.filter(
            record_type__name=type_name, name=slot_name, record__isnull=True,
        ).update(is_required=True)


def backwards(apps, schema_editor):
    UploadSlot = apps.get_model("documents", "UploadSlot")
    UploadSlot.objects.update(is_required=False, position=0)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0024_setup_requirements"),
        ("records", "0041_setup_requirements"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
