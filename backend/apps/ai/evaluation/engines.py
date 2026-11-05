"""Engine identities and effective evaluation conditions (IR-740). Pure.

The dedicated AI runtime (ADR-049) is its own engine. It is never recorded as
``controller-v1``, and it is not a reader setting: nothing here chooses which
path answers a reader.

Conditions are compared as they were in effect, not as configured: the model
that answered (from the physical attempts when there are any), the allowance
without its identity-only keys, the cache state and the question, corpus and
policy digests.
"""

from __future__ import annotations

from typing import Mapping, Sequence

RUNTIME_ARM = "runtime"
RUNTIME_ENGINE = "ai-runtime-1"
#: `ai.runs.public.PROTOCOL`, the wire protocol the reader and this collector speak.
RUNTIME_TRANSPORT = "runs-reader-1"
#: The run-file row shape this collector writes for the runtime.
RUNTIME_SCHEMA = "runtime-rows-1"

#: Limit keys that name a campaign, not an allowance.
IDENTITY_LIMIT_KEYS = frozenset({"campaign_key"})
SHARED_KEYS = ("corpus_snapshot_digest", "data_policy", "set_digests", "rubric_version",
               "cache_state")


def runtime_identity() -> dict:
    return {"engine": RUNTIME_ENGINE, "transport": RUNTIME_TRANSPORT, "schema": RUNTIME_SCHEMA}


def normalize_model(name) -> str:
    return str(name).strip().casefold()


def effective_models(manifest: Mapping) -> list[str]:
    """The language models that answered; the configured ones when none is recorded."""
    served = {normalize_model(a["model"]) for a in manifest.get("physical_attempts") or ()
              if a.get("operation") == "llm" and a.get("model")}
    if served:
        return sorted(served)
    declared = manifest.get("model_ids") or {}
    values = declared.values() if isinstance(declared, Mapping) else [declared]
    return sorted({normalize_model(v) for v in values if v})


def effective_limits(limits: Mapping | None) -> dict:
    return {k: v for k, v in (limits or {}).items() if k not in IDENTITY_LIMIT_KEYS}


def _shared(manifest: Mapping, key: str):
    return manifest.get(key)


def mismatches(labelled: Sequence[tuple[str, Mapping]], mode: str) -> list[str]:
    """Why these manifests are not comparable under ``mode``; empty when they are.

    ``architecture``: everything equal. ``model``: only the models differ.
    ``capability``: only the allowance differs, and it must.
    """
    first_label, first = labelled[0]
    problems = []
    for label, manifest in labelled[1:]:
        for key in SHARED_KEYS:
            if _shared(manifest, key) != _shared(first, key):
                problems.append(f"{label}: {key} differs from {first_label}; "
                                "conditions are not equal")
        if mode != "model" and effective_models(manifest) != effective_models(first):
            problems.append(f"{label}: model_ids differ from {first_label} "
                            f"({effective_models(manifest)} vs {effective_models(first)}); "
                            "conditions are not equal")
        if mode != "capability" and (effective_limits(manifest.get("limits"))
                                     != effective_limits(first.get("limits"))):
            problems.append(f"{label}: limits differ from {first_label}; "
                            "conditions are not equal")
    if mode == "capability" and not problems and all(
            effective_limits(m.get("limits")) == effective_limits(first.get("limits"))
            for _, m in labelled[1:]):
        problems.append("equal allowances (limits) make this an architecture comparison, "
                        "not a capability report")
    return problems
