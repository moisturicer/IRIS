"""IR-956: the answer-quality set, its freeze, the scorer and the verdict. No database."""

import copy

import pytest

from apps.ai.evaluation import answer_quality as aq

PAPER = "Stable Policy Learning"
OTHER = "MATISSE in the era of GRAVITY+"
PRIVATE = "A Private Draft"


def _case(family, n, **expect):
    expect.setdefault("outcome", "answer")
    expect.setdefault("records", [PAPER])
    expect.setdefault("pages", [{"record": PAPER, "page": 4}])
    expect.setdefault("reference", "Bagging can stabilize an unstable base learner.")
    case = {"id": f"{family}-{n:02d}", "family": family, "reader": "a",
            "turns": [{"user": f"question {family} {n}"}], "expect": expect,
            "sources": ["new"]}
    if family == "F11":
        case["scope"] = PAPER
    return case


def _set():
    cases = []
    for family in aq.FAMILIES:
        for n in range(1, 9):
            if family == "F12":
                continue
            cases.append(_case(family, n))
    for n in range(1, 5):
        a = _case("F12", 2 * n - 1, records=[PRIVATE], pages=[{"record": PRIVATE, "page": 1}],
                  reference="It reaches CIDEr .838.")
        b = _case("F12", 2 * n, outcome="refuse", records=[], pages=[], reference="",
                  forbidden=[PRIVATE])
        a["pair"] = b["pair"] = f"P{n}"
        b["reader"] = "b"
        b["turns"] = copy.deepcopy(a["turns"])
        cases += [a, b]
    return {"schema_version": 1, "set_id": "answer-quality-test", "version": 1,
            "corpus": {"snapshot_id": "proxy-arxiv-40", "titles": [PAPER, OTHER],
                       "private": {"title": PRIVATE, "readable_by": "a"}},
            "cases": cases}


def test_a_complete_set_validates():
    assert aq.validate_set(_set()) == []


def test_every_family_needs_eight_questions():
    data = _set()
    data["cases"] = [c for c in data["cases"] if c["id"] != "F05-01"]
    assert any("F05" in e and "8" in e for e in aq.validate_set(data))


def test_labels_must_name_corpus_papers_and_carry_a_reference_or_count():
    data = _set()
    data["cases"][0]["expect"]["records"] = ["Not A Paper"]
    data["cases"][1]["expect"]["reference"] = ""
    count = next(c for c in data["cases"] if c["family"] == "F04")
    count["expect"] = {"outcome": "count", "records": [], "pages": []}
    errors = aq.validate_set(data)
    assert any("Not A Paper" in e for e in errors)
    assert any(data["cases"][1]["id"] in e and "reference" in e for e in errors)
    assert any(count["id"] in e and "count" in e for e in errors)


def test_the_reader_who_cannot_read_the_private_paper_is_never_labelled_with_it():
    data = _set()
    b = next(c for c in data["cases"] if c["reader"] == "b")
    b["expect"]["reference"] = f"See {PRIVATE}."
    assert any(b["id"] in e and "private" in e for e in aq.validate_set(data))


def test_paper_chat_cases_name_their_scope_and_two_reader_pairs_ask_the_same_question():
    data = _set()
    scoped = next(c for c in data["cases"] if c["family"] == "F11")
    del scoped["scope"]
    b = next(c for c in data["cases"] if c["reader"] == "b")
    b["turns"] = [{"user": "something else"}]
    errors = aq.validate_set(data)
    assert any(scoped["id"] in e and "scope" in e for e in errors)
    assert any("P1" in e and "same" in e for e in errors)


GRADER = "openai/grader-model"


def test_a_lock_covers_questions_labels_rubric_and_grader():
    data = _set()
    lock = aq.make_lock(data, grader_model=GRADER)
    assert aq.check_lock(data, lock, grader_model=GRADER) == []
    relabelled = _set()
    relabelled["cases"][0]["expect"]["pages"][0]["page"] = 5
    assert any("edited in place" in e for e in aq.check_lock(relabelled, lock, grader_model=GRADER))
    reworded = _set()
    reworded["cases"][0]["turns"][0]["user"] = "a different question"
    assert aq.check_lock(reworded, lock, grader_model=GRADER)
    assert any("grader" in e for e in aq.check_lock(data, lock, grader_model="other/model"))
    stale = {**lock, "rubric_sha256": "0" * 64}
    assert any("rubric" in e for e in aq.check_lock(data, stale, grader_model=GRADER))


def test_a_changed_set_under_a_new_version_needs_its_own_lock():
    data = _set()
    lock = aq.make_lock(data, grader_model=GRADER)
    data["version"] = 2
    assert any("version" in e for e in aq.check_lock(data, lock, grader_model=GRADER))


ACCESS = aq.Access(title_to_id={PAPER: 53, OTHER: 30, PRIVATE: 73},
                   visible={"a": {53, 30, 73}, "b": {53, 30}})


class RecordingGrader:
    """Answers from a script and keeps every payload it was shown."""

    model = GRADER

    def __init__(self, verdict=None):
        self.verdict = verdict or {"correctness": "correct", "declined": False, "claims": [
            {"claim": "bagging stabilises", "citation": 1, "supported": True}]}
        self.seen = []

    def grade(self, payload):
        self.seen.append(payload)
        return self.verdict


def _row(case, answer="Bagging can stabilize it.", citations=((53, 4),), outcome="answered",
         mode=None, latency=1200, cost=0.01):
    turns = [{"number": n, "outcome": "answered", "public_answer": None, "latency_ms": 10}
             for n in range(1, len(case["turns"]))]
    public = None if outcome != "answered" else {
        "answer": answer, **({"mode": mode} if mode else {}),
        "citations": [{"record_id": r, "page": p, "text": f"passage {r}:{p}"}
                      for r, p in citations]}
    turns.append({"number": len(case["turns"]), "outcome": outcome, "public_answer": public,
                  "latency_ms": latency})
    return {"id": case["id"], "turns": turns, "cost": cost}


def _scored(case, row, grader):
    payload = aq.grader_payload(case, row, ACCESS)
    return aq.score_case(case, row, ACCESS, grader.grade(payload) if payload else None)


def test_a_correct_cited_answer_scores_on_every_exact_check():
    case = _case("F01", 1)
    score = _scored(case, _row(case), RecordingGrader())
    assert score["correctness"] == 1.0
    assert (score["record_hit"], score["page_hit"], score["support"]) == (1.0, 1.0, 1.0)
    assert score["leaks"] == 0 and not score["failed"]
    assert (score["latency_ms"], score["cost_usd"]) == (1200, 0.01)


def test_a_wrong_page_misses_the_page_but_not_the_record():
    case = _case("F01", 1)
    score = _scored(case, _row(case, citations=((53, 9),)), RecordingGrader())
    assert (score["record_hit"], score["page_hit"]) == (1.0, 0.0)


def test_failed_capped_and_unrun_questions_count_as_failures_and_are_not_graded():
    grader = RecordingGrader()
    for outcome in ("failure", "cap_stop", "timeout", "cancellation", "not_run"):
        case = _case("F01", 1)
        score = _scored(case, _row(case, outcome=outcome), grader)
        assert score["failed"] and score["correctness"] == 0.0 and score["support"] == 0.0
    assert grader.seen == []


def test_a_conversation_that_stopped_before_its_last_turn_failed():
    case = _case("F08", 1)
    case["turns"] = [{"user": "first"}, {"user": "then"}]
    row = _row(case)
    row["turns"] = row["turns"][:1]
    assert _scored(case, row, RecordingGrader())["failed"]


def test_the_grader_sees_only_what_the_reader_could_read_and_a_leak_is_counted():
    case = _case("F12", 2, outcome="refuse", records=[], pages=[], reference="",
                 forbidden=[PRIVATE])
    case["reader"] = "b"
    grader = RecordingGrader({"correctness": "incorrect", "declined": False, "claims": []})
    row = _row(case, answer="It reaches CIDEr .838.", citations=((73, 1), (53, 4)))
    score = _scored(case, row, grader)
    shown = grader.seen[0]
    assert [c["record"] for c in shown["citations"]] == [PAPER]
    assert "73" not in str(shown) and PRIVATE not in str(shown)
    assert score["leaks"] == 1


def test_naming_the_unreadable_paper_in_the_text_is_a_leak():
    case = _case("F12", 2, outcome="refuse", records=[], pages=[], reference="",
                 forbidden=[PRIVATE])
    case["reader"] = "b"
    row = _row(case, answer=f"I cannot show you {PRIVATE}.", citations=())
    assert _scored(case, row, RecordingGrader())["leaks"] == 1


def test_counts_are_checked_exactly_whatever_the_grader_says():
    case = _case("F04", 1, outcome="count", count=5, records=[], pages=[], reference="")
    wrong = RecordingGrader({"correctness": "correct", "declined": False, "claims": []})
    assert _scored(case, _row(case, answer="There are 4 such papers.", citations=()),
                   wrong)["correctness"] == 0.0
    assert _scored(case, _row(case, answer="Five papers are listed.", citations=()),
                   wrong)["correctness"] == 1.0
    assert _scored(case, _row(case, answer="There are 5 papers in 2 areas.", citations=()),
                   wrong)["correctness"] == 1.0


def test_a_refusal_is_read_from_the_engine_when_it_says_so_and_from_the_grader_otherwise():
    case = _case("F10", 1, outcome="refuse", records=[], pages=[], reference="")
    grader = RecordingGrader({"correctness": "incorrect", "declined": False, "claims": []})
    django = _scored(case, _row(case, answer="", mode="no_results", citations=()), grader)
    assert django["refused"] and django["correctness"] == 1.0
    agent = _scored(case, _row(case, answer="Nothing found.", citations=()),
                    RecordingGrader({"correctness": "correct", "declined": True, "claims": []}))
    assert agent["refused"] and agent["correctness"] == 1.0
    invented = _scored(case, _row(case, answer="It concluded X.", citations=()), grader)
    assert not invented["refused"] and invented["correctness"] == 0.0


def test_an_answerable_question_that_was_refused_scores_nothing():
    case = _case("F01", 1)
    score = _scored(case, _row(case, answer="", mode="no_results", citations=()),
                    RecordingGrader())
    assert score["refused"] and score["correctness"] == 0.0


def test_unsupported_and_uncited_claims_lower_citation_support():
    case = _case("F01", 1)
    grader = RecordingGrader({"correctness": "partial", "declined": False, "claims": [
        {"claim": "x", "citation": 1, "supported": True},
        {"claim": "y", "citation": 1, "supported": False},
        {"claim": "z", "citation": None, "supported": True}]})
    score = _scored(case, _row(case), grader)
    assert score["correctness"] == 0.5
    assert score["support"] == pytest.approx(1 / 3)


def test_an_unreadable_grade_is_recorded_not_guessed():
    case = _case("F01", 1)
    score = aq.score_case(case, _row(case), ACCESS, None)
    assert score["grade_missing"] and score["correctness"] is None


def _score(family, correctness=1.0, support=1.0, **extra):
    base = {"id": f"{family}-x", "family": family, "reader": "a", "expected_outcome": "answer",
            "outcome": "answered", "failed": False, "refused": False,
            "correctness": correctness, "support": support, "record_hit": 1.0,
            "page_hit": 1.0, "listing_hit": None, "leaks": 0, "grade_missing": False,
            "latency_ms": 1000, "cost_usd": 0.02, "compaction": []}
    return {**base, **extra}


def _arms(agent_overrides=None, django_overrides=None):
    django = [_score(f, **(django_overrides or {}).get(f, {})) for f in aq.FAMILIES]
    agent = [_score(f, **(agent_overrides or {}).get(f, {})) for f in aq.FAMILIES]
    return {"django": django, "agent": agent}


def test_the_summary_reports_each_measure_per_family_and_overall():
    scores = [_score("F01", latency_ms=n * 100, cost_usd=0.01) for n in range(1, 21)]
    scores.append(_score("F10", expected_outcome="refuse", refused=True, support=None,
                         record_hit=None, page_hit=None))
    scores.append(_score("F01", correctness=0.0, support=0.0, failed=True, outcome="timeout",
                         latency_ms=None, leaks=1))
    summary = aq.summarize(scores)
    overall, f01 = summary["overall"], summary["families"]["F01"]
    assert overall["questions"] == 22 and overall["failures"] == 1 and overall["leaks"] == 1
    assert f01["questions"] == 21
    assert f01["correctness"] == pytest.approx(20 / 21)
    assert f01["p95_latency_ms"] == 1900
    assert summary["families"]["F10"]["refusal_accuracy"] == 1.0
    assert f01["refusal_accuracy"] is None
    assert overall["cost_per_question_usd"] == pytest.approx((20 * 0.01 + 0.02 + 0.02) / 22)


def test_the_agent_passes_when_it_matches_django_without_leaks_or_family_drops():
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in _arms().items()})
    assert verdict["result"] == "pass" and verdict["reasons"] == []


def test_a_single_leak_fails_the_agent():
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in
                          _arms(agent_overrides={"F12": {"leaks": 1}}).items()})
    assert verdict["result"] == "fail"
    assert any("leak" in r for r in verdict["reasons"])
    assert "F12" in verdict["deciding_families"]


def test_a_family_more_than_ten_points_down_fails_even_if_overall_is_higher():
    agent = {f: {"correctness": 1.0} for f in aq.FAMILIES}
    agent["F07"] = {"correctness": 0.85}
    django = {f: {"correctness": 0.5} for f in aq.FAMILIES}
    django["F07"] = {"correctness": 0.96}
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in
                          _arms(agent_overrides=agent, django_overrides=django).items()})
    assert verdict["result"] == "fail" and verdict["deciding_families"] == ["F07"]


def test_exactly_ten_points_down_is_not_a_drop():
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in _arms(
        agent_overrides={"F03": {"correctness": 0.9}, "F04": {"correctness": 1.0}},
        django_overrides={"F04": {"correctness": 0.9}}).items()})
    assert verdict["result"] == "pass"


def test_lower_overall_citation_support_fails():
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in
                          _arms(agent_overrides={"F02": {"support": 0.95}}).items()})
    assert verdict["result"] == "fail" and any("support" in r for r in verdict["reasons"])


def test_an_ungraded_answer_blocks_a_pass():
    verdict = aq.verdict({arm: aq.summarize(s) for arm, s in _arms(
        agent_overrides={"F05": {"grade_missing": True, "correctness": None}}).items()})
    assert verdict["result"] == "fail" and any("graded" in r for r in verdict["reasons"])


def test_the_report_states_the_verdict_and_every_family():
    summaries = {arm: aq.summarize(s) for arm, s in _arms().items()}
    text = aq.render_markdown({"set_id": "answer-quality-test", "version": 1,
                               "summaries": summaries, "verdict": aq.verdict(summaries),
                               "not_run": ["F09-03"], "conditions": []})
    assert "PASS" in text and "F09-03" in text
    for family, name in aq.FAMILIES.items():
        assert family in text and name in text


def _cases(n):
    return [_case("F01", i) for i in range(1, n + 1)]


def test_both_engines_answer_each_case_before_the_next_and_a_spent_budget_stops_both():
    calls = []
    collectors = {arm: (lambda case, arm=arm: calls.append((arm, case["id"])) or _row(case))
                  for arm in aq.ARMS}
    budget = iter([True, True, False, True])
    run = aq.collect_both(_cases(4), collectors, fits=lambda case: next(budget))
    assert calls == [("django", "F01-01"), ("agent", "F01-01"),
                     ("django", "F01-02"), ("agent", "F01-02")]
    assert run["not_run"] == ["F01-03", "F01-04"]
    unrun = aq.score_case(_cases(4)[2], run["rows"]["agent"].get("F01-03"), ACCESS, None)
    assert unrun["failed"] and unrun["outcome"] == "not_run"


def test_a_collector_that_raises_records_a_failure_and_the_run_goes_on():
    def broken(case):
        raise ValueError("reopen failed")
    run = aq.collect_both(_cases(2), {"django": broken, "agent": _row}, fits=lambda c: True)
    assert run["rows"]["django"]["F01-02"]["turns"][-1]["outcome"] == "failure"
    assert run["rows"]["agent"]["F01-02"]["turns"][-1]["outcome"] == "answered"


def test_a_failed_question_keeps_its_reason_and_throttling_is_a_condition_problem():
    def throttled(case):
        raise ValueError("conversation creation failed with HTTP 429")
    run = aq.collect_both(_cases(2), {"django": throttled, "agent": _row}, fits=lambda c: True)
    assert "HTTP 429" in run["rows"]["django"]["F01-01"]["error"]
    problems = aq.throttled_problems(run["rows"])
    assert len(problems) == 1 and "2 questions" in problems[0]
    assert aq.throttled_problems({"agent": {"F01-01": _row(_cases(1)[0])}}) == []


class FlakyGrader(RecordingGrader):
    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    def grade(self, payload):
        if self.failures:
            self.failures -= 1
            raise aq.GraderError("not JSON")
        return super().grade(payload)


def test_grading_retries_once_then_leaves_the_answer_ungraded():
    cases = _cases(2)
    rows = {arm: {c["id"]: _row(c) for c in cases} for arm in aq.ARMS}
    grades, problems = aq.grade_all(cases, rows, ACCESS, FlakyGrader(1), fits=lambda c: True)
    assert all(grades[arm][c["id"]] for arm in aq.ARMS for c in cases) and problems == []
    grades, problems = aq.grade_all(cases[:1], rows, ACCESS, FlakyGrader(2), fits=lambda c: True)
    assert grades["django"]["F01-01"] is None and "F01-01" in problems[0]


def test_grading_stops_before_a_call_the_budget_cannot_cover():
    cases = _cases(2)
    rows = {arm: {c["id"]: _row(c) for c in cases} for arm in aq.ARMS}
    grader = RecordingGrader()
    grades, problems = aq.grade_all(cases, rows, ACCESS, grader,
                                    fits=lambda case: case["id"] == "F01-01")
    assert len(grader.seen) == 2 and grades["agent"]["F01-02"] is None
    assert any("F01-02" in p and "budget" in p for p in problems)


class ScriptedLLM:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def generate(self, system, user):
        self.prompts.append((system, user))
        return self.reply


def test_the_model_grader_sends_the_fixed_rubric_and_reads_fenced_json():
    llm = ScriptedLLM('```json\n{"correctness": "partial", "declined": false, "claims": []}\n```')
    grade = aq.ModelGrader(llm, model=GRADER).grade({"question": "q"})
    assert grade["correctness"] == "partial" and llm.prompts[0][0] == aq.RUBRIC


@pytest.mark.parametrize("reply", ["not json", '{"correctness": "great", "declined": false, '
                                   '"claims": []}', '{"correctness": "correct"}'])
def test_the_model_grader_refuses_a_malformed_verdict(reply):
    with pytest.raises(aq.GraderError):
        aq.ModelGrader(ScriptedLLM(reply), model=GRADER).grade({"question": "q"})


def test_a_budget_covers_every_turn_of_both_engines_and_both_grades_at_the_run_ceiling():
    case = _case("F09", 1)
    case["turns"] = [{"user": "a"}, {"action": "compact"}, {"user": "b"}]
    budget = aq.Budget(run_ceiling_micros=100, remaining=lambda: 799)
    assert budget.worst_case_micros(case) == (3 * 2 + 2) * 100
    assert not budget.fits(case)
    assert aq.Budget(run_ceiling_micros=100, remaining=lambda: 800).fits(case)
    assert aq.Budget(run_ceiling_micros=100, remaining=lambda: 200).fits_grade(case)


def test_the_report_scores_both_engines_and_counts_unrun_cases_as_failures_in_each():
    data = _set()
    first, second = data["cases"][0], data["cases"][1]
    rows = {arm: {first["id"]: _row(first)} for arm in aq.ARMS}
    grades = {arm: {first["id"]: RecordingGrader().verdict} for arm in aq.ARMS}
    report = aq.build_report(data, rows, ACCESS, grades, not_run=[second["id"]],
                             conditions=[])
    for arm in aq.ARMS:
        by_id = {s["id"]: s for s in report["scores"][arm]}
        assert len(by_id) == len(data["cases"])
        assert by_id[first["id"]]["correctness"] == 1.0
        assert by_id[second["id"]]["failed"] and by_id[second["id"]]["outcome"] == "not_run"
    assert report["verdict"]["result"] == "pass"
    assert report["not_run"] == [second["id"]]


def test_a_page_label_may_name_the_page_its_chunk_starts_on_as_an_alternative():
    case = _case("F01", 1, pages=[{"record": PAPER, "page": 4, "also": [3]}])
    assert aq.validate_set({**_set(), "cases": [*_set()["cases"][1:], case]}) == []
    assert _scored(case, _row(case, citations=((53, 3),)), RecordingGrader())["page_hit"] == 1.0
    assert _scored(case, _row(case, citations=((53, 2),)), RecordingGrader())["page_hit"] == 0.0


def test_an_unreadable_paper_both_cited_and_named_is_one_leak():
    case = _case("F12", 2, outcome="refuse", records=[], pages=[], reference="",
                 forbidden=[PRIVATE])
    case["reader"] = "b"
    row = _row(case, answer=f"See {PRIVATE}.", citations=((73, 1),))
    assert _scored(case, row, RecordingGrader())["leaks"] == 1


def test_cost_per_question_leaves_out_questions_whose_cost_is_unknown():
    case = _case("F01", 1)
    unrun = aq.score_case(case, None, ACCESS, None)
    crashed = aq.score_case(case, aq._failed_row(case), ACCESS, None)
    assert unrun["cost_usd"] is None and crashed["cost_usd"] is None
    paid = _score("F01", cost_usd=0.04)
    summary = aq.summarize([paid, {**paid, "cost_usd": None}])
    assert summary["overall"]["cost_per_question_usd"] == pytest.approx(0.04)
