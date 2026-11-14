"""Which signal placed each heading, and how often line boxes matched (IR-1057).

Reads stored Unstructured results beside their PDFs; calls no vendor and
touches no database. ``--pair result.json evidence.json`` per paper, using the
evidence stored at extraction; a ``.pdf`` in its place is read in-process.
"""

import json
from io import BytesIO
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.ai.extraction.shaping_unstructured import shaping_report
from apps.documents.pdf_evidence import reader


class Command(BaseCommand):
    help = "Report the heading cascade and line-box match rate on stored Unstructured results."

    def add_arguments(self, parser):
        parser.add_argument("--pair", nargs=2, action="append", required=True,
                            metavar=("RESULT_JSON", "EVIDENCE_JSON_OR_PDF"))
        parser.add_argument("--out", help="Also write the report here as JSON.")

    def handle(self, *args, pair, out=None, **options):
        papers = {}
        for result, pdf in pair:
            raw = json.loads(Path(result).read_text(encoding="utf-8"))
            source = Path(pdf)
            evidence = (json.loads(source.read_text(encoding="utf-8")) if source.suffix == ".json"
                        else reader.read(BytesIO(source.read_bytes()), max_pages=2000))
            report = shaping_report(raw, evidence)
            boxes = report["line_boxes"]
            lined = sum(boxes.values())
            for name, outcome in (("match_rate", "matched"), ("fallback_rate", "fallback"),
                                  ("no_text_layer_rate", "no_text_layer")):
                report[name] = round(boxes.get(outcome, 0) / lined, 3) if lined else None
            papers[Path(pdf).name] = report
            self.stdout.write(
                f"{Path(pdf).name}: signals {report['signals']}, line boxes {boxes} "
                f"(match {report['match_rate']}, fallback {report['fallback_rate']})"
            )
            for text, level, signal in report["headings"]:
                self.stdout.write(f"  L{level} {signal:<13} {text[:70]}")
        if out:
            Path(out).write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
