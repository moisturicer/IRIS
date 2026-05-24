"""
Seed UploadStatus and UploadSlot rows from the IRIS Workflow Documentation.

UploadStatus progression: For Application → Reviewed → Filed → Approved / Disapproved
UploadSlots per RecordType (see Section 4 of the workflow PDF).
"""
from django.db import migrations


STATUSES = ["For Application", "Reviewed", "Filed", "Approved", "Disapproved"]

# (slot_name, record_type_name, is_required)
SLOTS = [
    # --- Proposal ---
    ("NDA",                                    "Proposal",          True),
    ("Thesis Revision Form",                   "Proposal",          True),
    ("Patent Search Report",                   "Proposal",          True),
    ("Patent Draft",                           "Proposal",          True),
    ("Ethics Clearance",                       "Proposal",          True),
    ("Assessment File",                        "Proposal",          True),
    ("Utility Model",                          "Proposal",          True),
    ("Industrial Design",                      "Proposal",          True),
    ("Trademark",                              "Proposal",          True),
    ("Copyright",                              "Proposal",          True),
    ("Commercialization Initial Assessment",   "Proposal",          False),
    ("Community Extension Initial Assessment", "Proposal",          False),

    # --- Thesis / Research ---
    ("Intellectual Property Application Status",      "Thesis / Research", True),
    ("Publication / Conference Presentation / Both",  "Thesis / Research", True),
    ("Release Form",                                  "Thesis / Research", True),
    ("Patent Search Report",                          "Thesis / Research", True),
    ("Patent Draft",                                  "Thesis / Research", True),
    ("Ethics Clearance",                              "Thesis / Research", True),
    ("Assessment File",                               "Thesis / Research", True),
    ("Commercialization Assessment",                  "Thesis / Research", True),
    ("Community Extension",                           "Thesis / Research", True),
    ("Utility Model",                                 "Thesis / Research", True),
    ("Industrial Design",                             "Thesis / Research", True),
    ("Trademark",                                     "Thesis / Research", True),
    ("Copyright",                                     "Thesis / Research", True),

    # --- Project ---
    ("NDA",                                    "Project",           True),
    ("Intellectual Property Application Status",      "Project",   True),
    ("Publication / Conference Presentation / Both",  "Project",   True),
    ("Release Form",                           "Project",           True),
    ("Patent Search Report",                   "Project",           True),
    ("Patent Draft",                           "Project",           True),
    ("Ethics Clearance",                       "Project",           True),
    ("Assessment File",                        "Project",           True),
    ("Commercialization Assessment",           "Project",           True),
    ("Community Extension",                    "Project",           True),
    ("Utility Model",                          "Project",           True),
    ("Industrial Design",                      "Project",           True),
    ("Trademark",                              "Project",           True),
    ("Copyright",                              "Project",           True),
    ("Commercialization Initial Assessment",   "Project",           False),
    ("Community Extension Initial Assessment", "Project",           False),
]


def seed(apps, schema_editor):
    UploadStatus = apps.get_model("documents", "UploadStatus")
    UploadSlot   = apps.get_model("documents", "UploadSlot")
    RecordType   = apps.get_model("records",   "RecordType")

    for name in STATUSES:
        UploadStatus.objects.get_or_create(name=name)

    for slot_name, rt_name, is_required in SLOTS:
        rt = RecordType.objects.filter(name=rt_name).first()
        if rt:
            UploadSlot.objects.get_or_create(
                name=slot_name,
                record_type=rt,
                defaults={"is_required": is_required},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_pdfextraction"),
        ("records",   "0002_seed_record_types"),
    ]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
