"""The gateway serves nobody without the shared service secret (IR-156).

ADR-014 precondition 1. This is the whole of the gateway's authentication: it
holds a provider API key, and ADR-014 is explicit that an unauthenticated
service holding a vendor credential is not a partial deployment — there is no
middle state.

The suite also pins the two things easiest to get wrong when adding auth:
`/health` must stay open, because Compose needs it before any secret is
exchanged; and an *unconfigured* secret must fail closed, because a gateway
that starts with no secret and serves everything looks healthy while being the
exact deployment the precondition forbids.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

SECRET = "test-secret-not-a-real-one"
HEADER = "x-iris-service-secret"


def _client(monkeypatch, secret: str | None):
    """Rebuild the app with a given configured secret.

    `settings` is module-level and read at import, so the module is reloaded
    rather than mutated — patching the object in place would leave the next
    test observing this one's value.
    """
    import ai.infrastructure.settings as settings_module

    if secret is None:
        monkeypatch.delenv("SERVICE_SECRET", raising=False)
    else:
        monkeypatch.setenv("SERVICE_SECRET", secret)
    importlib.reload(settings_module)

    import ai.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


class TestUnauthenticatedRequests:
    def test_the_root_is_refused_without_a_secret(self, monkeypatch):
        """`/` is not public. An unauthenticated root that names the service is
        free reconnaissance for anything that reaches the network."""
        assert _client(monkeypatch, SECRET).get("/").status_code == 401

    def test_an_api_route_is_refused_without_a_secret(self, monkeypatch):
        r = _client(monkeypatch, SECRET).post("/api/v1/ai/ask", json={"query": "hi"})
        assert r.status_code == 401

    def test_a_wrong_secret_is_refused(self, monkeypatch):
        r = _client(monkeypatch, SECRET).get("/", headers={HEADER: "wrong"})
        assert r.status_code == 401

    def test_an_empty_secret_header_is_refused(self, monkeypatch):
        r = _client(monkeypatch, SECRET).get("/", headers={HEADER: ""})
        assert r.status_code == 401

    def test_a_prefix_of_the_secret_is_refused(self, monkeypatch):
        """Guards the comparison itself: a truncated secret must not pass, and
        the comparison is `hmac.compare_digest` so it does not leak the prefix
        through timing either."""
        r = _client(monkeypatch, SECRET).get("/", headers={HEADER: SECRET[:-1]})
        assert r.status_code == 401


class TestAuthenticatedRequests:
    def test_the_correct_secret_is_accepted(self, monkeypatch):
        r = _client(monkeypatch, SECRET).get("/", headers={HEADER: SECRET})
        assert r.status_code == 200

    def test_health_is_open_without_a_secret(self, monkeypatch):
        """Compose's healthcheck runs before any secret is exchanged, and the
        response reveals only liveness."""
        r = _client(monkeypatch, SECRET).get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"


class TestUnconfiguredGateway:
    """An unconfigured secret must fail closed, not open."""

    @pytest.mark.parametrize("path", ["/", "/api/v1/ai/ask"])
    def test_every_route_refuses_when_no_secret_is_configured(self, monkeypatch, path):
        client = _client(monkeypatch, "")
        r = client.get(path) if path == "/" else client.post(path, json={"query": "hi"})
        assert r.status_code == 503

    def test_health_still_answers_when_no_secret_is_configured(self, monkeypatch):
        """Otherwise a misconfigured gateway is indistinguishable from a dead
        one, and Compose reports it unhealthy instead of misconfigured."""
        assert _client(monkeypatch, "").get("/health").status_code == 200


class TestNoCors:
    """ADR-014 precondition 3. A browser is not a client of this service."""

    def test_no_cors_middleware_is_installed(self, monkeypatch):
        import ai.main as main_module

        _client(monkeypatch, SECRET)
        names = [m.cls.__name__ for m in main_module.app.user_middleware]
        assert "CORSMiddleware" not in names, names

    def test_a_cross_origin_preflight_is_not_granted(self, monkeypatch):
        """The behavioural half: no `access-control-allow-origin` comes back,
        whatever middleware is or is not installed."""
        r = _client(monkeypatch, SECRET).options(
            "/",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}
