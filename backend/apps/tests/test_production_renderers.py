"""
IR-925: production answers the API in JSON only, never DRF's browsable API.

The browsable API is a developer tool: an HTML page for every endpoint that
lists its methods and fields and offers forms to call it. DRF serves it to any
request that accepts HTML, which is every browser, unless the renderers are
narrowed. Development keeps it; production must not.

**Seam: the real production settings module, in its own process**, as in
`test_transport_security.py`, because `config.settings.production` refuses to
import without its environment and a test process has already chosen its
settings. The requests go through the real middleware stack to a protected
route, asked signed out, so the view answers 401 before it reads the database
or the cache. DRF renders that 401 with the same renderers as any other reply.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

PROBE = """
import json, django
django.setup()
from django.test import Client

def ask(accept, path="/api/v1/records/"):
    response = Client(raise_request_exception=False).get(
        path, HTTP_ACCEPT=accept, HTTP_X_FORWARDED_PROTO="https",
    )
    body = response.content.decode("utf-8", "replace")
    return {
        "status": response.status_code,
        "content_type": response.get("Content-Type", ""),
        "browsable": "Django REST framework" in body or "<html" in body.lower(),
    }

BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

print("RESULT" + json.dumps({
    "browser": ask(BROWSER),
    "html_only": ask("text/html"),
    "json": ask("application/json"),
    # DRF's `?format=api` asks for the browsable renderer by name.
    "format_api": ask(BROWSER, path="/api/v1/records/?format=api"),
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
        "REGISTRATION_EMAIL_DOMAINS": "cit.edu",
        "TRUSTED_PROXY_COUNT": "2",
        "FRONTEND_URL": "https://iris.example.edu",
        "EMAIL_HOST": "smtp.example.edu",
        "EMAIL_HOST_USER": "iris@example.edu",
        "EMAIL_HOST_PASSWORD": "test-only",
        "LLAMAPARSE_API_KEY": "llx-test",
        "LLAMAPARSE_VERSION": "2026-09-28",
    }
    done = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(l for l in done.stdout.splitlines() if l.startswith("RESULT"))
    return json.loads(line[len("RESULT"):])


def test_a_browser_gets_json_not_the_browsable_page(production):
    answer = production["browser"]
    assert answer["status"] == 401, answer
    assert answer["content_type"].startswith("application/json"), answer
    assert not answer["browsable"], answer


def test_asking_for_html_alone_is_refused_in_json(production):
    answer = production["html_only"]
    assert answer["status"] == 406, answer
    assert answer["content_type"].startswith("application/json"), answer
    assert not answer["browsable"], answer


def test_naming_the_browsable_renderer_in_the_url_finds_nothing(production):
    answer = production["format_api"]
    assert answer["status"] == 404, answer
    assert not answer["browsable"], answer


def test_a_json_client_is_answered_as_before(production):
    answer = production["json"]
    assert answer["status"] == 401, answer
    assert answer["content_type"].startswith("application/json"), answer
