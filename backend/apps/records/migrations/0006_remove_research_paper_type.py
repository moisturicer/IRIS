"""
Remove the legacy "Research Paper" RecordType that was seeded in an earlier
version of the database but is not part of the IRIS workflow.

Any records of this type are reassigned to "Thesis / Research" since that is
the closest semantic match for general academic papers.
"""
from django.db import migrations


def remove_research_paper(apps, schema_editor):
    RecordType = apps.get_model("records", "RecordType")
    UploadSlot = apps.get_model("documents", "UploadSlot")
    Record     = apps.get_model("records",   "Record")

    rp = RecordType.objects.filter(name="Research Paper").first()
    if not rp:
        return  # already gone — nothing to do

    # Reassign any records that use this type
    thesis = RecordType.objects.filter(name="Thesis / Research").first()
    if thesis:
        Record.objects.filter(record_type=rp).update(record_type=thesis)

    # Delete slots for this type, then the type itself
    UploadSlot.objects.filter(record_type=rp).delete()
    rp.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("records",   "0005_alter_record_pipeline_status"),
        ("documents", "0003_seed_upload_slots"),
    ]
    operations = [migrations.RunPython(remove_research_paper, migrations.RunPython.noop)]
