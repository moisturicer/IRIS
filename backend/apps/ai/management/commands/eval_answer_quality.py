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

``--reader-a`` and ``--reader-b`` name the two readers by email. Every request
carries a token minted for it, so a run outlives the token lifetime; tokens go
only into Authorization headers.
"""

from __future__ import annotations

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

DEFAULT_OUT = "../docs/evaluation/runs"


def _user(email, reader: str):
    from django.contrib.auth import get_user_model

    if not email:
        raise CommandError(f"--reader-{reader} must name reader {reader.upper()} by email")
    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        raise CommandError(f"no active account for reader {reader.upper()}")
    return user


def _service_secret():
    import os

    return os.environ.get("AI_GATEWAY_SERVICE_SECRET", "").strip()


def _bearer(user, *, start=None, clock=time.monotonic, idle_seconds=15 * 60):
    """Headers with an access token minted per request from a tracked session.

    The app refuses a token without a session (ADR-045 §4), and a session idle
    for thirty minutes ends, so one left unused for fifteen is replaced.
    """
    if start is None:
        from apps.accounts.sessions import start_session as start
    state = {"refresh": None, "used": None}

    def headers():
        if state["refresh"] is None or clock() - state["used"] > idle_seconds:
            state["refresh"] = start(user)
        state["used"] = clock()
        return {"Authorization": f"Bearer {state['refresh'].access_token}"}
    return headers


def _edge_headers(fetch, *, secret, record_id):
    """What the reader edge adds before the gateway: a fresh grant, never the reader's token."""
    def headers():
        grant = fetch(record_id)
        if not grant:
            raise CommandError("Django refused the runtime grant (is AI_RUNTIME_READER on?)")
        out = {"X-IRIS-Reader-Grant": grant, "X-IRIS-Protocol": "runs-reader-1",
               "X-IRIS-Service-Secret": secret}
        if record_id is not None:
            out["X-IRIS-Record"] = str(record_id)
        return out
    return headers


def _grant_fetcher(reader):
    """The edge's subrequest, made in-process as ``reader``."""
    def fetch(record_id):
        extra = {"HTTP_X_IRIS_RECORD": str(record_id)} if record_id is not None else {}
        response = reader._fresh().get("/api/v1/ai/runtime/edge-grant/", **extra)
        return response.headers.get("X-IRIS-Reader-Grant") if response.status_code == 204 else None
    return fetch


def _stray_attempts(since, rows) -> list[str]:
    """Campaign attempts made during collection that no case accounts for."""
    ours = {a["id"] for arm in rows.values() for row in arm.values()
            for turn in row.get("turns") or () for a in turn.get("physical_attempts") or ()}
    stray = sorted(a["id"] for a in since if a["id"] not in ours)
    if not stray:
        return []
    return [f"the campaign charged attempts no case made ({', '.join(map(str, stray))}); "
            "other work shared the campaign during the run"]


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


def _served_model_problems(rows, runtime_model) -> list[str]:
    """Whether the runtime's charged attempts prove it answered on this campaign and model."""
    answered = [t for row in rows.values() for t in row.get("turns") or ()
                if t.get("outcome") == "answered"]
    attempts = [a for t in answered for a in t.get("physical_attempts") or ()]
    if answered and not attempts:
        return ["the runtime charged no attempt to this campaign; its cost and the budget "
                "gate are unattributed (does the runtime share the campaign key?)"]
    served = {normalize_model(a["model"]) for a in attempts
              if a.get("operation") == "llm" and a.get("model")}
    other = sorted(served - {normalize_model(runtime_model)})
    return [f"the runtime also answered with {other}, not only {runtime_model!r}"] if other else []


def _allowed_host():
    hosts = [h for h in settings.ALLOWED_HOSTS if h and h[0] not in "*."]
    return hosts[0] if hosts else "localhost"


class _Reader:
    def __init__(self, user):
        self.client, self.headers = APIClient(HTTP_HOST=_allowed_host()), _bearer(user)

    def _fresh(self):
        self.client.credentials(HTTP_AUTHORIZATION=self.headers()["Authorization"],
                                HTTP_X_IRIS_PROTOCOL="public-1")
        return self.client

    def post(self, path, payload):
        return self._fresh().post(path, payload, format="json")

    def get(self, path):
        return self._fresh().get(path)


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


def _scope(case, access):
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
        parser.add_argument("--reader-a", metavar="EMAIL")
        parser.add_argument("--reader-b", metavar="EMAIL")
        parser.add_argument("--preflight", action="store_true",
                            help="with --run: check everything, send nothing")
        parser.add_argument("--runtime-url")
        parser.add_argument("--runtime-gateway", metavar="URL",
                            help="the gateway itself; the command plays the reader edge")
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
        if (options["write_lock"] or options["run"] or options["rescore"]) and (
                options["min_per_family"] < aq.MIN_PER_FAMILY):
            # A lowered minimum may validate a draft; it never freezes or scores one.
            short = aq.validate_set(data)
            if short:
                raise CommandError("only a full set is frozen or scored: " + "; ".join(short))
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

    @staticmethod
    def _admission():
        from apps.ai.admission.limits import ENFORCE, mode, read_limits

        if mode() != ENFORCE:
            raise CommandError("paid runs need AI_PROVIDER_ADMISSION=enforce")
        try:
            return read_limits()
        except Exception as exc:
            raise CommandError(f"admission limits unavailable: {exc}") from None

    def _preconditions(self, options):
        from apps.ai.inference.profiles import profile_for
        from apps.ai.inference.tasks import InferenceTask

        if not (options["runtime_url"] or options["runtime_gateway"]) or not options["runtime_model"]:
            raise CommandError("--run needs --runtime-url (or --runtime-gateway) and "
                               "--runtime-model")
        if options["runtime_gateway"] and not settings.AI_RUNTIME_READER:
            raise CommandError("--runtime-gateway needs AI_RUNTIME_READER on, as the edge does")
        if options["runtime_gateway"] and not _service_secret():
            raise CommandError("--runtime-gateway needs AI_GATEWAY_SERVICE_SECRET")
        if NEW_RUN_ENGINE != LEGACY_ENGINE:
            raise CommandError(f"the Django arm must be {LEGACY_ENGINE}, this code runs "
                               f"{NEW_RUN_ENGINE}")
        if settings.AI_DURABLE_ASK:
            raise CommandError("the Django arm needs synchronous Ask IRIS (AI_DURABLE_ASK off) "
                               "for attributable costs")
        if getattr(settings, "AI_EVIDENCE_DECISION", "off") != "off":
            raise CommandError("the evidence shadow must be off during a counted run")
        limits = self._admission()
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
        from apps.ai.admission.limits import output_cap
        from apps.ai.admission.llm import AdmittedLLMProvider
        from apps.ai.inference.profiles import DataPolicy, profile_for
        from apps.ai.inference.tasks import InferenceTask
        from apps.ai.providers.dialects import dialect_for
        from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter

        # The grader spends the answer task's vendor account, so admission charges one account.
        answer = profile_for(InferenceTask.ANSWER)
        cap = output_cap()
        adapter = OpenAICompatibleAdapter(
            base_url=answer.base_url, api_key=answer.api_key, model=options["grader_model"],
            temperature=0.0, reasoning_effort="",
            dialect=dialect_for(answer.vendor.value, (),
                                answer.data_policy is DataPolicy.ZERO_RETENTION),
            max_tokens=min(options["grader_max_tokens"], cap or options["grader_max_tokens"]),
            bounded_attempts=True)
        return AdmittedGrader(AdmittedLLMProvider(adapter, lane=options["grader_lane"]),
                              model=options["grader_model"], lane=options["grader_lane"],
                              run_key=f"eval-grade:{run_id}")

    def _run(self, data, options):
        import uuid

        limits, answer_model = self._preconditions(options)
        users = {r: _user(options[f"reader_{r}"], r) for r in aq.READERS}
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
        watermark = CampaignAttempts(limits.campaign_key).snapshot()
        caps = {"case_attempts": 10 ** 6}
        readers = {r: _Reader(users[r]) for r in aq.READERS}
        seam_for = self._seams(options, users, readers)
        if options["preflight"]:
            self._preflight(data, options, limits, answer_model, seam_for, access)
            return

        def django(case):
            return collect_case(readers[case["reader"]], _scope(case, access),
                                attempts=django_attempts, limits=caps)

        def agent(case):
            seam = seam_for(case["reader"], access.title_to_id.get(case.get("scope")))
            return collect_case_runtime(seam, _scope(case, access),
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
        conditions = [] if after.as_dict() == access.as_dict() else [
            "access state changed during the run"]
        conditions += _served_model_problems(rows.get("agent", {}), options["runtime_model"])
        if previous is None:
            conditions += _stray_attempts(
                CampaignAttempts(limits.campaign_key).since(watermark), rows)
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
            "conditions": conditions,
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

    def _preflight(self, data, options, limits, answer_model, seam_for, access):
        """Every check a paid run makes before sending, and nothing sent."""
        problems = [f"no admission price for {m}" for m in
                    (answer_model, options["runtime_model"], options["grader_model"])
                    if normalize_model(m) not in {normalize_model(k) for k in limits.prices}]
        if options["runtime_gateway"]:
            private = data["corpus"].get("private") or {}
            for reader in aq.READERS:
                expected = {None: True}
                if private.get("title") in access.title_to_id:
                    expected[access.title_to_id[private["title"]]] = (
                        reader == private["readable_by"])
                for record_id, granted in expected.items():
                    try:
                        seam_for(reader, record_id).headers()
                        got = True
                    except CommandError:
                        got = False
                    if got != granted:
                        problems.append(f"reader {reader} {'got' if got else 'was refused'} a "
                                        f"runtime grant for record {record_id}")
        try:
            probe = httpx.get(f"{options['runtime_gateway'] or options['runtime_url']}/health",
                              timeout=10)
            if probe.status_code >= 500:
                problems.append(f"the runtime answered {probe.status_code}")
        except httpx.HTTPError as exc:
            problems.append(f"the runtime is unreachable: {exc}")
        budget = aq.Budget(run_ceiling_micros=limits.run.cost_micros,
                           remaining=self._remaining(limits), arms=2)
        worst = sum(budget.worst_case_micros(c) for c in data["cases"]) / 1e6
        self.stdout.write(f"campaign {limits.campaign_key}: ${budget.remaining() / 1e6:.2f} left; "
                          f"all {len(data['cases'])} cases at their worst ${worst:.2f}")
        if problems:
            raise CommandError("preflight failed:\n  " + "\n  ".join(problems))
        self.stdout.write("preflight passed: nothing was sent")

    def _seams(self, options, users, readers):
        """A seam per (reader, scope): through the reader edge, or straight to the gateway."""
        client = httpx.Client(base_url=options["runtime_gateway"] or options["runtime_url"],
                              timeout=options["run_deadline_seconds"])
        if options["runtime_gateway"]:
            secret = _service_secret()
            return lambda r, record_id: RuntimeSeam(
                client, prefix="/api/v1/ai",
                headers=_edge_headers(_grant_fetcher(readers[r]), secret=secret,
                                      record_id=record_id))
        seams = {r: RuntimeSeam(client, headers=_bearer(users[r])) for r in aq.READERS}
        return lambda r, record_id: (seams[r].scoped(record_id) if record_id is not None
                                     else seams[r])

    def _rescore(self, data, options):
        limits = self._admission()
        path = Path(options["rescore"])
        record = load_json(path)
        if record.get("set_sha256") != aq.set_digest(data):
            raise CommandError("the run file was collected from a different set")
        if record.get("grader_model") != options["grader_model"]:
            raise CommandError("rescore with the run's own pinned grader")
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
