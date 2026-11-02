"""Configuration checks, as functions that return problems (IR-154).

The settings modules decide *policy* — which variables are mandatory, what a
production deployment may look like. This module decides *nothing*; it reports
what is wrong with a set of values it is handed, and the caller raises. That
split exists so the rules can be tested against crafted inputs rather than by
booting Django once per broken environment, which is the only way anyone
actually verifies a fail-fast path.

Every function returns **all** the problems it finds, never the first. A
deployment that fixes one variable per restart is a bad afternoon, and a
half-configured process that starts is worse than one that refuses.

Pure: no Django, no I/O, no environment access, no clock.
"""

from typing import Iterable, Mapping, Sequence


def non_blank(entries: Iterable[object]) -> tuple[str, ...]:
    """The entries that survive stripping.

    ``"".split(",")`` is ``[""]`` — truthy as a list, empty as a
    configuration. Every list-valued setting here goes through this so that
    ``ALLOWED_HOSTS=`` cannot read as "one host configured".
    """
    return tuple(
        str(entry).strip() for entry in entries if not _is_blank(entry)
    )


def _is_blank(value: object) -> bool:
    """A value that is set to nothing is not a value that is present.

    Two failure modes, both of which a deployment actually hits. A secret set
    to the empty string: an unset shell variable interpolated into an env file
    yields ``KEY=``, not an absent key. And a list-valued variable that parsed
    to nothing: ``ALLOWED_HOSTS=`` read through ``csv_list`` is ``[]``, which
    is exactly as unconfigured as an absent key and must not read as present
    merely because it is no longer a string.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, frozenset)):
        return not non_blank(value)
    return False


def missing_required(values: Mapping[str, object]) -> tuple[str, ...]:
    """The names in ``values`` that are absent or blank, in the order given."""
    return tuple(name for name, value in values.items() if _is_blank(value))


def production_problems(
    *,
    debug: bool,
    allowed_hosts: Sequence[object],
    cors_allowed_origins: Sequence[object],
    cors_allow_all_origins: bool,
) -> tuple[str, ...]:
    """What is wrong with this configuration for a publicly reachable deployment.

    Keyword-only on purpose: four values, three of them list-shaped, is exactly
    the signature where a positional swap type-checks and silently inverts a
    security check.
    """
    problems: list[str] = []

    if debug:
        problems.append(
            "DEBUG is True in production — it serves tracebacks containing "
            "settings values, including secrets, to anyone who triggers a 500."
        )

    hosts = non_blank(allowed_hosts)
    if not hosts:
        problems.append(
            "ALLOWED_HOSTS is empty — Django refuses every request without it, "
            "and a value inherited from the development default is not a "
            "production configuration."
        )
    elif "*" in hosts:
        problems.append(
            "ALLOWED_HOSTS contains '*' — that disables the Host header check "
            "entirely, which is what it exists to perform."
        )

    if cors_allow_all_origins:
        problems.append(
            "CORS_ALLOW_ALL_ORIGINS is enabled — combined with "
            "CORS_ALLOW_CREDENTIALS it lets any origin make authenticated "
            "requests on a logged-in user's behalf."
        )

    origins = non_blank(cors_allowed_origins)
    if not origins:
        problems.append(
            "CORS_ALLOWED_ORIGINS is empty — set it to the deployed frontend "
            "origin."
        )
    # No https-only rule here on purpose. It is the obvious next check, and
    # production.py does set SECURE_SSL_REDIRECT — but S-04 puts TLS
    # termination out of scope (D-03), and this ticket's Definition of Done
    # requires an interim deployment running with DEBUG=False. Refusing an
    # http origin would stop that deployment booting at all. Worth adding the
    # day TLS lands, not before.

    return tuple(problems)


def recovery_problems(
    *,
    limits: Mapping[str, object],
    counter_hmac_key: object,
    mail_encryption_keys: Sequence[object],
    secret_key: object,
    retry_delays: Sequence[int],
) -> tuple[str, ...]:
    """What is wrong with ADR-045 §8's account-recovery configuration (IR-642).

    ``limits`` maps each numeric setting's name to its parsed value; every one
    must be a positive integer, because a zero or negative limit would switch a
    protection off without anyone deciding to. The counter key must be set and
    must not be ``SECRET_KEY`` reused. Each mail key must be a Fernet key: 32
    bytes, urlsafe base64 -- checked by length and alphabet here, so this
    module stays free of the cryptography import. Mail attempts cannot exceed
    one more than ``retry_delays``: an attempt with no delay to wait would
    fail in the worker rather than here.
    """
    problems: list[str] = []

    for name, value in limits.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            problems.append(f"{name} must be a positive whole number, not {value!r}.")

    attempts = limits.get("RECOVERY_MAIL_MAX_ATTEMPTS")
    if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > len(retry_delays) + 1:
        problems.append(
            f"RECOVERY_MAIL_MAX_ATTEMPTS is {attempts}, but only "
            f"{len(retry_delays)} retry delays exist; use at most {len(retry_delays) + 1}."
        )

    if _is_blank(counter_hmac_key):
        problems.append(
            "RECOVERY_COUNTER_HMAC_KEY is not set. It keys the recipient "
            "identifiers recovery limits count by, and has no default."
        )
    elif not _is_blank(secret_key) and str(counter_hmac_key).strip() == str(secret_key).strip():
        problems.append(
            "RECOVERY_COUNTER_HMAC_KEY must be a separate secret from SECRET_KEY."
        )

    keys = non_blank(mail_encryption_keys)
    if not keys:
        problems.append(
            "RECOVERY_MAIL_ENCRYPTION_KEY is not set. It encrypts pending "
            "recovery mail, and has no default."
        )
    for index, key in enumerate(keys, start=1):
        if not _looks_like_fernet_key(key):
            problems.append(
                f"RECOVERY_MAIL_ENCRYPTION_KEY entry {index} is not a Fernet key "
                "(44 characters of urlsafe base64 encoding 32 bytes)."
            )

    return tuple(problems)


def _looks_like_fernet_key(key: str) -> bool:
    import base64
    import binascii

    if len(key) != 44:
        return False
    try:
        return len(base64.urlsafe_b64decode(key.encode("ascii"))) == 32
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return False


def recovery_transport_problems(*, frontend_url, email_host, email_user, email_password, sender):
    """Production recovery links and mail must have a usable fixed destination."""
    from urllib.parse import urlsplit

    problems = []
    try:
        origin = urlsplit(frontend_url)
        valid = (
            origin.scheme == "https" and bool(origin.hostname)
            and origin.username is None and origin.password is None
            and not origin.path and not origin.query and not origin.fragment
            and (origin.port is None or 0 < origin.port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        problems.append("FRONTEND_URL must be a fixed HTTPS origin without a path, query or credentials.")
    for name, value in (
        ("EMAIL_HOST", email_host), ("EMAIL_HOST_USER", email_user),
        ("EMAIL_HOST_PASSWORD", email_password), ("DEFAULT_FROM_EMAIL", sender),
    ):
        if _is_blank(value):
            problems.append(f"{name} must be set for recovery email delivery.")
    return tuple(problems)
