"""
The source-scan helper reads the project's code and nothing else (IR-338).

Every source-scan guard in the backend walks a directory tree through
`source_files.python_sources`. Before it, each guard had its own inline
filter, only one of them excluded `.venv` and none excluded `venv/`, so a
developer with a local environment inside `backend/` got false failures --
a UnicodeDecodeError on a third-party file -- that CI never saw.

No database and no Django settings -- it reads files.
"""

from pathlib import Path

from testing.source_files import python_sources

BACKEND = Path(__file__).resolve().parents[2]

#: Not valid UTF-8, as the cp1252 file in a real `venv/` that started this was.
NOT_UTF8 = b"# -*- coding: cp1252 -*-\nquote = '\x93'\n"


def _write(path: Path, content: bytes = b"x = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _relative(paths, root):
    return {p.relative_to(root).as_posix() for p in paths}


def test_a_real_source_file_is_included(tmp_path):
    _write(tmp_path / "apps" / "records" / "models.py")

    assert _relative(python_sources(tmp_path), tmp_path) == {"apps/records/models.py"}


def test_local_environments_are_excluded_and_never_read(tmp_path):
    _write(tmp_path / "apps" / "views.py")
    for env in ("venv", ".venv", "env"):
        _write(tmp_path / env / "Lib" / "site-packages" / "xlwt" / "Formatting.py", NOT_UTF8)

    found = python_sources(tmp_path)

    assert _relative(found, tmp_path) == {"apps/views.py"}
    for path in found:
        path.read_text(encoding="utf-8")


def test_a_folder_marked_with_pyvenv_cfg_is_excluded_whatever_its_name(tmp_path):
    _write(tmp_path / "apps" / "views.py")
    _write(tmp_path / "my-python" / "pyvenv.cfg", b"home = C:\\Python314\n")
    _write(tmp_path / "my-python" / "Lib" / "thing.py", NOT_UTF8)

    assert _relative(python_sources(tmp_path), tmp_path) == {"apps/views.py"}


def test_caches_and_installed_packages_are_excluded(tmp_path):
    _write(tmp_path / "apps" / "views.py")
    _write(tmp_path / "apps" / "__pycache__" / "views.py")
    _write(tmp_path / "site-packages" / "pkg.py")
    _write(tmp_path / "node_modules" / "pkg" / "build.py")

    assert _relative(python_sources(tmp_path), tmp_path) == {"apps/views.py"}


def test_migrations_and_tests_are_kept_for_each_guard_to_decide(tmp_path):
    _write(tmp_path / "apps" / "records" / "migrations" / "0001_initial.py")
    _write(tmp_path / "apps" / "records" / "tests" / "test_models.py")

    assert _relative(python_sources(tmp_path), tmp_path) == {
        "apps/records/migrations/0001_initial.py",
        "apps/records/tests/test_models.py",
    }


def test_a_pattern_narrows_the_file_names(tmp_path):
    _write(tmp_path / "apps" / "test_views.py")
    _write(tmp_path / "apps" / "views.py")

    found = python_sources(tmp_path, pattern="test_*.py")

    assert _relative(found, tmp_path) == {"apps/test_views.py"}


def test_the_real_project_scan_finds_real_source():
    """A guard on the guards: none of them can pass by scanning nothing."""
    found = _relative(python_sources(BACKEND), BACKEND)

    assert "apps/records/models.py" in found
    assert "config/settings/base.py" in found
    assert not any(part in {"venv", ".venv", "__pycache__"} for p in found for part in p.split("/"))
