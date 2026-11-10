"""Submit a burst of distinct questions to the runtime agent at once (IR-1007).

    python manage.py eval_runtime_capacity --questions burst.json --n 100 \\
        --reader a@cit.edu --reader b@cit.edu ... \\
        --runtime-gateway http://127.0.0.1:8956 --providers real --cache cold

Each question opens its own Conversation as one of the ``--reader`` accounts,
in turn, through the gateway with the edge's grant made in-process (as
``eval_answer_quality --runtime-gateway`` does). ``--deep-share`` of them are
deep runs. Every submission counts (`runtime_burst.summarize`), and the run
file records the campaign spend charged during the burst.

``--providers real`` needs provider admission enforcing: admission refuses any
attempt past the campaign's spendable share, so a burst cannot overspend, and
an attempt it refuses is a failed submission in the denominator.
"""

import json
import threading
import time

import httpx
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from apps.ai.evaluation import runtime_burst
from apps.ai.evaluation.replay import RuntimeAttempts
from apps.ai.evaluation.runfile import load_json, write_run

from apps.ai.evaluation.runtime_replay import RuntimeSeam

from .eval_answer_quality import DEFAULT_OUT, _edge_headers, _grant_fetcher, _Reader, _service_secret

#: Django's production worker count (gunicorn, ADR-017): the edge's grant concurrency.
EDGE_WORKERS = 4


def _campaign():
    from apps.ai.admission.ledger import ALIAS
    from apps.ai.admission.limits import enforcing, read_limits
    from apps.ai.models import ProviderCampaign

    if not enforcing():
        raise CommandError("AI_PROVIDER_ADMISSION is not 'enforce': a paid burst would bypass the campaign")
    limits = read_limits()
    return limits.campaign_key, lambda: ProviderCampaign.objects.using(ALIAS).filter(
        key=limits.campaign_key).values("charged_attempts", "charged_cost_micros").first() or {
        "charged_attempts": 0, "charged_cost_micros": 0}


class Command(BaseCommand):
    help = "Measure a simultaneous burst of distinct questions on the runtime agent."

    def add_arguments(self, parser):
        parser.add_argument("--questions", required=True, help="JSON list of distinct questions.")
        parser.add_argument("--n", type=int, default=100)
        parser.add_argument("--reader", action="append", required=True, help="An account email; repeat.")
        parser.add_argument("--deep-share", type=float, default=0.25)
        parser.add_argument("--runtime-gateway", required=True)
        parser.add_argument("--providers", required=True, choices=("fake", "real"))
        parser.add_argument("--cache", required=True, choices=("cold", "warm"))
        parser.add_argument("--run-deadline-seconds", type=float, default=660.0)
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--conditions", help="JSON object of declared conditions to record.")
        parser.add_argument("--out", default=DEFAULT_OUT)

    def handle(self, *args, **options):
        n = options["n"]
        questions = list(dict.fromkeys(load_json(options["questions"])))
        if len(questions) < n:
            raise CommandError(f"{len(questions)} distinct questions given; {n} needed")
        users = []
        for email in dict.fromkeys(options["reader"]):
            user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
            if user is None:
                raise CommandError(f"no active account {email}")
            users.append(user)
        secret = _service_secret()
        if not secret:
            raise CommandError("AI_GATEWAY_SERVICE_SECRET is unset")
        campaign, charged = (None, None)
        if options["providers"] == "real":
            campaign, charged = _campaign()
        items = runtime_burst.plan_items(questions[:n], readers=list(range(len(users))),
                                         deep_share=options["deep_share"])
        client = httpx.Client(base_url=options["runtime_gateway"], timeout=60.0,
                              limits=httpx.Limits(max_connections=n + 10))

        # The edge is Django: at most EDGE_WORKERS grants at once, each returning its connection.
        edge = threading.BoundedSemaphore(EDGE_WORKERS)

        def seam_for(index):
            # One reader client per submission: the in-process test client is not shared by threads.
            fetch = _grant_fetcher(_Reader(users[index]))

            def granted(record_id):
                with edge:
                    try:
                        return fetch(record_id)
                    finally:
                        connections.close_all()
            return RuntimeSeam(client, prefix="/api/v1/ai",
                               headers=_edge_headers(granted, secret=secret, record_id=None))

        before = charged() if charged else None
        started = time.monotonic()
        rows = runtime_burst.run_burst(items, seam_for, deadline_seconds=options["run_deadline_seconds"],
                                       poll_seconds=options["poll_seconds"], after=connections.close_all)
        wall_ms = round((time.monotonic() - started) * 1000)
        client.close()
        spend = None
        if charged:
            after = charged()
            attempts = RuntimeAttempts(campaign)
            for row in rows:
                physical = attempts.for_run(row["run_id"]) if row["run_id"] else []
                row["attempts"] = len(physical)
                row["cost_usd"] = round(sum(p["cost_usd"] for p in physical), 6)
            spend = {"campaign": campaign,
                     "attempts": after["charged_attempts"] - before["charged_attempts"],
                     "cost_usd": (after["charged_cost_micros"] - before["charged_cost_micros"]) / 1e6}
        for row in rows:
            row["reader"] = users[int(row["reader"])].email
        summary = runtime_burst.summarize(rows, provider=options["providers"], cache=options["cache"],
                                          wall_ms=wall_ms)
        record = {"ticket": "IR-1007", "summary": summary, "spend": spend,
                  "readers": len(users), "deep_share": options["deep_share"],
                  "conditions": json.loads(options["conditions"]) if options.get("conditions") else None,
                  "rows": rows}
        path = write_run(options["out"], "IR-1007-runtime-capacity", record)
        self.stdout.write(f"{summary['claim']}: {summary['outcomes']} in {wall_ms / 1000:.0f} s -> {path}")
