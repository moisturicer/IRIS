"""Score formula transcription against the authors' LaTeX (IR-1102).

For each paper: shape its stored ``hi_res`` result, crop every Formula from
its PDF at 300 dpi, ask the configured formula transcription model, and score
each reply with the IR-984 spike's ``latex_truth.py`` against the arXiv source.
Spends credits: one model call per formula. The run file holds counts and
scores only, never paper text (ADR-023 proxy tier).
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

SCORER = (Path(__file__).resolve().parents[5] / "docs" / "evaluation" / "runs"
          / "2026-11-13-unstructured-spike" / "formulas" / "latex_truth.py")


def load_scorer(path: Path = SCORER):
    spec = importlib.util.spec_from_file_location("latex_truth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Command(BaseCommand):
    help = "Transcribe each hi_res Formula of the proxy papers and score it (spends credits)."

    def add_arguments(self, parser):
        parser.add_argument("--papers", required=True, help="comma-separated paper names")
        parser.add_argument("--pdfs", required=True, help="directory of <paper>.pdf")
        parser.add_argument("--results", required=True, help="directory of <paper>/result.json (hi_res)")
        parser.add_argument("--sources", required=True, help="directory of <paper>/tex (arXiv source)")
        parser.add_argument("--out", required=True, help="run file to write (counts and scores only)")
        parser.add_argument("--replies", help="also write the raw replies here, for reading by hand; never commit")

    def handle(self, *args, **options):
        from apps.ai.composition import composition_root
        from apps.ai.extraction.shaping_unstructured import shape_unstructured
        from apps.ai.formula_transcriptions import PROMPT_VERSION, SYSTEM, USER, read_reply
        from apps.documents import formulas
        from apps.documents.pdf_evidence import crops

        root = composition_root()
        transcriber = root.formula_transcriber()
        if transcriber is None:
            raise CommandError("no formula transcription model is configured (LLM_TRANSCRIBE_FORMULA_MODEL)")
        models = list(root.formula_transcriber_models())
        scorer = load_scorer()
        rows, replies = [], []
        for paper in [p.strip() for p in options["papers"].split(",") if p.strip()]:
            raw = json.loads((Path(options["results"]) / paper / "result.json").read_text(encoding="utf-8"))
            document = shape_unstructured(raw)
            targets = formulas.targets(document)
            pdf = (Path(options["pdfs"]) / f"{paper}.pdf").read_bytes()
            images = crops.render(pdf, [t.fractions(document.page_sizes[t.page]) for t in targets],
                                  max_pages=500)
            truth = scorer.equations(Path(options["sources"]) / paper / "tex")
            predictions = []
            for target, image in zip(targets, images):
                started = time.monotonic()
                latex, description, error = "", "", ""
                if image is None:
                    error = "not_rendered"
                else:
                    try:
                        latex, description = read_reply(transcriber.describe_image(SYSTEM, USER, image, "image/png"))
                    except Exception as exc:  # recorded, so one failure does not end the run
                        error = type(exc).__name__
                predictions.append(latex)
                replies.append({"paper": paper, "name": target.name, "page": target.page,
                                "latex": latex, "description": description})
                rows.append({"paper": paper, "page": target.page, "error": error,
                             "has_description": bool(description),
                             "seconds": round(time.monotonic() - started, 1)})
            scored = iter(scorer.score([p for p in predictions if p], truth)) if truth else iter(())
            for row, latex in zip(rows[-len(predictions):], predictions):
                match = next(scored, None) if latex else None
                if match:
                    row.update(exact=match["exact"], similarity=match["similarity"])
                else:
                    row.update(exact=False, similarity=0.0)
            self.stdout.write(f"{paper}: {len(targets)} formulas, {len(truth)} source equations")
        exact = sum(r["exact"] for r in rows)
        close = sum(r["similarity"] >= 0.95 for r in rows)
        report = {
            "ticket": "IR-1102", "tier": "proxy", "models": models, "prompt_version": PROMPT_VERSION,
            "dpi": crops.DPI, "scorer": "docs/evaluation/runs/2026-11-13-unstructured-spike/formulas/latex_truth.py",
            "formulas": len(rows), "transcribed": sum(not r["error"] and r["similarity"] > 0 for r in rows),
            "exact_after_normalization": exact, "similarity_at_least_0_95": close,
            "mean_similarity": round(sum(r["similarity"] for r in rows) / len(rows), 3) if rows else 0.0,
            "rows": rows,
        }
        Path(options["out"]).write_text(json.dumps(report, indent=1), encoding="utf-8")
        if options.get("replies"):
            Path(options["replies"]).write_text(json.dumps(replies, indent=1, ensure_ascii=False), encoding="utf-8")
        self.stdout.write(f"exact {exact}/{len(rows)}, >=0.95 {close}/{len(rows)}; wrote {options['out']}")
