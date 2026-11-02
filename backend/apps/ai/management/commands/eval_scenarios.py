"""Run free scenario suites in isolated test databases; write text-free evidence."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.replay import git_commit
from apps.ai.evaluation.runfile import load_json, write_run
from apps.ai.evaluation.scenarios import SUITES, browser_result, junit_result


class Command(BaseCommand):
    help = "Exercise IR-608 access/recovery contracts and real Postgres worker fences (no vendor)."

    def add_arguments(self, parser):
        parser.add_argument("--test-database-name", default="iris_ir608",
                            help="Dedicated test database base name; pytest adds test_.")
        parser.add_argument("--workers", action="store_true", help="Also launch independent worker tests.")
        parser.add_argument("--browser-evidence", help="Named manual browser exercise JSON; never jsdom results.")
        parser.add_argument("--out", default="../docs/evaluation/runs")

    def handle(self, *args, **options):
        try:
            browser = browser_result(load_json(options["browser_evidence"]) if options["browser_evidence"] else None)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        commit = git_commit()
        if browser.get("git_commit", commit) != commit:
            raise CommandError("browser exercise commit does not match this checkout")
        rows = {}
        backend = Path(__file__).resolve().parents[4]
        for name, (kind, nodes) in SUITES.items():
            if name == "durability" and not options["workers"]:
                rows[name] = {"kind": kind, "status": "not_measured", "passed": False,
                              "reason": "independent_workers_not_requested"}
                continue
            with tempfile.TemporaryDirectory(prefix="iris-scenarios-") as temporary:
                report = Path(temporary) / "results.xml"
                # Keep traceback/diagnostic output private and ephemeral.
                with (Path(temporary) / "pytest.log").open("w", encoding="utf-8") as log:
                    try:
                        result = subprocess.run([sys.executable, "-m", "pytest", *nodes,
                                                 "--junitxml", str(report)], cwd=backend,
                                                env={**os.environ, "DB_NAME": options["test_database_name"],
                                                     "AI_RESEARCH_LANE": "off", "AI_EVIDENCE_DECISION": "off"},
                                                stdout=log, stderr=log,
                                                timeout=600, check=False)
                        row = junit_result(report, result.returncode) if report.exists() else {
                            "status": "not_measured", "passed": False, "reason": "test_environment_unavailable"}
                    except subprocess.TimeoutExpired:
                        row = {"status": "not_measured", "passed": False, "reason": "exercise_timeout"}
                rows[name] = {"kind": kind, "suites": nodes, **row}
            self.stdout.write(f"{name}: {rows[name]['status']} passed={rows[name]['passed']}")
        rows["browser"] = browser
        run = {"schema_version": 1, "issue": "IR-608", "git_commit": commit,
               "providers": "fake", "capacity_fit": False, "scenarios": rows,
               "enablement_blocked": any(not row["passed"] for row in rows.values())}
        path = write_run(options["out"], "IR-608-scenarios", run)
        self.stdout.write(f"wrote {path}")
