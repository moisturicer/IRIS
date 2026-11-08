"""Answer quality of both Ask IRIS engines on one frozen set (IR-956). Pure.

The set is twelve question families over the proxy corpus. Each case is a
Conversation whose last turn is the scored question; its ``expect`` holds the
labels: expected Records and pages, a reference answer or an exact count, and
whether the reader should be refused. Scoring is automatic: exact checks for
citations, pages, counts, refusals and access leaks, plus a pinned model
grader with the fixed rubric below. Nothing here signs, approves or
adjudicates (IR-955).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Iterable, Mapping, Protocol, Sequence

FAMILIES = {
    "F01": "single fact",
    "F02": "meaning only",
    "F03": "multi-paper comparison",
    "F04": "exact metadata count",
    "F05": "listing",
    "F06": "naming a paper",
    "F07": "late detail in a long Manuscript",
    "F08": "multi-turn follow-up",
    "F09": "compaction then exact-detail recovery",
    "F10": "unanswerable or out of corpus",
    "F11": "Paper Chat scoped to one Record",
    "F12": "two readers with different access",
}
MIN_PER_FAMILY = 8
READERS = ("a", "b")
OUTCOMES = ("answer", "refuse", "count")
COMPACT = "compact"


def norm(text) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", str(text or "").casefold()).split())


def mentions(text, title) -> bool:
    return bool(norm(title)) and f" {norm(title)} " in f" {norm(text)} "


# -- the set ----------------------------------------------------------------


def _titles(expect: Mapping) -> list[str]:
    return [*expect.get("records", []), *(p.get("record") for p in expect.get("pages", [])),
            *(expect.get("listing") or []), *(expect.get("forbidden") or [])]


def validate_set(data: Mapping, *, min_per_family: int = MIN_PER_FAMILY) -> list[str]:
    """Why ``data`` is not a usable set; empty when it is."""
    errors = []
    corpus = data.get("corpus") or {}
    private = (corpus.get("private") or {}).get("title")
    known = set(corpus.get("titles") or []) | ({private} if private else set())
    cases = data.get("cases") or []
    seen, pairs = set(), {}
    for case in cases:
        cid = case.get("id")
        if cid in seen:
            errors.append(f"{cid}: duplicate id")
        seen.add(cid)
        if case.get("family") not in FAMILIES:
            errors.append(f"{cid}: unknown family {case.get('family')!r}")
        reader = case.get("reader")
        if reader not in READERS:
            errors.append(f"{cid}: reader must be one of {READERS}")
        turns = case.get("turns") or []
        if not turns or not (turns[-1].get("user") or "").strip():
            errors.append(f"{cid}: the last turn must be a question")
        for turn in turns:
            if "action" in turn and turn["action"] != COMPACT:
                errors.append(f"{cid}: unknown turn action {turn['action']!r}")
            elif "action" not in turn and not (turn.get("user") or "").strip():
                errors.append(f"{cid}: an empty turn")
        if not case.get("sources"):
            errors.append(f"{cid}: sources must say where the case came from")
        expect = case.get("expect") or {}
        outcome = expect.get("outcome")
        if outcome not in OUTCOMES:
            errors.append(f"{cid}: outcome must be one of {OUTCOMES}")
        if outcome == "answer" and not (expect.get("reference") or "").strip():
            errors.append(f"{cid}: an answer needs a reference")
        if outcome == "count" and (type(expect.get("count")) is not int or expect["count"] < 0):
            errors.append(f"{cid}: a count question needs an exact count")
        if outcome == "refuse" and (expect.get("records") or expect.get("pages")):
            errors.append(f"{cid}: a refusal expects no Records")
        for page in expect.get("pages", []):
            if any(type(n) is not int or n < 1 for n in [page.get("page"), *page.get("also", [])]):
                errors.append(f"{cid}: page must be a positive integer")
            if page.get("record") not in expect.get("records", []):
                errors.append(f"{cid}: a page's Record must be among the expected Records")
        for title in _titles(expect) + ([case["scope"]] if case.get("scope") else []):
            if title not in known:
                errors.append(f"{cid}: {title!r} is not a corpus paper")
        if private and reader != (corpus.get("private") or {}).get("readable_by"):
            labels = [*expect.get("records", []), *(p.get("record") for p in expect.get(
                "pages", [])), *(expect.get("listing") or [])]
            if private in labels or private == case.get("scope") or mentions(
                    expect.get("reference"), private):
                errors.append(f"{cid}: labelled with the private paper its reader cannot read")
        if case.get("family") == "F11" and not case.get("scope"):
            errors.append(f"{cid}: a Paper Chat case needs a scope")
        if case.get("family") != "F11" and case.get("scope"):
            errors.append(f"{cid}: only Paper Chat cases are scoped")
        if case.get("family") == "F12":
            pairs.setdefault(case.get("pair"), []).append(case)
    for family in FAMILIES:
        count = sum(c.get("family") == family for c in cases)
        if count < min_per_family:
            errors.append(f"{family}: {count} questions, at least {min_per_family} required")
    for pair, members in pairs.items():
        if sorted(m.get("reader") for m in members) != list(READERS):
            errors.append(f"pair {pair}: needs one case per reader")
        elif len({json.dumps(m.get("turns"), sort_keys=True) for m in members}) != 1:
            errors.append(f"pair {pair}: both readers must ask the same turns")
    return errors


# -- the rubric and the freeze --------------------------------------------------

RUBRIC_VERSION = "aq-rubric-1"
RUBRIC = """You grade one answer from a research-repository assistant. You see the
question (and the earlier questions of the same conversation), the labelled
reference, and the answer with the passages it cites. You see nothing else:
judge only from what is in front of you, never from your own knowledge of the
papers.

Return one JSON object and nothing else:
{"correctness": "correct" | "partial" | "incorrect",
 "declined": true | false,
 "claims": [{"claim": "<one factual claim from the answer>",
             "citation": <the 1-based number of the cited passage it relies on, or null>,
             "supported": true | false}]}

correctness: "correct" when the answer states what the reference states (other
wording is fine; extra correct detail is fine); "partial" when it gets part of
it right and nothing wrong; "incorrect" when it misses the point, contradicts
the reference or declines a question the reference answers. When the expected
outcome is "refuse", "correct" means it said it has no evidence for this and
invented nothing.
declined: true when the answer says it cannot answer from the repository or
found no relevant sources, and gives no substantive answer.
claims: every factual claim about a paper or its content. A claim is supported
only when the passage it cites states it. A claim with no citation is not
supported. General background that names no paper is not a claim. List no
claims for a declined answer."""


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def set_digest(data: Mapping) -> str:
    """Questions and labels: the corpus, readers and every case, nothing descriptive."""
    return _digest({"corpus": data.get("corpus"), "cases": data.get("cases")})


def rubric_digest() -> str:
    return _digest({"version": RUBRIC_VERSION, "rubric": RUBRIC})


def make_lock(data: Mapping, *, grader_model: str) -> dict:
    lock = {"set_id": data["set_id"], "version": data["version"],
            "set_sha256": set_digest(data), "rubric_version": RUBRIC_VERSION,
            "rubric_sha256": rubric_digest(), "grader_model": grader_model,
            "cases": len(data["cases"])}
    lock["lock_sha256"] = _digest(lock)
    return lock


def check_lock(data: Mapping, lock: Mapping, *, grader_model: str) -> list[str]:
    """Why ``data`` scored by ``grader_model`` is not what ``lock`` froze; empty when it is."""
    problems = []
    if (lock.get("set_id"), lock.get("version")) != (data.get("set_id"), data.get("version")):
        problems.append(f"the lock is for {lock.get('set_id')} version {lock.get('version')}, "
                        f"not {data.get('set_id')} version {data.get('version')}; "
                        "a changed set is a new version with its own lock")
    elif lock.get("set_sha256") != set_digest(data):
        problems.append("questions or labels were edited in place; "
                        "save the change as a new version and freeze that")
    if lock.get("rubric_sha256") != rubric_digest() or lock.get("rubric_version") != RUBRIC_VERSION:
        problems.append("the rubric differs from the frozen one")
    if lock.get("grader_model") != grader_model:
        problems.append(f"grader model {grader_model!r} is not the frozen "
                        f"{lock.get('grader_model')!r}")
    body = {k: v for k, v in lock.items() if k != "lock_sha256"}
    if lock.get("lock_sha256") != _digest(body):
        problems.append("the lock file itself was edited")
    return problems


# -- exact checks and grading ---------------------------------------------------

_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50})
#: Django's wire mode for "no readable sources matched" (`presentation.NO_RESULTS_MODE`).
NO_RESULTS = "no_results"
_GRADES = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


class Access:
    """Which Records each reader could read, measured on the database the run used."""

    def __init__(self, *, title_to_id: Mapping[str, int], visible: Mapping[str, Iterable[int]]):
        self.title_to_id = dict(title_to_id)
        self.id_to_title = {v: k for k, v in self.title_to_id.items()}
        self.visible = {reader: set(ids) for reader, ids in visible.items()}

    def as_dict(self) -> dict:
        return {"title_to_id": self.title_to_id,
                "visible": {r: sorted(ids) for r, ids in self.visible.items()}}

    @classmethod
    def from_dict(cls, value: Mapping) -> "Access":
        return cls(title_to_id=value["title_to_id"], visible=value["visible"])


class Grader(Protocol):
    model: str

    def grade(self, payload: Mapping) -> Mapping: ...


def numbers_in(text) -> set[int]:
    found = {int(n.replace(",", "")) for n in re.findall(r"(?<![\d.])\d[\d,]*(?![\d.]*\d)",
                                                          str(text or ""))}
    return found | {_WORDS[w] for w in norm(text).split() if w in _WORDS}


def _scored_turn(case: Mapping, row: Mapping | None):
    turns = (row or {}).get("turns") or []
    last = turns[-1] if turns else None
    if last is None or last.get("number") != len(case["turns"]):
        return None
    return last


def _answer(turn) -> tuple[str, str | None, list]:
    public = (turn or {}).get("public_answer") or {}
    text = public.get("answer") or public.get("message") or ""
    return text, public.get("mode"), list(public.get("citations") or [])


def _answered(turn) -> bool:
    return bool(turn) and turn.get("outcome") == "answered"


def grader_payload(case: Mapping, row: Mapping | None, access: Access) -> dict | None:
    """What the grader may see, or ``None`` when there is no answer to grade.

    Only citations of Records the case's reader could read are passed on, so the
    grader never sees a passage the reader could not.
    """
    turn = _scored_turn(case, row)
    if not _answered(turn):
        return None
    text, _, citations = _answer(turn)
    readable = access.visible.get(case["reader"], set())
    expect = case["expect"]
    return {
        "earlier_questions": [t["user"] for t in case["turns"][:-1] if t.get("user")],
        "question": case["turns"][-1]["user"],
        "expected_outcome": expect["outcome"],
        "reference": expect.get("reference") or "",
        **({"expected_count": expect["count"]} if expect["outcome"] == "count" else {}),
        "answer": text,
        "citations": [{"number": n, "record": access.id_to_title.get(c.get("record_id")),
                       "page": c.get("page"), "passage": c.get("text") or c.get("quote") or ""}
                      for n, c in enumerate(citations, 1) if c.get("record_id") in readable],
    }


def _fraction(hits: int, total: int):
    return hits / total if total else None


def score_case(case: Mapping, row: Mapping | None, access: Access,
               grade: Mapping | None) -> dict:
    """Every measure of one question for one engine. ``grade`` is the grader's verdict."""
    expect = case["expect"]
    turn = _scored_turn(case, row)
    failed = not _answered(turn)
    text, mode, citations = _answer(turn) if not failed else ("", None, [])
    readable = access.visible.get(case["reader"], set())
    cited = {c.get("record_id") for c in citations}
    unreadable = [t for t, i in access.title_to_id.items() if i not in readable]
    leaks = len({i for i in cited if i not in readable and i is not None}
                | {access.title_to_id[t] for t in unreadable if mentions(text, t)})
    expected_ids = [access.title_to_id.get(t) for t in expect.get("records", [])]
    cited_pages = {(c.get("record_id"), c.get("page")) for c in citations}
    pages = expect.get("pages", [])
    page_hits = sum(any((access.title_to_id.get(p["record"]), n) in cited_pages
                        for n in (p["page"], *p.get("also", ()))) for p in pages)
    listing = expect.get("listing") or []
    graded = grade is not None and not failed
    refused = mode == NO_RESULTS or bool(graded and grade.get("declined"))
    known_refusal = failed or mode == NO_RESULTS or graded
    outcome = expect["outcome"]
    if failed:
        correctness = 0.0
    elif outcome == "refuse":
        correctness = (1.0 if refused else 0.0) if known_refusal else None
    elif mode == NO_RESULTS or (graded and refused):
        correctness = 0.0
    elif outcome == "count":
        correctness = 1.0 if expect["count"] in numbers_in(text) else 0.0
    else:
        correctness = _GRADES.get(grade.get("correctness")) if graded else None
    claims = list(grade.get("claims") or []) if graded else []
    if failed:
        support = 0.0
    elif outcome == "refuse":
        support = None
    elif refused:
        support = 0.0
    else:
        support = _fraction(sum(bool(c.get("supported")) and c.get("citation") is not None
                                for c in claims), len(claims))
    return {
        "id": case["id"], "family": case["family"], "reader": case["reader"],
        "expected_outcome": outcome, "outcome": (turn or {}).get("outcome", "not_run"),
        "failed": failed, "refused": refused and not failed, "correctness": correctness,
        "support": support,
        "record_hit": 0.0 if failed and expected_ids else _fraction(
            sum(i in cited for i in expected_ids), len(expected_ids)),
        "page_hit": 0.0 if failed and pages else _fraction(page_hits, len(pages)),
        "listing_hit": 0.0 if failed and listing else _fraction(
            sum(mentions(text, t) or access.title_to_id.get(t) in cited for t in listing),
            len(listing)),
        "leaks": leaks,
        "grade_missing": not failed and grade is None,
        "latency_ms": (turn or {}).get("latency_ms"),
        "cost_usd": None if (row or {}).get("cost") is None else float(row["cost"]),
        "compaction": [t.get("outcome") for t in (row or {}).get("turns") or ()
                       if t.get("action") == COMPACT],
    }


# -- report and verdict ---------------------------------------------------------

ARMS = ("django", "agent")
#: IR-955's bar: how far one family may fall below Django, in correctness or support.
FAMILY_DROP = 0.10
_COMPARED = (("correctness", "correctness"), ("support", "citation support"))
_EPSILON = 1e-9


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def p95(values):
    values = sorted(v for v in values if v is not None)
    return values[math.ceil(0.95 * len(values)) - 1] if values else None


def _measures(scores: Sequence[Mapping]) -> dict:
    refusals = [s for s in scores if s["expected_outcome"] == "refuse"]
    answerable = [s for s in scores if s["expected_outcome"] != "refuse"]
    return {
        "questions": len(scores),
        "correctness": _mean(s["correctness"] for s in scores),
        "support": _mean(s["support"] for s in scores),
        "record_accuracy": _mean(s["record_hit"] for s in scores),
        "page_accuracy": _mean(s["page_hit"] for s in scores),
        "listing_accuracy": _mean(s.get("listing_hit") for s in scores),
        "refusal_accuracy": _mean(float(s["refused"]) for s in refusals),
        "false_refusals": sum(s["refused"] for s in answerable),
        "leaks": sum(s["leaks"] for s in scores),
        "failures": sum(s["failed"] for s in scores),
        "ungraded": sum(s["grade_missing"] for s in scores),
        "cost_per_question_usd": _mean(s["cost_usd"] for s in scores),
        "p95_latency_ms": p95(s["latency_ms"] for s in scores),
    }


def summarize(scores: Sequence[Mapping]) -> dict:
    return {"overall": _measures(scores),
            "families": {f: _measures([s for s in scores if s["family"] == f])
                         for f in FAMILIES if any(s["family"] == f for s in scores)}}


def _below(agent, django, margin=0.0) -> bool:
    return agent is not None and django is not None and agent < django - margin - _EPSILON


def verdict(summaries: Mapping[str, Mapping], conditions: Sequence[str] = ()) -> dict:
    """IR-955's switch bar: the agent matches or beats Django on overall correctness and
    citation support, leaks nothing, and no family falls more than ten points in either."""
    agent, django = summaries["agent"], summaries["django"]
    reasons = [f"conditions differ: {c}" for c in conditions]
    deciding = []
    ungraded = sum(s["overall"]["ungraded"] for s in summaries.values())
    if ungraded:
        reasons.append(f"{ungraded} answers were not graded; rescore before deciding")
    if agent["overall"]["leaks"]:
        reasons.append(f"the agent leaked {agent['overall']['leaks']} times")
        deciding += [f for f, m in agent["families"].items() if m["leaks"]]
    for key, name in _COMPARED:
        if agent["overall"][key] is None or _below(agent["overall"][key], django["overall"][key]):
            reasons.append(f"overall {name} {_pct(agent['overall'][key])} is below "
                           f"Django's {_pct(django['overall'][key])}")
    drops = []
    for family in FAMILIES:
        a, d = agent["families"].get(family), django["families"].get(family)
        if not a or not d:
            continue
        for key, name in _COMPARED:
            if _below(a[key], d[key], FAMILY_DROP):
                drops.append(family)
                reasons.append(f"{family} {FAMILIES[family]}: {name} {_pct(a[key])} vs "
                               f"Django's {_pct(d[key])}, more than ten points down")
    deciding += drops
    if reasons and not deciding:
        deciding = [f for f in sorted(FAMILIES, key=lambda f: _delta(summaries, f))
                    if _delta(summaries, f) < 0]
    closest = min((f for f in FAMILIES if f in agent["families"] and f in django["families"]),
                  key=lambda f: _delta(summaries, f), default=None)
    return {"result": "fail" if reasons else "pass", "reasons": reasons,
            "deciding_families": list(dict.fromkeys(deciding)),
            "closest_family": closest}


def _delta(summaries, family) -> float:
    a = summaries["agent"]["families"].get(family, {}).get("correctness")
    d = summaries["django"]["families"].get(family, {}).get("correctness")
    return 0.0 if a is None or d is None else a - d


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


_COLUMNS = (("correctness", "correct", _pct), ("support", "cited support", _pct),
            ("page_accuracy", "page", _pct), ("refusal_accuracy", "refusal", _pct),
            ("leaks", "leaks", str), ("failures", "failed", str),
            ("cost_per_question_usd", "US$/q",
             lambda v: "n/a" if v is None else f"{v:.4f}"),
            ("p95_latency_ms", "p95 ms", lambda v: "n/a" if v is None else str(v)))


def render_markdown(report: Mapping) -> str:
    summaries, decided = report["summaries"], report["verdict"]
    lines = [f"# Answer quality — {report['set_id']} v{report['version']}", "",
             f"**{decided['result'].upper()}** against IR-955's bar: the agent matches or "
             "beats Django `lanes-v1` on overall correctness and citation support, leaks "
             "nothing, and drops no family by more than ten points.", ""]
    lines += [f"- {r}" for r in decided["reasons"]] or ["- every condition of the bar holds"]
    closest = decided.get("closest_family")
    nothing = "none" + (f" (closest: {closest} {FAMILIES[closest]})" if closest else "")
    lines += ["", "Families that decided it: " + (", ".join(
        f"{f} {FAMILIES[f]}" for f in decided["deciding_families"]) or nothing), ""]
    if report.get("conditions"):
        lines += ["Condition problems:", *[f"- {c}" for c in report["conditions"]], ""]
    if report.get("not_run"):
        lines += ["Not run (counted as failures): " + ", ".join(report["not_run"]), ""]
    if report.get("grading_problems"):
        lines += ["Grading problems:", *[f"- {p}" for p in report["grading_problems"]], ""]
    header = "| family | engine | n | " + " | ".join(c[1] for c in _COLUMNS) + " |"
    lines += [header, "|" + "---|" * (len(_COLUMNS) + 3)]
    for family in ("overall", *FAMILIES):
        for arm in ARMS:
            m = (summaries[arm]["overall"] if family == "overall"
                 else summaries[arm]["families"].get(family))
            if not m:
                continue
            label = "overall" if family == "overall" else f"{family} {FAMILIES[family]}"
            lines.append(f"| {label} | {arm} | {m['questions']} | " +
                         " | ".join(fmt(m[key]) for key, _, fmt in _COLUMNS) + " |")
    lines += ["", "Proxy corpus only: never a finding about CIT-U research."]
    return "\n".join(lines) + "\n"


# -- collection, grading and spend ------------------------------------------------


class GraderError(Exception):
    """The grader's reply was not a verdict under the rubric."""


class ModelGrader:
    """The pinned model grader: the fixed rubric as system prompt, one answer per call."""

    def __init__(self, llm, *, model: str):
        self.llm, self.model = llm, model

    def grade(self, payload: Mapping) -> dict:
        reply = self.llm.generate(RUBRIC, json.dumps(payload, ensure_ascii=False, indent=1))
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(reply or "").strip())
        try:
            verdict = json.loads(body)
        except ValueError:
            raise GraderError("the grader did not reply with JSON") from None
        if (not isinstance(verdict, dict) or verdict.get("correctness") not in _GRADES
                or not isinstance(verdict.get("declined"), bool)
                or not isinstance(verdict.get("claims"), list)
                or not all(isinstance(c, dict) and isinstance(c.get("supported"), bool)
                           for c in verdict["claims"])):
            raise GraderError("the grader's reply does not follow the rubric")
        return verdict


class Budget:
    """Worst-case spend against what is left of the campaign.

    Every turn of either engine and every grading call is admitted under the run
    ceiling, so a case can cost at most that ceiling per call. A case that might
    not fit is not started: nothing is sent for it.
    """

    def __init__(self, *, run_ceiling_micros: int, remaining, arms: int = len(ARMS)):
        self.run_ceiling_micros, self.remaining, self.arms = run_ceiling_micros, remaining, arms

    def worst_case_micros(self, case: Mapping) -> int:
        """Every turn of each collected engine, then one grading call per engine."""
        return (len(case["turns"]) * self.arms + len(ARMS)) * self.run_ceiling_micros

    def fits(self, case: Mapping) -> bool:
        return self.worst_case_micros(case) <= self.remaining()

    def fits_grade(self, case: Mapping) -> bool:
        return len(ARMS) * self.run_ceiling_micros <= self.remaining()


def _failed_row(case: Mapping, outcome: str = "failure", error: str | None = None) -> dict:
    row = {"id": case["id"], "status": "incomplete", "cost": None, "turns": [
        {"number": 1, "outcome": outcome, "public_answer": None, "latency_ms": None}]}
    if error:
        row["error"] = error[:300]
    return row


def throttled_problems(rows: Mapping) -> list[str]:
    """A question the rate limiter refused measured the deployment, not the engine."""
    hit = sorted({cid for arm in rows.values() for cid, row in arm.items()
                  if "HTTP 429" in (row.get("error") or "")})
    if not hit:
        return []
    return [f"the rate limiter refused {len(hit)} questions (HTTP 429), e.g. {hit[0]}; "
            "raise the API_THROTTLE_* rates for the run's readers"]


def collect_both(cases: Sequence[Mapping], collectors: Mapping, *, fits) -> dict:
    """Each case through every engine before the next, so a stop affects both alike.

    ``fits(case)`` is asked before a case starts; the first case that does not fit
    and every case after it are not run, and are scored as failures.
    """
    rows = {arm: {} for arm in collectors}
    not_run = []
    for case in cases:
        if not_run or not fits(case):
            not_run.append(case["id"])
            continue
        for arm, collect in collectors.items():
            try:
                rows[arm][case["id"]] = collect(case)
            except Exception as exc:  # an unfollowable engine is a failed question, not a crash
                rows[arm][case["id"]] = _failed_row(case, error=f"{type(exc).__name__}: {exc}")
    return {"rows": rows, "not_run": not_run}


def grade_all(cases: Sequence[Mapping], rows: Mapping, access: Access, grader: Grader, *,
              fits, previous: Mapping | None = None) -> tuple[dict, list[str]]:
    """The grader's verdict per engine and case; ``None`` where it could not grade.

    A verdict in ``previous`` is kept, so a rescore only grades what is missing.
    """
    grades = {arm: dict((previous or {}).get(arm) or {}) for arm in rows}
    problems = []
    stopped = False
    for case in cases:
        payloads = {arm: grader_payload(case, rows[arm].get(case["id"]), access)
                    for arm in rows if grades[arm].get(case["id"]) is None}
        pending = [arm for arm, payload in payloads.items() if payload]
        if not pending:
            continue
        if stopped or not fits(case):
            stopped = True
            for arm in pending:
                grades[arm][case["id"]] = None
            problems.append(f"{case['id']}: not graded, the campaign budget cannot cover it")
            continue
        for arm in pending:
            payload = payloads[arm]
            for attempt in (1, 2):
                try:
                    grades[arm][case["id"]] = grader.grade(payload)
                    break
                except GraderError as exc:
                    if attempt == 2:
                        grades[arm][case["id"]] = None
                        problems.append(f"{case['id']} ({arm}): {exc}")
    return grades, problems


def build_report(data: Mapping, rows: Mapping, access: Access, grades: Mapping, *,
                 not_run: Sequence[str], conditions: Sequence[str]) -> dict:
    """Every question scored for each engine, the summaries and the verdict.

    A case an engine never answered (not run, or missing) is scored as a failure.
    """
    scores = {arm: [score_case(case, rows.get(arm, {}).get(case["id"]), access,
                               (grades.get(arm) or {}).get(case["id"]))
                    for case in data["cases"]] for arm in ARMS}
    summaries = {arm: summarize(scores[arm]) for arm in ARMS}
    return {"scores": scores, "summaries": summaries,
            "verdict": verdict(summaries, conditions), "not_run": list(not_run),
            "conditions": list(conditions)}
