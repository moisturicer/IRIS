"""IR-740: the dedicated runtime's engine identity and effective-condition comparison. Pure."""

import pytest

from apps.ai.evaluation.engines import (
    RUNTIME_ARM,
    RUNTIME_ENGINE,
    RUNTIME_SCHEMA,
    RUNTIME_TRANSPORT,
    effective_limits,
    effective_models,
    mismatches,
    normalize_model,
    runtime_identity,
)


def manifest(**over):
    base = {"corpus_snapshot_digest": "c0ffee", "model_ids": {"answer": "m1"},
            "data_policy": "no-training", "limits": {"case_cost_usd": 1.0},
            "set_digests": {"development": "d", "held_out": "h"}, "rubric_version": 1,
            "cache_state": "cold", "physical_attempts": []}
    base.update(over)
    return base


def test_the_runtime_has_its_own_engine_transport_and_schema_identity():
    assert RUNTIME_ENGINE == "ai-runtime-1"
    assert RUNTIME_ENGINE not in ("controller-v1", "lanes-v1")
    assert (RUNTIME_ARM, RUNTIME_TRANSPORT, RUNTIME_SCHEMA) == (
        "runtime", "runs-reader-1", "runtime-rows-1")
    assert runtime_identity() == {"engine": "ai-runtime-1", "transport": "runs-reader-1",
                                  "schema": "runtime-rows-1"}


def test_model_names_are_compared_after_trimming_and_case_folding():
    assert normalize_model("  Vendor/Model-A ") == "vendor/model-a"


def test_effective_models_are_the_ones_that_actually_answered_not_the_configured_name():
    declared = manifest(model_ids={"plan": "Alias", "answer": "alias"})
    assert effective_models(declared) == ["alias"]
    served = manifest(model_ids={"answer": "alias"}, physical_attempts=[
        {"operation": "llm", "model": "Fallback-1"}, {"operation": "llm", "model": "fallback-1"},
        {"operation": "embed", "model": "voyage"}])
    assert effective_models(served) == ["fallback-1"]


def test_identity_only_limit_keys_are_not_a_budget():
    assert effective_limits({"case_cost_usd": 1.0, "campaign_key": "k1"}) == {"case_cost_usd": 1.0}
    assert effective_limits(None) == {}


def test_matched_manifests_have_no_mismatch_even_with_different_model_key_shapes():
    controller = manifest(model_ids={"plan": "m1", "answer": "m1"},
                          limits={"case_cost_usd": 1.0, "campaign_key": "a"})
    runtime = manifest(model_ids={"agent": "M1"}, limits={"case_cost_usd": 1.0, "campaign_key": "b"})
    assert mismatches([("controller", controller), ("runtime", runtime)], "architecture") == []


@pytest.mark.parametrize("key, value, named", [
    ("corpus_snapshot_digest", "other", "corpus_snapshot_digest"),
    ("model_ids", {"agent": "m2"}, "model_ids"),
    ("data_policy", "retains", "data_policy"),
    ("limits", {"case_cost_usd": 5.0}, "limits"),
    ("cache_state", "warm", "cache_state"),
    ("set_digests", {"development": "x", "held_out": "h"}, "set_digests"),
    ("rubric_version", 2, "rubric_version")])
def test_an_architecture_comparison_names_every_unequal_condition(key, value, named):
    found = mismatches([("controller", manifest()), ("runtime", manifest(**{key: value}))],
                       "architecture")
    assert len(found) == 1 and named in found[0] and "runtime" in found[0]


def test_a_model_comparison_lets_only_the_models_differ():
    a, b = manifest(), manifest(model_ids={"answer": "m2"})
    assert mismatches([("m1", a), ("m2", b)], "model") == []
    assert mismatches([("m1", a), ("m2", manifest(model_ids={"answer": "m2"}, cache_state="warm"))],
                      "model") != []


def test_a_capability_comparison_needs_a_larger_allowance_and_nothing_else_different():
    base, bigger = manifest(), manifest(limits={"case_cost_usd": 5.0})
    assert mismatches([("base", base), ("bigger", bigger)], "capability") == []
    same = mismatches([("base", base), ("again", manifest())], "capability")
    assert len(same) == 1 and "architecture comparison" in same[0]
    other_model = mismatches([("base", base), ("bigger", manifest(
        limits={"case_cost_usd": 5.0}, model_ids={"answer": "m2"}))], "capability")
    assert len(other_model) == 1 and "model_ids" in other_model[0]


def test_missing_cache_state_in_every_manifest_is_the_old_artifact_shape_and_still_compares():
    old = [("a", {k: v for k, v in manifest().items() if k != "cache_state"}),
           ("b", {k: v for k, v in manifest().items() if k != "cache_state"})]
    assert mismatches(old, "architecture") == []


def test_repetitions_under_one_capability_label_share_an_allowance():
    base, bigger = manifest(), manifest(limits={"case_cost_usd": 5.0})
    drift = mismatches([("larger", bigger), ("larger", manifest(limits={"case_cost_usd": 9.0})),
                        ("base", base)], "capability")
    assert drift == ["larger: repetitions ran different allowances (limits)"]


def test_repetitions_may_mix_cold_and_warm_but_every_label_must_run_the_same_states():
    cold, warm = manifest(), manifest(cache_state="warm")
    mixed = [("a", cold), ("a", warm), ("b", warm), ("b", cold)]
    assert mismatches(mixed, "architecture") == []
    lopsided = mismatches([("a", cold), ("a", warm), ("b", cold)], "architecture")
    assert lopsided == ["b: cache_state differs from a; conditions are not equal"]
