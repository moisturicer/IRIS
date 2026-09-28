"""Building the `LLMProvider` a Profile describes (IR-378).

One adapter per protocol (ADR-021), so a Profile is a `base_url`, an
`api_key` and a model list -- and the list is walked by the same resilience
stack `CompositionRoot.llm()` already used, not by a second one.

**The cross-vendor entry is still appended for `answer`, and only there.**
`LLM_FALLBACK_API_KEY` configures a second *vendor*, which ADR-008 refuses;
its removal is a later ticket under IR-375, and dropping it here instead would
change the behaviour of a deployment that opted in, which this ticket promises
not to do.
"""

from __future__ import annotations

from apps.ai.providers.openai_compatible import LLMUnavailable
from apps.ai.providers.ports import LLMProvider
from apps.ai.resilience.llm import (
    LLMProviderConfig,
    build_resilient_llm,
    cross_vendor_fallback_config,
)

from .profiles import Profile
from .tasks import InferenceTask


def build_profile_llm(profile: Profile) -> LLMProvider:
    """The provider `profile`'s task reaches its model through."""
    if not profile.is_configured:
        raise LLMUnavailable(
            f"the {profile.task.value!r} Inference task has no model. Set "
            f"{profile.task.settings_prefix}_MODEL, or leave the task off; "
            "there is no shared default to fall through to (ADR-021)."
        )

    # A task whose Reasoning is not shown sends no reasoning configuration at
    # all (IR-380), rather than inheriting `LLM_REASONING_EFFORT`: there is no
    # live-typing moment to show the working in, and the tokens are paid for
    # either way. `None` keeps the inherited setting for the tasks that do.
    reasoning_effort = None if profile.reasoning_visible else ""

    configs = [
        LLMProviderConfig(
            base_url=profile.base_url,
            api_key=profile.api_key,
            model=model,
            reasoning_effort=reasoning_effort,
            vendor=profile.vendor.value,
        )
        for model in profile.models
    ]

    if profile.task is InferenceTask.ANSWER:
        legacy = cross_vendor_fallback_config()
        if legacy is not None:
            configs.append(legacy)

    return build_resilient_llm(configs)
