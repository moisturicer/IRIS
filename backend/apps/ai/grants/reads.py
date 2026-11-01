"""Which Records a reader may research (IR-718, ADR-049 §5).

`research_records(user)` is the one entry point. `AI_RESEARCH_READ_POLICY`:

- `application` (default): `Record.objects.visible_to(user)`.
- `database`: PostgreSQL's row policy (`ai/0035`), read as the verified
  reader over the restricted `research` database alias.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from typing import Optional

import psycopg2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections
from django.utils.connection import ConnectionDoesNotExist

from apps.ai.grants import config as grant_config
from apps.ai.grants.policy import PROTECTED_TABLES

APPLICATION = "application"
DATABASE = "database"
MODES = (APPLICATION, DATABASE)
DJANGO_RUNTIME_ROLE = "iris_django_runtime"
#: Configured only when the policy is `database`.
ALIAS = "research"
INSUFFICIENT_PRIVILEGE = "42501"

_run: ContextVar = ContextVar("research_run", default=None)


def mode() -> str:
    return getattr(settings, "AI_RESEARCH_READ_POLICY", APPLICATION)


@contextmanager
def bound_run(run):
    """Read under `run`'s own grant for the body (ADR-049 §6)."""
    token = _run.set(run)
    try:
        yield
    finally:
        _run.reset(token)


def current_run():
    return _run.get()


def _grant(user):
    """(token, purpose), or None when no grant may be issued."""
    from apps.ai.grants import issue

    run = current_run()
    try:
        if run is None:
            return issue.record_read_grant(user).token, issue.RECORD_READ
        if run.user_id != getattr(user, "pk", None):
            return None
        return issue.reader_grant(user, run).token, issue.READER_RUN
    except issue.GrantRefused:
        return None


def _refused(exc: DatabaseError) -> bool:
    """PostgreSQL refused the grant (insufficient_privilege)."""
    cause = exc.__cause__
    return getattr(cause, "pgcode", None) == INSUFFICIENT_PRIVILEGE


def _database_ids(user, scope_record_id: Optional[int]) -> list[int]:
    from apps.ai.grants import database

    grant = _grant(user)
    if grant is None:
        return []
    token, purpose = grant
    try:
        with database.research_identity(token, purpose, using=ALIAS):
            with connections[ALIAS].cursor() as cursor:
                if scope_record_id is None:
                    cursor.execute("SELECT id FROM records_record")
                else:
                    cursor.execute("SELECT id FROM records_record WHERE id = %s", [scope_record_id])
                return [row[0] for row in cursor.fetchall()]
    except DatabaseError as exc:
        if _refused(exc):
            return []
        raise


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


def _raw_connection():
    """A DB-API connection from the alias, outside Django's cursor wrapper.

    The startup check runs in `ready()`, where Django warns on queries.
    """
    wrapper = connections[ALIAS]
    return wrapper.get_new_connection(wrapper.get_connection_params())


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
            with closing(_raw_connection()) as conn, conn.cursor() as cursor:
                found += credential_problems(cursor)
        except ConnectionDoesNotExist:
            found.append(f"DATABASES has no '{ALIAS}' alias")
        except psycopg2.Error as exc:
            found.append(f"the research login cannot connect ({type(exc).__name__})")
    if found:
        raise ImproperlyConfigured(
            "; ".join(found) + " (AI_RESEARCH_READ_POLICY=database, IR-718; see backend/.env.example)")
