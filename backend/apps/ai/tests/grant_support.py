"""Shared setup for the research-grant suites (IR-717): keys, roles, a probe login."""

import base64
import secrets
import uuid
from contextlib import contextmanager
from datetime import timedelta

import psycopg2
import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

KEY_A = base64.urlsafe_b64encode(b"a" * 32).decode().rstrip("=")
KEY_B = base64.urlsafe_b64encode(b"b" * 32).decode().rstrip("=")
AUDIENCE = "iris-ai-runtime"
DEPLOYMENT = "ir717-test"


def enable_grants(settings, *, keys=f"k1:{KEY_A}", active="k1", ttl=300):
    settings.AI_RESEARCH_GRANTS = True
    settings.AI_RESEARCH_GRANT_KEYS = keys
    settings.AI_RESEARCH_GRANT_ACTIVE_KEY = active
    settings.AI_RESEARCH_GRANT_AUDIENCE = AUDIENCE
    settings.AI_RESEARCH_GRANT_DEPLOYMENT = DEPLOYMENT
    settings.AI_RESEARCH_GRANT_TTL_SECONDS = ttl


def can_create_roles() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
        return bool(cursor.fetchone()[0])


def require_role_privileges():
    if not can_create_roles():
        pytest.skip("restricted-role tests need CREATEROLE on the test database user (IR-717)")


@contextmanager
def probe_login(group="iris_ai_runtime"):
    """A throwaway LOGIN role that is only a member of `group`, and a raw connection as it."""
    name = f"iris_probe_{uuid.uuid4().hex[:10]}"
    password = secrets.token_urlsafe(16)
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{name}" LOGIN PASSWORD %s IN ROLE {group}', [password])
    params = connection.settings_dict
    conn = psycopg2.connect(
        host=params["HOST"] or "localhost", port=params["PORT"] or "5432",
        dbname=params["NAME"], user=name, password=password,
    )
    try:
        yield conn
    finally:
        conn.close()
        with connection.cursor() as cursor:
            cursor.execute(f'DROP ROLE IF EXISTS "{name}"')


@pytest.fixture
def grant_db(settings):
    """Grants on, keys installed, roles provisioned; keys removed afterwards."""
    require_role_privileges()
    enable_grants(settings)
    call_command("provision_research_roles")
    call_command("install_research_grant_keys")
    yield settings
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM iris_authz.grant_key")


def owned_run(user, *, record=None, state="queued", seconds=120):
    from apps.ai.models import AskRun, Conversation

    conversation = Conversation.objects.create(user=user, record=record)
    return AskRun.objects.create(
        user=user, conversation=conversation, state=state,
        deadline_at=timezone.now() + timedelta(seconds=seconds),
    )
