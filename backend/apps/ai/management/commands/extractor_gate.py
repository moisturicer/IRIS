"""The extractor quality gate, on a database copy (IR-989, ADR-067 decision 2).

    python manage.py extractor_gate export  --question-set <set.json> --out <dir>
    python manage.py extractor_gate install <dir>
    python manage.py extractor_gate measure --question-set <set.json> --out <measures.json>
    python manage.py extractor_gate verdict --llamaparse <measures.json> <run.json> \\
                                            --unstructured <measures.json> <run.json> --out <verdict.json>

A paper holds one stored read, so the arms take turns: install one read,
build its trial chunk sets with ``eval_retrieval --variant``, measure it,
then install the other. Calls no vendor; ``install`` re-shapes with today's code.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.ai.evaluation import extractor_gate as gate


class Command(BaseCommand):
    help = "Swap, measure and judge stored extractor reads for IR-989. Development only."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        export = sub.add_parser("export")
        export.add_argument("--question-set", type=Path, required=True)
        export.add_argument("--out", type=Path, required=True)
        install = sub.add_parser("install")
        install.add_argument("directory", type=Path)
        measure = sub.add_parser("measure")
        measure.add_argument("--question-set", type=Path, required=True)
        measure.add_argument("--out", type=Path, required=True)
        judge = sub.add_parser("verdict")
        judge.add_argument("--llamaparse", nargs=2, type=Path, required=True, metavar=("MEASURES", "RUN"))
        judge.add_argument("--unstructured", nargs=2, type=Path, required=True, metavar=("MEASURES", "RUN"))
        judge.add_argument("--out", type=Path, required=True)

    def handle(self, *args, action, **options):
        if action != "verdict" and not settings.DEBUG:
            raise CommandError("Refused with DEBUG off: run it on a database copy.")
        getattr(self, f"_{action}")(**options)

    def _extractions(self, question_set):
        from apps.ai.trial_reads import records_in_question_set
        from apps.documents.models import DocumentKind, PdfExtraction

        ids = records_in_question_set(question_set)
        if not ids:
            raise CommandError(f"{question_set} names no paper in this database.")
        return (PdfExtraction.objects.select_related("record")
                .filter(record_id__in=ids, kind=DocumentKind.MANUSCRIPT).order_by("record__title"))

    def _export(self, *, question_set, out, **_):
        out.mkdir(parents=True, exist_ok=True)
        for extraction in self._extractions(question_set):
            path = out / f"{slugify(extraction.record.title)[:80]}.json"
            path.write_text(json.dumps(gate.export_read(extraction), ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"  {extraction.extractor}: {path.name}")

    def _install(self, *, directory, **_):
        for path in sorted(directory.glob("*.json")):
            read = json.loads(path.read_text(encoding="utf-8"))
            gate.install_read(read)
            self.stdout.write(f"  {read['extractor']}: {read['title']}")

    def _measure(self, *, question_set, out, **_):
        papers = {e.record.title: gate.measure_paper(e) for e in self._extractions(question_set)}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"papers": papers}, indent=1, ensure_ascii=False), encoding="utf-8")
        for title, m in papers.items():
            self.stdout.write(f"  {m['extractor']}: off-level {m['off_level']}/{m['numbered_headings']}, "
                              f"LaTeX {m['latex_formulas']}/{m['formulas']}  {title[:50]}")

    def _verdict(self, *, llamaparse, unstructured, out, **_):
        result = gate.verdict(llamaparse=gate.arm_from_files(*llamaparse),
                              unstructured=gate.arm_from_files(*unstructured))
        payload = {"eligible": result.eligible,
                   "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in result.checks]}
        out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        for check in result.checks:
            self.stdout.write(f"  {'pass' if check.passed else 'FAIL'} {check.name}: {check.detail}")
        self.stdout.write("Eligible." if result.eligible else "Not eligible: LlamaParse stays.")
