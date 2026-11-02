"""The same-origin edge gets only the authenticated reader's scoped grant (IR-730)."""

import pytest
from rest_framework.test import APIClient

from apps.ai.grants import database
from apps.records.models import PipelineStatus, Record
from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def test_edge_auth_issues_verified_reader_identity_without_a_service_secret(grant_db):
    client = APIClient()
    path = "/api/v1/ai/runtime/edge-grant/"
    assert client.get(path).status_code == 401
    user = make_user("edge-reader@cit.edu")
    client.force_authenticate(user)
    response = client.get(path)
    assert response.status_code == 204
    assert database.verify(response["X-IRIS-Reader-Grant"], "reader_session")["sub"] == user.pk
    assert "X-IRIS-Service-Secret" not in response
    assert client.get(path, HTTP_X_IRIS_RECORD="not-a-record").status_code == 400
    assert client.get(path, HTTP_X_IRIS_RECORD="9223372036854775808").status_code == 400
    assert client.get(path, HTTP_X_IRIS_RECORD="1234567").status_code == 404


def test_edge_scope_grants_only_readable_records_and_hides_other_records(grant_db):
    client = APIClient()
    client.force_authenticate(make_user("edge-scope@cit.edu"))
    path = "/api/v1/ai/runtime/edge-grant/"
    readable = Record.objects.create(title="Published scope", pipeline_status=PipelineStatus.PUBLISHED)
    hidden = Record.objects.create(title="Another reader's draft", pipeline_status=PipelineStatus.DRAFT)
    response = client.get(path, HTTP_X_IRIS_RECORD=str(readable.pk))
    assert response.status_code == 204
    claims = database.verify(response["X-IRIS-Reader-Grant"], "reader_session")
    assert claims["rec"] == readable.pk
    refused = client.get(path, HTTP_X_IRIS_RECORD=str(hidden.pk))
    missing = client.get(path, HTTP_X_IRIS_RECORD="9223372036854775807")
    assert refused.status_code == missing.status_code == 404
    assert refused.content == missing.content
