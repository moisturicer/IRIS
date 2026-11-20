"""The indexing authority indexes only published papers (IR-1252, ADR-052 as amended 2026-11-21).

The two Postgres functions the AI runtime asks before it indexes a paper ("may
this paper be a source?") now require what Django's disclosure gate requires:
published and not deleted, besides the consent, IP and embargo they already read.
A released paper still in review, or accepted but kept unlisted, is no longer a
source. The access fence already watches `pipeline_status` (`0003`), so a paper
leaving publication fences its outstanding work.

The verifier gets its column grants here, as `0009` and `0010` did, so an
already-provisioned database works without re-running `provision_research_roles`.
"""

from importlib import import_module

from django.db import migrations

previous = import_module("apps.publication.migrations.0010_indexing_reads_the_stored_answer")

#: The one published status (`core.enums.PUBLICLY_VISIBLE_STATUSES`), frozen here.
PUBLISHED = "published"

OLD_GATE = "r.ai_consent IS TRUE"
if previous.SQL.count(OLD_GATE) != 2:
    raise RuntimeError("IR-1252 expected the consent check once in each indexing function")
OLD_SOURCE = "WHERE r.ai_consent IS TRUE"
if previous.SQL.count(OLD_SOURCE) != 1:
    raise RuntimeError("IR-1252 expected indexing_source's WHERE to start at the consent check")

SQL = (
    previous.SQL
    .replace(OLD_GATE, f"r.ai_consent IS TRUE AND r.pipeline_status = '{PUBLISHED}'")
    # indexed_source_current already refuses a deleted paper; indexing_source didn't say so.
    .replace("WHERE r.ai_consent IS TRUE", "WHERE NOT r.is_deleted AND r.ai_consent IS TRUE")
)

GRANT = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (pipeline_status, is_deleted) ON public.records_record TO iris_authz_verifier;
    END IF;
END $$"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0010_indexing_reads_the_stored_answer")]
    operations = [
        migrations.RunSQL(GRANT, migrations.RunSQL.noop),
        migrations.RunSQL(SQL, previous.SQL),
    ]
