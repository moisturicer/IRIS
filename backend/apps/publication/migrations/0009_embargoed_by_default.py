"""The indexing authority reads `is_embargoed` (IR-882, ADR-052 as amended).

`records/0032` makes every paper embargoed until released. The answer stamp is
renamed in Django only and keeps its column, `embargo_answered_at`. Both indexing
checks read the old four states, so they are rewritten here: only a released paper
is a source. The access fence also watches the new flag, so a release or a new
embargo fences outstanding work as before.
"""

from importlib import import_module

from django.db import migrations

previous = import_module("apps.publication.migrations.0008_indexing_authority")

OLD_STAMP = (
    "OR to_jsonb(NEW)->'embargo_answered_at' IS DISTINCT FROM to_jsonb(OLD)->'embargo_answered_at'"
)
NEW_STAMP = OLD_STAMP + "\n           OR NEW.is_embargoed IS DISTINCT FROM OLD.is_embargoed"
if previous.FENCE.count(OLD_STAMP) != 1:
    raise RuntimeError("IR-882 expected one embargo answer stamp in the fence")
FENCE = previous.FENCE.replace(OLD_STAMP, NEW_STAMP)

OLD_GATE = (
    "AND r.embargo_answered_at IS NOT NULL\n"
    "      AND (r.embargo_released_at IS NOT NULL OR r.embargoed_until IS NULL)"
)
OLD_GATE_INNER = (
    "AND r.embargo_answered_at IS NOT NULL\n"
    "        AND (r.embargo_released_at IS NOT NULL OR r.embargoed_until IS NULL)"
)
if previous.SQL.count(OLD_GATE) != 1 or previous.SQL.count(OLD_GATE_INNER) != 1:
    raise RuntimeError("IR-882 expected the embargo gate once in each indexing function")
SQL = (
    previous.SQL.replace(OLD_GATE, "AND NOT r.is_embargoed")
    .replace(OLD_GATE_INNER, "AND NOT r.is_embargoed")
    .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
)

#: The definer functions run as the verifier, which `provision_research_roles`
#: grants column by column. The new column needs its own grant, here, so an already-provisioned database works without re-running it.
GRANT = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (is_embargoed) ON public.records_record TO iris_authz_verifier;
    END IF;
END $$"""


class Migration(migrations.Migration):
    dependencies = [
        ("publication", "0008_indexing_authority"),
        ("records", "0032_embargoed_by_default"),
    ]
    operations = [
        migrations.RunSQL(GRANT, migrations.RunSQL.noop),
        migrations.RunSQL(FENCE, previous.FENCE),
        migrations.RunSQL(SQL, previous.SQL.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")),
    ]
