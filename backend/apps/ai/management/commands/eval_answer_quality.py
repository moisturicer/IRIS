"""Answer quality of Django `lanes-v1` and the runtime agent on one frozen set (IR-956).

    python manage.py eval_answer_quality --set S.json --validate
    python manage.py eval_answer_quality --set S.json --write-lock L.json --grader-model M
    python manage.py eval_answer_quality --set S.json --lock L.json --grader-model M \\
        --run --runtime-url URL --runtime-model M2
    python manage.py eval_answer_quality --set S.json --lock L.json --grader-model M \\
        --rescore RUN.json [--reuse-django RUN.json --run ...]

``--run`` sends every case to both engines on paid model calls, one case at a
time, through provider admission: a case whose worst case would not fit in what
is left of the campaign is not started, and it and every later case are
reported as not run and scored as failures. It then grades every answer with
the pinned grader and writes a run file and a Markdown report. ``--rescore``
grades whatever a run file left ungraded and rewrites the report;
``--reuse-django`` collects only the agent and keeps the earlier Django answers,
for rerunning the agent arm after a runtime change.

Reader A's JWT is ``IRIS_EVAL_TOKEN`` and reader B's ``IRIS_EVAL_TOKEN_B``; they
go only into Authorization headers.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rest_framework.test import APIClient

from apps.ai.evaluation import answer_quality as aq
from apps.ai.evaluation.engines import RUNTIME_ENGINE, normalize_model
from apps.ai.evaluation.replay import CampaignAttempts, RuntimeAttempts, collect_case
from apps.ai.evaluation.runfile import file_digest, load_json, write_json
from apps.ai.evaluation.runtime_replay import (DEFAULT_DEADLINE_SECONDS, RuntimeSeam,
                                               collect_case_runtime)
from apps.ai.controller.versions import LEGACY_ENGINE, NEW_RUN_ENGINE

TOKEN_ENV = {"a": "IRIS_EVAL_TOKEN", "b": "IRIS_EVAL_TOKEN_B"}
DEFAULT_OUT = "../docs/evaluation/runs"


def _token(reader: str) -> str:
    token = os.environ.get(TOKEN_ENV[reader], "").strip()
    if not token:
        raise CommandError(f"{TOKEN_ENV[reader]} must hold reader {reader.upper()}'s JWT")
    return token


def _user(token: str):
    from rest_framework_simplejwt.authentication import JWTAuthentication

    auth = JWTAuthentication()
    try:
        return auth.get_user(auth.get_validated_token(token))
    except Exception as exc:
        raise CommandError(f"an evaluation token is not valid here: {exc}") from None


def measure_access(data, users) -> tuple[aq.Access, list[str]]:
    """Every corpus title's Record and what each reader can read, measured now."""
    from apps.records.models import Record

    corpus = data["corpus"]
    private = (corpus.get("private") or {}).get("title")
    titles = [*corpus["titles"], *([private] if private else [])]
    problems, ids = [], {}
    for title in titles:
        found = list(Record.objects.filter(title=title).values_list("pk", flat=True))
        if len(found) != 1:
            problems.append(f"{title!r}: {len(found)} Records carry this title, need exactly 1")
        else:
            ids[title] = found[0]
    visible = {reader: set(Record.objects.visible_to(user).filter(pk__in=ids.values())
                           .values_list("pk", flat=True)) for reader, user in users.items()}
    access = aq.Access(title_to_id=ids, visible=visible)
    for reader in aq.READERS:
        unreadable = [t for t in corpus["titles"] if ids.get(t) not in visible[reader]]
        if unreadable:
            problems.append(f"reader {reader} cannot read {len(unreadable)} corpus papers, "
                            f"e.g. {unreadable[0]!r}")
    listed = Record.objects.publicly_visible().count()
    if listed != len(corpus["titles"]):
        problems.append(f"the catalogue lists {listed} published Records, the count labels "
                        f"assume exactly the {len(corpus['titles'])} corpus papers")
    if private and private in ids:
        owner = corpus["private"]["readable_by"]
        for reader in aq.READERS:
            if (ids[private] in visible[reader]) != (reader == owner):
                problems.append(f"the private paper must be readable by reader {owner} only")
    return access, problems


class _Reader:
    def __init__(self, token):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}",
                                HTTP_X_IRIS_PROTOCOL="public-1")

    def post(self, path, payload):
        return self.client.post(path, payload, format="json")

    def get(self, path):
        return self.client.get(path)


class DjangoAttempts(CampaignAttempts):
    """Django's own attempts in the shared campaign: the runtime's are its own (owner ai)."""

    def _query(self):
        return super()._query().exclude(owner="ai")


class AdmittedGrader(aq.ModelGrader):
    """The grader, each call its own admitted run charged to ``lane``."""

    def __init__(self, llm, *, model, lane, run_key):
        super().__init__(llm, model=model)
        self.lane, self.run_key, self.calls = lane, run_key, 0

    def grade(self, payload):
        from apps.ai.admission import scope
        from apps.ai.providers.openai_compatible import LLMUnavailable

        self.calls += 1
        with scope.workload(self.lane), scope.run(scope.new_run(
                f"{self.run_key}:{self.calls}")):
            try:
                return super().grade(payload)
            except LLMUnavailable as exc:
                raise aq.GraderError(f"the grader was unavailable: {exc}") from None


def _scope(data, case, access):
    case = dict(case)
    if case.get("scope"):
        case["scope_record_id"] = access.title_to_id[case["scope"]]
    case.setdefault("split", "development")
    return case


class Command(BaseCommand):
    help = "Measure Ask IRIS answer quality on both engines with one frozen set (IR-956)."

    def add_arguments(self, parser):
        parser.add_argument("--set", required=True)
        parser.add_argument("--lock")
        parser.add_argument("--grader-model")
        parser.add_argument("--validate", action="store_true")
        parser.add_argument("--write-lock", metavar="PATH")
        parser.add_argument("--run", action="store_true")
        parser.add_argument("--rescore", metavar="RUN")
        parser.add_argument("--reuse-django", metavar="RUN",
                            help="Keep this run file's Django answers; collect only the agent.")
        parser.add_argument("--runtime-url")
        parser.add_argument("--runtime-model",
                            help="The model the runtime deployment answers with.")
        parser.add_argument("--depth", choices=("ordinary", "deep"), default="deep")
        parser.add_argument("--data-policy", default="proxy-corpus-vendor-no-training")
        parser.add_argument("--grader-lane", default="chat")
        parser.add_argument("--grader-max-tokens", type=int, default=2000)
        parser.add_argument("--run-deadline-seconds", type=float,
                            default=DEFAULT_DEADLINE_SECONDS)
        parser.add_argument("--min-per-family", type=int, default=aq.MIN_PER_FAMILY)
        parser.add_argument("--out", default=DEFAULT_OUT)

    def handle(self, *args, **options):
        data = load_json(options["set"])
        errors = aq.validate_set(data, min_per_family=options["min_per_family"])
        if errors:
            raise CommandError("invalid set:\n  " + "\n  ".join(errors))
        if options["validate"]:
            self._describe(data)
        if options["write_lock"]:
            self._write_lock(data, options)
        if options["run"] or options["rescore"]:
            if not options["lock"] or not options["grader_model"]:
                raise CommandError("scoring needs --lock and --grader-model")
            problems = aq.check_lock(data, load_json(options["lock"]),
                                     grader_model=options["grader_model"])
            if problems:
                raise CommandError("the set is not frozen as given: " + "; ".join(problems))
            if options["run"] and options["rescore"]:
                raise CommandError("--run and --rescore are separate steps")
            if options["run"]:
                self._run(data, options)
            else:
                self._rescore(data, options)

    def _describe(self, data):
        cases = data["cases"]
        self.stdout.write(f"{data['set_id']} v{data['version']}: {len(cases)} questions, valid")
        for family, name in aq.FAMILIES.items():
            n = sum(c["family"] == family for c in cases)
            self.stdout.write(f"  {family} {name}: {n}")

    def _write_lock(self, data, options):
        if not options["grader_model"]:
            raise CommandError("--write-lock needs the --grader-model it freezes")
        lock = aq.make_lock(data, grader_model=options["grader_model"])
        path = Path(options["write_lock"])
        if path.exists():
            existing = load_json(path)
            if existing != lock:
                raise CommandError(f"{path} already freezes a different set, rubric or grader; "
                                   "a changed set is a new version with a new lock file")
        write_json(path, lock)
        self.stdout.write(f"froze {data['set_id']} v{data['version']} -> {path}")

    # -- the paid run ---------------------------------------------------------

    def _preconditions(self, options):
        from apps.ai.admission.limits import ENFORCE, mode, read_limits
        from apps.ai.inference.profiles import profile_for
        from apps.ai.inference.tasks import InferenceTask

        if not options["runtime_url"] or not options["runtime_model"]:
            raise CommandError("--run needs --runtime-url and --runtime-model")
        if NEW_RUN_ENGINE != LEGACY_ENGINE:
            raise CommandError(f"the Django arm must be {LEGACY_ENGINE}, this code runs "
                               f"{NEW_RUN_ENGINE}")
        if settings.AI_DURABLE_ASK:
            raise CommandError("the Django arm needs synchronous Ask IRIS (AI_DURABLE_ASK off) "
                               "for attributable costs")
        if getattr(settings, "AI_EVIDENCE_DECISION", "off") != "off":
            raise CommandError("the evidence shadow must be off during a counted run")
        if mode() != ENFORCE:
            raise CommandError("paid runs need AI_PROVIDER_ADMISSION=enforce")
        try:
            limits = read_limits()
        except Exception as exc:
            raise CommandError(f"admission limits unavailable: {exc}") from None
        answer_model = profile_for(InferenceTask.ANSWER).model
        if normalize_model(answer_model) != normalize_model(options["runtime_model"]):
            raise CommandError(f"both engines must answer with one model: Django uses "
                               f"{answer_model!r}, the runtime {options['runtime_model']!r}")
        return limits, answer_model

    def _remaining(self, limits):
        from apps.ai.admission.ledger import ALIAS
        from apps.ai.models import ProviderCampaign

        def remaining():
            campaign = ProviderCampaign.objects.using(ALIAS).filter(
                key=limits.campaign_key).first()
            spent = campaign.charged_cost_micros if campaign else 0
            return limits.spendable.cost_micros - spent
        return remaining

    def _grader(self, options, run_id):
        from apps.ai.admission.llm import AdmittedLLMProvider
        from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

        adapter = OpenAICompatibleAdapter(
            model=options["grader_model"], temperature=0.0, reasoning_effort="",
            max_tokens=options["grader_max_tokens"], bounded_attempts=True)
        return AdmittedGrader(AdmittedLLMProvider(adapter, lane=options["grader_lane"]),
                              model=options["grader_model"], lane=options["grader_lane"],
                              run_key=f"eval-grade:{run_id}")

    def _run(self, data, options):
        import uuid

        limits, answer_model = self._preconditions(options)
        users = {reader: _user(_token(reader)) for reader in aq.READERS}
        access, problems = measure_access(data, users)
        if problems:
            raise CommandError("access state is not what the set needs:\n  "
                               + "\n  ".join(problems))
        previous = load_json(options["reuse_django"]) if options["reuse_django"] else None
        if previous is not None:
            if previous.get("set_sha256") != aq.set_digest(data):
                raise CommandError("--reuse-django comes from a different set")
            if previous["access"] != access.as_dict():
                raise CommandError("access state changed since the reused Django run")
            if normalize_model(previous["models"]["answer"]) != normalize_model(answer_model):
                raise CommandError("the reused Django run answered with another model")
        django_attempts = DjangoAttempts(limits.campaign_key)
        runtime_attempts = RuntimeAttempts(limits.campaign_key)
        if previous is None and django_attempts.snapshot() != 0:
            raise CommandError("the campaign already has attempts; use a fresh dedicated "
                               "campaign key so every charge is this run's")
        caps = {"case_attempts": 10 ** 6}
        readers = {r: _Reader(_token(r)) for r in aq.READERS}
        seams = {r: RuntimeSeam(httpx.Client(
            base_url=options["runtime_url"], headers={"Authorization": f"Bearer {_token(r)}"},
            timeout=options["run_deadline_seconds"])) for r in aq.READERS}

        def django(case):
            return collect_case(readers[case["reader"]], _scope(data, case, access),
                                attempts=django_attempts, limits=caps)

        def agent(case):
            seam = seams[case["reader"]]
            if case.get("scope"):
                seam = seam.scoped(access.title_to_id[case["scope"]])
            return collect_case_runtime(seam, _scope(data, case, access),
                                        attempts=runtime_attempts, limits=caps,
                                        depth=options["depth"],
                                        deadline_seconds=options["run_deadline_seconds"])

        collectors = {"agent": agent} if previous else {"django": django, "agent": agent}
        budget = aq.Budget(run_ceiling_micros=limits.run.cost_micros,
                           remaining=self._remaining(limits), arms=len(collectors))
        started = time.monotonic()
        collected = aq.collect_both(data["cases"], collectors, fits=budget.fits)
        rows = collected["rows"]
        not_run = collected["not_run"]
        if previous:
            rows["django"] = previous["rows"]["django"]
            not_run = sorted(set(not_run) | set(previous.get("not_run") or []))
        after, _ = measure_access(data, users)
        run_id = str(uuid.uuid4())
        record = {
            "schema": "answer-quality-run-1", "run_id": run_id, "ticket": "IR-956",
            "set_id": data["set_id"], "version": data["version"],
            "set_sha256": aq.set_digest(data), "set_file_sha256": file_digest(options["set"]),
            "lock": load_json(options["lock"]), "grader_model": options["grader_model"],
            "rubric_version": aq.RUBRIC_VERSION,
            "engines": {"django": LEGACY_ENGINE, "agent": RUNTIME_ENGINE},
            "models": {"answer": answer_model, "runtime": options["runtime_model"]},
            "runtime": {"url_declared": True, "depth": options["depth"]},
            "data_policy": options["data_policy"], "campaign_key": limits.campaign_key,
            "access": access.as_dict(),
            "conditions": ([] if after.as_dict() == access.as_dict()
                           else ["access state changed during the run"]),
            "reused_django_from": (previous or {}).get("run_id"),
            "collection_seconds": round(time.monotonic() - started),
            "rows": rows, "not_run": not_run,
            "grades": {"django": (previous or {}).get("grades", {}).get("django", {})},
        }
        path = Path(options["out"]) / f"{time.strftime('%Y%m%d-%H%M%S')}-IR-956-answer-quality-{run_id[:8]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, record)
        self.stdout.write(f"collected -> {path} ({len(not_run)} not run)")
        self._score(data, record, path, options, budget.fits_grade)

    def _rescore(self, data, options):
        from apps.ai.admission.limits import read_limits

        path = Path(options["rescore"])
        record = load_json(path)
        if record.get("set_sha256") != aq.set_digest(data):
            raise CommandError("the run file was collected from a different set")
        if record.get("grader_model") != options["grader_model"]:
            raise CommandError("rescore with the run's own pinned grader")
        limits = read_limits()
        budget = aq.Budget(run_ceiling_micros=limits.run.cost_micros,
                           remaining=self._remaining(limits))
        self._score(data, record, path, options, budget.fits_grade)

    def _score(self, data, record, path, options, fits_grade):
        access = aq.Access.from_dict(record["access"])
        grades, problems = aq.grade_all(data["cases"], record["rows"], access,
                                        self._grader(options, record["run_id"]),
                                        fits=fits_grade, previous=record.get("grades"))
        report = aq.build_report(data, record["rows"], access, grades,
                                 not_run=record["not_run"], conditions=record["conditions"])
        record.update(grades=grades, grading_problems=problems, **report)
        write_json(path, record)
        markdown = path.with_suffix(".md")
        markdown.write_text(aq.render_markdown({**report, "set_id": data["set_id"],
                                                "version": data["version"],
                                                "grading_problems": problems}),
                            encoding="utf-8")
        self.stdout.write(f"{report['verdict']['result'].upper()} -> {markdown}")
        for problem in problems:
            self.stdout.write(f"  {problem}")
