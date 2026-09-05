"""
LLM synthesis for grounded answers.

The provider is optional on purpose. IRIS ships with placeholder credentials in
`.env.example`, so `is_configured()` is false on a fresh checkout and the caller
falls back to extractive synthesis. Adding a real key upgrades the same endpoint
to full generative RAG with no other change.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: Values that appear in .env.example — present, but not real credentials.
PLACEHOLDER_KEYS = {"", "your-anthropic-key", "your-openai-key", "changeme", "sk-local-dev-placeholder"}

SYSTEM_PROMPT = (
    "You are IRIS, the research assistant for Cebu Institute of Technology – University. "
    "Answer ONLY from the numbered sources provided. Cite them inline as [1], [2] and so on, "
    "matching the source numbers given. If the sources do not contain the answer, say so plainly "
    "instead of guessing. Be concise and factual; never invent titles, authors, findings or numbers."
)


class LLMGenerator:
    """Thin wrapper over the configured provider. Never raises to the caller."""

    def __init__(self) -> None:
        self.api_key = (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()
        self.model = getattr(settings, "AI_LLM_MODEL", "claude-sonnet-5")

    def is_configured(self) -> bool:
        return self.api_key not in PLACEHOLDER_KEYS and self.api_key.startswith("sk-")

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
            import anthropic
        except ImportError:
            logger.info("anthropic SDK not installed; falling back to extractive synthesis")
            return None

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self.build_prompt(question, sources)}],
            )
            return "".join(block.text for block in message.content if block.type == "text").strip()
        except Exception:
            # A provider outage must not take the endpoint down — the extractive
            # answer below is still grounded and still cites real records.
            logger.exception("LLM generation failed; falling back to extractive synthesis")
            return None
