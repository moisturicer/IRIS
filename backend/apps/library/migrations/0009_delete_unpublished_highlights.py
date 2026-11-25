"""
IR-1326: delete every stored highlight on a paper that isn't published.

From IR-1326 a private highlight exists only on a published paper (ADR-065 as
amended 2026-11-24). On a draft or a paper in review, highlighting is a review
comment, so the highlights made there before this change are removed, not kept
hidden. A note is untouched: only highlights go.

There is no way back: backwards does nothing, and the rows stay deleted.
"""

from django.db import migrations

PUBLISHED = "published"


def delete_unpublished_highlights(apps, schema_editor):
    ReadingHighlight = apps.get_model("library", "ReadingHighlight")
    ReadingHighlight.objects.exclude(record__pipeline_status=PUBLISHED).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0008_savedfeed_year_range"),
        ("records", "0044_recordtype_position"),
    ]

    operations = [migrations.RunPython(delete_unpublished_highlights, migrations.RunPython.noop)]
