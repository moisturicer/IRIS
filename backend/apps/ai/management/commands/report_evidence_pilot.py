"""Report the evidence-decision pilot's results (IR-467, ADR-035 §10, §11).

    python manage.py report_evidence_pilot
    python manage.py report_evidence_pilot --curated ../docs/evaluation/runs/<file>.json \\
        --plan ../docs/evaluation/evidence_pilot_plan.json --stage confirmatory

Reads `eval_evidence` result files (the only source of accuracy) and the
shadow rows of real traffic (operations only, no ground truth) and writes one
report that keeps them apart. It calls no model and no vendor, creates no row
of any kind, and puts no question text or Turn id in its output.

An absent sample plan, curated file or shadow row is reported as absent. Under
`--stage confirmatory` a plan that is not fully declared stops the command, and
shadow rows created before the plan's `declared_at` are excluded and counted,
so a confirmatory figure cannot come from data seen before the plan was.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import DatabaseError, OperationalError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.ai.evaluation.pilot_report import (
    PLAN_DECLARED,
    STAGE_CONFIRMATORY,
    STAGE_EXPLORATORY,
    ReportInputError,
    assess_plan,
    build_report,
    check_curated_file,
    render_markdown,
    to_json,
)
from apps.ai.models import ShadowEvidenceDecision, ShadowEvidenceTally

DEFAULT_RUNS = Path(settings.BASE_DIR).parent / "docs" / "evaluation" / "runs"
CURATED_GLOB = "*-evidence-*.json"
REPORT_MARK = "-evidence-pilot-"

ROW_FIELDS = (
    "status",
    "outcome",
    "created_at",
    "finished_at",
    "reclaims",
    "fenced_out_completions",
    "parity_matched",
    "decision",
    "detector",
    "manifest",
)


def _moment(value, label):
    parsed = parse_datetime(value) if value else None
    if value and parsed is None:
        raise CommandError(f"{label} is not an ISO datetime: {value!r}")
    if parsed is not None and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return parsed


class Command(BaseCommand):
    help = (
        "Write the evidence-decision pilot report: curated figures and shadow "
        "operations in separate sections. Calls no model and no vendor."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--curated",
            nargs="*",
            help="eval_evidence result files. Default: every "
            f"{CURATED_GLOB} in --out, newest last.",
        )
        parser.add_argument("--plan", help="Sample plan (JSON); see docs/evaluation/README.md.")
        parser.add_argument(
            "--stage",
            choices=(STAGE_EXPLORATORY, STAGE_CONFIRMATORY),
            default=STAGE_EXPLORATORY,
        )
        parser.add_argument("--since", help="Shadow rows created at or after this ISO datetime.")
        parser.add_argument("--until", help="Shadow rows created before this ISO datetime.")
        parser.add_argument("--out", default=str(DEFAULT_RUNS))
        parser.add_argument(
            "--stamp",
            help="Filename stamp. Default: now. The stamp never enters the report body.",
        )
        parser.add_argument("--no-write", action="store_true")

    def _widen_stream_encoding(self):
        """A Windows console defaults to cp1252 and the report holds a §."""
        for stream in (self.stdout, self.stderr):
            reconfigure = getattr(getattr(stream, "_out", None), "reconfigure", None)
            if reconfigure is None:
                continue
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    def handle(self, *args, **options):
        self._widen_stream_encoding()
        out_dir = Path(options["out"])
        runs = self._curated(options["curated"], out_dir)
        plan = self._plan(options["plan"])
        since, until = _moment(options["since"], "--since"), _moment(options["until"], "--until")

        excluded_early = 0
        if options["stage"] == STAGE_CONFIRMATORY:
            stage = assess_plan(plan)[STAGE_CONFIRMATORY]
            if stage["status"] != PLAN_DECLARED:
                raise CommandError(
                    "the confirmatory sample plan is "
                    f"{stage['status'].replace('_', ' ')}"
                    + (f" (missing: {', '.join(stage['missing'])})" if stage.get("missing") else "")
                    + ". It must be declared before the confirmatory run, and "
                    "this command will not write a confirmatory report without it."
                )
            declared = _moment(stage["plan"]["declared_at"], "plan declared_at")
            if since is None or since < declared:
                since = declared

        shadow_rows, tallies, unavailable = None, None, None
        try:
            rows = ShadowEvidenceDecision.objects.all()
            if options["stage"] == STAGE_CONFIRMATORY:
                excluded_early = rows.filter(created_at__lt=since).count()
            if since:
                rows = rows.filter(created_at__gte=since)
            if until:
                rows = rows.filter(created_at__lt=until)
            shadow_rows = list(rows.order_by("pk").values(*ROW_FIELDS))
            if not (since or until):
                tallies = dict(ShadowEvidenceTally.objects.values_list("code", "count"))
        except (OperationalError, DatabaseError) as exc:
            unavailable = f"database not readable: {type(exc).__name__}"

        report = build_report(
            curated_runs=runs,
            shadow_rows=shadow_rows,
            shadow_tallies=tallies,
            plan=plan,
            stage=options["stage"],
            window={
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
            },
            excluded_early=excluded_early,
            shadow_unavailable=unavailable,
        )

        self.stdout.write(render_markdown(report))
        if not options["no_write"]:
            self._write(report, out_dir, options["stage"], options["stamp"])

    def _curated(self, given, out_dir):
        paths = (
            [Path(p) for p in given]
            if given
            else sorted(
                p for p in out_dir.glob(CURATED_GLOB) if REPORT_MARK not in p.name
            )
        )
        runs = []
        for path in paths:
            try:
                runs.append((path.name, json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError) as exc:
                raise CommandError(f"cannot read curated file {path}: {exc}")
        try:
            for name, data in runs:
                check_curated_file(data, name)
        except ReportInputError as exc:
            raise CommandError(str(exc))
        return runs

    def _plan(self, path):
        if not path:
            return None
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"cannot read the sample plan {path}: {exc}")

    def _write(self, report, out_dir, stage, stamp):
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = stamp or timezone.now().strftime("%Y%m%d-%H%M%S")
        base = out_dir / f"{stamp}{REPORT_MARK}{stage}"
        base.with_suffix(".json").write_text(to_json(report), encoding="utf-8")
        base.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"\nWritten to {base}.json and .md"))
