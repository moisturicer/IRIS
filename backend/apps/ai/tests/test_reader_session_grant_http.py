"""A reader session for the AI runtime, issued by Django (IR-722, ADR-049 §6)."""

import pytest
from django.db import connection
from django.urls import reverse

from apps.ai.grants import database
from apps.records.models import Record
from core.enums import PipelineStatus
from .corpus import make_user
from .grant_support import enable_grants

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def open_session(client, **body):
    return client.post(reverse("ai-runtime-grant"), body, format="json")


def test_a_signed_in_reader_gets_a_session_bound_to_them_alone(grant_keys, client_for):
    reader = make_user("session-grant@cit.edu")
    other = make_user("session-grant-other@cit.edu")
    response = open_session(client_for(reader), sub=other.pk, run="x")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"status", "grant", "expires_at"}
    claims = database.verify(body["grant"], "reader_session")
    assert claims["sub"] == reader.pk
    assert claims["gen"] == reader.credential_version
    assert claims["run"] is None and claims["cnv"] is None and claims["rec"] is None


def test_the_session_cannot_be_replayed_for_another_purpose(grant_keys, client_for):
    reader = make_user("session-grant-replay@cit.edu")
    token = open_session(client_for(reader)).json()["grant"]
    for purpose in ("record_read", "reader_run", "ingestion"):
        assert database.verify(token, purpose) is None


def test_the_session_reads_no_record(grant_keys, client_for):
    reader = make_user("session-grant-reads@cit.edu")
    Record.objects.create(title="Public paper", pipeline_status=PipelineStatus.PUBLISHED)
    token = open_session(client_for(reader)).json()["grant"]
    with database.research_identity(token, "reader_session"):
        with connection.cursor() as cursor:
            cursor.execute("SELECT iris_authz.research_record_ids()")
            assert cursor.fetchone()[0] == []


def test_a_departed_reader_is_refused_at_once(grant_keys, client_for):
    reader = make_user("session-grant-gone@cit.edu")
    token = open_session(client_for(reader)).json()["grant"]
    reader.credential_version += 1
    reader.save(update_fields=["credential_version"])
    assert database.verify(token, "reader_session") is None
    with connection.cursor() as cursor:
        def status(pk):
            cursor.execute("SELECT iris_authz.reader_status(%s)", [pk])
            return cursor.fetchone()[0]

        assert status(reader.pk) == "active"
        reader.is_active = False
        reader.save(update_fields=["is_active"])
        assert status(reader.pk) == "inactive"
        assert status(-1) == "gone"


def test_unavailable_authorization_is_a_safe_outcome(settings, client_for):
    reader = make_user("session-grant-off@cit.edu")
    settings.AI_RESEARCH_GRANTS = False
    off = open_session(client_for(reader))
    enable_grants(settings)
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM iris_authz.grant_key")
    unverifiable = open_session(client_for(reader))
    for response in (off, unverifiable):
        assert response.status_code == 200
        assert response.json() == {"status": "unavailable"}


def test_anonymous_readers_get_nothing(grant_keys, client):
    assert client.post(reverse("ai-runtime-grant"), {}, format="json").status_code in (401, 403)
