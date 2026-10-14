"""Scoring the first fixed-workflow milestone against pinned labels (IR-550).

The first milestone is the metadata count (IR-543), the presence listing
(IR-546) and the topic-match count (IR-547). A milestone set is the
fixed-workflow baseline fixture's format: records, the two populations, human
relevance labels per topic, and one `contract` per case. An optional `split`
names development and held-out cases and pins the held-out ones by digest.

**Each measure owns its denominator and its ground truth**, and none is folded
into another (pilot README §6):

- a metadata count is checked against its population's record keys, never
  against what the workflow returned;
- candidate recall is owed every labelled-relevant Record the asker can see,
  whether or not the workflow found it;
- screening precision and recall are over assessed candidates with a
  `relevant` or `not_relevant` label, and every other candidate is reported
  outside both denominators;
- answer quality exists only where a person reviewed it, and a model judge
  is never interpreted here: the threshold for that is the owner's.

Small public samples are exploratory and inconclusive, never CIT-U
reliability evidence. Pure: no database and no file I/O.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from .capacity import percentile

METADATA = "metadata_count"
TOPIC_COUNT = "topic_match_count"
LISTING = "presence_listing"
MILESTONE_FAMILIES = (METADATA, TOPIC_COUNT, LISTING)

CIT_U = "cit-u"
TIERS = ("synthetic", "proxy", CIT_U)

INCLUDED, EXCLUDED, UNCERTAIN, UNASSESSED = "included", "excluded", "uncertain", "unassessed"
JUDGED = (INCLUDED, EXCLUDED, UNCERTAIN)

#: Prefix of a candidate the set holds no label for. It is reported, never
#: treated as a breach or as relevant: the set simply says nothing about it.
UNLABELLED = "unlabelled:"

#: Named security and lifecycle scenarios, and the tests that assert them.
#: A run observes none of these; the report says so rather than implying it.
SCENARIOS = (
    ("invisible records never appear",
     "apps/ai/tests/test_fixed_workflow_baseline_http.py::test_baseline_outcome_through_http_sse_and_replay"),
    ("AI-restricted records are never named or sent",
     "apps/ai/tests/test_listing_workflow_http.py::test_content_a_model_may_not_read_is_counted_but_never_sent_or_named"),
    ("access revoked mid-run is re-checked",
     "apps/ai/tests/test_listing_workflow_http.py::test_a_paper_that_becomes_unreadable_after_the_preview_is_never_sent_or_shown_again"),
    ("cancel and retry of an owned run",
     "apps/ai/tests/test_durable_ask_http.py::OwnedRunLifecycleTests::test_cancel_commits_one_terminal_state_and_suppresses_the_late_answer"),
    ("a foreign run is refused",
     "apps/ai/tests/test_durable_ask_http.py::OwnedRunLifecycleTests::test_someone_elses_run_cannot_be_cancelled_or_retried"),
    ("a deleted conversation stays deleted",
     "apps/ai/tests/test_durable_ask_http.py::QueuedQuestionTests::test_a_conversation_deleted_mid_answer_stays_deleted"),
    ("the original deadline bounds every attempt",
     "apps/ai/tests/test_admission_http.py::test_every_vendor_call_is_bounded_by_the_original_deadline"),
    ("an exhausted campaign refuses paid work",
     "apps/ai/tests/test_admission_http.py::test_an_exhausted_campaign_says_busy_and_keeps_the_sources"),
)
SCENARIO_STATUS = "asserted by tests, not observed in this run"


class MilestoneSetError(ValueError):
    """The labels cannot be scored against: say which case and why."""


@dataclass(frozen=True)
class MilestoneSet:
    data: Mapping[str, Any]
    development: tuple[str, ...]
    held_out: tuple[str, ...]
    lock_verified: Optional[bool]

    @property
    def cases(self) -> list[dict]:
        return list(self.data["cases"])

    def population(self, name: str) -> frozenset[str]:
        return frozenset(self.data["populations"][name]["record_keys"])

    def labels(self, topic: str) -> Mapping[str, str]:
        return self.data["relevance"][topic]["labels"]


@dataclass
class Observation:
    """What one case's final response carried, with Record ids already mapped to keys."""

    case_id: str
    mode: Optional[str]
    listing: Optional[dict] = None
    #: From the original submission to the final response.
    latency_ms: Optional[int] = None


def held_out_digest(data: Mapping[str, Any], held_out: Sequence[str]) -> str:
    """SHA-256 over the held-out cases, their labels and the populations they rest on."""
    cases = {case["id"]: case for case in data["cases"]}
    pinned = []
    for case_id in sorted(held_out):
        case = {k: v for k, v in cases[case_id].items() if k != "baseline"}
        topic = case.get("topic")
        pinned.append({"case": case,
                       "relevance": data["relevance"].get(topic) if topic else None})
    blob = json.dumps({"populations": data["populations"], "held_out": pinned},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def parse_milestone_set(data: Mapping[str, Any]) -> MilestoneSet:
    ids = [case["id"] for case in data["cases"]]
    for case in data["cases"]:
        contract = case.get("contract", {})
        if case["family"] == METADATA:
            population = data["populations"][contract["population"]]["record_keys"]
            if contract["count"] != len(set(population)):
                raise MilestoneSetError(
                    f"{case['id']}: contract count {contract['count']} disagrees with its "
                    f"population of {len(set(population))} records")
        if case["family"] in (TOPIC_COUNT, LISTING) and case.get("topic") not in data["relevance"]:
            raise MilestoneSetError(f"{case['id']}: no relevance labels for its topic")

    split = data.get("split")
    if not split:
        return MilestoneSet(data, tuple(ids), (), None)
    development, held_out = tuple(split.get("development", ())), tuple(split.get("held_out", ()))
    for case_id in (*development, *held_out):
        if case_id not in ids:
            raise MilestoneSetError(f"{case_id}: split names a case the set does not hold")
    for case_id in set(development) & set(held_out):
        raise MilestoneSetError(f"{case_id}: in both development and held-out")
    lock_verified = None
    if held_out:
        if split.get("lock") != held_out_digest(data, held_out):
            raise MilestoneSetError("held-out lock does not match its cases and labels")
        lock_verified = True
    return MilestoneSet(data, development, held_out, lock_verified)


def _frac(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _sum_fracs(fracs: Sequence[dict]) -> dict:
    return _frac(sum(f["numerator"] for f in fracs), sum(f["denominator"] for f in fracs))


def _rows(observation: Optional[Observation]) -> list[dict]:
    if observation is None or not observation.listing:
        return []
    return list(observation.listing.get("candidates") or [])


def _metadata(cases, by_case) -> dict:
    exact, wrong, missing = 0, [], []
    for case in cases:
        observation = by_case.get(case["id"])
        block = (observation.listing or {}).get("count") if observation else None
        if not block:
            missing.append(case["id"])
            continue
        expected, reported = case["contract"]["count"], block.get("total")
        if reported == expected:
            exact += 1
        else:
            wrong.append({"case": case["id"], "expected": expected, "reported": reported})
    return {"denominator": len(cases), "exact": exact, "wrong": wrong, "missing": missing,
            "ground_truth": "the contract count, checked against its population's record keys"}


def _breaches(case_id, rows, visible, eligible) -> list[dict]:
    found = []
    for row in rows:
        key = row["record_key"]
        if key.startswith(UNLABELLED):
            continue
        if key not in visible:
            found.append({"case": case_id, "record_key": key,
                          "why": "not in the asker's metadata population"})
        elif key not in eligible and row["state"] in JUDGED:
            found.append({"case": case_id, "record_key": key, "why": "not AI-eligible but was judged"})
        elif key not in eligible and not row.get("restricted"):
            found.append({"case": case_id, "record_key": key, "why": "not AI-eligible but was named"})
    return found


def _screening(rows, labels) -> dict:
    tp = fp = fn = 0
    outside = Counter({"label_uncertain": 0, "unlabelled": 0, "screener_uncertain": 0,
                       "not_assessed": 0})
    for row in rows:
        label, state = labels.get(row["record_key"]), row["state"]
        if state == UNASSESSED:
            outside["not_assessed"] += 1
        elif state == UNCERTAIN:
            outside["screener_uncertain"] += 1
        elif label is None:
            outside["unlabelled"] += 1
        elif label not in ("relevant", "not_relevant"):
            outside["label_uncertain"] += 1
        elif state == INCLUDED:
            tp, fp = tp + (label == "relevant"), fp + (label == "not_relevant")
        elif state == EXCLUDED:
            fn += label == "relevant"
    return {"precision": _frac(tp, tp + fp), "recall": _frac(tp, tp + fn),
            "outside_denominators": dict(outside)}


def _recall(rows, owed) -> dict:
    found = {row["record_key"] for row in rows}
    return {**_frac(len(owed & found), len(owed)), "missed": sorted(owed - found)}


def _topics(milestone: MilestoneSet, cases, by_case) -> dict:
    visible, eligible = milestone.population(METADATA), milestone.population("ai_assessment_eligible")
    breaches, screening, recall, eligible_recall = [], {}, {}, {}
    selected = unassessed = restricted = 0
    inconclusive, inconsistent, relevant_included, missing = [], [], {}, []
    for case in cases:
        case_id, labels = case["id"], milestone.labels(case["topic"])
        observation = by_case.get(case_id)
        if observation is None:
            missing.append(case_id)
        rows = _rows(observation)
        breaches += _breaches(case_id, rows, visible, eligible)
        screening[case_id] = _screening(rows, labels)
        relevant = {key for key, label in labels.items() if label == "relevant"}
        recall[case_id] = _recall(rows, relevant & visible)
        eligible_recall[case_id] = _recall(rows, relevant & visible & eligible)
        selected += len(rows)
        unassessed += sum(row["state"] == UNASSESSED for row in rows)
        restricted += sum(bool(row.get("restricted")) for row in rows)
        if observation and (observation.listing or {}).get("completeness") == "inconclusive":
            inconclusive.append(case_id)
        if case["family"] == TOPIC_COUNT and observation:
            included = [row for row in rows if row["state"] == INCLUDED]
            reported = ((observation.listing or {}).get("topic_count") or {}).get("matches")
            if reported != len(included):
                inconsistent.append({"case": case_id, "reported": reported,
                                     "included_candidates": len(included)})
            relevant_included[case_id] = sum(labels.get(row["record_key"]) == "relevant"
                                             for row in included)
    return {
        "breaches": breaches,
        "screening": {
            "by_case": screening,
            "precision": _sum_fracs([s["precision"] for s in screening.values()]),
            "recall": _sum_fracs([s["recall"] for s in screening.values()]),
            "ground_truth": "human relevance labels over assessed candidates only",
        },
        "candidate_recall": {
            "by_case": recall,
            "ai_eligible_by_case": eligible_recall,
            "overall": _sum_fracs(list(recall.values())),
            "ground_truth": "every labelled-relevant Record in the asker's metadata population",
        },
        "coverage": {"selected": selected, "unassessed": unassessed, "restricted": restricted,
                     "unassessed_rate": _frac(unassessed, selected),
                     "inconclusive_cases": inconclusive, "missing": missing},
        "topic_counts": {"inconsistent": inconsistent,
                         "labelled_relevant_among_included": relevant_included},
    }


def _measures(milestone: MilestoneSet, cases, by_case) -> dict:
    return {"metadata_counts": _metadata([c for c in cases if c["family"] == METADATA], by_case),
            **_topics(milestone, [c for c in cases if c["family"] != METADATA], by_case)}


def _answer_quality(scored: Sequence[str], reviews: Sequence[Mapping]) -> dict:
    reviews = [r for r in reviews if r["case"] in scored]
    reviewers = list(dict.fromkeys(r["reviewer"] for r in reviews))
    if not reviewers:
        status = "not_reviewed"
    elif any(r.get("independent") for r in reviews) and len(reviewers) > 1:
        status = "independently_reviewed"
    else:
        status = "exploratory_single_reviewer"
    primary = [r for r in reviews if reviewers and r["reviewer"] == reviewers[0]]
    judged = [r for r in primary if r.get("answer_correct") is not None]

    def pooled(key):
        rows = [r[key] for r in primary if r.get(key)]
        return _frac(sum(r["supported"] for r in rows), sum(r["total"] for r in rows))

    disagreements = []
    for case_id in scored:
        verdicts = {r["reviewer"]: r.get("answer_correct") for r in reviews
                    if r["case"] == case_id and r.get("answer_correct") is not None}
        if len(set(verdicts.values())) > 1:
            disagreements.append({"case": case_id, "field": "answer_correct", "verdicts": verdicts})
    return {
        "status": status,
        "reviewers": reviewers,
        "primary_reviewer": reviewers[0] if reviewers else None,
        "rubrics": sorted({r["rubric"] for r in reviews if r.get("rubric")}),
        "reviewed_fraction": _frac(len({r["case"] for r in reviews}), len(scored)),
        "answer_correct": _frac(sum(bool(r["answer_correct"]) for r in judged), len(judged)),
        "claim_support": pooled("claims"),
        "citation_support": pooled("citations"),
        "disagreements": disagreements,
    }


def _judge(judge: Sequence[Mapping], reviews: Sequence[Mapping], primary: Optional[str]) -> dict:
    # Validated against an independent reviewer where one exists; otherwise
    # against the exploratory reviewer, and the report says which.
    labelled = [r for r in reviews if r.get("answer_correct") is not None]
    independent = [r for r in labelled if r.get("independent")]
    rows = independent or [r for r in labelled if r["reviewer"] == primary]
    against = "independent reviewer" if independent else "exploratory reviewer (not independent)"
    human = {r["case"]: r["answer_correct"] for r in rows}
    shared = [j for j in judge if j["case"] in human]
    if not judge:
        return {"supplied": False, "interpretable": False, "agreement": None,
                "why": "no judge scores supplied"}
    if not shared:
        return {"supplied": True, "interpretable": False, "agreement": None,
                "why": "no human labels on the judged cases, so judge scores are not interpreted"}
    agree = sum(j["answer_correct"] == human[j["case"]] for j in shared)
    return {"supplied": True, "interpretable": False, "agreement": _frac(agree, len(shared)),
            "against": against,
            "why": f"agreement measured on {len(shared)} human-labelled cases; the threshold "
                   "for interpreting judge scores is the owner's and is OPEN"}


def _standing(milestone: MilestoneSet, tier: str, answers: dict) -> dict:
    why = []
    if tier != CIT_U:
        why.append(f"{tier} data is not CIT-U reliability evidence")
    if not milestone.held_out:
        why.append("no held-out questions: every case is development")
    if answers["status"] != "independently_reviewed":
        why.append("no independent second review")
    return {
        "evidence": "exploratory_inconclusive" if why else "eligible_for_owner_review",
        "why": "; ".join(why) or "held-out, CIT-U and independently reviewed; owner gates still apply",
        "institutional_quality_claim": not why,
    }


def score(milestone: MilestoneSet, observations: Sequence[Observation], *, tier: str,
          reviews: Sequence[Mapping] = (), judge: Sequence[Mapping] = ()) -> dict:
    if tier not in TIERS:
        raise MilestoneSetError(f"unknown tier {tier!r}")
    by_case = {o.case_id: o for o in observations}
    scored = [c for c in milestone.cases if c["family"] in MILESTONE_FAMILIES]
    scored_ids = [c["id"] for c in scored]
    held_out = [c for c in scored if c["id"] in milestone.held_out]
    answers = _answer_quality(scored_ids, reviews)
    latencies = {cid: by_case[cid].latency_ms for cid in scored_ids
                 if cid in by_case and by_case[cid].latency_ms is not None}
    usage = Counter()
    unreported = []
    for cid in scored_ids:
        observed = ((by_case.get(cid) and by_case[cid].listing) or {}).get("observed")
        if not observed:
            unreported.append(cid)
            continue
        for key in ("model_calls", "prompt_tokens_estimated", "cache_hits", "cache_misses"):
            usage[key] += observed.get(key, 0)
    return {
        "tier": tier,
        "scope": {"scored_cases": scored_ids,
                  "out_of_milestone": {c["id"]: c["family"] for c in milestone.cases
                                       if c["family"] not in MILESTONE_FAMILIES}},
        "split": {"development": list(milestone.development), "held_out": list(milestone.held_out),
                  "lock_verified": milestone.lock_verified},
        **_measures(milestone, scored, by_case),
        # Held-out figures on their own, never pooled into a development figure.
        "held_out": _measures(milestone, held_out, by_case) if held_out else None,
        "answer_quality": answers,
        "judge": _judge(judge, reviews, answers["primary_reviewer"]),
        "latency_ms": {"n": len(latencies), "p50": percentile(list(latencies.values()), 0.5),
                       "p95": percentile(list(latencies.values()), 0.95),
                       "missing": [cid for cid in scored_ids if cid not in latencies]},
        "usage": {**{k: usage.get(k, 0) for k in ("model_calls", "prompt_tokens_estimated",
                                                   "cache_hits", "cache_misses")},
                  "unreported": unreported},
        "scenarios": [{"scenario": name, "test": test, "status": SCENARIO_STATUS}
                      for name, test in SCENARIOS],
        "standing": _standing(milestone, tier, answers),
    }
