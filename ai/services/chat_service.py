"""Ask a question of the configured LLM provider (IR-156).

`api/chat.py` has imported `ChatService` since the gateway was written; the
module never existed, so the router failed at import and the container could
not boot. This supplies it.

**It is a delegation, not a stub.** The service takes an `LLMProvider` port and
calls it — it does not invent an answer, and it does not fall back to canned
text when the provider is unavailable. A gateway that returns plausible prose
when its provider is down is worse than one that errors: ADR-008 is explicit
that degradation is FTS, chosen by Django, not fabrication chosen here.

**No retrieval lives here.** Under ADR-014 precondition 4, Django owns
retrieval and visibility filtering, and the gateway has no database access at
all. Context arrives as an argument from the caller that already applied the
visibility predicate, which is what keeps a generated citation from ever
pointing at a record the reader cannot open.
"""

from __future__ import annotations

from ai.domain.ports import LLMProvider


class ChatService:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def ask_question(self, query: str, context: str = "") -> str:
        """Put one question to the provider and return its answer verbatim.

        `context` is passed through untouched. The gateway does not select it,
        rank it, or filter it — that decision was already made by the caller
        under its own permission rules, and second-guessing it here would be a
        second visibility path.
        """
        if not query or not query.strip():
            # A blank prompt bills a request and returns whatever the model
            # free-associates. Refuse it here rather than at the vendor.
            raise ValueError("query must not be empty")
        return await self._llm.generate_response(query, context)
