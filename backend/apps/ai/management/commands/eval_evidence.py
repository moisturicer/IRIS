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

**`--chain` (IR-486) scores the whole proposed decision chain** (IR-484):
structural rules, the detector, Jev with two cutoffs, an LLM route-label
confirmation of every direct candidate, and the Jev-failure path where the LLM
decides alone, beside the single-decider arms. It replays stored
`--model-decision` result files (`--from-run jev=PATH`, repeatable) or collects
fresh runs (`--live jev,label,tool`, which spends credits). Stored replay costs
nothing, reads no database and calls no vendor. It writes a `chain` result file,
never an `evidence` one, so `report_evidence_pilot` does not read it, and it
chooses no operating point: both cutoffs are required.

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
from apps.ai.evaluation import chain as chained
from apps.ai.evaluation.evidence import MIN_EXAMPLES, annotated, judge, run_curated
from apps.ai.evidence import (
    SETTING_MODE,
    active_rule_set,
    configured_mode,
    institution_terms,
)
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.jev_noul import (
    CORPUS_DESCRIPTION_VERSION,
    STATE_FIELDS,
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

#: A run with more fallbacks than this is reported alone, never pooled.
FALLBACK_POOLING_LIMIT = chained.FALLBACK_POOLING_LIMIT

#: `--live` names to the `--decision-mode` that builds each decider.
LIVE_MODES = {
    chained.DECIDER_JEV: "jev-noul",
    chained.DECIDER_LABEL: "route-label",
    chained.DECIDER_TOOL: "tools",
}

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


def _declared_tier(path) -> str:
    """The tier the file itself declares; a missing one is not assumed proxy."""
    try:
        return str(json.loads(Path(path).read_text(encoding="utf-8")).get("tier") or "")
    except (OSError, ValueError, AttributeError):
        return ""


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
            "--chain",
            action="store_true",
            help="Score the full decision chain offline (IR-486) instead of "
            "the detector report. Needs --search-cutoff and --direct-cutoff "
            "and at least one decider run.",
        )
        parser.add_argument(
            "--from-run",
            action="append",
            default=[],
            metavar="DECIDER=PATH",
            help="With --chain: a stored --model-decision result file for "
            "jev, label or tool. Repeat it: each file is one replicate.",
        )
        parser.add_argument(
            "--live",
            default="",
            help="With --chain: collect fresh runs for these deciders "
            "(comma list of jev, label, tool). Spends credits; jev is the "
            "public proxy set only.",
        )
        parser.add_argument(
            "--repeats",
            type=int,
            default=1,
            help="With --chain --live: replicates per live decider (default 1; "
            "the held-out comparison asks for at least 3).",
        )
        parser.add_argument(
            "--search-cutoff",
            type=float,
            help="With --chain: Jev probability from which a question searches.",
        )
        parser.add_argument(
            "--direct-cutoff",
            type=float,
            help="With --chain: below this a question is a direct candidate; "
            "between the two cutoffs is uncertain and searches. Equal "
            "cutoffs leave no uncertain band.",
        )
        parser.add_argument(
            "--ablate-resolved",
            action="store_true",
            help="With --chain --live: also collect each decider with the "
            "Resolved question withheld, to compare raw-only input.",
        )
        parser.add_argument(
            "--resolver-label",
            default="",
            help="With --chain: names the resolver that produced the set's "
            "Resolved questions, recorded so two sets resolved by different "
            "models compare by label.",
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

        if options["chain"]:
            return self._handle_chain(options, question_set)

        mode = options["decision_mode"]
        label_mode = mode == "route-label"
        jev_mode = mode == "jev-noul"
        if mode != "tools" and not options["model_decision"]:
            raise CommandError(f"--decision-mode {mode} needs --model-decision.")
        if options["max_tokens"] < 1:
            raise CommandError("--max-tokens must be positive.")
        if jev_mode and _declared_tier(question_set.source) != "proxy":
            raise CommandError(
                "--decision-mode jev-noul is approved for the public proxy "
                f"question set only (IR-482), and the set must declare "
                f'"tier": "proxy" itself; this one declares '
                f"{_declared_tier(question_set.source)!r}. Retention terms are "
                "unverified."
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
                    "state_fields": list(STATE_FIELDS),
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

    def _handle_chain(self, options, question_set):
        """Score the chain over stored and/or freshly collected decider runs."""
        if options["search_cutoff"] is None or options["direct_cutoff"] is None:
            raise CommandError(
                "--chain needs both --search-cutoff and --direct-cutoff: the "
                "tool draws the curve and chooses no operating point."
            )
        try:
            bands = chained.Bands(options["search_cutoff"], options["direct_cutoff"])
        except chained.ChainError as exc:
            raise CommandError(str(exc))
        live = [n.strip() for n in options["live"].split(",") if n.strip()]
        unknown = [n for n in live if n not in LIVE_MODES]
        if unknown:
            raise CommandError(
                f"--live names {unknown}; choose from {sorted(LIVE_MODES)}."
            )
        if options["repeats"] < 1:
            raise CommandError("--repeats must be positive.")
        if options["ablate_resolved"] and not live:
            raise CommandError(
                "--ablate-resolved needs --live: a stored run cannot be "
                "re-asked without the Resolved question."
            )
        if chained.DECIDER_JEV in live and _declared_tier(question_set.source) != "proxy":
            raise CommandError(
                "--live jev is approved for the public proxy question set only "
                '(IR-482), and the set must declare "tier": "proxy" itself.'
            )

        runs: dict[str, list] = {name: [] for name in chained.DECIDERS}
        sources = []
        for spec in options["from_run"]:
            name, _, path = spec.partition("=")
            if not path or name not in chained.DECIDERS:
                raise CommandError(
                    f"--from-run takes DECIDER=PATH with DECIDER one of "
                    f"{chained.DECIDERS}, not {spec!r}."
                )
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                runs[name].append(
                    chained.run_from_result_file(name, data, Path(path).name)
                )
            except (OSError, ValueError, chained.ChainError) as exc:
                raise CommandError(f"{path}: {exc}")
            sources.append({"decider": name, "path": path, "sha256": _digest(path)})

        questions = annotated(question_set)
        if not questions:
            raise CommandError(
                "no question in this set carries an evidence_required annotation."
            )
        rule_set = active_rule_set()
        detector = EvidenceDetector(rule_set)
        judgements = tuple(judge(detector, q) for q in questions)

        facts = [chained.facts_from_judgement(j) for j in judgements]
        try:
            chained.validate_runs(facts, runs)
        except chained.ChainError as exc:
            raise CommandError(str(exc))
        if "label" in live and options["max_tokens"] < 1:
            raise CommandError("--max-tokens must be positive.")

        raw_only: dict[str, list] = {name: [] for name in chained.DECIDERS}
        deciders_used = {}
        for name in live:
            decider = self._decider(LIVE_MODES[name], options["max_tokens"])
            deciders_used[name] = LIVE_MODES[name]
            for _ in range(options["repeats"]):
                runs[name].append(
                    chained.collect_run(
                        name,
                        decider,
                        questions,
                        source=f"live {name}",
                        prompt_digest=self._live_digest(name, options),
                    )
                )
                if options["ablate_resolved"]:
                    raw_only[name].append(
                        chained.collect_run(
                            name,
                            decider,
                            questions,
                            use_resolved=False,
                            source=f"live {name} raw-only",
                            prompt_digest=self._live_digest(name, options),
                        )
                    )

        runs = {name: tuple(rs) for name, rs in runs.items() if rs}
        if not runs:
            raise CommandError(
                "--chain needs decider runs: pass --from-run DECIDER=PATH or --live."
            )
        raw_facts = [chained.facts_from_judgement(j, lane="raw") for j in judgements]

        ablations = {"resolver_label": options["resolver_label"] or "not recorded"}
        try:
            raw_detector = chained.build_report(
                question_set={}, facts=raw_facts, runs=runs, bands=bands
            )
            ablations["detector_input"] = {
                "raw_only": [a.summary() for a in raw_detector.arms],
                "note": "the detector on the raw question alone; the main "
                "arms use raw and Resolved together",
            }
            raw_runs = {n: tuple(rs) for n, rs in raw_only.items() if rs}
            if raw_runs:
                merged = {**runs, **raw_runs}
                ablations["decider_input"] = {
                    "raw_only": [
                        chained.evaluate_arm(arm, facts, merged, bands).summary()
                        for arm in chained.available_arms(merged)
                        if any(d in raw_runs for d in arm.needs)
                    ],
                    "note": "live deciders asked without the Resolved question",
                }
            report = chained.build_report(
                question_set=question_set.as_dict(),
                facts=facts,
                runs=runs,
                bands=bands,
                ablations=ablations,
                provenance={
                    "git_commit": _git_commit(),
                    "question_set_path": question_set.source,
                    "question_set_sha256": _digest(question_set.source),
                    "rule_set_digest": rule_set.digest,
                    "stored_runs": sources,
                    "live_deciders": deciders_used,
                    "repeats": options["repeats"] if live else None,
                    "model_builds": {
                        name: sorted({m for r in rs for m in r.models})
                        for name, rs in runs.items()
                    },
                    "prompt_digests": {
                        name: sorted({r.prompt_digest for r in rs if r.prompt_digest})
                        for name, rs in runs.items()
                    },
                    "cost_usd": round(
                        sum(
                            d.cost_usd or 0.0
                            for rs in runs.values()
                            for r in rs
                            for d in r.decisions.values()
                        ),
                        6,
                    ),
                    "decisions_without_reported_cost": sum(
                        1
                        for rs in runs.values()
                        for r in rs
                        for d in r.decisions.values()
                        if d.cost_usd is None
                    ),
                    "jev_vendor_terms": (
                        JEV_VENDOR_TERMS if chained.DECIDER_JEV in runs else None
                    ),
                },
            )
        except chained.ChainError as exc:
            raise CommandError(str(exc))

        self.stdout.write("")
        self.stdout.write(report.render())
        path = None
        if not options["no_write"]:
            out_dir = Path(options["out"])
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(
                c if c.isalnum() or c in "-_" else "-" for c in question_set.name
            ).strip("-")
            stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
            path = out_dir / f"{stamp}-chain-{safe or 'run'}.json"
            path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
        for result in report.arms:
            if result.reported_alone:
                self.stdout.write(
                    self.style.WARNING(
                        f"{result.arm.name}: replicate(s) {list(result.reported_alone)} "
                        f"exceeded {FALLBACK_POOLING_LIMIT:.0%} fallbacks and are "
                        "reported alone, not pooled."
                    )
                )
        if report.skipped_arms:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped for want of a decider run: "
                    f"{', '.join(report.skipped_arms)}."
                )
            )
        if path is not None:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Results written to {path}"))


    @staticmethod
    def _live_digest(name: str, options) -> str:
        from apps.ai.evidence.model_decision import prompt_digest

        return {
            chained.DECIDER_JEV: lambda: jev_digest(PINNED_MODEL),
            chained.DECIDER_LABEL: lambda: route_label_digest(options["max_tokens"]),
            chained.DECIDER_TOOL: prompt_digest,
        }[name]()

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
        model = report.model
        if model and model.decisions and model.fallbacks / len(model.decisions) > FALLBACK_POOLING_LIMIT:
            self.stdout.write(
                self.style.WARNING(
                    f"{model.fallbacks} of {len(model.decisions)} calls fell back "
                    f"to evidence (over {FALLBACK_POOLING_LIMIT:.0%}). Report this "
                    "run on its own; do not pool it with the others."
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
