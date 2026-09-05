"""
Retrieve-then-synthesise pipeline behind `POST /api/v1/ai/ask/`.

Retrieval is always real: it ranks the actual CIT-U corpus and every citation
points at a record the asker can open. Synthesis has two modes:

  * generative  — a configured LLM writes the answer from the retrieved sources
  * extractive  — no provider configured, so the answer is assembled from the
                  sources themselves and labelled as such

Both modes are grounded. Neither invents a record.
"""
from __future__ import annotations

import re

from .llm_generator import LLMGenerator
from .retrieval import RetrievedSource, search_records

DEFAULT_TOP_K = 5

NO_RESULTS_MESSAGE = (
    "No published records in the CIT-U repository matched that question. "
    "Try different keywords, or browse Discover to see what is available."
)

EXTRACTIVE_NOTE = (
    "_Retrieval-only mode: IRIS found and ranked these records, but no language "
    "model is configured, so this answer quotes the records rather than "
    "synthesising them. Set `ANTHROPIC_API_KEY` to enable written answers._"
)


def _first_sentences(text: str, limit: int = 2) -> str:
    """A short, faithful extract — never paraphrased, so it cannot misstate the source."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return "No abstract on file."
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    extract = " ".join(sentences[:limit]).strip()
    return extract if len(extract) <= 400 else f"{extract[:397]}…"


def _extractive_answer(question: str, sources: list[RetrievedSource]) -> str:
    lines = [
        f"Here is what the CIT-U repository holds on **{question.strip().rstrip('?')}** "
        f"— {len(sources)} matching record{'s' if len(sources) != 1 else ''}:",
        "",
    ]
    for i, s in enumerate(sources, start=1):
        year = s.year or "n.d."
        # Blank lines between each part — consecutive markdown lines would
        # otherwise collapse the byline and the extract into one paragraph.
        lines.append(f"**[{i}] {s.title}**")
        lines.append("")
        lines.append(f"*{s.authors} · {year}*")
        lines.append("")
        lines.append(_first_sentences(s.abstract))
        lines.append("")
    lines.append(EXTRACTIVE_NOTE)
    return "\n".join(lines)


class RAGPipelineService:
    """Answer a question against the record corpus."""

    def __init__(self, generator: LLMGenerator | None = None) -> None:
        self.generator = generator or LLMGenerator()

    def answer(self, question: str, top_k: int = DEFAULT_TOP_K) -> dict:
        question = (question or "").strip()
        if not question:
            return {
                "answer": None,
                "citations": [],
                "sources": [],
                "message": "Ask a question to search the repository.",
                "mode": "empty",
            }

        sources = search_records(question, top_k=top_k)
        if not sources:
            return {
                "answer": None,
                "citations": [],
                "sources": [],
                "message": NO_RESULTS_MESSAGE,
                "mode": "no_results",
            }

        generated = self.generator.generate(question, sources)
        if generated:
            answer, mode, message = generated, "generative", None
        else:
            answer = _extractive_answer(question, sources)
            mode = "extractive"
            message = "Retrieval-only mode — no language model configured."

        return {
            "answer": answer,
            "citations": [s.id for s in sources],
            "sources": [s.as_dict() for s in sources],
            "message": message,
            "mode": mode,
        }
