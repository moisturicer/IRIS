"""Recorded vendor output and small authored contract payloads for tests."""

import json
from pathlib import Path


RECORDINGS = Path(__file__).parent / "fixtures" / "llamaparse"


def recorded(name):
    directory = RECORDINGS / name
    raw = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    raw["grounded_items"] = [
        json.loads(line)
        for line in (directory / "grounded_items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return raw


def result_with(items):
    return {
        "items": {"pages": [{"page_number": 1, "page_width": 612, "page_height": 792, "items": items}]},
        "metadata": {"pages": [{"page_number": 1, "printed_page_number": "iv"}]},
    }
