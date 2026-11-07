"""The indexing authority reads the paper's stored AI answer (IR-791, ADR-054).

`records/0034` adds `Record.ai_consent`, the Contact person's answer copied onto
the paper when its draft was created. The disclosure gate in Python now reads it,
so the two Postgres functions the AI runtime asks ("may this paper be a source?")
must read it too -- left on `dpa_accepted_at`, which nothing stamps any more, they
would refuse every paper while the Python gate allowed it. Only `True` is consent:
a No and "no answer stored" are both refused.

The access fence also watches the column. A paper's answer changes in one case,
a person's No-to-Yes choice for "all my papers", and that must fence outstanding
work as a release does. The verifier role gets its column grant here, as `0009`
did for `is_embargoed`, so an already-provisioned database works without re-running
`provision_research_roles`.
"""

from importlib import import_module

from django.db import migrations

previous = import_module("apps.publication.migrations.0009_embargoed_by_default")

OLD_WATCH = "OR NEW.dpa_accepted_at IS DISTINCT FROM OLD.dpa_accepted_at"
NEW_WATCH = "OR NEW.ai_consent IS DISTINCT FROM OLD.ai_consent"
if previous.FENCE.count(OLD_WATCH) != 1:
    raise RuntimeError("IR-791 expected the consent stamp once in the access fence")
FENCE = previous.FENCE.replace(OLD_WATCH, NEW_WATCH)

OLD_GATE = "r.dpa_accepted_at IS NOT NULL"
if previous.SQL.count(OLD_GATE) != 2:
    raise RuntimeError("IR-791 expected the consent stamp once in each indexing function")
SQL = previous.SQL.replace(OLD_GATE, "r.ai_consent IS TRUE")

GRANT = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (ai_consent) ON public.records_record TO iris_authz_verifier;
    END IF;
END $$"""


class Migration(migrations.Migration):
    dependencies = [
        ("publication", "0009_embargoed_by_default"),
        ("records", "0034_record_ai_consent"),
    ]
    operations = [
        migrations.RunSQL(GRANT, migrations.RunSQL.noop),
        migrations.RunSQL(FENCE, previous.FENCE),
        migrations.RunSQL(SQL, previous.SQL),
    ]
