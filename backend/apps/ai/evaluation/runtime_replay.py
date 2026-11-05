"""Collect development conversations through the dedicated runtime (IR-740).

The collector owns no retrieval, permission or answer logic. It submits each
question to the runtime's authenticated run route, follows the run's status
until it ends, and reopens the saved Conversation: the submit / progress /
reopen seam a reader uses. What it writes is the same run-file row IR-606
writes, so review packets, human review and scoring need no second format.

The runtime assigns the Conversation on the first question, and a later
question names it and the revision the reader saw.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Mapping

import httpx

from .replay import NOT_TRACED, STOP_OUTCOMES

RUNTIME_PREFIX = "/api/v1/ai/runtime"
ACTIVE = frozenset({"queued", "running"})
#: Seconds the collector waits for one run before it cancels it.
DEFAULT_DEADLINE_SECONDS = 660.0
DEFAULT_POLL_SECONDS = 1.0
UNAVAILABLE_NOTE = "This answer is unavailable because its sources changed"


class RuntimeSeam:
    """The runtime's routes behind one client.

    By default the reader's own edge: ``/api/v1/ai/runtime/*`` with the evaluating
    user's bearer token on the client, where the edge fetches the grant and fixes
    the protocol. A direct client (the gateway in a test) passes ``prefix`` and
    ``headers``, a callable returning the grant and protocol headers.
    """

    def __init__(self, client, *, prefix: str = RUNTIME_PREFIX,
                 headers: Callable[[], Mapping] = lambda: {}):
        self.client, self.prefix, self.headers = client, prefix, headers

    def submit(self, body: Mapping, key: str):
        return self.client.post(f"{self.prefix}/runs", json=dict(body),
                                headers={**self.headers(), "Idempotency-Key": key})

    def status(self, run_id):
        return self.client.get(f"{self.prefix}/runs/{run_id}", headers=self.headers() or None)

    def cancel(self, run_id):
        return self.client.post(f"{self.prefix}/runs/{run_id}/cancel",
                                headers=self.headers() or None)

    def reopen(self, conversation_id):
        return self.client.get(f"{self.prefix}/conversations/{conversation_id}",
                               headers=self.headers() or None)


def _body(response) -> dict:
    try:
        return response.json() or {}
    except (ValueError, AttributeError):
        return {}


def _public_answer(turn: Mapping) -> dict:
    return {
        "answer": turn.get("answer"), "kind": turn.get("kind"),
        "citations": [{"marker": None, "record_id": c.get("record_id"), "record_title": None,
                       "page": c.get("page"), "text": c.get("quote")}
                      for c in turn.get("citations") or ()],
        "facts": turn.get("facts") or [],
    }


def _capped(limits: Mapping, attempts: int, cost: float) -> bool:
    return bool(
        (limits.get("case_attempts") is not None and
         attempts + limits.get("turn_max_attempts", 1) > limits["case_attempts"]) or
        (limits.get("case_cost_usd") is not None and
         cost + limits.get("turn_max_cost_usd", 0) > limits["case_cost_usd"]))


def _follow(seam, run: dict, *, clock, sleep, deadline_seconds, poll_seconds):
    """The run's observed public states and how it ended."""
    seen = [run]
    started = clock()
    while run["state"] in ACTIVE:
        if clock() - started >= deadline_seconds:
            seam.cancel(run["id"])
            return seen, "timeout"
        polled = seam.status(run["id"])
        if polled.status_code != 200:
            return seen, "failure"
        run = _body(polled)
        seen.append(run)
        if run["state"] in ACTIVE:
            sleep(poll_seconds)
    if run["state"] == "completed":
        return seen, "completed"
    return seen, {"cancelled": "cancellation", "expired": "timeout"}.get(run["state"], "failure")


def collect_case_runtime(seam, case: Mapping, *, attempts=None, limits: Mapping | None = None,
                         diagnostics=None, clock=time.monotonic, sleep=time.sleep,
                         faults=None, depth: str = "deep",
                         deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
                         poll_seconds: float = DEFAULT_POLL_SECONDS) -> dict:
    """One case as a runtime Conversation: ordered turns, then a final reopen.

    ``diagnostics`` and ``faults`` belong to the Django path and are ignored.
    ``attempts.for_run(run_id)`` supplies the runtime ledger's physical attempts.
    """
    limits = limits or {}
    conversation_id, revision = None, None
    recorded, total_attempts, total_cost = [], 0, 0.0
    start = clock()
    transcript: list = []
    for number, source in enumerate(case["turns"], 1):
        if _capped(limits, total_attempts, total_cost):
            recorded.append({"number": number, "question": source["user"],
                             "outcome": "cap_stop", "public_answer": None,
                             "citation_record_ids": [], "source_ids": [], "saved_turn": None,
                             "reopened_transcript": None, "latency_ms": 0,
                             "physical_attempts": [], "usage_status": "missing"})
            break
        body = {"question": source["user"], "depth": depth}
        if conversation_id:
            body.update(conversation_id=conversation_id, base_revision=revision)
        turn_start = clock()
        answer, saved, events, run_id, outcome = None, None, [], None, "failure"
        try:
            submitted = seam.submit(body, f"eval-{uuid.uuid4().hex}")
            if submitted.status_code == 503 and _body(submitted).get("status") == "busy":
                outcome = "cap_stop"
            elif submitted.status_code in (200, 201):
                run = _body(submitted)
                run_id = run["id"]
                conversation_id = conversation_id or run["conversation_id"]
                seen, ended = _follow(seam, run, clock=clock, sleep=sleep,
                                      deadline_seconds=deadline_seconds,
                                      poll_seconds=poll_seconds)
                events = [{"name": "run", "data": item} for item in seen]
                outcome = ended
        except (TimeoutError, httpx.TimeoutException):
            outcome = "timeout"
        except (OSError, ConnectionError, httpx.TransportError):
            outcome = "failure"
        except KeyboardInterrupt:
            outcome = "cancellation"
        elapsed = round((clock() - turn_start) * 1000)
        physical = attempts.for_run(run_id) if attempts and run_id else []
        unsettled = any(row["state"] == "open" for row in physical)
        total_attempts += len(physical)
        total_cost += sum(row["cost_usd"] for row in physical)
        reopened_turns = None
        if conversation_id and run_id and outcome in ("completed", "failure", "timeout",
                                                      "cancellation"):
            reopened = seam.reopen(conversation_id)
            if reopened.status_code != 200:
                raise ValueError(f"conversation reopen failed with HTTP {reopened.status_code}")
            snapshot = _body(reopened)
            transcript, revision = snapshot.get("turns", []), snapshot.get("revision")
            reopened_turns = transcript
            saved = next((t for t in transcript if t.get("run_id") == run_id), None)
        if outcome == "completed":
            if saved is None or not (saved.get("answer") or "").strip():
                outcome = "empty"
            elif (saved["answer"].startswith(UNAVAILABLE_NOTE)
                    or not (seen[-1].get("sources_available", True))):
                outcome = "failure"
            else:
                answer, outcome = _public_answer(saved), "answered"
        if unsettled:
            outcome = "failure"
        citations = (answer or {}).get("citations") or []
        recorded.append({
            "number": number, "question": source["user"], "outcome": outcome,
            "public_answer": answer, "public_events": events,
            "citation_record_ids": [c["record_id"] for c in citations
                                    if isinstance(c.get("record_id"), int)],
            "source_ids": [], "saved_turn": saved, "reopened_transcript": reopened_turns,
            "latency_ms": elapsed, "physical_attempts": physical,
            "cost_final": not unsettled,
            "usage_status": ("reported" if physical and all(p["usage_reported"] for p in physical)
                             else "missing"),
            "diagnostics": {"stage": NOT_TRACED},
            **({"runtime_run_id": run_id} if run_id else {}),
        })
        if outcome in STOP_OUTCOMES:
            break
    if conversation_id:
        final = seam.reopen(conversation_id)
        if final.status_code != 200:
            raise ValueError(f"final reopen failed with HTTP {final.status_code}")
        final_turns = _body(final).get("turns", [])
    else:
        final_turns = []
    complete = len(recorded) == len(case["turns"]) and all(
        t["outcome"] == "answered" for t in recorded)
    return {
        "id": case["id"], "family": case["family"], "split": case["split"],
        "conversation_id": conversation_id, "status": "complete" if complete else "incomplete",
        "turns": recorded, "reopened_transcript": final_turns,
        "latency_ms": round((clock() - start) * 1000), "cost": total_cost,
        "physical_attempts": total_attempts,
        "cost_final": all(t.get("cost_final", True) for t in recorded),
    }

