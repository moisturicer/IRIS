"""The AI runtime reads only papers that may reach the AI (IR-1252, ADR-052 as amended 2026-11-21).

`iris_authz.research_record_ids()` is what every research row policy asks. For
the AI runtime's purpose, `reader_session` (Ask IRIS and Paper Chat), it now also
requires what Django's disclosure gate requires (`apps/ai/policy`): published,
released from embargo, consent given, and an IP mark released by KTTO. Every
reader is held to it, the paper's own owners, Adviser and office staff included,
and a paper that stops qualifying is refused at the run's next read. Django's
own purposes, `record_read` and `reader_run`, still read by visibility alone,
because they show a person their own papers and earlier answers.

Built from 0049's SQL, so only this clause differs; CREATE OR REPLACE keeps the
function's owner and grants. It only narrows. The columns are the verifier's
already; the grant below repeats them so a database provisioned before this
migration works without re-running `provision_research_roles`.
"""

from importlib import import_module

from django.db import migrations

_previous = import_module("apps.ai.migrations.0049_research_reads_hide_drafts")

#: The one published status (`core.enums.PUBLICLY_VISIBLE_STATUSES`), frozen here
#: as the migration's own value.
PUBLISHED = "published"

ANCHOR = """\
     WHERE NOT r.is_deleted
       AND (scope IS NULL OR r.id = scope)"""

#: ADR-052 as amended 2026-11-21, for the AI runtime alone.
DISCLOSABLE = ANCHOR + f"""
       AND (claims->>'pur' <> 'reader_session'
            OR (r.pipeline_status = '{PUBLISHED}' AND NOT r.is_embargoed
                AND r.ai_consent IS TRUE
                AND (NOT r.is_ip OR r.ip_released_at IS NOT NULL)))"""

GRANT = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (pipeline_status, is_embargoed, ai_consent, is_ip, ip_released_at)
            ON public.records_record TO iris_authz_verifier;
    END IF;
END $$"""


def _swap(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"0050 expected one {old!r}")
    return sql.replace(old, new)


PREVIOUS_IDS = _previous.IDS
IDS = _swap(PREVIOUS_IDS, ANCHOR, DISCLOSABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0049_research_reads_hide_drafts"),
        ("records", "0036_record_ai_consent"),
    ]

    operations = [
        migrations.RunSQL(GRANT, migrations.RunSQL.noop),
        migrations.RunSQL(IDS, PREVIOUS_IDS),
    ]
