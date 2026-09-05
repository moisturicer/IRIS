"""The import smoke test (IR-82).

Every one of the defects that has stopped IRIS running so far — an undefined
name in a view, a URLconf that fails to import — is machine-detectable and
none of them was machine-detected, because nothing imported the project the
way Django itself does at boot. This is that check, as a test rather than a
manual `manage.py check`.

Marked ``django_required`` so it skips cleanly, rather than erroring, in an
environment with no Django installed — see ``conftest.py``.
"""

import pytest

pytestmark = pytest.mark.django_required


def test_root_urlconf_resolves_without_error():
    """Forces Django to import every URLconf module reachable from the root,
    including every app's ``urls.py`` and everything each one imports.

    This is precisely the check that catches an undefined name in a view: a
    broken import anywhere in that chain raises here, at collection-adjacent
    time, instead of silently at the first real request.
    """
    from django.urls import get_resolver

    resolver = get_resolver()

    assert resolver.url_patterns, "the root URLconf resolved to no patterns at all"


def test_django_setup_completes_and_apps_are_ready():
    """`django.apps.apps.check_apps_ready()` raises unless every INSTALLED_APPS
    entry imported and registered cleanly — a broader net than the URLconf
    alone, since a model or admin registration can fail independently of any
    view.
    """
    from django.apps import apps

    apps.check_apps_ready()
    assert apps.get_app_configs(), "no Django app registered — INSTALLED_APPS is empty"


def test_management_commands_are_discoverable():
    """A smoke check on ``manage.py`` itself: if `config.settings` cannot be
    loaded, or `DJANGO_SETTINGS_MODULE` is wrong, this is where it shows up
    without needing to shell out to a subprocess.
    """
    from django.core.management import get_commands

    commands = get_commands()
    assert "migrate" in commands
    assert "makemigrations" in commands
