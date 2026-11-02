"""The `slow` marker (IR-835).

Migration tests migrate the schema backwards and forwards, 7-20s each, so they
are marked by filename here rather than one by one. Other slow tests carry
``@pytest.mark.slow`` themselves. ``pytest -m "not slow"`` skips them locally;
CI selects nothing and runs everything.
"""

import pytest

MIGRATION_TEST_SUFFIX = "_migration.py"


def is_migration_test(nodeid: str) -> bool:
    return nodeid.split("::", 1)[0].endswith(MIGRATION_TEST_SUFFIX)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    # tryfirst: the marks must exist before `-m` deselects.
    for item in items:
        if is_migration_test(item.nodeid):
            item.add_marker(pytest.mark.slow)
