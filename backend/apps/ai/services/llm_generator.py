"""
LLM synthesis for grounded answers.

The provider is optional on purpose. IRIS ships with no key in `.env.example`,
so `is_configured()` is false on a fresh checkout and the caller falls back to
extractive synthesis. Adding a real key upgrades the same endpoint to full
generative RAG with no other change.

**Repointed off Anthropic by ADR-021.** This called `anthropic` directly, a
vendor chosen in an import statement rather than a decision record -- and the
package was never declared as a dependency, so the import failed and every
environment silently degraded to extractive answers. It now goes through
`OpenAICompatibleAdapter`, which serves Groq (development) and OpenRouter
(production) from the same code.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: Values that appear in .env.example — present, but not real credentials.
PLACEHOLDER_KEYS = {
    "", "your-anthropic-key", "your-openai-key", "your-groq-key",
    "changeme", "sk-local-dev-placeholder",
}

SYSTEM_PROMPT = (
    "You are IRIS, the research assistant for Cebu Institute of Technology – University. "
    "Answer ONLY from the numbered sources provided. Cite them inline as [1], [2] and so on, "
    "matching the source numbers given. If the sources do not contain the answer, say so plainly "
    "instead of guessing. Be concise and factual; never invent titles, authors, findings or numbers."
)


class LLMGenerator:
    """Thin wrapper over the configured provider. Never raises to the caller."""

    def __init__(self, provider=None) -> None:
        self.api_key = (getattr(settings, "LLM_API_KEY", "") or "").strip()
        self.model = getattr(settings, "LLM_MODEL", "")
        self._provider = provider

    def is_configured(self) -> bool:
        """Whether a usable key is present.

        No vendor prefix check. The previous version required the key to start
        with `sk-`, which is OpenAI's and Anthropic's shape -- a Groq key
        (`gsk_...`) would have been rejected as malformed even when perfectly
        valid. Under ADR-021 the key's shape is the vendor's business.
        """
        return self.api_key not in PLACEHOLDER_KEYS

    def build_prompt(self, question: str, sources) -> str:
        blocks = []
        for i, s in enumerate(sources, start=1):
            blocks.append(
                f"[{i}] (record #{s.id}) {s.title}\n"
                f"Authors: {s.authors}\n"
                f"Year: {s.year or 'n.d.'}\n"
                f"Abstract: {s.abstract or '(no abstract on file)'}"
            )
        corpus = "\n\n".join(blocks)
        return f"Sources:\n\n{corpus}\n\nQuestion: {question}"

    def generate(self, question: str, sources) -> str | None:
        """Return the model's answer, or None when unavailable — caller degrades."""
        if not self.is_configured() or not sources:
            return None

        try:
            provider = self._provider
            if provider is None:
                from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

                provider = OpenAICompatibleAdapter()
            return provider.generate(
                system=SYSTEM_PROMPT, user=self.build_prompt(question, sources)
            ).strip()
        except Exception:
            # A provider outage must not take the endpoint down — the extractive
            # answer below is still grounded and still cites real records.
            logger.exception("LLM generation failed; falling back to extractive synthesis")
            return None
