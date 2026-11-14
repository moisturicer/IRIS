"""`eval_formula_transcription` scores each cropped formula against its source (IR-1102)."""

import json

from django.core.management import call_command

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.vision import ImageDescribingLLM

LAYOUT = {"layout_width": 2125, "layout_height": 2750, "system": "PixelSpace"}
SOURCE = r"""
\begin{equation} E = m c^2 \end{equation}
\begin{equation} a^2 + b^2 = c^2 \end{equation}
"""


class Transcriber(ScriptedLLM, ImageDescribingLLM):
    def __init__(self, replies):
        super().__init__()
        self.replies = iter(replies)

    def describe_image(self, system, user, image, media_type):
        assert image.startswith(b"\x89PNG")
        return next(self.replies)


def formula(element_id, top):
    points = [[250, top], [250, top + 100], [1000, top + 100], [1000, top]]
    return {"type": "Formula", "element_id": element_id, "text": "OCR",
            "metadata": {"page_number": 1, "coordinates": {"points": points, **LAYOUT}}}


def test_each_formula_is_scored_and_no_paper_text_is_written(tmp_path):
    (tmp_path / "p1").mkdir()
    (tmp_path / "p1" / "result.json").write_text(json.dumps({"elements": [formula("a", 500), formula("b", 900)]}))
    (tmp_path / "p1.pdf").write_bytes(pdf_bytes(FIXTURES["figures"]))
    (tmp_path / "p1" / "tex").mkdir()
    (tmp_path / "p1" / "tex" / "main.tex").write_text(SOURCE)
    out = tmp_path / "run.json"
    replies = [json.dumps({"latex": "E = m c^2", "description": "Energy."}),
               json.dumps({"latex": "a^2 + b^2 = d^2", "description": "Not quite."})]

    with use_composition_root(CompositionRoot(llm=Transcriber(replies))):
        call_command("eval_formula_transcription", papers="p1", pdfs=str(tmp_path),
                     results=str(tmp_path), sources=str(tmp_path), out=str(out))

    report = json.loads(out.read_text())
    assert (report["formulas"], report["transcribed"], report["exact_after_normalization"]) == (2, 2, 1)
    assert "m c^2" not in out.read_text()
