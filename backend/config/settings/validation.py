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


def _is_blank(value: object) -> bool:
    """A secret set to the empty string is not a secret that is present.

    This is the failure mode a deployment actually hits: an unset shell
    variable interpolated into an env file yields ``KEY=``, not an absent key.
    """
    return value is None or (isinstance(value, str) and not value.strip())


def missing_required(values: Mapping[str, object]) -> tuple[str, ...]:
    """The names in ``values`` that are absent or blank, in the order given."""
    return tuple(name for name, value in values.items() if _is_blank(value))


def non_blank(entries: Iterable[object]) -> tuple[str, ...]:
    """The entries that survive stripping.

    ``"".split(",")`` is ``[""]`` — truthy as a list, empty as a
    configuration. Every list-valued setting here goes through this so that
    ``ALLOWED_HOSTS=`` cannot read as "one host configured".
    """
    return tuple(
        str(entry).strip() for entry in entries if not _is_blank(entry)
    )


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
    for origin in origins:
        if not origin.startswith("https://"):
            problems.append(
                f"CORS_ALLOWED_ORIGINS contains a non-https origin: {origin}. "
                "production.py sets SECURE_SSL_REDIRECT, so this is either "
                "dead configuration or a downgrade."
            )

    return tuple(problems)
