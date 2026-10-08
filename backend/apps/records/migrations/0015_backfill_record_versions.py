"""
IR-416: give every submitted record the version history that can be known
(ADR-032 §13, as amended 2026-10-08).

No earlier manuscript is recorded anywhere: `Record.abstract_file` is replaced
in place. So each non-draft record gets exactly **one** version, naming its
current manuscript:

- **Never resubmitted** (`resubmission_count == 0`): v1, `submission`, dated
  when consent was stamped at submission (`dpa_accepted_at`, IR-226), else
  when the record was created, and credited to whoever stamped that consent.
- **Resubmitted k times**: v(k + 1), `revision`, dated `last_resubmitted_at`.
  Nobody is credited, because no resubmitter was recorded. No v1 to vk are
  made up, so the history starts at v(k + 1), and the next resubmission writes
  v(k + 2).

Records made by import, seed or `load_corpus` were never submitted, so they
carry no consent and get a version credited to nobody. A record with no
manuscript gets a version with none. **Every existing `Review.version` stays
null:** dating a review against a reconstructed version would invent the link,
as `reviews/0008` declined to invent `Review.assignment`.

Written against the historical models, as every backfill here is. Records that
already have a version are skipped, because the live code reached them first.
Reversing deletes nothing a person wrote, and `0014` reversed drops the table.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    RecordVersion = apps.get_model("records", "RecordVersion")

    versions = []
    for record in (
        Record.objects.exclude(pipeline_status="draft")
        .exclude(versions__isnull=False)
        .order_by("pk")
    ):
        resubmissions = record.resubmission_count or 0
        if resubmissions:
            number, cause, created_by_id = resubmissions + 1, "revision", None
            created_at = record.last_resubmitted_at or record.updated_at
        else:
            number, cause = 1, "submission"
            created_by_id = record.dpa_accepted_by_id
            created_at = record.dpa_accepted_at or record.created_at
        versions.append(RecordVersion(
            record_id=record.pk,
            number=number,
            cause=cause,
            manuscript=record.abstract_file.name or None,
            created_by_id=created_by_id,
            created_at=created_at,
        ))

    RecordVersion.objects.bulk_create(versions)


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0014_record_version"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
