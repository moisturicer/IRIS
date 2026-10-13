from types import SimpleNamespace

import pytest

from apps.ai.providers.deadline import model_call_deadline
from apps.ai.providers.voyage import VoyageEmbeddingProvider

pytestmark = pytest.mark.django_required


def test_a_tool_embedding_request_uses_the_remaining_run_deadline(monkeypatch, settings):
    settings.VOYAGE_API_KEY = "test-key"
    requests = []
    def post(*args, **kwargs):
        requests.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"data": [{"data": [{"embedding": [1, 0]}]}]})
    monkeypatch.setattr("httpx.post", post)
    with model_call_deadline(3):
        assert VoyageEmbeddingProvider(dimensions=2).embed_query("floods") == [1, 0]
    assert 0 < requests[0]["timeout"] <= 3
