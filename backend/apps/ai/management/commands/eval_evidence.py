"""Measure the evidence detector against the annotated questions (IR-464).

    python manage.py eval_evidence --questions docs/evaluation/proxy_starter.json
    python manage.py eval_evidence --questions ... --min-examples 10 --no-write

The curated instrument of ADR-035 §10 — the one that supplies accuracy numbers.
It reads the questions carrying `evidence_required` / `expected_outcome` /
`institutional`, submits each to the detector on the raw text, on the Resolved
text, and on the two combined by OR, and reports over-fires and misses **per
reason code, per lane**.

**By default it costs nothing and touches nothing.** No model call, no vendor
call, no database read, and no `Conversation`, `Turn` or shadow row — so unlike
`eval_retrieval` it is safe to run on any checkout, and it needs no `--user`
because nothing here is filtered by visibility.

**`--model-decision` is the exception (IR-465).** It puts each question to the
`answer` model as one tool-offering call and reports the model's route beside
the detector's, in its own section: agreement, the union, and each fallback
reason code. It spends vendor credits, so it is manual and never CI, like
`eval_retrieval`. It still reads no record and creates no `Conversation`,
`Turn` or shadow row, and the model's hypothetical direct answers are measured
for length and discarded (ADR-035 §10).

**Nothing consumes a verdict.** Neither half is wired into the answer path:
production routing is out of scope for ADR-035 (§11).
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.ai.evaluation import QuestionSetError, load_question_set
from apps.ai.evaluation.evidence import MIN_EXAMPLES, run_curated
from apps.ai.evidence import (
    SETTING_MODE,
    active_rule_set,
    configured_mode,
    institution_terms,
)
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.jev_noul import (
    CORPUS_DESCRIPTION_VERSION,
    JevNoulDecision,
    jev_digest,
)
from apps.ai.evidence.model_decision import MAX_PRIOR_QUESTIONS, ModelEvidenceDecision
from apps.ai.evidence.route_label import (
    ROUTE_LABEL_MAX_TOKENS,
    RouteLabelDecision,
    route_label_digest,
)
from apps.ai.inference import InferenceTask, Vendor, profile_for
from apps.ai.providers.openrouter_decisions import (
    DECISIONS_URL,
    PINNED_MODEL,
    OpenRouterDecisionsAdapter,
)
from apps.ai.providers.tool_calling import ToolCallingLLM

DEFAULT_OUT = Path("docs") / "evaluation" / "runs"

#: Recorded in every Jev run file (IR-482, ADR-036 amendment).
JEV_VENDOR_TERMS = (
    "UNVERIFIED: OpenRouter's docs state no retention, training or rate-limit "
    "terms for the alpha Decisions API. Treat everything sent as retained."
)
JEV_APPROVAL = {
    "approver": "JIVE",
    "date": "2026-10-08",
    "scope": "live requests to the alpha Decisions API with the public proxy "
    "question set only; not reader questions, private documents, sensitive "
    "school data, or any run through shadow or the answer path",
}
JEV_STATE_FIELDS = (
    "corpus",
    "question",
    "rewritten_question_untrusted",
    "earlier_questions",
)


def _openrouter_decision_model():
    """The Decisions adapter, on the key of a task already at OpenRouter.

    No new setting: the first Inference task whose Profile is at OpenRouter and
    carries a key lends it. Another vendor's key is never sent here.
    """
    for task in InferenceTask:
        profile = profile_for(task)
        if profile.vendor is Vendor.OPENROUTER and profile.api_key:
            return OpenRouterDecisionsAdapter(profile.api_key)
    raise CommandError(
        "--decision-mode jev-noul needs an OpenRouter key, and no Inference "
        "task is at OpenRouter with one. Set e.g. LLM_SUMMARY_VENDOR=openrouter "
        "and LLM_SUMMARY_API_KEY (a Groq key is never sent to OpenRouter)."
    )


def _git_commit() -> str:
    """The commit this run's code came from. ``IRIS_GIT_COMMIT`` wins, since
    the container has no git; the same convention as `eval_retrieval`."""
    given = os.environ.get("IRIS_GIT_COMMIT", "").strip()
    if given:
        return given
    try:
        return (
            subprocess.run(
                ["git", "describe", "--always", "--dirty"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            or "unknown"
        )
    except Exception:
        return "unknown"


def _digest(path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unknown"


class Command(BaseCommand):
    help = (
        "Report the evidence detector's over-fires and misses per reason code "
        "against the annotated question set. Calls no model and no vendor "
        "unless --model-decision is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--questions",
            required=True,
            help="Path to the annotated question set (JSON).",
        )
        parser.add_argument(
            "--min-examples",
            type=int,
            default=MIN_EXAMPLES,
            help=f"Fewer labelled examples than this in a category and the "
            f"category is reported as inconclusive (default: {MIN_EXAMPLES}).",
        )
        parser.add_argument(
            "--drop-incomplete",
            action="store_true",
            help="Skip questions still holding a TODO instead of refusing the "
            "set.",
        )
        parser.add_argument(
            "--model-decision",
            action="store_true",
            help="Also ask the answer model for its route on each question and "
            "report it beside the detector's. Calls the vendor and spends "
            "credits (IR-465).",
        )
        parser.add_argument(
            "--decision-mode",
            choices=("tools", "route-label", "jev-noul"),
            default="tools",
            help="With --model-decision: 'tools' offers search_corpus (IR-465); "
            "'route-label' asks for {\"route\":\"search\"|\"answer\"} through "
            "plain generate, with no tool (IR-481); 'jev-noul' asks "
            "OpenRouter's Decisions API (typesafe/jev-1.13) for a probability "
            "and reports a threshold curve (IR-482). Public proxy set only.",
        )
        parser.add_argument(
            "--max-tokens",
            type=int,
            default=ROUTE_LABEL_MAX_TOKENS,
            help="Completion cap for --decision-mode route-label "
            f"(default: {ROUTE_LABEL_MAX_TOKENS}).",
        )
        parser.add_argument(
            "--out",
            default=str(DEFAULT_OUT),
            help=f"Directory for the results file (default: {DEFAULT_OUT}).",
        )
        parser.add_argument(
            "--no-write",
            action="store_true",
            help="Print the report without writing a results file.",
        )

    def handle(self, *args, **options):
        self._widen_stream_encoding()
        try:
            question_set = load_question_set(
                options["questions"], drop_incomplete=options["drop_incomplete"]
            )
        except QuestionSetError as exc:
            raise CommandError(str(exc))

        mode = options["decision_mode"]
        label_mode = mode == "route-label"
        jev_mode = mode == "jev-noul"
        if mode != "tools" and not options["model_decision"]:
            raise CommandError(f"--decision-mode {mode} needs --model-decision.")
        if options["max_tokens"] < 1:
            raise CommandError("--max-tokens must be positive.")
        if jev_mode and question_set.tier != "proxy":
            raise CommandError(
                "--decision-mode jev-noul is approved for the public proxy "
                f"question set only (IR-482); this set's tier is "
                f"{question_set.tier!r}. Retention terms are unverified."
            )
        decider = (
            self._decider(mode, options["max_tokens"])
            if options["model_decision"]
            else None
        )

        rule_set = active_rule_set()
        model_provenance = {}
        if decider and jev_mode:
            model_provenance = {
                "decision_mode": mode,
                "prompt_digest": jev_digest(PINNED_MODEL),
                "request": {
                    "endpoint": DECISIONS_URL,
                    "model_requested": PINNED_MODEL,
                    "question_type": "noul",
                    "state_fields": list(JEV_STATE_FIELDS),
                    "corpus_description_version": CORPUS_DESCRIPTION_VERSION,
                    "max_prior_questions": MAX_PRIOR_QUESTIONS,
                },
                "vendor_terms": JEV_VENDOR_TERMS,
                "approval": JEV_APPROVAL,
                "workers": 1,
            }
        elif decider:
            from apps.ai.evidence.model_decision import prompt_digest
            from apps.ai.evidence.shadow import generation_parameters

            model_provenance = {
                "decision_mode": options["decision_mode"],
                "prompt_digest": (
                    route_label_digest(options["max_tokens"])
                    if label_mode
                    else prompt_digest()
                ),
                "generation": {
                    **generation_parameters(),
                    **({"max_tokens": options["max_tokens"]} if label_mode else {}),
                },
                "workers": 1,
            }
        report = run_curated(
            EvidenceDetector(rule_set),
            question_set,
            min_examples=options["min_examples"],
            decider=decider,
            provenance={
                "git_commit": _git_commit(),
                "question_set_path": question_set.source,
                "question_set_sha256": _digest(question_set.source),
                "rule_set_digest": rule_set.digest,
                SETTING_MODE: configured_mode(),
                "institution_terms": len(institution_terms()),
                # Recorded as absent rather than omitted, so a results file
                # without a model run can still be compared with one that has.
                "model_decision": bool(decider),
                "model": (
                    PINNED_MODEL if jev_mode else "answer task" if decider else None
                ),
                **model_provenance,
            },
        )

        if not report.judgements:
            raise CommandError(
                "no question in this set carries an evidence_required "
                "annotation, so there is nothing to measure the detector "
                "against. docs/evaluation/README.md says how to label one."
            )

        self.stdout.write("")
        self.stdout.write(report.render())

        path = None
        if not options["no_write"]:
            path = self._write(report, question_set, Path(options["out"]))

        self._warn(report)
        if path is not None:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Results written to {path}"))

    def _decider(self, mode: str = "tools", max_tokens: int = 0):
        """The decision over the `answer` task, refused when nothing is
        configured rather than scored as a column of fallbacks.

        A run with no model would report every question as a fallback to
        evidence: a plausible-looking number measuring nothing.
        """
        if mode == "jev-noul":
            # Never builds the composition root: nothing here is the answer path.
            return JevNoulDecision(_openrouter_decision_model())
        label_mode = mode == "route-label"
        # Imported here so that a run without the flag never reaches it, and a
        # test that makes the root explode can prove that.
        from apps.ai.composition import composition_root

        root = composition_root()
        if not root.generation_configured():
            raise CommandError(
                "--model-decision needs the answer model, and none is "
                "configured (LLM_API_KEY, LLM_MODEL). Without one every "
                "question would fall back to evidence and the section would "
                "measure nothing."
            )
        if label_mode:
            return RouteLabelDecision(self._capped_llm(root, max_tokens))
        llm = root.llm_for(InferenceTask.ANSWER)
        if not isinstance(llm, ToolCallingLLM):
            raise CommandError(
                f"the answer provider ({type(llm).__name__}) cannot carry a "
                "tool-calling decision."
            )
        return ModelEvidenceDecision(llm)

    def _capped_llm(self, root, max_tokens: int):
        """The `answer` Profile's model with a completion cap, on its own
        breaker so a run never opens the reader's. An injected provider (a test
        fake) is used as it is."""
        injected = getattr(root, "_llm", None)
        if injected is not None:
            return injected
        from apps.ai.inference import build_profile_llm, profile_for

        return build_profile_llm(
            profile_for(InferenceTask.ANSWER),
            breaker_key="evidence_route_label_eval",
            max_tokens=max_tokens,
        )

    def _widen_stream_encoding(self):
        """A Windows console defaults to cp1252 and the report holds a §."""
        for stream in (self.stdout, self.stderr):
            reconfigure = getattr(getattr(stream, "_out", None), "reconfigure", None)
            if reconfigure is None:
                continue
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    def _warn(self, report):
        inconclusive = report.inconclusive_categories
        if inconclusive:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"{len(inconclusive)} category(ies) hold fewer than "
                    f"{report.min_examples} labelled examples and are "
                    f"inconclusive: {', '.join(inconclusive)}. Their accuracy "
                    f"figures are not a measurement."
                )
            )
        coverage = report.coverage
        if coverage["unannotated"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{coverage['unannotated']} of "
                    f"{coverage['questions_in_set']} questions carry no "
                    f"evidence annotation and were not judged."
                )
            )
        combined = report.lane("combined")
        if combined and combined.misses:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(combined.misses)} question(s) needing the corpus "
                    f"raised no reason code: {', '.join(combined.misses)}. The "
                    f"detector is defense in depth, not a classifier — the "
                    f"model decision is what covers these (--model-decision), "
                    f"and neither half is trusted alone (ADR-035 §5)."
                )
            )

    def _write(self, report, question_set, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(
            c if c.isalnum() or c in "-_" else "-" for c in question_set.name
        ).strip("-")
        path = out_dir / f"{stamp}-evidence-{safe or 'run'}.json"
        path.write_text(
            json.dumps(report.as_dict(), indent=2), encoding="utf-8"
        )
        return path
