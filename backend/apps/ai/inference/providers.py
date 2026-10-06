"""Building the `LLMProvider` a Profile describes (IR-378, IR-385, IR-386).

One adapter per protocol (ADR-036), so a Profile is a `base_url`, an
`api_key` and a model list -- and the list is walked by the same resilience
stack every task shares, `apps.ai.resilience.llm.build_task_llm`.

**Who walks the list depends on the vendor** (IR-385). Both routes stay inside
one account, which is the only kind of fallback ADR-008 §Amendment permits:

* a vendor with no native multi-model field -- Groq -- is looped here: one
  config per model, wrapped in `FallbackLLMProvider`, which moves to the next
  model only on a failure another model could fix (`network`, `timeout`,
  `rate_limit`);
* a vendor that resolves the list itself -- OpenRouter, which declares
  `VendorDialect.resolves_fallback` -- gets **one** config carrying the whole
  list, sent as the native `models` field. Looping there would send a second
  request for a fallback the vendor already performed.

**Cross-vendor failover is gone, not switched off** (IR-385). The
`LLM_FALLBACK_*` second vendor IR-321 shipped -- a second key, a second
company receiving IRIS text -- was the contradiction ADR-008 recorded by name.
Its settings and the config they built are deleted, so a Profile's fallback
list is the only fallback there is.

**One circuit breaker for the whole list, keyed on the task (IR-386).**
`build_task_llm`, not a per-model breaker: the latter would let two tasks
sharing a vendor and model share a breaker too -- a busy `summary` tripping
it would stop `answer` for a reason that has nothing to do with answering.
Keying on `profile.task.breaker_key` instead means each task's breaker only
opens once every model in *its own* list has failed a call, not on the first
one.
"""

from __future__ import annotations

from apps.ai.providers.dialects import dialect_for
from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.resilience.llm import LLMProviderConfig, build_task_llm

from .profiles import Profile


def build_profile_llm(profile: Profile) -> LLMProvider:
    """The provider `profile`'s task reaches its model through."""
    if not profile.is_configured:
        raise LLMUnavailable(
            f"the {profile.task.value!r} Inference task has no model. Set "
            f"{profile.task.settings_prefix}_MODEL, or leave the task off; "
            "there is no shared default to fall through to (ADR-036)."
        )

    # A task whose Reasoning is not shown sends no reasoning configuration at
    # all (IR-380), rather than inheriting `LLM_REASONING_EFFORT`: there is no
    # live-typing moment to show the working in, and the tokens are paid for
    # either way. `None` keeps the inherited setting for the tasks that do.
    reasoning_effort = None if profile.reasoning_visible else ""

    def config(model: str, fallback_models: tuple[str, ...] = ()) -> LLMProviderConfig:
        return LLMProviderConfig(
            base_url=profile.base_url,
            api_key=profile.api_key,
            model=model,
            reasoning_effort=reasoning_effort,
            vendor=profile.vendor.value,
            fallback_models=fallback_models,
        )

    if dialect_for(profile.vendor.value).resolves_fallback:
        configs = [config(profile.model, profile.fallback_models)]
    else:
        configs = [config(model) for model in profile.models]

    return build_task_llm(configs, breaker_key=profile.task.breaker_key)
