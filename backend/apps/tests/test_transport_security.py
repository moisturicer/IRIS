"""
IR-662: production HTTPS does not redirect-loop behind the TLS proxy.

Nothing in this repository terminates TLS: `frontend/nginx.conf` listens on
plain 8080, so TLS always ends in front of nginx. `SECURE_SSL_REDIRECT` with no
`SECURE_PROXY_SSL_HEADER` therefore saw every request as HTTP and redirected it
to HTTPS, forever.

**Seam: the real production settings module, in its own process**, because
`config.settings.production` refuses to import without its environment and a
test process has already chosen its settings. The requests go through the real
middleware stack and stop at it or at URL resolution, so no database is used.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
NGINX_CONF = BACKEND.parent / "frontend" / "nginx.conf"

PROBE = """
import json, django
django.setup()
from django.conf import settings
from django.test import Client

def ask(**headers):
    response = Client(raise_request_exception=False).get("/no-such-path/", **headers)
    return {"status": response.status_code, "location": response.get("Location", "")}

print("RESULT" + json.dumps({
    "plain": ask(),
    "forwarded_https": ask(HTTP_X_FORWARDED_PROTO="https"),
    "forwarded_http": ask(HTTP_X_FORWARDED_PROTO="http"),
    "session_cookie_secure": settings.SESSION_COOKIE_SECURE,
    "csrf_cookie_secure": settings.CSRF_COOKIE_SECURE,
}))
"""


@pytest.fixture(scope="module")
def production():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DEBUG": "False",
        "ALLOWED_HOSTS": "testserver",
        "CORS_ALLOWED_ORIGINS": "https://iris.example.edu",
    }
    done = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(l for l in done.stdout.splitlines() if l.startswith("RESULT"))
    return json.loads(line[len("RESULT"):])


def test_a_request_the_proxy_says_was_https_is_not_redirected(production):
    assert production["forwarded_https"]["status"] != 301, production["forwarded_https"]


def test_a_plain_request_is_redirected_to_https(production):
    assert production["plain"]["status"] == 301
    assert production["plain"]["location"].startswith("https://")


def test_a_request_the_proxy_says_was_http_is_redirected_to_https(production):
    assert production["forwarded_http"]["status"] == 301


def test_session_and_csrf_cookies_stay_secure(production):
    assert production["session_cookie_secure"] is True
    assert production["csrf_cookie_secure"] is True


def test_nginx_forwards_the_scheme_the_client_used():
    """
    Text, like the other nginx pins: the backend container has no nginx. With
    `$scheme` nginx always reported its own plain listener, http.
    """
    if not NGINX_CONF.exists():
        pytest.skip("frontend/nginx.conf is not mounted in the backend container")
    conf = NGINX_CONF.read_text(encoding="utf-8")
    forwarded = re.findall(r"proxy_set_header\s+X-Forwarded-Proto\s+(\S+);", conf)
    assert forwarded, "nginx no longer forwards X-Forwarded-Proto"
    assert set(forwarded) == {"$forwarded_proto"}
