"""Which Records a reader may research, from the one database policy (IR-718, ADR-049 §5).

`research_records(user)` is the entry point every research read uses.
`AI_RESEARCH_READ_POLICY` picks who answers:

- `application` (default): `Record.objects.visible_to(user)`, as today.
- `database`: PostgreSQL's row policy (migration `ai/0035`), read as the
  verified reader over a restricted `iris_django_runtime` login. The
  application's owner connection is never used for this decision.

Switching needs a credential change only an operator can make, so it is
off by default and refused at startup unless the login is restricted.
"""

from __future__ import annotations

from contextlib import closing
from typing import Optional

import psycopg2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections

from apps.ai.grants import config as grant_config
from apps.ai.grants.policy import PROTECTED_TABLES

APPLICATION = "application"
DATABASE = "database"
MODES = (APPLICATION, DATABASE)
DJANGO_RUNTIME_ROLE = "iris_django_runtime"


def mode() -> str:
    return getattr(settings, "AI_RESEARCH_READ_POLICY", APPLICATION)


def _connect():
    params = connections["default"].settings_dict
    return psycopg2.connect(
        host=params["HOST"] or "localhost", port=params["PORT"] or "5432",
        dbname=params["NAME"], user=settings.AI_RESEARCH_DB_USER,
        password=settings.AI_RESEARCH_DB_PASSWORD, connect_timeout=5,
        application_name="iris-research-read",
    )


def _database_ids(user, scope_record_id: Optional[int]) -> list[int]:
    from apps.ai.grants import issue

    try:
        token = issue.record_read_grant(user).token
    except issue.GrantRefused:
        return []
    with closing(_connect()) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT iris_authz.begin_research(%s, 'record_read')", [token])
                if scope_record_id is None:
                    cursor.execute("SELECT id FROM records_record")
                else:
                    cursor.execute("SELECT id FROM records_record WHERE id = %s", [scope_record_id])
                return [row[0] for row in cursor.fetchall()]
        except psycopg2.errors.InsufficientPrivilege:
            return []
        finally:
            conn.rollback()


def research_records(user, *, scope_record_id: Optional[int] = None):
    """The Records `user` may research, optionally narrowed to one."""
    from apps.records.models import Record

    if mode() == DATABASE:
        return Record.objects.filter(pk__in=_database_ids(user, scope_record_id))
    visible = Record.objects.visible_to(user)
    if scope_record_id is not None:
        visible = visible.filter(pk=scope_record_id)
    return visible


def credential_problems(cursor) -> list[str]:
    """Why the connected login may not serve research reads."""
    found = []
    cursor.execute(
        "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, %s, 'MEMBER') "
        "FROM pg_roles WHERE rolname = current_user", [DJANGO_RUNTIME_ROLE])
    superuser, bypass, member = cursor.fetchone()
    if superuser:
        found.append("the research login must not be a superuser")
    if bypass:
        found.append("the research login must not have BYPASSRLS")
    if not member:
        found.append(f"the research login must be a member of {DJANGO_RUNTIME_ROLE}")
    cursor.execute(
        """SELECT c.relname, pg_has_role(current_user, c.relowner, 'MEMBER'), c.relrowsecurity
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)""", [list(PROTECTED_TABLES)])
    rows = {name: (owns, secured) for name, owns, secured in cursor.fetchall()}
    for table in PROTECTED_TABLES:
        owns, secured = rows.get(table, (False, False))
        if owns:
            found.append(f"the research login must not own tables; it owns {table}")
        if not secured:
            found.append(f"{table} has no row security; run migrate")
    return found


def verify_research_read_configuration() -> None:
    """Startup check, from `AiConfig.ready()`."""
    current = mode()
    if current not in MODES:
        raise ImproperlyConfigured(
            f"AI_RESEARCH_READ_POLICY must be one of {', '.join(MODES)} (IR-718)")
    if current == APPLICATION:
        return
    found = []
    if not grant_config.enabled():
        found.append("AI_RESEARCH_GRANTS must be on")
    for name in ("AI_RESEARCH_DB_USER", "AI_RESEARCH_DB_PASSWORD"):
        if not str(getattr(settings, name, "") or "").strip():
            found.append(f"{name} is required")
    if not found:
        try:
            with closing(_connect()) as conn, conn.cursor() as cursor:
                found += credential_problems(cursor)
        except psycopg2.Error as exc:
            found.append(f"the research login cannot connect ({type(exc).__name__})")
    if found:
        raise ImproperlyConfigured(
            "; ".join(found) + " (AI_RESEARCH_READ_POLICY=database, IR-718; see backend/.env.example)")
