"""IR-542: the fixed-workflow pilot's fixtures are internally consistent.

No database and no Django models: these check the files a reviewer reads,
so a hand edit that breaks a population, a label or the pinned proxy set
fails here rather than in a later workflow ticket.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
BASELINE = Path(__file__).resolve().parents[1] / "fixtures" / "fixed_workflow_baseline.json"
PROXY = ROOT / "docs" / "evaluation" / "proxy_starter.json"
AUDIT = ROOT / "docs" / "evaluation" / "fixed-workflow-pilot" / "proxy_audit.json"

FAMILIES = {
    "metadata_count", "topic_match_count", "presence_listing", "paper_chat_scope",
    "passage_citation", "failure_generation_unavailable", "failure_screening_unavailable",
}
LABELS = {"relevant", "not_relevant", "uncertain"}


def _baseline():
    return json.loads(BASELINE.read_text())


def _records():
    return {r["key"]: r for r in _baseline()["records"]}


def test_record_keys_and_titles_are_distinct():
    records = _baseline()["records"]
    assert len({r["key"] for r in records}) == len(records)
    assert len({r["title"] for r in records}) == len(records)


def test_metadata_population_is_every_published_record_the_asker_can_see():
    records = _records()
    population = _baseline()["populations"]["metadata_count"]["record_keys"]
    assert sorted(population) == sorted(
        key for key, r in records.items() if r["state"] == "published" and r["owner"] is None
    )


def test_ai_eligibility_is_a_separate_narrower_population():
    """A disclosure-refused Record still counts in metadata; AI may not read it."""
    populations = _baseline()["populations"]
    metadata = set(populations["metadata_count"]["record_keys"])
    eligible = set(populations["ai_assessment_eligible"]["record_keys"])
    records = _records()
    assert eligible < metadata
    assert eligible == {k for k in metadata if records[k]["disclosure"] == "permitted"}


def test_relevance_labels_cover_every_record_with_a_known_label():
    records = _records()
    for topic in _baseline()["relevance"].values():
        assert set(topic["labels"]) == set(records)
        assert set(topic["labels"].values()) <= LABELS


def test_every_case_names_a_known_family_and_records():
    baseline = _baseline()
    records = _records()
    ids = [case["id"] for case in baseline["cases"]]
    assert len(set(ids)) == len(ids)
    for case in baseline["cases"]:
        assert case["family"] in FAMILIES
        assert case["baseline"], case["id"]
        for value in _record_references(case):
            assert value in records, (case["id"], value)


def _record_references(node):
    if isinstance(node, dict):
        for name, value in node.items():
            if name in ("record", "scope_record") and isinstance(value, str):
                yield value
            elif name.endswith("_keys") or name.endswith("_within") or name == "never_mentions":
                yield from value
            else:
                yield from _record_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from _record_references(item)


def test_topic_count_contract_partitions_the_metadata_population():
    """Matches, exclusions, uncertainty and unassessed are disjoint and whole."""
    baseline = _baseline()
    metadata = set(baseline["populations"]["metadata_count"]["record_keys"])
    eligible = set(baseline["populations"]["ai_assessment_eligible"]["record_keys"])
    case = next(c for c in baseline["cases"] if c["family"] == "topic_match_count")
    contract = case["contract"]
    parts = [set(contract[k]) for k in
             ("assessed_match_keys", "excluded_keys", "uncertain_keys", "unassessed_keys")]
    assert sum(len(p) for p in parts) == len(set().union(*parts)) == len(metadata)
    assert set().union(*parts) == metadata
    assert set(contract["unassessed_keys"]) == metadata - eligible
    labels = baseline["relevance"][case["topic"]]["labels"]
    assert {k for k in eligible if labels[k] == "relevant"} == set(contract["assessed_match_keys"])
    assert contract["candidate_limit"] == 20


def test_every_citation_label_quotes_its_records_text():
    records = _records()
    for case in _baseline()["cases"]:
        labels = list(case["contract"].get("citations", ()))
        labels += [run["expect"]["citation"] for run in case["baseline"]
                   if "citation" in run["expect"]]
        for label in labels:
            assert label["quote"] in records[label["record"]]["text"]
            assert label["page"] == 4  # the one page the corpus builder writes


def test_the_proxy_audit_pins_the_proxy_set_it_audited():
    audit = json.loads(AUDIT.read_text())
    assert audit["source"]["sha256"] == hashlib.sha256(PROXY.read_bytes()).hexdigest(), (
        "docs/evaluation/proxy_starter.json changed after IR-542 pinned it; "
        "re-audit it and update proxy_audit.json deliberately"
    )


def test_the_proxy_audit_assigns_every_question_to_exactly_one_split():
    audit = json.loads(AUDIT.read_text())
    ids = [q["id"] for q in json.loads(PROXY.read_text())["questions"]]
    development, held_out = audit["split"]["development"], audit["split"]["held_out"]
    assert sorted(development + held_out) == sorted(ids)
    assert not set(development) & set(held_out)
    assert audit["question_count"] == len(ids)
    for group in audit["adaptable_candidates"].values():
        assert set(group["question_ids"]) <= set(ids)
