"""The configured chat-completions AGENT provider, read fail-closed (IR-860).

Every `AGENT_LLM_*` name is required and nothing defaults. Capacity is
declared per model; a listed model with no declaration stays unknown, and
IR-732 refuses it. Nothing here is inferred from a model name or a vendor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from typing import Mapping

from ai.admission.limits import NotConfigured
from ai.agent.context import Capacity

REQUIRED = (
    "AGENT_LLM_ENDPOINT",
    "AGENT_LLM_API_KEY",
    "AGENT_LLM_MODELS",
    "AGENT_LLM_CAPABILITIES",
    "AGENT_LLM_DATA_POLICY",
    "AGENT_LLM_CAPACITIES",
)
#: Every `Capacity` field must be stated; `max_reasoning_tokens` may be null.
CAPACITY_FIELDS = tuple(f.name for f in fields(Capacity))
OPENROUTER = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class AgentProviderConfig:
    endpoint: str
    #: Never logged or repeated in a message.
    api_key: str
    models: frozenset[str]
    capabilities: frozenset[str]
    data_policy: str
    capacities: Mapping[str, Capacity]
    routing: Mapping | None = None
    #: PROMPT_CACHE_OFF or PROMPT_CACHE_RUN (IR-953); off unless set.
    prompt_cache: str = "off"

    def __repr__(self) -> str:
        return f"AgentProviderConfig(endpoint={self.endpoint!r}, models={sorted(self.models)!r})"


def _raw(values, name) -> str:
    value = getattr(values, name, None)
    return "" if value is None else str(value).strip()


def _names(values, name) -> frozenset[str]:
    return frozenset(part.strip() for part in _raw(values, name).split(",") if part.strip())


def _capacity(model: str, entry) -> Capacity:
    if not isinstance(entry, dict) or set(entry) != set(CAPACITY_FIELDS):
        raise NotConfigured(f"AGENT_LLM_CAPACITIES[{model!r}] must state exactly {', '.join(CAPACITY_FIELDS)}")
    try:
        return Capacity(**entry)
    except (TypeError, ValueError):
        raise NotConfigured(f"AGENT_LLM_CAPACITIES[{model!r}] is malformed") from None


def read(values) -> AgentProviderConfig:
    """The provider's declaration, or `NotConfigured` naming what is wrong."""
    missing = [name for name in REQUIRED if not _raw(values, name)]
    if missing:
        raise NotConfigured(", ".join(missing))
    endpoint = _raw(values, "AGENT_LLM_ENDPOINT").rstrip("/")
    if not endpoint.startswith(("https://", "http://")):
        raise NotConfigured("AGENT_LLM_ENDPOINT must be an http(s) URL")
    models = _names(values, "AGENT_LLM_MODELS")
    if not models:
        raise NotConfigured("AGENT_LLM_MODELS")
    try:
        declared = json.loads(_raw(values, "AGENT_LLM_CAPACITIES"))
    except ValueError:
        raise NotConfigured("AGENT_LLM_CAPACITIES must be a JSON object") from None
    if not isinstance(declared, dict):
        raise NotConfigured("AGENT_LLM_CAPACITIES must be a JSON object")
    unlisted = sorted(set(declared) - models)
    if unlisted:
        raise NotConfigured(f"AGENT_LLM_CAPACITIES names models not in AGENT_LLM_MODELS: {', '.join(unlisted)}")
    routing = None
    if endpoint == OPENROUTER:
        try:
            routing = json.loads(_raw(values, "AGENT_LLM_ROUTING"))
        except ValueError:
            raise NotConfigured("AGENT_LLM_ROUTING must be valid JSON") from None
        if not isinstance(routing, dict) or set(routing) != {
                "only", "allow_fallbacks", "data_collection", "zdr", "max_price", "require_parameters"}:
            raise NotConfigured("AGENT_LLM_ROUTING must name the exact OpenRouter provider controls")
        only = routing["only"]
        prices = routing["max_price"]
        if (not isinstance(only, list) or not only or len(only) > 4
                or any(not isinstance(tag, str) or not tag or tag.strip() != tag for tag in only)
                or len(set(only)) != len(only)
                or routing["allow_fallbacks"] is not False
                or routing["data_collection"] != "deny" or routing["zdr"] is not True
                or routing["require_parameters"] is not True
                or not isinstance(prices, dict) or set(prices) != {"prompt", "completion"}
                or any(type(value) not in (int, float) or not 0 < value < 100
                       for value in prices.values())):
            raise NotConfigured("AGENT_LLM_ROUTING must restrict provider, retention and price")
    return AgentProviderConfig(
        endpoint=endpoint,
        api_key=_raw(values, "AGENT_LLM_API_KEY"),
        models=models,
        capabilities=_names(values, "AGENT_LLM_CAPABILITIES"),
        data_policy=_raw(values, "AGENT_LLM_DATA_POLICY"),
        capacities={model: _capacity(model, entry) for model, entry in declared.items()},
        routing=routing,
        prompt_cache=_prompt_cache(values),
    )


PROMPT_CACHE_OFF, PROMPT_CACHE_RUN = "off", "run"


def _prompt_cache(values) -> str:
    """Optional: blank is off. "run" keys the vendor's prompt cache to one run, never wider (IR-953)."""
    chosen = _raw(values, "AGENT_LLM_PROMPT_CACHE") or PROMPT_CACHE_OFF
    if chosen not in (PROMPT_CACHE_OFF, PROMPT_CACHE_RUN):
        raise NotConfigured("AGENT_LLM_PROMPT_CACHE must be off or run")
    return chosen
