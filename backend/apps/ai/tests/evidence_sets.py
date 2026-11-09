"""Curated evidence-question sets the eval_evidence command tests write (IR-465, IR-484)."""

import json

QUOTE = "the document stopped moving and nobody noticed that it had"


def write_set(tmp_path, *questions):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps({"name": "curated-model", "tier": "proxy", "questions": list(questions)}),
        encoding="utf-8",
    )
    return str(path)


def grounded(qid, text):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "corpus",
        "expected_outcome": "answer",
        "expected": [{"record": "A", "quote": QUOTE}],
    }


def direct(qid, text):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "none",
        "expected_outcome": "answer",
        "expected": [],
    }
