"""Submit a burst of distinct questions together and count every one (IR-550).

    IRIS_EVAL_TOKEN=... python manage.py eval_pilot_capacity \\
        --base-url http://localhost:8000 --questions burst.json --n 100 \\
        --providers fake --cache cold --user reader@cit.edu

Sends ``--n`` distinct questions from ``--questions`` (a JSON list of
strings) to ``/api/v1/ai/ask/stream/`` at once, and reports the share
generated within 10 s of the original submission over **every** submission
(`capacity.summarize`). Only ``--providers real --cache cold`` with at least
100 distinct questions can measure capacity; anything else is a control or
unverified, and the run file says which.

``--user`` names the account whose JWT is in ``IRIS_EVAL_TOKEN``. Each
question then gets its own new Conversation of that user, so a server with
``AI_DURABLE_ASK`` on queues it and the measured latency includes the queue.
Without ``--user`` the questions are one-off and answered inline. Which path
ran is read from the streams (`run_queued`), not declared.

One identity is throttled (``ai_query``, 60/hour); a throttled submission is
a rejection and stays in the denominator. A real 100-submission burst needs
that limit raised for the evaluation, which is the deployment owner's call.

``--providers real`` first plans the burst against the shared provider
campaign at each run's per-run cap. If it does not fit before the protected
reserve, nothing is sent: the run file records the plan and capacity stays
unverified. ``--providers`` and ``--cache`` declare how the server was
configured; a ``cold`` burst that reports any cache hit is counted as warm.
"""

import asyncio

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.campaign import PaidRunRefused, paid_plan
from apps.ai.evaluation.capacity import Burst, summarize
from apps.ai.evaluation.http_driver import submit_all
from apps.ai.evaluation.runfile import eval_token, load_json, write_run
from apps.ai.management.commands.eval_retrieval import DEFAULT_OUT
from apps.ai.models import Conversation

from .eval_pilot_milestone import STREAM_PATH


def _path(streams) -> str:
    queued = sum(any(name == "run_queued" for name, _ in events) for events in streams)
    return "queued" if queued == len(streams) else "inline" if not queued else "mixed"


class Command(BaseCommand):
    help = "Measure a simultaneous burst of distinct Ask IRIS submissions."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--questions", required=True, help="JSON list of distinct questions.")
        parser.add_argument("--n", type=int, default=100)
        parser.add_argument("--providers", required=True, choices=("fake", "real"))
        parser.add_argument("--cache", required=True, choices=("cold", "warm"))
        parser.add_argument("--user", help="The token's account; queues each question.")
        parser.add_argument("--out", default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        n = options["n"]
        questions = list(dict.fromkeys(load_json(options["questions"])))
        if len(questions) < n:
            raise CommandError(f"{len(questions)} distinct questions given; {n} needed")
        questions = questions[:n]
        token = eval_token()

        record = {"providers": options["providers"], "cache": options["cache"], "requested": n}
        plan = None
        if options["providers"] == "real":
            try:
                plan = paid_plan(n)
            except PaidRunRefused as exc:
                raise CommandError(str(exc)) from None
            record["plan"] = plan

        if plan is not None and not plan["fits"]:
            record["summary"] = {"claim": "unverified", "submissions": 0,
                                 "why": f"burst does not fit the spendable campaign: {plan['blocking']}"}
        else:
            extras = self._conversations(options["user"], n)
            results = asyncio.run(submit_all(questions, base_url=options["base_url"],
                                             path=STREAM_PATH, token=token, extras=extras))
            submissions = [submission for submission, _ in results]
            record["summary"] = summarize(Burst(
                tuple(submissions), provider=options["providers"], cache=options["cache"],
                simultaneous=True, path=_path([events for _, events in results])))
            record["submissions"] = [
                {"index": i, "outcome": s.result, "submitted_ms": s.submitted_ms,
                 "final_ms": s.final_ms, "cache_hits": s.cache_hits}
                for i, s in enumerate(submissions)]

        out = write_run(options["out"],
                        f"pilot-capacity-{options['providers']}-{options['cache']}", record)
        summary = record["summary"]
        self.stdout.write(f"claim {summary['claim']}")
        if summary.get("submissions"):
            self.stdout.write(f"{summary['successes_under_goal']}/{summary['submissions']} generated "
                              f"under 10 s on the {summary['path']} path; "
                              f"outcomes {summary['outcomes']}")
        self.stdout.write(f"wrote {out}")

    def _conversations(self, email, n):
        if not email:
            return None
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"no account {email!r}")
        return [{"conversation_id": Conversation.objects.create(user=user).pk} for _ in range(n)]
