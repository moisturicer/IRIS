"""Release-readiness manifest over IR-605's campaign evidence (IR-741). Free: no DB, no vendor.

    python manage.py eval_readiness --build --report campaign.json --candidate runtime \\
        --baseline frozen.json --baseline-arm controller --baseline-sha256 <digest> \\
        --scenarios ir608.json --workload w.json --profile p.json --measurements m.json \\
        --approvals approvals.json [--capability cap.json] [--model model.json]
    python manage.py eval_readiness --preflight --workload w.json --profile p.json \\
        --approvals approvals.json
    python manage.py eval_readiness --validate-measurement m.json
    python manage.py eval_readiness --verify manifest.json \\
        [--check-files] [--assert-ready --expect-commit SHA]

Reads files an operator already holds, and writes one manifest naming each input by path and
SHA-256. A blocked manifest is a normal result and exits 0; it says what is missing. This
collects nothing, calls no model and authorizes no release, spending or deployment.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.readiness import (ReadinessRefused, assert_ready, build_readiness,
                                          collection_preflight, scenario_rows,
                                          validate_measurement, verify_manifest)
from apps.ai.evaluation.runfile import file_digest, load_json, write_run
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT

#: Every input file the manifest records by path and SHA-256, named as the manifest names it.
INPUTS = ("report", "baseline", "scenarios", "workload", "profile", "measurements",
          "approvals", "capability", "model")


class Command(BaseCommand):
    help = "Build, verify or preflight the release-readiness manifest."

    def add_arguments(self, parser):
        parser.add_argument("--build", action="store_true")
        parser.add_argument("--preflight", action="store_true",
                            help="May paid collection begin? Names every missing item.")
        parser.add_argument("--validate-measurement", metavar="FILE",
                            help="Check a workload-measurement-1 file is well formed (shape "
                                 "only: a well-formed file is not evidence).")
        parser.add_argument("--verify", metavar="MANIFEST",
                            help="Check a manifest is internally sound.")
        parser.add_argument("--check-files", action="store_true",
                            help="With --verify: re-hash every input the manifest names. "
                                 "Implied by --assert-ready.")
        parser.add_argument("--assert-ready", action="store_true",
                            help="With --verify: also refuse unless the manifest is ready.")
        parser.add_argument("--expect-commit", help="With --assert-ready: the candidate commit.")
        parser.add_argument("--report", help="An eval_campaign report file (architecture mode).")
        parser.add_argument("--candidate", default="runtime")
        parser.add_argument("--baseline", help="The frozen baseline campaign report.")
        parser.add_argument("--baseline-arm", help="The arm of the baseline to compare against.")
        parser.add_argument("--baseline-sha256",
                            help="Frozen digest of the baseline report (canonical JSON).")
        parser.add_argument("--scenarios", help="IR-608 eval_scenarios run file.")
        parser.add_argument("--workload", help="The predeclared workload.")
        parser.add_argument("--profile", help="The authorized latency/cost profile.")
        parser.add_argument("--measurements", help="A workload-measurement-1 file.")
        parser.add_argument("--approvals", help="Recorded approval references.")
        parser.add_argument("--capability", help="A capability-mode report, kept separate.")
        parser.add_argument("--model", help="A model-mode report, kept separate.")
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        modes = [bool(options[k]) for k in ("build", "preflight", "verify",
                                            "validate_measurement")]
        if sum(modes) != 1:
            raise CommandError("give exactly one of --build, --preflight, --verify or "
                               "--validate-measurement")
        try:
            if options["build"]:
                return self._build(options)
            if options["preflight"]:
                return self._preflight(options)
            if options["validate_measurement"]:
                return self._validate_measurement(options)
            self._verify(options)
        except ReadinessRefused as exc:
            raise CommandError(str(exc)) from None

    @staticmethod
    def _load(options, key):
        return load_json(options[key]) if options.get(key) else None

    @staticmethod
    def _mapping(value, what):
        if value is not None and not isinstance(value, dict):
            raise CommandError(f"{what} must be a JSON object")
        return value

    def _validate_measurement(self, options):
        defects = validate_measurement(load_json(options["validate_measurement"]))
        for defect in defects:
            self.stdout.write(f"DEFECT {defect}")
        if defects:
            raise CommandError(f"not a well-formed workload-measurement-1: {len(defects)} "
                               "defect(s)")
        self.stdout.write("well formed. Shape only: this is not evidence, and the workload and "
                          "cost gates still judge the numbers.")

    def _preflight(self, options):
        result = collection_preflight(
            self._mapping(self._load(options, "workload"), "--workload"),
            self._mapping(self._load(options, "profile"), "--profile"),
            self._mapping(self._load(options, "approvals"), "--approvals"))
        w = self.stdout.write
        for item in result["missing"]:
            w(f"MISSING {item}")
        if not result["allowed"]:
            raise CommandError("live collection is not allowed: "
                               f"{len(result['missing'])} item(s) missing")
        w("allowed: every declaration, cap and approval is recorded. This authorizes nothing "
          "by itself.")

    def _verify(self, options):
        manifest = load_json(options["verify"])
        if not isinstance(manifest, dict):
            raise CommandError("manifest cannot be accepted: the file is not a JSON object")
        problems = [] if options["assert_ready"] else verify_manifest(manifest)
        if options["check_files"] or options["assert_ready"]:
            problems += self._file_problems(manifest)
        if options["assert_ready"]:
            try:
                assert_ready(manifest, expect_commit=options["expect_commit"])
            except ReadinessRefused as exc:
                problems.append(str(exc))
        if problems:
            raise CommandError("manifest cannot be accepted: " + "; ".join(problems))
        if options["assert_ready"]:
            self.stdout.write("ready: every gate is met. A named person's release decision is "
                              "still required.")
        else:
            self.stdout.write(f"sound; status {manifest['status']}")

    @staticmethod
    def _file_problems(manifest):
        """Re-hash each input the manifest names: a digest in a file proves nothing alone."""
        problems = []
        for name, ref in (manifest.get("inputs") or {}).items():
            path = Path(str(ref.get("path", "")))
            if not path.is_file():
                problems.append(f"input {name} ({ref.get('path')}) is not on disk to re-hash")
            elif file_digest(path) != ref.get("sha256"):
                problems.append(f"input {name} ({ref.get('path')}) has changed since the "
                                "manifest was built")
        return problems

    def _build(self, options):
        if not options["report"]:
            raise CommandError("--build needs --report")
        baseline = None
        if options["baseline"]:
            for key in ("baseline_arm", "baseline_sha256"):
                if not options[key]:
                    raise CommandError(f"--baseline needs --{key.replace('_', '-')}")
            baseline = {"report": load_json(options["baseline"]), "arm": options["baseline_arm"],
                        "expected_sha256": options["baseline_sha256"]}
        scenarios = self._mapping(self._load(options, "scenarios"), "--scenarios")
        if scenarios is not None:
            scenarios = scenario_rows(scenarios)
        references = {name: {"path": Path(options[name]).as_posix(),
                             "sha256": file_digest(options[name])}
                      for name in INPUTS if options.get(name)}
        manifest = build_readiness(
            self._mapping(load_json(options["report"]), "--report"),
            candidate=options["candidate"], baseline=baseline, scenarios=scenarios,
            workload=self._mapping(self._load(options, "workload"), "--workload"),
            profile=self._mapping(self._load(options, "profile"), "--profile"),
            measurements=self._mapping(self._load(options, "measurements"), "--measurements"),
            approvals=self._mapping(self._load(options, "approvals"), "--approvals"),
            references=references,
            capability=self._mapping(self._load(options, "capability"), "--capability"),
            model=self._mapping(self._load(options, "model"), "--model"))
        out = write_run(options["out"], f"IR-741-readiness-{manifest['set_id']}", manifest)
        w = self.stdout.write
        for name, gate in manifest["gates"].items():
            w(f"{name}: {gate['status']}")
        for line in manifest["blocking"]:
            w(f"BLOCKING {line}")
        for gap in manifest["human_review_gaps"]:
            w(f"HUMAN REVIEW {gap}")
        for decision in manifest["policy_decisions"]:
            w(f"CONFIRM {decision['id']} with {decision['confirm_with']}: {decision['applied']}")
        w(("evidence_met" if manifest["status"] == "evidence_met" else "BLOCKED")
          + f"; wrote {out}")
