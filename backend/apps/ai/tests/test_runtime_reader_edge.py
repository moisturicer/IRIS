"""The same-origin edge gets only the authenticated reader's scoped grant (IR-730)."""

import pytest
from rest_framework.test import APIClient

from apps.ai.grants import database
from apps.records.models import PipelineStatus, Record
from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def switch_on(settings):
    """The runtime reader path is a deployment decision, off by default (IR-863)."""
    settings.AI_RUNTIME_READER = True


def test_edge_auth_issues_verified_reader_identity_without_a_service_secret(grant_db, switch_on):
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


def test_edge_scope_grants_only_readable_records_and_hides_other_records(grant_db, switch_on):
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


@pytest.mark.parametrize("enabled, path", [(False, "django"), (True, "runtime")])
def test_the_deployment_switch_alone_names_the_reader_path(enabled, path, settings):
    settings.AI_RUNTIME_READER = enabled
    client = APIClient()
    assert client.get("/api/v1/ai/reader/").status_code == 401
    client.force_authenticate(make_user("reader-path@cit.edu"))
    # Nothing the browser sends can change the answer (IR-863).
    response = client.get("/api/v1/ai/reader/?path=runtime", HTTP_X_IRIS_READER_PATH="runtime")
    assert response.status_code == 200
    assert response.json() == {"path": path}
    assert response["Cache-Control"] == "no-store"


def test_with_the_switch_off_the_edge_issues_no_grant(grant_db, settings):
    settings.AI_RUNTIME_READER = False
    client = APIClient()
    client.force_authenticate(make_user("edge-off@cit.edu"))
    response = client.get("/api/v1/ai/runtime/edge-grant/")
    # 403 is a code nginx's auth_request passes on; it refuses the proxied route.
    assert response.status_code == 403
    assert "X-IRIS-Reader-Grant" not in response
