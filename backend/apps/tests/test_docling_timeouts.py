"""The two timeouts that govern one Docling conversion must agree (IR-249).

`DOCLING_TIMEOUT_SECONDS` is how long IRIS waits. `DOCLING_SERVE_MAX_SYNC_WAIT`
is how long docling-serve will keep a synchronous conversion alive before
returning 504 — and it is the binding one, because no client-side value can
extend a request the server has already abandoned.

They disagreed for as long as the Docling container had existed: the worker
waited 900 seconds while the server, with `MAX_SYNC_WAIT` unset and therefore
at its own default of 120, gave up after two minutes. Individually a 45-page
submission converts in roughly a minute, so every single-document run passed;
two uploaded together each slowed past the cap and both failed. Bulk ingestion
did not work at all, and the API reported 201 either way.

**Why this is a static test.** The extraction tests run against a fake
extractor with no container involved, so nothing in the suite can observe a
disagreement between two container settings. That is the same blind spot that
let IR-240's unrouted task ship green. Reading the compose files is what makes
the rule enforceable at all.

The server's wait is defined once, in `docling/compose.yml`, and both compose
files reach it with `extends` (IR-493). The test reads it there and checks that
each compose file extends that file, so a compose file that stopped doing so
fails here rather than silently running Docling at its default of 120 seconds.
"""

import os
import re
from pathlib import Path

import pytest

from testing.harness import strict_mode_requested

#: Repo root -- `backend/` is BASE_DIR, so the compose files are one level up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")
_DOCLING_COMPOSE = "docling/compose.yml"

#: A literal, or the default of `${DOCLING_MAX_SYNC_WAIT:-900}`.
_SERVER_WAIT = re.compile(
    r"DOCLING_SERVE_MAX_SYNC_WAIT=(?:\$\{DOCLING_MAX_SYNC_WAIT:-)?(\d+)"
)
_EXTENDS_DOCLING = re.compile(r"file:\s*docling/compose\.yml")
_CLIENT_WAIT = re.compile(r"DOCLING_TIMEOUT_SECONDS=(\d+)")


def _compose_text(name: str) -> str:
    """The compose file's text, or a skip -- unless skipping is forbidden.

    Mirrors `test_worker_boot.py`: a test that silently opts out wherever it is
    inconvenient is the "green but toothless" failure this kind of module
    exists to prevent, so `IRIS_REQUIRE_DB` turns the skip into a failure.
    """
    path = _REPO_ROOT / name
    if not path.is_file():
        message = (
            f"{name} not found at {path} -- this suite needs a full repo "
            "checkout, not the backend/ mount inside the container"
        )
        if strict_mode_requested(os.environ):
            pytest.fail(message)
        pytest.skip(message)
    return path.read_text(encoding="utf-8")


def test_the_docling_server_wait_is_configured_at_all():
    """Left unset it defaults to 120 seconds, which is under the time a real
    45-page submission takes when anything else is converting alongside it."""
    text = _compose_text(_DOCLING_COMPOSE)
    assert _SERVER_WAIT.search(text), (
        f"{_DOCLING_COMPOSE} does not set DOCLING_SERVE_MAX_SYNC_WAIT. Unset, "
        "docling-serve abandons a conversion after its own default of 120s and "
        "returns 504, whatever DOCLING_TIMEOUT_SECONDS says (IR-249)."
    )


@pytest.mark.parametrize("name", _COMPOSE_FILES)
def test_each_compose_file_runs_docling_from_the_shared_definition(name):
    """The wait only applies where the service extends `docling/compose.yml`."""
    assert _EXTENDS_DOCLING.search(_compose_text(name)), (
        f"{name} does not extend {_DOCLING_COMPOSE}, so the server wait defined "
        "there does not apply and docling-serve falls back to 120s (IR-249)."
    )


@pytest.mark.parametrize("name", _COMPOSE_FILES)
def test_the_client_and_server_waits_agree(name):
    """Raising one without the other is the bug this file exists to catch."""
    server = _SERVER_WAIT.search(_compose_text(_DOCLING_COMPOSE))
    client = _CLIENT_WAIT.search(_compose_text(name))
    assert server and client, f"{name} and {_DOCLING_COMPOSE} must declare both waits"

    assert server.group(1) == client.group(1), (
        f"{name}: docling-serve gives up at {server.group(1)}s while IRIS waits "
        f"{client.group(1)}s. The server's cap is the binding one -- a client "
        "timeout cannot extend a request the server has already ended. Keep "
        "them equal (IR-249)."
    )
