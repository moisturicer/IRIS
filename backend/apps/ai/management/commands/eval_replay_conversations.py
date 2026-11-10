"""Replay development cases through the dedicated AI runtime's reader edge.

The cases go through the runtime's authenticated submit / progress / reopen
routes at ``--runtime-url`` (IR-740). That service is not this process, so its
provider mode and model are declared by the operator and recorded as declared.
The run is ``arm: runtime`` with its own engine, transport and schema identity.
Django's own arms (``current``, ``fixed_synthesis``, ``controller``) went with
its answer path in IR-957.
"""

from __future__ import annotations

from functools import partial

import httpx
from django.core.management.base import BaseCommand, CommandError

from apps.ai.admission.limits import ENFORCE, mode, read_limits
from apps.ai.evaluation.campaign_report import (CampaignRefused, require_frozen_for_held_out,
                                                require_paid_held_out)
from apps.ai.evaluation.conversations import check_lock, split_digests, validate_set
from apps.ai.evaluation.engines import (RUNTIME_ARM, RUNTIME_ENGINE, RUNTIME_TRANSPORT,
                                        runtime_identity)
from apps.ai.evaluation.replay import RuntimeAttempts, collect_run
from apps.ai.evaluation.runtime_replay import (DEFAULT_DEADLINE_SECONDS, RuntimeSeam,
                                               collect_case_runtime)
from apps.ai.evaluation.runfile import eval_token, file_digest, load_json, write_run


def runtime_seam(url: str, token: str) -> RuntimeSeam:
    """The reader's own edge at ``url``; the token goes only into the Authorization header."""
    client = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"},
                          timeout=DEFAULT_DEADLINE_SECONDS)
    return RuntimeSeam(client)


class Command(BaseCommand):
    help = "Collect selected development conversations through authenticated Ask IRIS."

    def add_arguments(self, parser):
        parser.add_argument("--set", required=True)
        parser.add_argument("--lock", required=True)
        parser.add_argument("--case", action="append", required=True,
                            help="Development case ID; repeat to collect several.")
        parser.add_argument("--arm", choices=(RUNTIME_ARM,), default=RUNTIME_ARM,
                            help="Evaluation arm label; the runtime is the only engine.")
        parser.add_argument("--runtime-url", required=True,
                            help="Collect through the dedicated runtime's authenticated reader "
                                 "edge at this origin (IR-740).")
        parser.add_argument("--runtime-model", default="scripted",
                            help="The model the runtime deployment is configured to use; "
                                 "recorded as declared by the operator.")
        parser.add_argument("--depth", choices=("ordinary", "deep"), default="deep")
        parser.add_argument("--run-deadline-seconds", type=float,
                            default=DEFAULT_DEADLINE_SECONDS)
        parser.add_argument("--providers", choices=("fake", "real"), default="fake")
        parser.add_argument("--smoke", action="store_true",
                            help="Require exactly one development case and fake providers.")
        parser.add_argument("--approval-id", help="Recorded paid campaign approval ID.")
        parser.add_argument("--held-out", action="store_true",
                            help="Open held-out cases; needs a frozen lock (IR-609).")
        parser.add_argument("--approvals", help="Recorded approvals; required for paid "
                            "held-out collection.")
        parser.add_argument("--data-policy", default="deterministic-fake-local")
        parser.add_argument("--case-attempts", type=int, default=10)
        parser.add_argument("--case-cost-usd", type=float)
        parser.add_argument("--cache", choices=("unknown", "cold", "warm"), default="unknown")
        parser.add_argument("--out", default="../docs/evaluation/runs")

    def handle(self, *args, **options):
        data = load_json(options["set"])
        report = validate_set(data, min_conversations=0)
        if report["errors"]:
            raise CommandError("invalid set: " + "; ".join(report["errors"]))
        lock = load_json(options["lock"])
        mismatches = check_lock(data, lock)
        if mismatches:
            raise CommandError("set lock mismatch: " + ", ".join(mismatches))
        split = "held_out" if options["held_out"] else "development"
        if options["held_out"]:
            try:
                require_frozen_for_held_out(data, lock)
                if options["providers"] == "real":
                    require_paid_held_out(load_json(options["approvals"])
                                          if options["approvals"] else None)
            except CampaignRefused as exc:
                raise CommandError(str(exc)) from None
        selected = []
        by_id = {case["id"]: case for case in data["conversations"]}
        for case_id in options["case"]:
            case = by_id.get(case_id)
            if case is None or case["split"] != split:
                raise CommandError(f"{case_id}: select a {split.replace('_', '-')} case")
            if case_id in [item["id"] for item in selected]:
                raise CommandError(f"{case_id}: duplicate case")
            selected.append(case)
        if options["case_attempts"] < 1 or (options["case_cost_usd"] is not None and
                                              options["case_cost_usd"] <= 0):
            raise CommandError("case caps must be positive")
        if options["smoke"] and (len(selected) != 1 or options["providers"] != "fake"
                                 or options["held_out"]):
            raise CommandError("--smoke requires one development case and fake providers")
        return self._runtime(options, data, selected, split)

    def _runtime(self, options, data, selected, split):
        """Collect through the dedicated runtime's reader edge; see the module docstring."""
        if options["run_deadline_seconds"] <= 0:
            raise CommandError("--run-deadline-seconds must be positive")
        caps = {"case_attempts": options["case_attempts"]}
        attempts, pricing = None, {}
        if options["providers"] == "real":
            if not options["approval_id"] or options["data_policy"] == "deterministic-fake-local":
                raise CommandError("real providers need an approval ID and approved data policy")
            if options["case_cost_usd"] is None or mode() != ENFORCE:
                raise CommandError("real providers need a case cost cap and enforced admission")
            if options["runtime_model"] == "scripted":
                raise CommandError("real providers need the deployment's --runtime-model")
            try:
                admission = read_limits()
            except Exception as exc:
                raise CommandError(f"admission limits unavailable: {exc}") from None
            attempts = RuntimeAttempts(admission.campaign_key)
            if attempts.snapshot() != 0:
                raise CommandError("the evaluation campaign already has attempts; "
                                   "use a fresh dedicated key")
            caps.update({
                "case_cost_usd": options["case_cost_usd"],
                "turn_max_attempts": admission.run.attempts,
                "turn_max_input_tokens": admission.run.input_tokens,
                "turn_max_output_tokens": admission.run.output_tokens,
                "turn_max_cost_usd": admission.run.cost_micros / 1_000_000,
                "campaign_attempts": admission.spendable.attempts,
                "campaign_input_tokens": admission.spendable.input_tokens,
                "campaign_output_tokens": admission.spendable.output_tokens,
                "campaign_cost_usd": admission.spendable.cost_micros / 1_000_000,
                "campaign_active_ms": admission.spendable.active_ms,
                "campaign_key": admission.campaign_key,
            })
            pricing = {model: {"input": price.input, "output": price.output}
                       for model, price in admission.prices.items()}
        elif options["case_cost_usd"] is not None:
            caps["case_cost_usd"] = options["case_cost_usd"]
        corpus = dict(data["corpus"])
        corpus["set_sha256"] = file_digest(options["set"])
        corpus["authorization_policy_version"] = "Record.visible_to+disclosure-gate"
        model = options["runtime_model"]
        profile = {"vendor": "operator_declared", "model": model, "fallbacks": [],
                   "reasoning_visible": False}
        run = collect_run(
            runtime_seam(options["runtime_url"], eval_token()), selected,
            set_id=data["set_id"], set_digests=split_digests(data), corpus=corpus,
            model_ids={"agent": model}, limits=caps, data_policy=options["data_policy"],
            cache=options["cache"], attempts=attempts, approval_id=options["approval_id"],
            model_profiles={"agent": profile}, partition_method=data.get("partition_method"),
            retrieval={"research": "runtime-local-tools", "declared_by": "operator"},
            pricing=pricing, arm=RUNTIME_ARM, engine_version=RUNTIME_ENGINE, split=split,
            protocol=RUNTIME_TRANSPORT, identity=runtime_identity(),
            runtime={"depth": options["depth"], "declared_by": "operator", "edge": "reader-edge"},
            case_collector=partial(collect_case_runtime, depth=options["depth"],
                                   deadline_seconds=options["run_deadline_seconds"]))
        run["manifest"]["set_sha256"] = corpus["set_sha256"]
        path = write_run(options["out"], f"IR-740-runtime-replay-{run['run_id']}", run)
        self.stdout.write(f"wrote {path} ({len(run['conversations'])} conversations)")
