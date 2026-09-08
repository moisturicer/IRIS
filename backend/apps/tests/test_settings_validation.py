"""Configuration that must stop the process, not warn (IR-154).

Three of this ticket's acceptance criteria are about what the application
*refuses* to do, and a refusal is only real if something exercises it. The
decision logic lives in ``config.settings.validation`` as pure functions
precisely so it can be exercised here without booting Django four times with
four broken environments — the settings modules call those functions and turn
a non-empty result into ``ImproperlyConfigured``.

Two of the tests at the bottom are source-level sweeps rather than behavioural
assertions. That is deliberate: ``CORS_ALLOW_ALL_ORIGINS`` being *absent* and
no credential literal *remaining* are properties of the repository, and a
runtime assertion cannot see a literal sitting in a settings module that the
active environment happens not to load.

Needs no Django, no database and no network. The two sweeps do read files,
so they are not pure — and because a repo-root file is not visible from
inside the backend container, they skip with a stated reason there rather
than searching nothing and reporting a pass.
"""

import re
from pathlib import Path

import pytest

from config.settings.validation import missing_required, production_problems

# backend/apps/tests/test_settings_validation.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
SETTINGS_DIR = BACKEND_DIR / "config" / "settings"


# ---- missing_required ----------------------------------------------------


def test_a_fully_populated_environment_has_nothing_missing():
    assert missing_required({"SECRET_KEY": "s3cret", "DB_PASSWORD": "hunter2"}) == ()


def test_an_absent_value_is_missing():
    assert missing_required({"SECRET_KEY": None}) == ("SECRET_KEY",)


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_a_blank_value_is_missing_not_present(blank):
    """A secret set to the empty string is the failure mode a deployment
    actually hits — an unset shell variable interpolated into an env file
    yields ``KEY=``, not an absent key. Treating that as "present" is how a
    process boots with an empty ``SECRET_KEY``.
    """
    assert missing_required({"SECRET_KEY": blank}) == ("SECRET_KEY",)


@pytest.mark.parametrize("empty", [[], [""], ["  ", ""], ()])
def test_a_list_valued_setting_that_parsed_to_nothing_is_missing(empty):
    """``ALLOWED_HOSTS=`` through ``csv_list`` is ``[]``.

    It stops being a string at that point, and an is-it-blank check written
    only for strings calls it present — which is how a required list-valued
    setting gets required in name only.
    """
    assert missing_required({"ALLOWED_HOSTS": empty}) == ("ALLOWED_HOSTS",)


def test_a_populated_list_is_not_missing():
    assert missing_required({"ALLOWED_HOSTS": ["iris.cit.edu"]}) == ()


def test_every_missing_name_is_reported_not_just_the_first():
    """A deployment fixing one variable per restart is a bad afternoon."""
    problems = missing_required(
        {"SECRET_KEY": "", "DB_USER": "iris", "DB_PASSWORD": None}
    )

    assert problems == ("SECRET_KEY", "DB_PASSWORD")


# ---- production_problems -------------------------------------------------


def _production_kwargs(**overrides):
    """A production configuration with nothing wrong with it."""
    base = {
        "debug": False,
        "allowed_hosts": ["iris.cit.edu"],
        "cors_allowed_origins": ["https://iris.cit.edu"],
        "cors_allow_all_origins": False,
    }
    base.update(overrides)
    return base


def test_a_correct_production_configuration_has_no_problems():
    assert production_problems(**_production_kwargs()) == ()


def test_debug_true_in_production_is_a_problem():
    problems = production_problems(**_production_kwargs(debug=True))

    assert any("DEBUG" in p for p in problems), problems


def test_empty_allowed_hosts_is_a_problem():
    problems = production_problems(**_production_kwargs(allowed_hosts=[]))

    assert any("ALLOWED_HOSTS" in p for p in problems), problems


def test_allowed_hosts_of_only_blank_entries_is_a_problem():
    """``ALLOWED_HOSTS=`` split on commas yields ``['']``, which is truthy as a
    list and empty as a configuration."""
    problems = production_problems(**_production_kwargs(allowed_hosts=["", "  "]))

    assert any("ALLOWED_HOSTS" in p for p in problems), problems


def test_wildcard_allowed_hosts_is_a_problem():
    problems = production_problems(**_production_kwargs(allowed_hosts=["*"]))

    assert any("ALLOWED_HOSTS" in p for p in problems), problems


def test_cors_allow_all_origins_is_a_problem():
    """With ``CORS_ALLOW_CREDENTIALS = True`` set in base.py, this lets any
    origin make authenticated requests on a logged-in user's behalf.
    """
    problems = production_problems(**_production_kwargs(cors_allow_all_origins=True))

    assert any("CORS_ALLOW_ALL_ORIGINS" in p for p in problems), problems


def test_empty_cors_allowed_origins_is_a_problem():
    problems = production_problems(**_production_kwargs(cors_allowed_origins=[]))

    assert any("CORS_ALLOWED_ORIGINS" in p for p in problems), problems


def test_a_plaintext_http_origin_is_a_problem_in_production():
    """production.py sets ``SECURE_SSL_REDIRECT = True``, so an http origin in
    the allowlist is either dead configuration or a downgrade."""
    problems = production_problems(
        **_production_kwargs(cors_allowed_origins=["http://iris.cit.edu"])
    )

    assert any("http://iris.cit.edu" in p for p in problems), problems


def test_problems_accumulate_rather_than_short_circuiting():
    problems = production_problems(
        debug=True,
        allowed_hosts=[],
        cors_allowed_origins=[],
        cors_allow_all_origins=True,
    )

    assert len(problems) == 4, problems


# ---- repository-level sweeps ---------------------------------------------


def _code_lines(text: str) -> list[str]:
    """Lines with comments and blank lines removed.

    Both sweeps below look for something that must not be *configured*, and a
    line explaining why it is no longer configured mentions it by name.
    Searching raw text makes documenting the fix indistinguishable from
    reintroducing it — the first draft of these two tests failed on their own
    explanatory comments.
    """
    lines = []
    for raw in text.splitlines():
        code = raw.split("#", 1)[0].strip()
        if code:
            lines.append(code)
    return lines


# A module-level assignment, not a mention. production.py *reads* the name via
# globals().get() to assert it is absent, which is the opposite of setting it.
_ASSIGNS_ALLOW_ALL = re.compile(r"^CORS_ALLOW_ALL_ORIGINS\s*=")


def test_no_settings_module_sets_cors_allow_all_origins():
    """AC: ``CORS_ALLOW_ALL_ORIGINS`` is absent.

    Absent, not False — a setting that is merely defaulted off is one edit away
    from being on again, and development.py is exactly where it was on.
    """
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in SETTINGS_DIR.glob("*.py")
        if any(
            _ASSIGNS_ALLOW_ALL.match(line)
            for line in _code_lines(path.read_text(encoding="utf-8"))
        )
    ]

    assert offenders == [], (
        f"CORS_ALLOW_ALL_ORIGINS is assigned in {offenders}; with "
        "CORS_ALLOW_CREDENTIALS = True it permits credentialed cross-origin "
        "requests from anywhere"
    )


# The password the repository shipped in both Compose files and in
# backend/.env.example. Named here so this test fails if it comes back under
# any of those names, and so the rotation criterion has something executable
# behind it rather than a checkbox.
RETIRED_CREDENTIALS = ("iris_password", "change-me-in-production")

SEARCHED_FILES = (
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "backend/.env.example",
    "backend/config/settings/base.py",
    "backend/config/settings/development.py",
    "backend/config/settings/production.py",
)


def test_no_retired_credential_literal_remains_in_tracked_configuration():
    """AC: no credential literal remains in the repository.

    These values were committed, so they are burned regardless of whether the
    deployment still uses them — rotation is the other half of this criterion
    and is an operations step, recorded on the ticket.
    """
    present = [r for r in SEARCHED_FILES if (REPO_ROOT / r).exists()]
    missing = [r for r in SEARCHED_FILES if r not in present]
    # The backend container mounts only backend/ at /app, so the Compose files
    # are unreachable from inside it. Skipping says so; searching four of six
    # files and passing would report this criterion met on the strength of the
    # two files that never held the credential.
    if missing:
        pytest.skip(
            "not a full checkout — cannot see " + ", ".join(missing) + ". "
            "This sweep runs in CI and on a developer machine."
        )

    offenders = []
    for relative in present:
        for line in _code_lines((REPO_ROOT / relative).read_text(encoding="utf-8")):
            for credential in RETIRED_CREDENTIALS:
                if credential in line:
                    offenders.append(f"{relative}: {credential} -> {line}")

    assert offenders == [], f"retired credential literals still present: {offenders}"
