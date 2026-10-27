"""Run or rescore the first fixed-workflow milestone (IR-550).

    IRIS_EVAL_TOKEN=... python manage.py eval_pilot_milestone \\
        --set labels.json --base-url http://localhost:8000 --tier proxy --providers fake
    python manage.py eval_pilot_milestone --set labels.json --from-run run.json \\
        --tier proxy --reviews reviews.json [--judge judge.json]

The first form submits each metadata-count, topic-count and listing case to a
running Ask IRIS over ``/api/v1/ai/ask/stream/``, one at a time, as the user
whose JWT is in ``IRIS_EVAL_TOKEN`` (never printed or written). The second
rescores a published run file, so a reviewer's verdicts can be added without
asking anything again.

``--providers real`` refuses to start unless provider admission is enforcing
and every question fits the campaign's spendable share at its per-run cap.
Paid evaluation needs its own approvals (pilot README §5-§7): this command
approves nothing.

The run file keeps states, figures and Record keys only (`sanitize_done`) and
is written to ``docs/evaluation/runs/``. Records are matched to the set's
keys by exact title; a title the database holds twice is refused.
"""

import asyncio

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.campaign import PaidRunRefused, paid_plan
from apps.ai.evaluation.http_driver import sanitize_done, submit_all
from apps.ai.evaluation.milestone import (
    MILESTONE_FAMILIES,
    TIERS,
    MilestoneSetError,
    Observation,
    parse_milestone_set,
    score,
)
from apps.ai.evaluation.runfile import eval_token, file_digest, load_json, write_run
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT
from apps.records.models import Record

STREAM_PATH = "/api/v1/ai/ask/stream/"


def record_keys(records) -> dict[int, str]:
    """Database Record id to the set's key, by exact title."""
    by_title = {row["title"]: row["key"] for row in records}
    keys, seen = {}, set()
    for pk, title in Record.objects.filter(title__in=by_title).values_list("pk", "title"):
        if title in seen:
            raise CommandError(f"title {title!r} is held by more than one Record")
        seen.add(title)
        keys[pk] = by_title[title]
    return keys


class Command(BaseCommand):
    help = "Run or rescore the first fixed-workflow milestone against pinned labels."

    def add_arguments(self, parser):
        parser.add_argument("--set", required=True, help="Milestone set (baseline fixture format).")
        parser.add_argument("--tier", required=True, choices=TIERS)
        parser.add_argument("--base-url", help="A running Ask IRIS to submit to.")
        parser.add_argument("--providers", choices=("fake", "real"),
                            help="What the server answers with. Required with --base-url.")
        parser.add_argument("--from-run", help="Rescore a published run file instead.")
        parser.add_argument("--reviews", help="Human review verdicts (JSON list).")
        parser.add_argument("--judge", help="Model judge scores (JSON list).")
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        data = load_json(options["set"])
        try:
            milestone = parse_milestone_set(data)
        except MilestoneSetError as exc:
            raise CommandError(str(exc)) from None
        if bool(options["base_url"]) == bool(options["from_run"]):
            raise CommandError("give exactly one of --base-url or --from-run")

        if options["from_run"]:
            previous = load_json(options["from_run"])
            runs, providers = previous["runs"], previous["providers"]
        else:
            providers = options["providers"]
            if not providers:
                raise CommandError("--providers is required with --base-url")
            runs = self._submit(data, options["base_url"], providers)

        observations = [Observation(r["case"], r["done"].get("mode"), r["done"].get("listing"),
                                    r.get("latency_ms")) for r in runs]
        report = score(milestone, observations, tier=options["tier"],
                       reviews=load_json(options["reviews"]) if options["reviews"] else (),
                       judge=load_json(options["judge"]) if options["judge"] else ())
        out = write_run(options["out"], f"pilot-milestone-{data['name']}", {
            "set": data["name"], "set_sha256": file_digest(options["set"]),
            "tier": options["tier"], "providers": providers,
            "rescored_from": options["from_run"], "runs": runs, "report": report,
        })
        self._print(report, out)

    def _submit(self, data, base_url, providers):
        token = eval_token()
        cases = [c for c in data["cases"] if c["family"] in MILESTONE_FAMILIES]
        if providers == "real":
            try:
                plan = paid_plan(len(cases))
            except PaidRunRefused as exc:
                raise CommandError(str(exc)) from None
            if not plan["fits"]:
                raise CommandError(
                    f"{len(cases)} runs do not fit the spendable campaign: {plan['blocking']}")
        keys = record_keys(data["records"])
        runs = []
        for case in cases:
            ((submission, events),) = asyncio.run(submit_all(
                [case["question"]], base_url=base_url, path=STREAM_PATH, token=token))
            done = next((d for name, d in reversed(events) if name == "done"), None)
            runs.append({
                "case": case["id"], "outcome": submission.result,
                "latency_ms": submission.elapsed_ms,
                "done": sanitize_done(done, keys=keys) if done else {},
            })
        return runs

    def _print(self, report, out):
        w = self.stdout.write
        counts = report["metadata_counts"]
        w(f"metadata counts exact {counts['exact']}/{counts['denominator']}"
          f" (missing {len(counts['missing'])})")
        for name in ("precision", "recall"):
            f = report["screening"][name]
            w(f"screening {name} {f['numerator']}/{f['denominator']}")
        f = report["candidate_recall"]["overall"]
        w(f"candidate recall {f['numerator']}/{f['denominator']}")
        f = report["coverage"]["unassessed_rate"]
        w(f"unassessed {f['numerator']}/{f['denominator']}")
        w(f"breaches {len(report['breaches'])}")
        w(f"answer quality {report['answer_quality']['status']}")
        w(f"standing {report['standing']['evidence']}: {report['standing']['why']}")
        w(f"wrote {out}")
