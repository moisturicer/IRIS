"""Build only providers approved and configured for reader-question routing."""

from __future__ import annotations

from django.conf import settings

from apps.ai.composition import composition_root
from apps.ai.inference import InferenceTask, Vendor, profile_for
from apps.ai.providers.openrouter_decisions import OpenRouterDecisionsAdapter


def configured_providers():
    """Jev is opt-in; an unapproved Groq backup is unavailable, not called."""
    jev = None
    if settings.AI_JEV_ROUTING_ENABLED:
        key = settings.AI_JEV_API_KEY.strip()
        if not key:
            for task in (InferenceTask.ROUTE, InferenceTask.SUMMARY, InferenceTask.ANSWER):
                profile = profile_for(task)
                if profile.vendor is Vendor.OPENROUTER and profile.api_key:
                    key = profile.api_key
                    break
        if key:
            jev = OpenRouterDecisionsAdapter(key)

    backup = None
    profile = profile_for(InferenceTask.ROUTE)
    if profile.is_configured and profile.api_key and (
        profile.vendor is not Vendor.GROQ or settings.AI_ROUTE_GROQ_APPROVED
    ):
        backup = composition_root().llm_for(InferenceTask.ROUTE)
    return jev, backup
