"""A Profile per Inference task (IR-378, ADR-036 §Amendment).

What a task needs to reach a model: vendor, model, the ordered models to fall
back to *inside that vendor account*, whether its Reasoning is shown, and what
the vendor may do with what it receives. Resolved from settings on demand,
never at import: a machine with no vendor account must still be able to build
a composition root, which is every machine the test suite runs on.

**Only the sanctioned pair.** Groq and OpenRouter, per ADR-036 -- an
unrecognised vendor raises rather than being passed through as a base URL.

**Fallback stays inside one vendor.** ``fallback_models`` shares the profile's
``base_url`` and ``api_key``; cross-vendor failover is still refused
(ADR-008 §Amendment).

**The `answer` Profile inherits today's flat settings.** ``LLM_BASE_URL``,
``LLM_API_KEY`` and ``LLM_MODEL`` are its defaults, so a deployment that sets
none of the per-task variables behaves exactly as it does now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .tasks import InferenceTask, inference_task


class Vendor(Enum):
    """A sanctioned inference vendor and where it answers."""

    GROQ = "groq"
    OPENROUTER = "openrouter"

    @property
    def base_url(self) -> str:
        return _VENDOR_BASE_URLS[self]


_VENDOR_BASE_URLS = {
    Vendor.GROQ: "https://api.groq.com/openai/v1",
    Vendor.OPENROUTER: "https://openrouter.ai/api/v1",
}


class UnknownVendor(ValueError):
    """A vendor outside ADR-036's sanctioned pair."""


def vendor(name: Union[Vendor, str]) -> Vendor:
    if isinstance(name, Vendor):
        return name
    try:
        return Vendor(str(name).strip().lower())
    except ValueError as exc:
        known = ", ".join(v.value for v in Vendor)
        raise UnknownVendor(
            f"{name!r} is not a sanctioned inference vendor (ADR-036): {known}."
        ) from exc


class DataPolicy(Enum):
    """What the vendor may do with what IRIS sends.

    Uniform across tasks: retaining logs is acceptable, training is not. The
    disclosure gate still decides what may leave IRIS at all -- this decides
    only what the recipient may do with it, and there is no per-task
    exemption from either.
    """

    NO_TRAINING = "no_training"


@dataclass(frozen=True)
class Profile:
    """How one Inference task reaches a model."""

    task: InferenceTask
    vendor: Vendor
    model: str
    fallback_models: tuple[str, ...]
    base_url: str
    api_key: str
    reasoning_visible: bool
    data_policy: DataPolicy = DataPolicy.NO_TRAINING
    #: OpenRouter providers this task may reach, or empty for any (IR-489).
    provider_only: tuple[str, ...] = ()
    #: Per-model OpenRouter endpoints, preserving each model's routing policy.
    model_provider_pins: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def is_configured(self) -> bool:
        """Whether this task has a model at all.

        A task with no model is simply off -- how a Groq-only developer runs
        IRIS without an OpenRouter account. A task that *is* configured but
        has no key is a deployment mistake, not an off switch, and startup
        refuses it (IR-379).
        """
        return bool(self.model)

    @property
    def models(self) -> tuple[str, ...]:
        """The model, then its fallbacks, in the order they are tried."""
        return (self.model, *self.fallback_models)


def _setting(name: str, default: str = "") -> str:
    value = getattr(settings, name, default)
    return (value or "").strip() if isinstance(value, str) else default


def _listed(name: str) -> tuple[str, ...]:
    raw = _setting(name)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _fallback_models(prefix: str) -> tuple[str, ...]:
    return _listed(f"{prefix}_FALLBACK_MODELS")


def _model_provider_pins(prefix: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    name = f"{prefix}_PROVIDER_PINS"
    raw = _setting(name)
    if not raw:
        return ()
    try:
        pins = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            f"{name} must be a JSON object of model to provider endpoint lists"
        ) from exc
    if not isinstance(pins, dict) or not all(
        isinstance(model, str)
        and model.strip()
        and isinstance(endpoints, list)
        and bool(endpoints)
        and all(
            isinstance(endpoint, str) and endpoint.strip()
            for endpoint in endpoints
        )
        for model, endpoints in pins.items()
    ):
        raise ImproperlyConfigured(
            f"{name} must map model names to nonempty provider endpoint lists"
        )
    return tuple((model, tuple(endpoints)) for model, endpoints in pins.items())


#: The setting *names* a task inherits when its own are unset. Keys, not
#: values: they are read through `_setting` below.
#:
#: `answer` inherits all three, so a deployment that sets none of the
#: per-task variables behaves exactly as it did before Profiles existed.
#: `resolve` inherits the vendor account and **not** the model (IR-383): it
#: has shipped since IR-296 over the flat account, so it must keep working
#: with no new configuration, but borrowing the *answer* model would send
#: every follow-up rewrite to the expensive one. Its own model ships as a
#: default instead. `summary` and `describe_figure` inherit nothing and are
#: off until configured.
_INHERITED_KEYS = {
    InferenceTask.ANSWER: ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"),
    InferenceTask.RESOLVE: ("LLM_BASE_URL", "LLM_API_KEY", ""),
}


def _vendor_at(base_url: str) -> Optional[Vendor]:
    """Which sanctioned vendor answers at ``base_url``, if any.

    Non-raising, unlike ``vendor()``: a base URL is also how a self-hosted
    vLLM or Ollama is reached (ADR-036 covers them as configurations of the
    same adapter), and an unrecognised one is not a mistake to refuse here.
    """
    for candidate, url in _VENDOR_BASE_URLS.items():
        if base_url == url:
            return candidate
    return None


def _inherited_model_key(task: InferenceTask) -> str:
    """The flat model setting ``task`` falls back to, if any.

    Unconditional, unlike the base URL and the key: naming a vendor says where
    a task runs, not that it has stopped being configured. A model inherited
    at a named vendor with no key of its own is a startup refusal (IR-379),
    not a task that quietly reads as off.
    """
    return _INHERITED_KEYS.get(task, ("", "", ""))[2]


def _inherited_keys(task: InferenceTask) -> tuple[str, str, str]:
    """The flat setting names ``task`` falls back to, if it is allowed to.

    A named vendor outranks the inherited flat settings, for the key as well
    as the URL: a task moved to OpenRouter must neither keep pointing at Groq
    because ``LLM_BASE_URL`` says so, nor carry the Groq key there. The flat
    settings describe one vendor, so inheriting half of them is how a request
    ends up at one vendor authenticated for another.

    One function rather than the same condition written at each reader: a
    startup refusal names the variable that would supply the key (IR-379), and
    a second copy of this rule desyncing would make it name the wrong one.
    """
    if _setting(f"{task.settings_prefix}_VENDOR"):
        return ("", "", "")
    return _INHERITED_KEYS.get(task, ("", "", ""))


def api_key_variables(task: Union[InferenceTask, str]) -> tuple[str, ...]:
    """Where ``task``'s key may be set, in the order ``profile_for`` reads them."""
    task = inference_task(task)
    own = f"{task.settings_prefix}_API_KEY"
    if task in (InferenceTask.ROUTE, InferenceTask.PLAN):
        parent_task = InferenceTask.RESOLVE if task is InferenceTask.ROUTE else InferenceTask.ANSWER
        resolve = profile_for(parent_task)
        route_url = _setting(f"{task.settings_prefix}_BASE_URL")
        if not _setting(f"{task.settings_prefix}_VENDOR") and (
            not route_url or _vendor_at(route_url) is resolve.vendor
        ):
            return (own, *api_key_variables(parent_task))
        return (own,)
    _, inherited, _ = _inherited_keys(task)
    return (own, inherited) if inherited else (own,)


def model_variables(task: Union[InferenceTask, str]) -> tuple[str, ...]:
    """Where ``task``'s model may be set, in the order ``profile_for`` reads them.

    The pair to ``api_key_variables``, and read against the environment rather
    than settings: a startup refusal asks whether the *operator* configured
    this task (IR-379), and `LLM_MODEL` ships with a default, so a resolved
    model does not mean anyone chose one.
    """
    task = inference_task(task)
    own = f"{task.settings_prefix}_MODEL"
    if task is InferenceTask.ROUTE:
        return (own, "LLM_RESOLVE_MODEL")
    if task is InferenceTask.PLAN:
        return (own, *model_variables(InferenceTask.ANSWER))
    inherited = _inherited_model_key(task)
    return (own, inherited) if inherited else (own,)


def profile_for(task: Union[InferenceTask, str]) -> Profile:
    """Resolve ``task``'s Profile from settings. Never cached, never eager."""
    task = inference_task(task)
    prefix = task.settings_prefix
    if task in (InferenceTask.ROUTE, InferenceTask.PLAN):
        parent_task = InferenceTask.RESOLVE if task is InferenceTask.ROUTE else InferenceTask.ANSWER
        resolve = profile_for(parent_task)
        named_vendor = _setting(f"{prefix}_VENDOR")
        chosen = vendor(named_vendor) if named_vendor else resolve.vendor
        base_url = _setting(f"{prefix}_BASE_URL") or (
            chosen.base_url if named_vendor else resolve.base_url
        )
        if not named_vendor:
            chosen = _vendor_at(base_url) or resolve.vendor
        api_key = _setting(f"{prefix}_API_KEY") or (
            "" if named_vendor or chosen is not resolve.vendor else resolve.api_key
        )
        return Profile(
            task=task,
            vendor=chosen,
            model=_setting(f"{prefix}_MODEL") or resolve.model,
            fallback_models=_fallback_models(prefix),
            base_url=base_url,
            api_key=api_key,
            reasoning_visible=bool(getattr(settings, f"{prefix}_REASONING", False)),
            provider_only=_listed(f"{prefix}_PROVIDER_ONLY") or (
                () if named_vendor else resolve.provider_only
            ),
            model_provider_pins=_model_provider_pins(prefix) or (
                resolve.model_provider_pins if task is InferenceTask.PLAN and not named_vendor else ()
            ),
        )
    # Already empty when a vendor is named, which is what stops half the flat
    # settings being inherited -- see `_inherited_keys`.
    inherited_base_url, inherited_api_key, _ = _inherited_keys(task)

    named_vendor = _setting(f"{prefix}_VENDOR")
    model = _setting(f"{prefix}_MODEL") or _setting(_inherited_model_key(task))

    base_url = _setting(f"{prefix}_BASE_URL") or _setting(inherited_base_url)
    api_key = _setting(f"{prefix}_API_KEY") or _setting(inherited_api_key)

    # Named, else read off whichever URL was resolved, else Groq -- the
    # first-class default. Inferring rather than assuming Groq: IR-382 selects
    # a vendor dialect on this field, and a Profile whose `vendor` disagrees
    # with its own `base_url` would send Groq's request shape to OpenRouter.
    chosen = (
        vendor(named_vendor)
        if named_vendor
        else (_vendor_at(base_url) or Vendor.GROQ)
    )

    return Profile(
        task=task,
        vendor=chosen,
        model=model,
        fallback_models=_fallback_models(prefix),
        base_url=base_url or chosen.base_url,
        api_key=api_key,
        reasoning_visible=bool(getattr(settings, f"{prefix}_REASONING", False)),
        # Never inherited: a pin is a choice about one task's model.
        provider_only=_listed(f"{prefix}_PROVIDER_ONLY"),
        model_provider_pins=_model_provider_pins(prefix),
    )
