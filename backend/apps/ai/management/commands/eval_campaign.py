"""Plan and report comparable Ask IRIS evaluation campaigns (IR-609). Free: no DB, no vendor.

    python manage.py eval_campaign --smoke run.json --case-cost-usd 0.5 \\
        --campaign-cost-usd 50 --planned-cases 900
    python manage.py eval_campaign --report --set s.json --lock s.lock.json \\
        --runs controller=r1.json --runs controller=r2.json --runs controller=r3.json \\
        --reviews reviews.json --approvals approvals.json --scenarios ir608.json \\
        [--label-review lr.json --packets p.json --counted] [--mode architecture|model]

Reads collected run files, named human reviews and IR-608 evidence. It
collects nothing, calls no model and authorizes no spending or release.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.campaign_report import (CampaignRefused, build_report,
                                                render_markdown, smoke_summary)
from apps.ai.evaluation.conversation_scoring import (DEFAULT_MIN_EXAMPLES, MODES,
                                                     ScoringError, check_evidence)
from apps.ai.evaluation.runfile import load_json, write_run
from apps.ai.management.commands.eval_conversations import Command as ScoreCommand
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT


class Command(BaseCommand):
    help = "Summarize a development smoke, or report a campaign of repeated arm runs."

    def add_arguments(self, parser):
        parser.add_argument("--smoke", help="A development smoke run file.")
        parser.add_argument("--case-cost-usd", type=float)
        parser.add_argument("--campaign-cost-usd", type=float)
        parser.add_argument("--planned-cases", type=int,
                            help="Case executions: cases x arms x repetitions.")
        parser.add_argument("--report", action="store_true")
        parser.add_argument("--set")
        parser.add_argument("--lock")
        parser.add_argument("--runs", action="append", default=[],
                            help="label=run.json; repeat a label once per repetition.")
        parser.add_argument("--reviews")
        parser.add_argument("--approvals", help="Recorded approval references.")
        parser.add_argument("--scenarios", help="IR-608 eval_scenarios run file.")
        parser.add_argument("--label-review")
        parser.add_argument("--packets", action="append", default=[])
        parser.add_argument("--exclude-run", action="append", default=[],
                            help="run_id=reason for a run left out of the report.")
        parser.add_argument("--counted", action="store_true")
        parser.add_argument("--mode", choices=MODES, default="architecture")
        parser.add_argument("--min-examples", type=int, default=DEFAULT_MIN_EXAMPLES)
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        if bool(options["smoke"]) == options["report"]:
            raise CommandError("give exactly one of --smoke or --report")
        try:
            if options["smoke"]:
                return self._smoke(options)
            self._report(options)
        except CampaignRefused as exc:
            raise CommandError(str(exc)) from None

    def _smoke(self, options):
        caps = ("case_cost_usd", "campaign_cost_usd", "planned_cases")
        if any(options[c] is None or options[c] <= 0 for c in caps):
            raise CommandError("--smoke needs positive --case-cost-usd, "
                               "--campaign-cost-usd and --planned-cases")
        summary = smoke_summary(load_json(options["smoke"]),
                                **{c: options[c] for c in caps})
        out = write_run(options["out"], "IR-609-smoke", summary)
        w = self.stdout.write
        w(f"smoke {summary['run_id']} ({summary['providers']}): {summary['complete']}/"
          f"{summary['conversations']} complete, outcomes {summary['outcomes']}")
        w(f"dearest conversation ${summary['max_conversation_cost_usd']:.4f} across "
          f"{', '.join(summary['operations_in_cap']) or 'no operations'}; projected "
          f"${summary['projected_campaign_cost_usd']:.4f} for {summary['planned_cases']} cases")
        for reason in summary["not_ready_reasons"]:
            w(f"NOT READY {reason}")
        w(("ready" if summary["ready"] else "not ready") + f"; wrote {out}")

    def _report(self, options):
        for key in ("set", "lock", "reviews"):
            if not options[key]:
                raise CommandError(f"--report needs --{key}")
        campaign = {}
        for spec in options["runs"]:
            label, _, path = spec.partition("=")
            if not path:
                raise CommandError("--runs takes label=run.json")
            campaign.setdefault(label, []).append(load_json(path))
        data, lock = load_json(options["set"]), load_json(options["lock"])
        reviews = load_json(options["reviews"])
        bundles = []
        for path in options["packets"]:
            loaded = load_json(path)
            bundles.extend(loaded if isinstance(loaded, list) else [loaded])
        excluded = []
        for spec in options["exclude_run"]:
            run_id, _, reason = spec.partition("=")
            if not reason.strip():
                raise CommandError("--exclude-run takes run_id=reason")
            excluded.append({"run_id": run_id, "reason": reason})
        scenarios = None
        if options["scenarios"]:
            loaded = load_json(options["scenarios"])
            scenarios = loaded.get("scenarios", loaded)
        approvals = load_json(options["approvals"]) if options["approvals"] else None
        report = build_report(data, lock, campaign, reviews, mode=options["mode"],
                              approvals=approvals, scenarios=scenarios,
                              min_examples=options["min_examples"],
                              counted=options["counted"], excluded=excluded)
        if options["counted"]:
            self._counted_evidence(data, options, lock, campaign, bundles, reviews)
        out = write_run(options["out"], f"IR-609-campaign-{data['set_id']}", report)
        out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
        w = self.stdout.write
        for label, arm in report["arms"].items():
            if arm["status"] != "measured":
                w(f"{label}: not_measured ({arm['reason']})")
                continue
            completion = arm["summary"]["task_completion"]
            w(f"{label}: {len(arm['repetitions'])} repetitions, completion "
              f"{completion['min']}-{completion['max']}, "
              f"breaches {len(arm['access_breaches'])}")
        for reason in report["not_counted_reasons"]:
            w(f"NOT COUNTED {reason}")
        for block in report["blocking"]:
            w(f"BLOCKING {block}")
        w(f"wrote {out} and {out.with_suffix('.md').name}")

    @staticmethod
    def _counted_evidence(data, options, lock, campaign, bundles, reviews):
        """The IR-607 counted checks, applied to every repetition."""
        flat = {f"{label}#{i}": run for label, runs in campaign.items()
                for i, run in enumerate(runs)}
        reasons = ScoreCommand._not_counted(data, options, lock, flat, bundles,
                                            data.get("label_status") != "human_reviewed")
        if reasons:
            raise CommandError("not a counted campaign: " + "; ".join(reasons))
        try:
            for run in flat.values():
                check_evidence([r for r in reviews if r.get("run_id") == run.get("run_id")],
                               [b for b in bundles if b.get("run_id") == run.get("run_id")],
                               {run["arm"]: run})
        except ScoringError as exc:
            raise CommandError(str(exc)) from None
