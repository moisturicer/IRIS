"""Opening and renewing a research session over HTTP (IR-717)."""

import uuid

import pytest
from django.db import connection
from django.urls import reverse

from apps.ai.grants import database
from apps.ai.models import AskRun
from .corpus import make_user
from .grant_support import grant_keys, owned_run  # noqa: F401

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def open_session(client, run_id, **body):
    return client.post(reverse("ai-ask-run-grant", args=[run_id]), body, format="json")


def renew(client, run_id, grant):
    return client.post(reverse("ai-ask-run-grant-renew", args=[run_id]), {"grant": grant}, format="json")


def test_a_reader_opens_a_session_on_their_own_run(grant_keys, client_for):
    reader = make_user("http-grant@cit.edu")
    other = make_user("http-grant-other@cit.edu")
    run = owned_run(reader, seconds=60)
    response = open_session(client_for(reader), run.pk, user=other.pk, sub=other.pk)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"status", "run_id", "grant", "expires_at"}
    assert body["status"] == "granted"
    claims = database.verify(body["grant"], "reader_run")
    # The client-supplied reader id is ignored.
    assert claims["sub"] == reader.pk
    assert claims["run"] == str(run.pk)
    assert claims["exp"] <= int(run.deadline_at.timestamp())


def test_foreign_and_missing_runs_look_the_same_and_create_nothing(grant_keys, client_for):
    reader = make_user("http-grant-foreign@cit.edu")
    owner = make_user("http-grant-owner@cit.edu")
    foreign = owned_run(owner)
    before = AskRun.objects.count()
    missing = open_session(client_for(reader), uuid.uuid4())
    theirs = open_session(client_for(reader), foreign.pk)
    assert missing.status_code == theirs.status_code == 404
    assert missing.json() == theirs.json()
    assert AskRun.objects.count() == before


def test_an_ended_run_opens_no_session(grant_keys, client_for):
    reader = make_user("http-grant-ended@cit.edu")
    run = owned_run(reader, state="succeeded")
    response = open_session(client_for(reader), run.pk)
    assert response.status_code == 409
    assert response.json() == {"status": "ended"}


def test_unavailable_authorization_is_a_safe_outcome(settings, client_for):
    from .grant_support import enable_grants

    reader = make_user("http-grant-off@cit.edu")
    run = owned_run(reader)
    settings.AI_RESEARCH_GRANTS = False
    off = open_session(client_for(reader), run.pk)
    # On, but the verifier holds no key: Django must not hand out a dead grant.
    enable_grants(settings)
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM iris_authz.grant_key")
    unverifiable = open_session(client_for(reader), run.pk)
    for response in (off, unverifiable):
        assert response.status_code == 200
        assert response.json() == {"status": "unavailable"}


def test_renewal_rechecks_the_reader_and_never_extends_the_run(grant_keys, client_for):
    reader = make_user("http-grant-renew@cit.edu")
    run = owned_run(reader, seconds=45)
    client = client_for(reader)
    first = open_session(client, run.pk).json()["grant"]
    renewed = renew(client, run.pk, first)
    assert renewed.status_code == 201
    claims = database.verify(renewed.json()["grant"], "reader_run")
    # The 45s deadline, not the 300s TTL, bounds the renewal.
    assert claims["exp"] == int(run.deadline_at.timestamp())
    assert AskRun.objects.get(pk=run.pk).deadline_at == run.deadline_at

    assert renew(client, run.pk, first[:-3] + "AAA").json() == {"status": "unauthorized"}
    assert renew(client, run.pk, "").json() == {"status": "invalid"}
    other = make_user("http-grant-thief@cit.edu")
    assert renew(client_for(other), run.pk, first).status_code == 404

    reader.credential_version += 1
    reader.save(update_fields=["credential_version"])
    refused = renew(client_for(reader), run.pk, first)
    assert refused.status_code == 403
    assert refused.json() == {"status": "unauthorized"}
