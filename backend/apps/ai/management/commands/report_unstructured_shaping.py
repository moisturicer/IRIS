"""Which signal placed each heading, and how often line boxes matched (IR-1057).

Reads stored Unstructured results beside their PDFs; calls no vendor and
touches no database. ``--pair result.json paper.pdf`` per paper.
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
                            metavar=("RESULT_JSON", "PDF"))
        parser.add_argument("--out", help="Also write the report here as JSON.")

    def handle(self, *args, pair, out=None, **options):
        papers = {}
        for result, pdf in pair:
            raw = json.loads(Path(result).read_text(encoding="utf-8"))
            evidence = reader.read(BytesIO(Path(pdf).read_bytes()), max_pages=2000)
            report = shaping_report(raw, evidence)
            boxes = report["line_boxes"]
            lined = sum(boxes.values())
            report["match_rate"] = round(boxes.get("matched", 0) / lined, 3) if lined else None
            report["fallback_rate"] = round(1 - report["match_rate"], 3) if lined else None
            papers[Path(pdf).name] = report
            self.stdout.write(
                f"{Path(pdf).name}: signals {report['signals']}, line boxes {boxes} "
                f"(match {report['match_rate']}, fallback {report['fallback_rate']})"
            )
            for text, level, source in report["headings"]:
                self.stdout.write(f"  L{level} {source:<13} {text[:70]}")
        if out:
            Path(out).write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")
