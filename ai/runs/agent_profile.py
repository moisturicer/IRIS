"""The AGENT deployment profile, read fail-closed at worker start (IR-862).

`RUNS_EXECUTOR=agent` pins new runs to IR-728's research Conversation. It
then requires the pinned model, per-depth `Bounds` and `Reserves`, the
IR-860 provider declaration and every admission limit. Nothing defaults and
nothing here is approved; a refusal names the key, never its value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from typing import Mapping, Optional

from ai.admission.limits import Limits, NotConfigured, read as read_limits
from ai.agent.budget import Bounds, profiles as checked_profiles
from ai.agent.compaction import Compaction
from ai.agent.context import Reserves
from ai.agent.protocol import Pin
from ai.infrastructure import agent_config
from ai.runs import config as runs_config

REQUIRED = ("RUNS_AGENT_MODEL", "RUNS_AGENT_BOUNDS", "RUNS_AGENT_RESERVES")


@dataclass(frozen=True)
class AgentProfile:
    pin: Pin
    bounds: Mapping[str, Bounds]
    reserves: Reserves
    provider: agent_config.AgentProviderConfig
    limits: Limits
    #: None never compacts (IR-734).
    compaction: Optional[Compaction] = None
    #: "enforce" repairs or trims a failing draft; "flag" delivers it and notes what it could not match; "advisory" only logs.
    checks: str = "enforce"


def _json(values, name, shape: str):
    try:
        return json.loads(str(getattr(values, name, "") or ""))
    except ValueError:
        raise NotConfigured(f"{name} must be {shape}") from None


def _record(cls, name, raw):
    names = {f.name for f in fields(cls)}
    if not isinstance(raw, dict) or set(raw) != names:
        raise NotConfigured(f"{name} must state exactly {', '.join(sorted(names))}")
    try:
        return cls(**raw)
    except (TypeError, ValueError):
        raise NotConfigured(f"{name} is malformed") from None


def _bounds(values) -> dict[str, Bounds]:
    raw = _json(values, "RUNS_AGENT_BOUNDS", "a JSON object of profiles per depth")
    if not isinstance(raw, dict) or set(raw) != set(runs_config.DEPTHS):
        raise NotConfigured(f"RUNS_AGENT_BOUNDS must name exactly {', '.join(runs_config.DEPTHS)}")
    return checked_profiles({depth: _record(Bounds, f"RUNS_AGENT_BOUNDS[{depth!r}]", entry)
                             for depth, entry in raw.items()})


def read(values) -> AgentProfile:
    """The whole profile, or `NotConfigured` naming the first problem."""
    from ai.agent.executor import CHAT_PROMPT_VERSION, CHAT_TOOL_VERSION
    from ai.admission.transport import RESEARCH_LANE
    from ai.infrastructure.openai_adapter import OpenAICompatibleAgentProvider

    missing = [name for name in REQUIRED if not str(getattr(values, name, "") or "").strip()]
    if missing:
        raise NotConfigured(", ".join(missing))
    provider = agent_config.read(values)
    limits = read_limits(values)
    if RESEARCH_LANE not in limits.lanes:
        raise NotConfigured(f"AI_ADMISSION_LANE_CONCURRENCY must name the {RESEARCH_LANE} lane")
    model = str(values.RUNS_AGENT_MODEL).strip()
    if model not in provider.models:
        raise NotConfigured("RUNS_AGENT_MODEL must be one of AGENT_LLM_MODELS")
    if model not in provider.capacities:
        raise NotConfigured("RUNS_AGENT_MODEL has no capacity in AGENT_LLM_CAPACITIES")
    if model not in limits.prices:
        raise NotConfigured("RUNS_AGENT_MODEL has no price in AI_ADMISSION_PRICES")
    bounds = _bounds(values)
    reserves = _record(Reserves, "RUNS_AGENT_RESERVES",
                       _json(values, "RUNS_AGENT_RESERVES", "a JSON object"))
    compaction = None
    if str(getattr(values, "RUNS_AGENT_COMPACTION", "") or "").strip():
        compaction = _record(Compaction, "RUNS_AGENT_COMPACTION",
                             _json(values, "RUNS_AGENT_COMPACTION", "a JSON object"))
        if not compaction.fits(provider.capacities[model], reserves):
            raise NotConfigured("RUNS_AGENT_COMPACTION leaves no room to summarize or finish"
                                " under RUNS_AGENT_MODEL's capacity")
    checks = str(getattr(values, "RUNS_AGENT_CHECKS", "") or "enforce").strip().lower()
    if checks not in ("enforce", "flag", "advisory"):
        raise NotConfigured("RUNS_AGENT_CHECKS must be enforce, flag or advisory")
    pin = Pin(
        model=model, endpoint=provider.endpoint, adapter=OpenAICompatibleAgentProvider.adapter,
        dialect=OpenAICompatibleAgentProvider.dialect.name, prompt_version=CHAT_PROMPT_VERSION,
        tool_version=CHAT_TOOL_VERSION, public_version=runs_config.PROTOCOL,
        state_version=runs_config.SCHEMA, data_policy=provider.data_policy,
    )
    return AgentProfile(pin=pin, bounds=bounds, reserves=reserves, provider=provider, limits=limits,
                        compaction=compaction, checks=checks)


def executor(profile: AgentProfile, dsn: str, *, provider=None):
    """The AGENT executor; every provider attempt goes through admission (IR-725).

    `provider` replaces the configured vendor adapter, for tests only.
    """
    from ai.admission.ledger import Ledger
    from ai.admission.transport import AdmittedAgentProvider
    from ai.agent.executor import PURPOSE, AgentExecutor
    from ai.infrastructure.openai_adapter import OpenAICompatibleAgentProvider

    inner = provider if provider is not None else OpenAICompatibleAgentProvider(profile.provider)
    admitted = AdmittedAgentProvider(inner, Ledger(dsn, profile.limits), purpose=PURPOSE)
    return AgentExecutor(admitted, profile.pin, profile.reserves, profiles=profile.bounds,
                         price=profile.limits.prices[profile.pin.model], compaction=profile.compaction,
                         checks=profile.checks)


def selected(values) -> Optional[AgentProfile]:
    """None unless the agent is selected; `RunsUnavailable` naming what is wrong."""
    if getattr(values, "RUNS_EXECUTOR", None) != "agent":
        return None
    try:
        return read(values)
    except NotConfigured as problem:
        raise runs_config.RunsUnavailable(f"AGENT profile: {problem}") from None
