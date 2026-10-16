"""Validate a conversation set or score reviewed runs (IR-598). Free: no DB, no vendor.

    python manage.py eval_conversations --set s.json --validate \\
        [--lock s.lock.json] [--write-lock s.lock.json] [--min-conversations 100]
    python manage.py eval_conversations --set s.json --score \\
        --runs current=a.json --runs controller=b.json --reviews reviews.json \\
        [--preferences p.json] [--judge j.json] [--mode architecture|model]

Scoring reads collected runs and human reviews; it collects nothing and
calls no model. A run made with fake providers is a contract check, never
quality evidence. Paid collection is not offered here.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversation_scoring import (
    ARMS,
    DEFAULT_MIN_EXAMPLES,
    MODES,
    ScoringError,
    calibrate_judge,
    check_conditions,
    cost_latency,
    preference,
    score_reviews,
)
from apps.ai.evaluation.conversations import (
    DEFAULT_MIN_CONVERSATIONS,
    check_lock,
    lock_record,
    validate_set,
)
from apps.ai.evaluation.runfile import file_digest, load_json, write_run
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT


def _pct(frac):
    value = frac["value"]
    if value is None:
        return "n/a (0)"
    return (f"{value:.3f} ({frac['numerator']}/{frac['denominator']}, "
            f"95% CI {frac['wilson_low']:.2f}-{frac['wilson_high']:.2f})")


class Command(BaseCommand):
    help = "Validate a conversation set, or score reviewed runs per arm and family."

    def add_arguments(self, parser):
        parser.add_argument("--set", required=True)
        parser.add_argument("--validate", action="store_true")
        parser.add_argument("--score", action="store_true")
        parser.add_argument("--lock", help="Lock file to check the set against.")
        parser.add_argument("--write-lock", help="Record the set's digests to this file.")
        parser.add_argument("--min-conversations", type=int, default=DEFAULT_MIN_CONVERSATIONS)
        parser.add_argument("--runs", action="append", default=[], help="arm=run.json")
        parser.add_argument("--reviews")
        parser.add_argument("--preferences")
        parser.add_argument("--judge")
        parser.add_argument("--mode", choices=MODES, default="architecture")
        parser.add_argument("--min-examples", type=int, default=DEFAULT_MIN_EXAMPLES)
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        if options["validate"] == options["score"]:
            raise CommandError("give exactly one of --validate or --score")
        data = load_json(options["set"])
        if options["validate"]:
            return self._validate(data, options)
        self._score(data, options)

    def _validate(self, data, options):
        w = self.stdout.write
        report = validate_set(data, min_conversations=options["min_conversations"])
        w(f"set {report['set_id']} ({report['label_status']}): {report['total']} conversations, "
          f"{report['supported_unambiguous']} supported and unambiguous")
        for split, counts in report["counts"].items():
            w(f"{split}: " + " ".join(f"{f}={n}" for f, n in counts.items()))
        w(f"coverage gaps: {', '.join(report['coverage_gaps']) or 'none'}")
        w(f"shared across splits (allowed): {len(report['allowed_shared'])}")
        w(f"digests development={report['digests']['development'][:16]} "
          f"held_out={report['digests']['held_out'][:16]}")
        if options["write_lock"]:
            import json
            from pathlib import Path
            Path(options["write_lock"]).write_text(
                json.dumps(lock_record(data), indent=2) + "\n", encoding="utf-8")
            w(f"wrote lock {options['write_lock']}")
        mismatched = check_lock(data, load_json(options["lock"])) if options["lock"] else []
        for error in report["errors"]:
            w(f"ERROR {error}")
        if mismatched:
            w(f"LOCK MISMATCH {', '.join(mismatched)}")
        if report["errors"] or mismatched:
            raise CommandError("validation failed")
        w("valid" + ("" if report["ready"] else " (not ready: coverage gaps)"))

    def _score(self, data, options):
        w = self.stdout.write
        report = validate_set(data, min_conversations=0)
        if report["errors"]:
            raise CommandError("the set is invalid: " + "; ".join(report["errors"]))
        runs = {}
        for spec in options["runs"]:
            label, _, path = spec.partition("=")
            if not path:
                raise CommandError("--runs takes arm=run.json")
            runs[label] = load_json(path)
        if not options["reviews"] or not runs:
            raise CommandError("--score needs --runs and --reviews")
        reviews = load_json(options["reviews"])
        try:
            if len(runs) > 1:
                check_conditions(runs, mode=options["mode"])
            arms = {}
            for label, run in runs.items():
                arm = run.get("arm") if options["mode"] == "architecture" else label
                scored = score_reviews(data, reviews, arm=label,
                                       min_examples=options["min_examples"])
                arms[label] = {"architecture": arm, "scores": scored,
                               "cost_latency": cost_latency(run)}
            extras = {}
            if options["preferences"]:
                extras["preference"] = preference(load_json(options["preferences"]))
            if options["judge"]:
                judge = load_json(options["judge"])
                items = judge["items"] if isinstance(judge, dict) else judge
                extras["judge"] = calibrate_judge(
                    items, adjudication=judge.get("adjudication") if isinstance(judge, dict) else None)
        except ScoringError as exc:
            raise CommandError(str(exc)) from None
        blocked = [k for k, v in arms.items() if v["scores"]["enablement_blocked"]]
        out = write_run(options["out"], f"conversations-{data['set_id']}", {
            "set_id": data["set_id"], "set_sha256": file_digest(options["set"]),
            "label_status": data["label_status"], "mode": options["mode"],
            "digests": report["digests"], "arms": arms, **extras,
            "enablement_blocked": bool(blocked), "blocked_arms": blocked,
        })
        self._print(arms, extras, blocked, out, data["label_status"])

    def _print(self, arms, extras, blocked, out, label_status):
        w = self.stdout.write
        if label_status != "human_reviewed":
            w("NOTE labels are draft_unreviewed: results are exploratory")
        for label, entry in arms.items():
            scores = entry["scores"]
            w(f"== {label} ({entry['architecture']}) reviewers {', '.join(scores['reviewers'])}")
            for family, m in scores["families"].items():
                w(f"{family} [{m['status']}] n={m['reviewed']} "
                  f"completion {_pct(m['task_completion'])} "
                  f"claims {_pct(m['claim_support'])} citations {_pct(m['citation_support'])}")
            for name, t in scores["targets"].items():
                w(f"target {name} >= {t['target']}: {t['status']} "
                  f"[{t['label']}]")
            cl = entry["cost_latency"]
            w(f"capacity {cl['capacity']} ({cl['capacity_reason'] or 'ok'}); {cl['evidence']}")
            for cache in ("cold", "warm"):
                g = cl[cache]
                w(f"{cache}: n={g['n']} p50={g['p50']} p95={g['p95']} "
                  f"cost/success={g['cost_per_successful_task']}")
            w(f"breaches {scores['access_breaches']['count']} of "
              f"{scores['access_breaches']['suite_size']}: {scores['access_breaches']['note']}")
        if "preference" in extras:
            p = extras["preference"]
            w(f"preference wins {p['wins']} losses {p['losses']} ties {p['ties']} "
              f"of {p['denominator']}, p={p['p_value']}")
        if "judge" in extras:
            j = extras["judge"]
            w(f"judge n={j['n']} agreement {j['agreement']:.2f} kappa {j['kappa']} "
              f"institutional_claim_allowed {j['institutional_claim_allowed']}")
        if blocked:
            w(f"ENABLEMENT BLOCKED by access breach in: {', '.join(blocked)}")
        w(f"wrote {out}")
