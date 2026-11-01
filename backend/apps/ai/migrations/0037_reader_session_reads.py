"""`reader_session` reads what its reader may; `rec` scopes it (IR-719, ADR-049 §5-6).

Built from 0035/0036's SQL so only these clauses differ; CREATE OR REPLACE
keeps each function's owner and grants.
"""

from importlib import import_module

from django.db import migrations

_policy = import_module("apps.ai.migrations.0035_research_read_policy")
_session = import_module("apps.ai.migrations.0036_reader_session_grant")


def _swap(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"0037 expected one {old!r}")
    return sql.replace(old, new)


SESSION_CLAIMS = """\
    ELSIF p_purpose = 'reader_session' THEN
        IF claims->>'run' IS NOT NULL OR claims->>'cnv' IS NOT NULL OR claims->>'rec' IS NOT NULL
           OR claims->>'job' IS NOT NULL OR claims->>'rev' IS NOT NULL THEN"""
SCOPED_SESSION_CLAIMS = """\
    ELSIF p_purpose = 'reader_session' THEN
        IF claims->>'run' IS NOT NULL OR claims->>'cnv' IS NOT NULL
           OR claims->>'job' IS NOT NULL OR claims->>'rev' IS NOT NULL
           OR (claims->>'rec')::bigint < 1 THEN"""

VERIFY = _swap(_session.VERIFY, SESSION_CLAIMS, SCOPED_SESSION_CLAIMS)

PREVIOUS_IDS = _swap(_policy.FUNCTION, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
IDS = _swap(
    _swap(PREVIOUS_IDS, "NOT IN ('record_read', 'reader_run')",
          "NOT IN ('record_read', 'reader_run', 'reader_session')"),
    "IF claims->>'pur' = 'reader_run' THEN scope",
    "IF claims->>'pur' IN ('reader_run', 'reader_session') THEN scope",
)


class Migration(migrations.Migration):

    dependencies = [("ai", "0036_reader_session_grant")]

    operations = [
        migrations.RunSQL(_policy.REFUSE_RUNTIME_LOGIN + VERIFY, _session.VERIFY),
        migrations.RunSQL(IDS, PREVIOUS_IDS),
    ]
