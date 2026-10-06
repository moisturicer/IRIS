"""
The one way a source-scan guard lists the project's Python files (IR-338).

A guard that reads source -- "nothing outside these modules names the
policy", "no bare workflow literal" -- must read the project's own code and
nothing else. Each guard used to walk its tree with its own inline filter;
only one excluded `.venv`, none excluded `venv/`, so a developer with a local
environment inside `backend/` hit a UnicodeDecodeError on a third-party file
that CI, which has no such folder, never saw.

Skipped folders are pruned during the walk rather than filtered afterwards, so
an environment is never descended into at all. A name matches at any depth,
which would also hide a project folder that happened to be called `env`;
`apps/tests/test_source_files.py` fails if one ever appears. `root` itself is
never tested for `pyvenv.cfg` -- a guard is pointed at project code, not into
an environment. `migrations` and `tests` are
**not** skipped here: whether a guard reads them is that guard's decision, and
several deliberately do.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

#: Folder names that are never project source. `env` is the third common name
#: for a local environment; any other name is caught by its `pyvenv.cfg`.
SKIPPED_DIRS = frozenset({"venv", ".venv", "env", "__pycache__", "site-packages", "node_modules"})


def _is_skipped(directory: Path) -> bool:
    return directory.name in SKIPPED_DIRS or (directory / "pyvenv.cfg").exists()


def python_sources(root: str | os.PathLike[str], pattern: str = "*.py") -> list[Path]:
    """Every file under `root` whose name matches `pattern`, sorted, outside skipped folders."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [name for name in dirnames if not _is_skipped(here / name)]
        found.extend(here / name for name in filenames if fnmatch(name, pattern))
    return sorted(found)
