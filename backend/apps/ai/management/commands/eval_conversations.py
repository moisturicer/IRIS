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

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.conversation_scoring import (
    DEFAULT_MIN_EXAMPLES,
    MODES,
    ScoringError,
    calibrate_judge,
    check_conditions,
    check_evidence,
    cost_latency,
    diagnostic_stages,
    preference,
    score_reviews,
)
from apps.ai.evaluation.conversations import (
    DEFAULT_MIN_CONVERSATIONS,
    check_label_review,
    check_lock,
    lock_record,
    postdates_lock,
    validate_set,
)
from apps.ai.evaluation.runfile import file_digest, load_json, write_json, write_run
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
        parser.add_argument("--lock", help="Lock file to check the set against. "
                            "Required with --score.")
        parser.add_argument("--allow-draft", action="store_true",
                            help="Score a draft_unreviewed set as exploratory only.")
        parser.add_argument("--write-lock", help="Record the set's digests to this file.")
        parser.add_argument("--label-review", help="A named person's label review of this "
                            "set version. Required for a counted --score.")
        parser.add_argument("--min-conversations", type=int, default=DEFAULT_MIN_CONVERSATIONS)
        parser.add_argument("--runs", action="append", default=[], help="arm=run.json")
        parser.add_argument("--reviews")
        parser.add_argument("--packets", action="append", default=[],
                            help="Review packets from eval_review_packets; checks evidence.")
        parser.add_argument("--counted", action="store_true",
                            help="Refuse unless this is counted quality evidence.")
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
        for warning in report["warnings"]:
            w(f"WARNING topic overlap {warning['development_topic']!r} / "
              f"{warning['held_out_topic']!r} share {', '.join(warning['words'])}")
        w(f"coverage gaps: {', '.join(report['coverage_gaps']) or 'none'}")
        w(f"shared across splits (allowed): {len(report['allowed_shared'])}")
        w(f"digests development={report['digests']['development'][:16]} "
          f"held_out={report['digests']['held_out'][:16]}")
        mismatched = check_lock(data, load_json(options["lock"])) if options["lock"] else []
        label = None
        if options["label_review"]:
            label = load_json(options["label_review"])
            problems = check_label_review(data, label)
            for problem in problems:
                w(f"LABEL REVIEW {problem}")
            if problems:
                raise CommandError("the label review does not cover this set version")
            w(f"label review by {label['reviewer']} covers every conversation"
              + (" (development fixture: not a person's approval)" if label.get("fixture") else ""))
        for error in report["errors"]:
            w(f"ERROR {error}")
        for blocker in report["lock_blockers"]:
            w(f"LOCK BLOCKED {blocker}")
        if mismatched:
            w(f"LOCK MISMATCH {', '.join(mismatched)}")
        if report["errors"] or mismatched:
            raise CommandError("validation failed")
        if options["write_lock"]:
            if report["lock_blockers"]:
                raise CommandError("not locked: " + "; ".join(report["lock_blockers"]))
            lock = {**lock_record(data), "locked_at": datetime.now(timezone.utc).isoformat()}
            if label is not None:
                lock["label_review"] = {"reviewer": label["reviewer"],
                                        "fixture": bool(label.get("fixture")),
                                        "sha256": file_digest(options["label_review"])}
            write_json(options["write_lock"], lock)
            w(f"wrote lock {options['write_lock']}")
        w("valid" + ("" if report["ready"] else " (not ready: coverage gaps)"))

    def _score(self, data, options):
        report = validate_set(data, min_conversations=0)
        if report["errors"]:
            raise CommandError("the set is invalid: " + "; ".join(report["errors"]))
        if not options["lock"]:
            raise CommandError("--score requires --lock")
        lock = load_json(options["lock"])
        mismatched = check_lock(data, lock)
        if mismatched:
            raise CommandError(f"the set no longer matches its lock: {', '.join(mismatched)}")
        draft = data["label_status"] != "human_reviewed"
        if draft and not options["allow_draft"]:
            raise CommandError("labels are draft_unreviewed; pass --allow-draft for an "
                               "exploratory score")
        runs = {}
        for spec in options["runs"]:
            label, _, path = spec.partition("=")
            if not path:
                raise CommandError("--runs takes arm=run.json")
            runs[label] = load_json(path)
        if not options["reviews"] or not runs:
            raise CommandError("--score needs --runs and --reviews")
        reviews = load_json(options["reviews"])
        bundles = []
        for path in options["packets"] or ():
            loaded = load_json(path)
            bundles.extend(loaded if isinstance(loaded, list) else [loaded])
        reasons = self._not_counted(data, options, lock, runs, bundles, draft)
        reasons += [f"{r.get('conversation')}: reviewer_kind is not stated"
                    for r in reviews if r.get("arm") in runs and "reviewer_kind" not in r]
        if options["counted"] and reasons:
            raise CommandError("not a counted campaign: " + "; ".join(reasons))
        self._check_freeze(data, lock, runs, reviews)
        try:
            check_conditions(runs, mode=options["mode"], set_digests=report["digests"])
            if bundles:
                check_evidence(reviews, bundles, runs)
            arms = {}
            for label, run in runs.items():
                arm = run.get("arm") if options["mode"] == "architecture" else label
                scored = score_reviews(data, reviews, arm=label,
                                       min_examples=options["min_examples"],
                                       rubric_version=run["manifest"]["rubric_version"])
                arms[label] = {"architecture": arm, "scores": scored,
                               "cost_latency": cost_latency(run),
                               "diagnostics": diagnostic_stages(run)}
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
        for label, entry in arms.items():
            single = sorted(c for c, a in entry["scores"]["review_audit"].items()
                            if a["resolution"] == "single")
            if single:
                reasons.append(f"{label}: {len(single)} conversations have one review, "
                               f"not two ({', '.join(single[:5])})")
        if options["counted"] and reasons:
            raise CommandError("not a counted campaign: " + "; ".join(reasons))
        blocked =[k for k, v in arms.items() if v["scores"]["enablement_blocked"]]
        out = write_run(options["out"], f"conversations-{data['set_id']}", {
            "set_id": data["set_id"], "set_sha256": file_digest(options["set"]),
            "label_status": data["label_status"], "exploratory_draft_labels": draft,
            "counted": not reasons, "not_counted_reasons": reasons,
            "mode": options["mode"],
            "digests": report["digests"], "arms": arms, **extras,
            "enablement_blocked": bool(blocked), "blocked_arms": blocked,
        })
        self._print(arms, extras, blocked, out, draft, reasons)

    @staticmethod
    def _not_counted(data, options, lock, runs, bundles, draft):
        """Why this score is not counted quality evidence; empty means it is."""
        reasons = []
        if draft:
            reasons.append("labels are draft_unreviewed")
        if not options["label_review"]:
            reasons.append("no label review was supplied")
        else:
            label = load_json(options["label_review"])
            problems = check_label_review(data, label)
            if problems:
                raise CommandError("the label review does not cover this set version: "
                                   + "; ".join(problems[:5]))
            pinned = (lock.get("label_review") or {}).get("sha256")
            if pinned and pinned != file_digest(options["label_review"]):
                raise CommandError("the label review differs from the one recorded in the lock")
            if label.get("fixture"):
                reasons.append("the label review is a development fixture, not a person's approval")
        if not bundles:
            reasons.append("no review packets: evidence authorization is unchecked")
        corpus = (data.get("corpus") or {}).get("paper_set_sha256")
        for name, run in runs.items():
            if run.get("providers") != "real":
                reasons.append(f"{name}: fake providers are a contract check")
            if run["manifest"].get("corpus_snapshot_digest") != corpus:
                reasons.append(f"{name}: run corpus differs from the locked corpus snapshot")
        return reasons

    @staticmethod
    def _check_freeze(data, lock, runs, reviews):
        held = {c["id"] for c in data["conversations"] if c.get("split") == "held_out"}
        froze = lock.get("locked_at")
        for name, run in runs.items():
            if not any(r.get("arm") == name and r.get("conversation") in held for r in reviews):
                continue
            if not postdates_lock(run["manifest"].get("timestamp_utc"), lock):
                raise CommandError(f"{name}: held-out output must postdate the lock; prompts "
                                   f"and rubric froze at {froze or 'no recorded time'}")
            if run["manifest"].get("rubric_version") != lock.get("rubric_version"):
                raise CommandError(f"{name}: rubric differs from the one that froze with the lock")

    def _print(self, arms, extras, blocked, out, draft, reasons=()):
        w = self.stdout.write
        if draft:
            w("NOTE exploratory_draft_labels: labels are draft_unreviewed")
        for reason in reasons:
            w(f"NOT COUNTED {reason}")
        for label, entry in arms.items():
            scores = entry["scores"]
            w(f"== {label} ({entry['architecture']}) reviewers {', '.join(scores['reviewers'])}")
            for family, m in scores["families"].items():
                w(f"{family} [{m['status']}] n={m['reviewed']} "
                  f"completion {_pct(m['task_completion'])} "
                  f"claims {_pct(m['claim_support'])} citations {_pct(m['citation_support'])}")
            for split, m in scores["splits"].items():
                w(f"{split}: n={m['reviewed']} completion {_pct(m['task_completion'])} "
                  f"claims {_pct(m['claim_support'])}")
            for name, t in scores["targets"].items():
                w(f"target {name} >= {t['target']}: {t['status']} "
                  f"[{t['label']}]")
            w(f"reviews: {scores['double_reviewed']} double-reviewed, not reviewed: "
              f"{', '.join(scores['not_reviewed']) or 'none'}")
            stages = entry["diagnostics"]["stages"]
            w("diagnostic stages (private, never a verdict): "
              + (", ".join(f"{k}={v}" for k, v in sorted(stages.items())) or "none"))
            cl = entry["cost_latency"]
            w(f"capacity {cl['capacity']} ({cl['capacity_reason'] or 'ok'}); {cl['evidence']}")
            for cache in ("cold", "warm"):
                g = cl[cache]
                w(f"{cache}: n={g['n']} p50={g['p50']}ms p95={g['p95']}ms no-latency={g['no_latency_recorded']} "
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
