"""Collect development conversations through the authenticated reader protocol.

The collector owns no retrieval or permission logic. Every answer and reopened
Turn is read from the same endpoints a reader uses. The optional admission
ledger supplies private physical-attempt diagnostics in a dedicated campaign.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Mapping

import httpx

from apps.ai.controller.versions import (ANSWER_PROMPT_VERSION, CONTROLLER_ENGINE,
                                         PLAN_PROMPT_VERSION, PROTOCOL_VERSION)
from apps.ai.public import PUBLIC_PROTOCOL

from .http_driver import parse_sse

CONVERSATIONS = "/api/v1/ai/conversations/"
ASK_STREAM = "/api/v1/ai/ask/stream/"
SCHEMA_VERSION = 1
STOP_OUTCOMES = frozenset({"timeout", "cancellation", "cap_stop", "failure", "empty"})


def _body(response) -> dict:
    try:
        return response.json()
    except (ValueError, AttributeError):
        return {}


def _events(response) -> list[tuple[str, dict]]:
    if hasattr(response, "streaming_content"):
        raw = b"".join(response.streaming_content).decode("utf-8")
    else:
        raw = response.text
    return parse_sse(raw)


def _outcome(status: int, events: list[tuple[str, dict]]) -> tuple[str, dict | None]:
    if status == 503:
        return "cap_stop", None
    if status != 200:
        return "failure", None
    for name, data in reversed(events):
        if name == "done":
            if data.get("mode") == "unavailable":
                return "failure", data
            if not (data.get("answer") or data.get("message")):
                return "empty", data
            return "answered", data
        if name == "run_cancelled":
            return "cancellation", None
        if name == "run_failed":
            return ("timeout" if data.get("reason") == "deadline_exceeded" else "failure"), None
    return "failure", None


def _ids(rows: list[dict], key: str) -> list[int]:
    return [row[key] for row in rows if isinstance(row, dict) and isinstance(row.get(key), int)]


def collect_case(reader, case: Mapping, *, attempts=None, limits: Mapping | None = None,
                 clock=time.monotonic) -> dict:
    """A fresh saved Conversation, then ordered turns and a final public reopen."""
    limits = limits or {}
    created = reader.post(CONVERSATIONS, {"title": f"Evaluation {case['id']}"})
    if created.status_code != 201:
        raise ValueError(f"conversation creation failed with HTTP {created.status_code}")
    conversation_id = _body(created)["id"]
    detail_path = f"{CONVERSATIONS}{conversation_id}/"
    recorded = []
    total_attempts = 0
    total_cost = 0.0
    start = clock()
    previous_turns: set[int] = set()
    for number, source in enumerate(case["turns"], 1):
        if ((limits.get("case_attempts") is not None and
             total_attempts + limits.get("turn_max_attempts", 1) > limits["case_attempts"]) or
            (limits.get("case_cost_usd") is not None and
             total_cost + limits.get("turn_max_cost_usd", 0) > limits["case_cost_usd"])):
            recorded.append({"number": number, "question": source["user"],
                             "outcome": "cap_stop", "public_answer": None,
                             "citation_record_ids": [], "source_ids": [], "saved_turn": None,
                             "reopened_transcript": None, "latency_ms": 0,
                             "physical_attempts": [], "usage_status": "missing"})
            break
        cursor = attempts.snapshot() if attempts else None
        turn_start = clock()
        answer = None
        try:
            response = reader.post(ASK_STREAM, {"question": source["user"],
                                                "conversation_id": conversation_id,
                                                "protocol": PUBLIC_PROTOCOL})
            events = _events(response) if response.status_code == 200 else []
            outcome, answer = _outcome(response.status_code, events)
        except (TimeoutError, httpx.TimeoutException):
            outcome = "timeout"
        except (OSError, ConnectionError, httpx.TransportError, ValueError):
            outcome = "failure"
        except KeyboardInterrupt:
            outcome = "cancellation"
        elapsed = round((clock() - turn_start) * 1000)
        physical = attempts.since(cursor) if attempts else []
        unsettled = any(row["state"] == "open" for row in physical)
        if unsettled:
            outcome = "failure"
        total_attempts += len(physical)
        total_cost += sum(row["cost_usd"] for row in physical)
        reopened = reader.get(detail_path)
        if reopened.status_code != 200:
            raise ValueError(f"conversation reopen failed with HTTP {reopened.status_code}")
        transcript = _body(reopened).get("turns", [])
        added = [turn for turn in transcript if turn.get("id") not in previous_turns]
        previous_turns.update(turn["id"] for turn in added)
        saved = added[-1] if added else None
        citations = (answer or {}).get("citations") or []
        sources = (answer or {}).get("sources") or []
        recorded.append({
            "number": number, "question": source["user"], "outcome": outcome,
            "public_answer": answer, "citation_record_ids": _ids(citations, "record_id"),
            "source_ids": _ids(sources, "id"), "saved_turn": saved,
            "reopened_transcript": transcript, "latency_ms": elapsed,
            "physical_attempts": physical, "cost_final": not unsettled,
            "usage_status": ("reported" if physical and all(p["usage_reported"] for p in physical)
                             else "missing"),
        })
        if outcome in STOP_OUTCOMES:
            break
    final = reader.get(detail_path)
    if final.status_code != 200:
        raise ValueError(f"final reopen failed with HTTP {final.status_code}")
    complete = len(recorded) == len(case["turns"]) and all(
        turn["outcome"] == "answered" for turn in recorded)
    return {
        "id": case["id"], "family": case["family"], "split": case["split"],
        "conversation_id": conversation_id, "status": "complete" if complete else "incomplete",
        "turns": recorded, "reopened_transcript": _body(final).get("turns", []),
        "latency_ms": round((clock() - start) * 1000), "cost": total_cost,
        "physical_attempts": total_attempts,
        "cost_final": all(turn.get("cost_final", True) for turn in recorded),
    }


def collect_run(reader, cases: list[Mapping], *, set_id: str, set_digests: Mapping,
                corpus: Mapping, model_ids: Mapping, limits: Mapping, data_policy: str,
                cache: str, attempts=None, approval_id=None, model_profiles=None,
                partition_method=None, retrieval=None, pricing=None,
                arm="controller", engine_version=CONTROLLER_ENGINE,
                clock=time.monotonic) -> dict:
    """One scorer-readable run; only supplied, approved manifest fields enter it."""
    run_id = str(uuid.uuid4())
    rows = []
    for case in cases:
        if case["split"] != "development":
            raise ValueError("collection is restricted to the development split")
        try:
            row = collect_case(reader, case, attempts=attempts, limits=limits, clock=clock)
        except (TimeoutError, httpx.TimeoutException, KeyboardInterrupt) as exc:
            row = _unfinished(case, "cancellation" if isinstance(exc, KeyboardInterrupt) else "timeout")
        except (OSError, ConnectionError, httpx.TransportError, ValueError):
            row = _unfinished(case, "failure")
        row["cache"] = cache
        rows.append(row)
        if row["status"] != "complete":
            break
    physical = [attempt for row in rows for turn in row["turns"]
                for attempt in turn["physical_attempts"]]
    manifest = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "set_id": set_id, "set_digests": dict(set_digests),
        "set_sha256": corpus.get("set_sha256"),
        "partition_method": partition_method,
        "corpus_snapshot_digest": corpus["paper_set_sha256"],
        "corpus_snapshot_id": corpus["snapshot_id"],
        "data_policy": data_policy, "permission_policy": corpus.get("authorization_policy_version"),
        "model_ids": dict(model_ids), "model_profiles": model_profiles or {},
        "retrieval": retrieval or {}, "limits": dict(limits),
        "pricing_per_million_tokens_usd": pricing or {},
        "controller_version": CONTROLLER_ENGINE if engine_version == CONTROLLER_ENGINE else None,
        "engine_version": engine_version,
        "controller_protocol_version": (PROTOCOL_VERSION if engine_version == CONTROLLER_ENGINE
                                        else None),
        "protocol_version": PUBLIC_PROTOCOL,
        "prompt_versions": ({"plan": PLAN_PROMPT_VERSION, "answer": ANSWER_PROMPT_VERSION}
                            if engine_version == CONTROLLER_ENGINE else {}),
        "cache_state": cache, "attempted_physical_calls": len(physical),
        "physical_attempts": physical, "campaign_approval_id": approval_id,
        "rubric_version": 1,
    }
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "arm": arm,
            "providers": "real" if attempts else "fake", "manifest": manifest,
            "conversations": rows, "capacity_fit": False}


def _unfinished(case: Mapping, outcome: str) -> dict:
    return {
        "id": case["id"], "family": case["family"], "split": case["split"],
        "conversation_id": None, "status": "incomplete", "turns": [{
            "number": 1, "question": case["turns"][0]["user"], "outcome": outcome,
            "public_answer": None, "citation_record_ids": [], "source_ids": [],
            "saved_turn": None, "reopened_transcript": None, "latency_ms": None,
            "physical_attempts": [], "usage_status": "missing",
        }], "reopened_transcript": [], "latency_ms": None,
        "cost": 0.0, "physical_attempts": 0, "cost_final": True,
    }


def git_commit() -> str:
    from .runfile import git_commit as current_commit

    return current_commit()


class CampaignAttempts:
    """Private accounting cursor for one dedicated admission campaign.

    Collection is sequential. The campaign must be dedicated to this run;
    otherwise unrelated work could enter the cursor interval and attribution
    would be invalid.
    """

    def __init__(self, campaign_key: str):
        if not campaign_key:
            raise ValueError("a dedicated admission campaign is required")
        self.campaign_key = campaign_key

    def _query(self):
        from apps.ai.models import ProviderReservation

        return ProviderReservation.objects.using("admission").filter(
            campaign__key=self.campaign_key)

    def snapshot(self) -> int:
        from django.db.models import Max

        return self._query().aggregate(value=Max("pk"))["value"] or 0

    def since(self, cursor: int) -> list[dict]:
        rows = self._query().filter(pk__gt=cursor).order_by("pk")
        return [{
            "id": row.pk, "run_key": row.run_key, "work_key": row.work_key,
            "operation": row.operation, "model": row.model, "state": row.state,
            "sent": row.sent, "usage_reported": row.usage_reported,
            "input_tokens": row.charge_input_tokens,
            "output_tokens": row.charge_output_tokens,
            "cost_usd": row.charge_cost_micros / 1_000_000,
            "price_basis": ("admission_charge_basis_not_persisted" if row.usage_reported
                            else "reservation"),
        } for row in rows if row.charge_attempts]
