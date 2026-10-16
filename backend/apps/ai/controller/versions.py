"""What a run pins when it starts (ADR-042, spec §2, §10).

There is no setting or reader choice between engines. A release changes
`NEW_RUN_ENGINE`; a rollback is reverting that line, and a queued run keeps
the engine pinned in its request.
"""

LEGACY_ENGINE = "lanes-v1"
CONTROLLER_ENGINE = "controller-v1"
ENGINES = (LEGACY_ENGINE, CONTROLLER_ENGINE)

#: Unchanged until the release gates in ADR-042 pass (IR-594..IR-597).
NEW_RUN_ENGINE = LEGACY_ENGINE

PROTOCOL_VERSION = "1"
PLAN_PROMPT_VERSION = "plan-1"
ANSWER_PROMPT_VERSION = "answer-1"


def pin(engine: str) -> dict:
    """The versions a run records; a legacy run needs only its engine."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}")
    if engine == LEGACY_ENGINE:
        return {"engine": engine}
    return {"engine": engine, "protocol": PROTOCOL_VERSION, "prompt": PLAN_PROMPT_VERSION,
            "answer_prompt": ANSWER_PROMPT_VERSION}


def supported_engine(versions) -> str:
    """Resolve only pins this release can execute; absent pins predate the controller."""
    if versions is None:
        return LEGACY_ENGINE
    if not isinstance(versions, dict):
        raise ValueError("invalid run pin")
    engine = versions.get("engine", LEGACY_ENGINE)
    if engine not in ENGINES:
        raise ValueError("unsupported engine")
    if engine == CONTROLLER_ENGINE and any(
        versions.get(key) != value for key, value in pin(engine).items()
    ):
        raise ValueError("unsupported controller versions")
    return engine
