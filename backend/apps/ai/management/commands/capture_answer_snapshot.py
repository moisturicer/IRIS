"""Freeze permitted retrieval once, without an answer-model call (IR-489)."""

from datetime import datetime, timezone
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.answers.citations import build_prompt
from apps.ai.composition import composition_root
from apps.ai.evaluation.answer_models import digest
from apps.ai.management.commands.eval_answers import write_report
from apps.ai.management.commands.eval_retrieval import _git_commit


class Command(BaseCommand):
    help = "Freeze gated answer prompts for labelled questions (retrieval spends credits)."

    def add_arguments(self, parser):
        parser.add_argument("--questions", required=True)
        parser.add_argument("--user", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--max-sources", type=int, default=8)
        parser.add_argument("--live", action="store_true", help="Allow retrieval calls that spend credits")

    def handle(self, *args, **options):
        try:
            output = Path(options["out"])
            if output.exists() or options["max_sources"] <= 0:
                raise ValueError("choose a new output and a positive source cap")
            labels = json.loads(Path(options["questions"]).read_text(encoding="utf-8"))
            questions = labels["questions"]
            if not questions or any(not q.get("reference") for q in questions):
                raise ValueError("every question needs a human-authored reference answer or expected refusal")
            if not options["live"]:
                self.stdout.write(f"Validated {len(questions)} references. Retrieval requires --live and may spend embedding/reranking credits.")
                return
            user = get_user_model().objects.get(email=options["user"])
            root = composition_root()
            retriever = root.retriever()
            selection = root.source_selection(max_sources=options["max_sources"])
            cases = []
            for question in questions:
                result = retriever.retrieve(
                    question["question"], user=user, limit=options["max_sources"])
                sources = selection.apply(result.passages)
                cases.append({"id": question["id"], "question": question["question"],
                    "reference": question["reference"], "prompt": build_prompt(question["question"], sources),
                    "source_count": len(sources), "retrieval_degraded": result.degraded,
                    "history_padding": question.get("history_padding", "")})
            write_report(output, {"version": 1, "tier": labels["tier"],
                "created_at": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(),
                "questions_digest": digest(labels), "max_sources": options["max_sources"],
                "cases": cases})
            self.stdout.write(f"Saved {len(cases)} frozen prompts to {output}")
        except (OSError, ValueError, KeyError, TypeError, get_user_model().DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
