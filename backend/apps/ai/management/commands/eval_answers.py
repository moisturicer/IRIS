"""Manual evaluation on frozen retrieval output; dry-run makes no calls."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.evaluation.answer_models import (
    HISTORY_ARMS, ModelSpec, comparison_markdown, estimate_run, experiment, validate_snapshot,
)
from apps.ai.providers.dialects import OpenRouterDialect
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter
from apps.ai.management.commands.eval_retrieval import _git_commit


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(path)


class Command(BaseCommand):
    help = "Evaluate answer models on frozen prompts; live calls require --live."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot", required=True)
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--live", action="store_true")

    def handle(self, *args, **options):
        try:
            snapshot = json.loads(Path(options["snapshot"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(options["manifest"]).read_text(encoding="utf-8"))
            validate_snapshot(snapshot)
            candidates = [ModelSpec.parse(c) for c in manifest["candidates"]]
            judges = [ModelSpec.parse(c) for c in manifest["judges"]]
            repeats = manifest.get("repeats", 2)
            arms = manifest.get("arms", [0, 25000, 50000, 100000, 150000])
            if repeats < 2:
                raise ValueError("at least two repeats required")
            if not candidates or not judges:
                raise ValueError("candidates and judges required")
            if not arms or any(a not in HISTORY_ARMS for a in arms):
                raise ValueError("unsupported history arm")
            for candidate in candidates:
                if not any(j.maker.lower() != candidate.maker.lower() for j in judges):
                    raise ValueError("each candidate requires an independent maker as judge")
            # Conservative planning bound, not an invoice prediction. All
            # token prices must be the maximum across context price tiers.
            requests = len(snapshot["cases"]) * len(candidates) * len(arms) * repeats
            plan = {"answer_requests": requests, "judge_requests": requests,
                    "maximum_history_tokens": max(arms),
                    "candidates": [asdict(c) for c in candidates],
                    "judges": [asdict(j) for j in judges]}
            plan.update(estimate_run(snapshot, candidates, judges, repeats, arms))
            if not options["live"]:
                self.stdout.write(json.dumps(plan, indent=2))
                return
            if any(s.hosting_region not in ("US", "EU") or not s.hosting_evidence for s in candidates + judges):
                raise ValueError("live runs require recorded US/EU hosting evidence for every model's provider pin")
            key = getattr(settings, "LLM_ANSWER_API_KEY", "") or getattr(settings, "LLM_API_KEY", "")
            if not key:
                raise ValueError("OpenRouter answer API key required")
            if Path(options["out"]).exists():
                raise ValueError("output exists; choose a new run file")
            run_cap = manifest["max_run_cost_usd"]
            if plan["estimated_total_usd"] > run_cap:
                raise ValueError("estimated spend exceeds manifest max_run_cost_usd")
            adapters = {}

            def complete(spec, system, user):
                if spec not in adapters:
                    adapters[spec] = OpenAICompatibleAdapter(
                        base_url="https://openrouter.ai/api/v1", api_key=key,
                        model=spec.build, temperature=0.1,
                        reasoning_effort=spec.reasoning_effort,
                        max_tokens=spec.max_tokens,
                        dialect=OpenRouterDialect(provider_only=spec.provider_only),
                    )
                return adapters[spec].complete_measured(system, user)

            metadata = {"git_commit": _git_commit(), "temperature": 0.1,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "manifest": manifest, "snapshot": snapshot}

            def checkpoint(report):
                write_report(Path(options["out"]), {**report, **metadata})

            report = experiment(snapshot, candidates, judges, complete,
                                repeats=repeats, arms=arms, checkpoint=checkpoint,
                                max_run_cost_usd=run_cap)
            checkpoint(report)
            Path(options["out"]).with_suffix(".md").write_text(comparison_markdown(report), encoding="utf-8")
            self.stdout.write(json.dumps(report["summary"], indent=2))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
