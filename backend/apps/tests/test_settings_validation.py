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

from config.settings.validation import (
    missing_required, production_problems, recovery_problems, recovery_transport_problems,
)


def test_production_recovery_requires_https_origin_and_smtp_credentials():
    problems = recovery_transport_problems(
        frontend_url="http://localhost:5173", email_host="", email_user="",
        email_password="", sender="",
    )
    for name in ("FRONTEND_URL", "EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL"):
        assert any(name in problem for problem in problems)


@pytest.mark.parametrize("origin", [
    "https://iris.example.edu/path", "https://user@iris.example.edu", "https://iris.example.edu#token",
    "https://iris.example.edu?query", "https://iris.example.edu:bad",
])
def test_recovery_links_require_an_origin_without_paths_or_credentials(origin):
    assert recovery_transport_problems(
        frontend_url=origin, email_host="smtp.example.edu", email_user="iris@example.edu",
        email_password="test-only", sender="iris@example.edu",
    )


def test_complete_production_recovery_transport_is_valid():
    assert recovery_transport_problems(
        frontend_url="https://iris.example.edu", email_host="smtp.example.edu",
        email_user="iris@example.edu", email_password="test-only", sender="iris@example.edu",
    ) == ()

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


def test_a_plaintext_http_origin_is_allowed_for_now():
    """Deliberately NOT a problem.

    An https-only rule is the obvious next check and production.py does set
    SECURE_SSL_REDIRECT — but S-04 puts TLS termination out of scope (D-03),
    and this ticket's Definition of Done requires an interim deployment running
    with DEBUG=False. Refusing an http origin would stop that deployment
    booting at all. This test pins the decision so adding the rule is a
    deliberate change rather than a silent one.
    """
    assert (
        production_problems(
            **_production_kwargs(cors_allowed_origins=["http://iris.cit.edu"])
        )
        == ()
    )


def test_problems_accumulate_rather_than_short_circuiting():
    """Asserted by content, not by count — a count breaks whenever a message
    is added or reworded, which is not the property under test."""
    problems = production_problems(
        debug=True,
        allowed_hosts=[],
        cors_allowed_origins=[],
        cors_allow_all_origins=True,
    )

    joined = " | ".join(problems)
    for expected in (
        "DEBUG",
        "ALLOWED_HOSTS",
        "CORS_ALLOW_ALL_ORIGINS",
        "CORS_ALLOWED_ORIGINS is empty",
    ):
        assert expected in joined, (expected, problems)


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
    # The AC is "no credential literal remains in the repository", which is
    # wider than S-04's grep over docker-compose*.yml and backend/config/.
    # README.md shipped the password three times -- a CREATE USER statement, a
    # sample .env and a defaults table -- and that grep would never have seen
    # it.
    "README.md",
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


# ---- recovery_problems (ADR-045 §8, IR-642) --------------------------------

FERNET_KEY = "ZmRmZGZkZmRmZGZkZmRmZGZkZmRmZGZkZmRmZGZkZmQ="  # 32 bytes, not a real key


def recovery(**overrides):
    values = {
        "limits": {"RECOVERY_RESET_TTL_SECONDS": 1800, "RECOVERY_COOLDOWN_SECONDS": 60},
        "counter_hmac_key": "counter-key",
        "mail_encryption_keys": [FERNET_KEY],
        "secret_key": "django-secret",
        "retry_delays": (30, 120, 300),
    }
    values.update(overrides)
    return recovery_problems(**values)


def test_the_accepted_recovery_configuration_has_no_problems():
    assert recovery() == ()


@pytest.mark.parametrize("value", [0, -1, "60", None, True])
def test_a_recovery_limit_must_be_a_positive_whole_number(value):
    problems = recovery(limits={"RECOVERY_COOLDOWN_SECONDS": value})
    assert len(problems) == 1 and "RECOVERY_COOLDOWN_SECONDS" in problems[0]


@pytest.mark.parametrize("attempts, accepted", [(1, True), (4, True), (5, False)])
def test_mail_attempts_cannot_outrun_the_retry_schedule(attempts, accepted):
    # ADR-045 §6 fixes three retry delays: a fifth attempt would have no delay
    # to wait, and the worker would fail on it instead of at start-up.
    problems = recovery(limits={"RECOVERY_MAIL_MAX_ATTEMPTS": attempts})
    assert (problems == ()) is accepted
    if not accepted:
        assert "RECOVERY_MAIL_MAX_ATTEMPTS" in problems[0]


@pytest.mark.parametrize("key", ["", "   ", None])
def test_the_counter_key_is_required(key):
    assert any("RECOVERY_COUNTER_HMAC_KEY" in p for p in recovery(counter_hmac_key=key))


def test_the_counter_key_cannot_be_the_django_secret():
    assert recovery(counter_hmac_key="same", secret_key="same") != ()


@pytest.mark.parametrize("keys", [[], [""], ["not-a-key"], [FERNET_KEY, "short"]])
def test_every_mail_key_must_be_a_fernet_key(keys):
    assert any("RECOVERY_MAIL_ENCRYPTION_KEY" in p for p in recovery(mail_encryption_keys=keys))


def test_every_recovery_problem_is_reported_at_once():
    problems = recovery(limits={"A": 0, "B": 0}, counter_hmac_key="", mail_encryption_keys=[])
    assert len(problems) == 4


def test_the_settings_module_refuses_to_start_without_the_recovery_secrets():
    source = (SETTINGS_DIR / "base.py").read_text(encoding="utf-8")
    assert "recovery_problems(" in source
    assert "raise ImproperlyConfigured(" in source.split("_recovery_problems = recovery_problems(")[1]
