"""Submit a burst of distinct questions together and count every one (IR-550).

    IRIS_EVAL_TOKEN=... python manage.py eval_pilot_capacity \\
        --base-url http://localhost:8000 --questions burst.json --n 100 \\
        --providers fake --cache cold

Sends ``--n`` distinct questions from ``--questions`` (a JSON list of
strings) to ``/api/v1/ai/ask/stream/`` at once, and reports the share
generated within 10 s of the original submission over **every** submission
(`capacity.summarize`). Only ``--providers real --cache cold`` with at least
100 distinct questions can measure capacity; anything else is a control or
unverified, and the run file says which.

``--providers real`` first plans the burst against the shared provider
campaign at each run's per-run cap. If it does not fit before the protected
reserve, nothing is sent: the run file records the plan and capacity stays
unverified. ``--cache`` is the operator's declaration of what the server was
configured with; this command cannot see it.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.campaign import PaidRunRefused, paid_plan
from apps.ai.evaluation.capacity import Burst, summarize
from apps.ai.evaluation.http_driver import burst
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT, _git_commit

from .eval_pilot_milestone import STREAM_PATH, _load


class Command(BaseCommand):
    help = "Measure a simultaneous burst of distinct Ask IRIS submissions."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--questions", required=True, help="JSON list of distinct questions.")
        parser.add_argument("--n", type=int, default=100)
        parser.add_argument("--providers", required=True, choices=("fake", "real"))
        parser.add_argument("--cache", required=True, choices=("cold", "warm"))
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        n = options["n"]
        questions = list(dict.fromkeys(_load(options["questions"])))
        if len(questions) < n:
            raise CommandError(f"{len(questions)} distinct questions given; {n} needed")
        questions = questions[:n]
        token = os.environ.get("IRIS_EVAL_TOKEN", "").strip()
        if not token:
            raise CommandError("IRIS_EVAL_TOKEN must hold the evaluating user's JWT")

        record = {"commit": _git_commit(), "providers": options["providers"],
                  "cache": options["cache"], "requested": n}
        plan = None
        if options["providers"] == "real":
            try:
                plan = paid_plan(n)
            except PaidRunRefused as exc:
                raise CommandError(str(exc)) from None
            record["plan"] = plan

        if plan is not None and not plan["fits"]:
            record["summary"] = {"claim": "unverified", "submitted": 0,
                                 "why": f"burst does not fit the spendable campaign: {plan['blocking']}"}
        else:
            submissions = asyncio.run(burst(questions, base_url=options["base_url"],
                                            path=STREAM_PATH, token=token))
            record["summary"] = summarize(Burst(tuple(submissions), provider=options["providers"],
                                                cache=options["cache"], simultaneous=True))
            record["submissions"] = [
                {"index": i, "outcome": s.outcome, "submitted_ms": s.submitted_ms,
                 "final_ms": s.final_ms} for i, s in enumerate(submissions)]

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path(options["out"]) / f"{stamp}-pilot-capacity-{options['providers']}-{options['cache']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        summary = record["summary"]
        self.stdout.write(f"claim {summary['claim']}")
        if summary.get("submitted"):
            self.stdout.write(f"{summary['successes_under_goal']}/{summary['submitted']} generated "
                              f"under 10 s; outcomes {summary['outcomes']}")
        self.stdout.write(f"wrote {out}")
