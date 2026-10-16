"""Replay development cases through the authenticated Ask IRIS reader.

The API runs in this process, so the manifest describes the settings that
actually served it. Fake mode injects deterministic providers explicitly.
"""

from __future__ import annotations

from contextlib import nullcontext

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.admission.limits import ENFORCE, mode, read_limits
from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.controller import versions
from apps.ai.evaluation.conversations import check_lock, split_digests, validate_set
from apps.ai.evaluation.replay import CampaignAttempts, collect_run
from apps.ai.evaluation.runfile import eval_token, file_digest, load_json, write_run
from apps.ai.inference.profiles import profile_for
from apps.ai.inference.tasks import InferenceTask
from apps.ai.providers.fakes import (DeterministicEmbeddingProvider, ScriptedReranker,
                                     ScriptedToolCallingLLM)


class LocalReader:
    def __init__(self, client):
        self.client = client

    def post(self, path, payload):
        return self.client.post(path, payload, format="json")

    def get(self, path):
        return self.client.get(path)


class Command(BaseCommand):
    help = "Collect selected development conversations through authenticated Ask IRIS."

    def add_arguments(self, parser):
        parser.add_argument("--set", required=True)
        parser.add_argument("--lock", required=True)
        parser.add_argument("--case", action="append", required=True,
                            help="Development case ID; repeat to collect several.")
        parser.add_argument("--arm", choices=("current", "fixed_synthesis", "controller"),
                            help="Evaluation arm label; never changes the reader engine.")
        parser.add_argument("--providers", choices=("fake", "real"), default="fake")
        parser.add_argument("--smoke", action="store_true",
                            help="Require exactly one development case and fake providers.")
        parser.add_argument("--approval-id", help="Recorded paid campaign approval ID.")
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
        mismatches = check_lock(data, load_json(options["lock"]))
        if mismatches:
            raise CommandError("set lock mismatch: " + ", ".join(mismatches))
        selected = []
        by_id = {case["id"]: case for case in data["conversations"]}
        for case_id in options["case"]:
            case = by_id.get(case_id)
            if case is None or case["split"] != "development":
                raise CommandError(f"{case_id}: select a development case")
            if case_id in [item["id"] for item in selected]:
                raise CommandError(f"{case_id}: duplicate case")
            selected.append(case)
        if options["case_attempts"] < 1 or (options["case_cost_usd"] is not None and
                                              options["case_cost_usd"] <= 0):
            raise CommandError("case caps must be positive")
        if options["smoke"] and (len(selected) != 1 or options["providers"] != "fake"):
            raise CommandError("--smoke requires one case and fake providers")
        engine = versions.NEW_RUN_ENGINE
        arm = options["arm"] or ("controller" if engine == versions.CONTROLLER_ENGINE
                                 else "current")
        if ((arm == "controller" and engine != versions.CONTROLLER_ENGINE) or
            (arm in ("current", "fixed_synthesis") and engine != versions.LEGACY_ENGINE)):
            raise CommandError(f"arm {arm} does not match this code's {engine} engine")

        attempt_reader = None
        pricing = {}
        caps = {"case_attempts": options["case_attempts"]}
        if options["providers"] == "real":
            if settings.AI_DURABLE_ASK:
                raise CommandError("real replay requires synchronous Ask IRIS for attributable costs")
            if getattr(settings, "AI_EVIDENCE_DECISION", "off") != "off":
                raise CommandError("real replay requires the asynchronous evidence shadow to be off")
            if not options["approval_id"] or options["data_policy"] == "deterministic-fake-local":
                raise CommandError("real providers need an approval ID and approved data policy")
            if options["case_cost_usd"] is None or mode() != ENFORCE:
                raise CommandError("real providers need a case cost cap and enforced admission")
            try:
                admission = read_limits()
            except Exception as exc:
                raise CommandError(f"admission limits unavailable: {exc}") from None
            attempt_reader = CampaignAttempts(admission.campaign_key)
            if attempt_reader.snapshot() != 0:
                raise CommandError("the evaluation campaign already has attempts; use a fresh dedicated key")
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
        corpus["authorization_policy_version"] = (
            "Record.visible_to+development-disclosure-bypass"
            if getattr(settings, "AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT", False)
            else "Record.visible_to+disclosure-gate")
        if attempt_reader:
            profiles = {task.value: profile_for(task) for task in
                        (InferenceTask.PLAN, InferenceTask.ANSWER)}
            models = {task: profile.model for task, profile in profiles.items()}
            safe_profiles = {task: {"vendor": profile.vendor.value,
                                    "model": profile.model,
                                    "fallbacks": list(profile.fallback_models),
                                    "reasoning_visible": profile.reasoning_visible}
                             for task, profile in profiles.items()}
        else:
            models = {"plan": "scripted", "answer": "scripted"}
            safe_profiles = {task: {"vendor": "deterministic_fake", "model": "scripted",
                                    "fallbacks": [], "reasoning_visible": False}
                             for task in models}
        retrieval = {
            "research_lane": (getattr(settings, "AI_RESEARCH_LANE", "off")
                              if attempt_reader else "off"),
            "keyword": bool(getattr(settings, "AI_KEYWORD_RETRIEVAL_ENABLED", False)),
            "fusion": bool(getattr(settings, "AI_RETRIEVAL_FUSION_ENABLED", False)),
            "screen_cache": bool(getattr(settings, "AI_SCREEN_CACHE", False)),
            "evidence_shadow": "off",
            "durable_ask": False,
            "embedding_model": (getattr(settings, "VOYAGE_EMBED_MODEL", "")
                                if attempt_reader else "deterministic_fake"),
            "rerank_model": (getattr(settings, "VOYAGE_RERANK_MODEL", "")
                             if attempt_reader else "deterministic_fake"),
        }
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {eval_token()}",
                           HTTP_X_IRIS_PROTOCOL="public-1")
        if options["providers"] == "fake":
            fake = ScriptedToolCallingLLM(
                script=lambda request: ScriptedToolCallingLLM.answering(
                    '{"next":"compose","basis":"general"}'),
                reply="Deterministic evaluation answer.")
            root = CompositionRoot(embedder=DeterministicEmbeddingProvider(),
                                   reranker=ScriptedReranker(), llm=fake, engine=engine)
            context = use_composition_root(root)
            settings_context = override_settings(AI_DURABLE_ASK=False,
                                                 AI_EVIDENCE_DECISION="off",
                                                 AI_RESEARCH_LANE="off")
        else:
            context = nullcontext()
            settings_context = nullcontext()
        with context, settings_context:
            run = collect_run(LocalReader(client), selected, set_id=data["set_id"],
                              set_digests=split_digests(data), corpus=corpus,
                              model_ids=models, limits=caps,
                              data_policy=options["data_policy"], cache=options["cache"],
                              attempts=attempt_reader, approval_id=options["approval_id"],
                              model_profiles=safe_profiles,
                              partition_method=data.get("partition_method"),
                              retrieval=retrieval, pricing=pricing,
                              arm=arm, engine_version=engine)
        run["manifest"]["set_sha256"] = corpus["set_sha256"]
        path = write_run(options["out"], f"IR-606-replay-{run['run_id']}", run)
        self.stdout.write(f"wrote {path} ({len(run['conversations'])} conversations)")
