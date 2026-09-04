"""Test harness bootstrap.

The chunking domain is pure Python and needs nothing from this file. What this
file does is make the *Django-dependent* tests honest: they skip with a stated
reason when the backend dependencies or the database are unavailable, instead
of erroring at collection or, worse, appearing to pass.
"""

import socket

import pytest


def _backend_deps_installed() -> bool:
    try:
        import django  # noqa: F401
        import decouple  # noqa: F401
        import pgvector  # noqa: F401
    except ImportError:
        return False
    return True


def _database_reachable() -> bool:
    if not _backend_deps_installed():
        return False
    try:
        from django.conf import settings

        db = settings.DATABASES["default"]
        host = db.get("HOST") or "localhost"
        port = int(db.get("PORT") or 5432)
    except Exception:
        host, port = "localhost", 5432

    sock = socket.socket()
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pytest_collection_modifyitems(config, items):
    deps = _backend_deps_installed()
    db = _database_reachable() if deps else False

    skip_django = pytest.mark.skip(
        reason="backend dependencies are not installed in this environment"
    )
    skip_db = pytest.mark.skip(
        reason="no PostgreSQL with pgvector reachable in this environment"
    )

    for item in items:
        if "db_required" in item.keywords and not db:
            item.add_marker(skip_db)
        elif "django_required" in item.keywords and not deps:
            item.add_marker(skip_django)
