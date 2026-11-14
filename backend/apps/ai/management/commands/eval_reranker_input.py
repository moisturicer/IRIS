"""What should the reranker read for uncaptioned Figures? (IR-1125)

Runs the four arms (today, A embedded, B described, C fallback) over a text
set and a figure set, every arm reranking the same recalled candidates, and
reports recall, paired wins and losses, exact p-values and the decision rule.

``--dry-run`` checks the labels, recalls once per question (query embeddings
only) and prints the rerank token estimate. A paid run first repeats that
estimate and refuses past ``--max-cost-usd``, and refuses unless a named
person has reviewed the figure labels.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.ai.composition import composition_root
from apps.ai.evaluation.labels import QuestionSetError, load_question_set
from apps.ai.evaluation.techniques import resolve
from apps.ai.evaluation.reranker_arms import (
    COST_CEILING_USD,
    FIGURE_SET,
    TEXT_SET,
    compare,
)
from apps.ai.evaluation.validation import check_question_set, render_checks
from apps.ai.management.commands.eval_retrieval import (
    DEFAULT_OUT,
    _git_commit,
    _question_set_digest,
)


class Command(BaseCommand):
    help = "IR-1125: compare what the reranker reads, paired over shared candidates."

    def add_arguments(self, parser):
        parser.add_argument("--text", required=True, help="The text question set (JSON).")
        parser.add_argument("--figures", required=True, help="The figure question set (JSON).")
        parser.add_argument("--figure-trial", default=None,
                            help="Trial chunk set the figure papers live in, e.g. labeled.")
        parser.add_argument("--user", required=True, help="Email to retrieve as.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Check labels and estimate rerank tokens; rerank nothing.")
        parser.add_argument("--cost-per-million", type=float, default=None,
                            help="Voyage rerank price in USD per million tokens.")
        parser.add_argument("--max-cost-usd", type=float, default=COST_CEILING_USD)
        parser.add_argument("--labels-reviewed-by", default="",
                            help="The person who reviewed the figure labels. Required to pay.")
        parser.add_argument("--out", default=str(DEFAULT_OUT))
        parser.add_argument("--no-write", action="store_true")

    def handle(self, *args, **options):
        try:
            sets = {
                TEXT_SET: load_question_set(options["text"]),
                FIGURE_SET: load_question_set(options["figures"]),
            }
        except QuestionSetError as exc:
            raise CommandError(str(exc))
        trial = options["figure_trial"]
        self._check_labels(sets, trial)

        user = get_user_model().objects.filter(email__iexact=options["user"]).first()
        if user is None:
            raise CommandError(f"no user with email {options['user']}")
        root = composition_root()
        roots = {TEXT_SET: root, FIGURE_SET: root.for_trial(trial) if trial else root}
        price = options["cost_per_million"]

        estimate = compare(roots, sets, user=user, reranker=None)
        cost = estimate.cost_usd(price)
        self.stdout.write(
            f"Estimate: {estimate.total_tokens} rerank tokens"
            + (f", ~${cost:.4f}" if cost is not None else " (unpriced)")
        )
        if options["dry_run"]:
            return self._finish(estimate, sets, options, user, price)

        if not options["labels_reviewed_by"].strip():
            raise CommandError(
                "--labels-reviewed-by is required: a named person reviews the figure labels "
                "before the paid run (IR-1125)."
            )
        if cost is None:
            raise CommandError("--cost-per-million is required for a paid run.")
        if cost > options["max_cost_usd"]:
            raise CommandError(
                f"estimated ${cost:.4f} exceeds --max-cost-usd {options['max_cost_usd']}"
            )
        result = compare(roots, sets, user=user, reranker=root.reranker(), recalls=estimate.recalls)
        result.provenance["estimated_tokens"] = estimate.total_tokens
        result.provenance["labels_reviewed_by"] = options["labels_reviewed_by"].strip()
        self._finish(result, sets, options, user, price)
        spent = result.cost_usd(price)
        if spent is not None and spent > options["max_cost_usd"]:
            self.stderr.write(f"Spent ${spent:.4f}, over the ${options['max_cost_usd']} ceiling.")

    def _check_labels(self, sets, trial):
        for name, question_set in sets.items():
            checks = check_question_set(question_set, trial if name == FIGURE_SET else None)
            self.stdout.write(f"{name}: {render_checks(checks)}")
            if any(not c.ok for c in checks):
                raise CommandError(f"some {name} labels do not resolve")

    def _finish(self, result, sets, options, user, price):
        result.provenance.update({
            "git_commit": _git_commit(),
            "retrieved_as": user.email,
            "figure_trial": options["figure_trial"],
            "techniques": resolve().as_dict(),
            "question_sets": {
                name: {"path": qs.source, "sha256": _question_set_digest(qs.source)}
                for name, qs in sets.items()
            },
        })
        self.stdout.write("")
        self.stdout.write(result.render(price))
        if options["no_write"]:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        kind = "dry" if result.dry_run else "paid"
        path = Path(options["out"]) / f"{stamp}-reranker-input-{kind}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.as_dict(price), indent=2, default=str), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Results written to {path}"))
