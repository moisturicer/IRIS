"""Reading inputs and writing run files for the IR-550 pilot commands.

A run file names the commit its code came from and is written once to
``docs/evaluation/runs/``. The evaluating user's JWT is read here and goes
only into an ``Authorization`` header: it is never printed or written.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import CommandError

# The one provenance rule every run file shares (IR-394), re-exported publicly.
from apps.ai.management.commands.eval_retrieval import _git_commit as git_commit

TOKEN_ENV = "IRIS_EVAL_TOKEN"


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError(f"cannot read {path}: {exc}") from None


def file_digest(path) -> str:
    """SHA-256 of a labels file as given, so a re-labelled file is a different run."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unknown"


def eval_token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise CommandError(f"{TOKEN_ENV} must hold the evaluating user's JWT")
    return token


def write_run(out_dir, name: str, record: dict) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(out_dir) / f"{stamp}-{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"commit": git_commit(), **record}, indent=2) + "\n",
                   encoding="utf-8")
    return out


def write_json(path, value) -> None:
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
