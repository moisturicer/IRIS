"""IR-740: collecting the dedicated runtime through its submit / progress / reopen seam.

Pure: a scripted seam stands in for the authenticated routes, so these prove the
collector's contract (row shape, outcomes, usage, caps, identity) and nothing about
a model. `test_ir740_runtime_collection_db.py` drives the real routes.
"""

import itertools

import pytest

from apps.ai.evaluation.engines import RUNTIME_ENGINE, runtime_identity
from apps.ai.evaluation.replay import collect_run
from apps.ai.evaluation.review_packets import build_packets
from apps.ai.evaluation.runtime_replay import RuntimeSeam, collect_case_runtime

from .test_conversations import conv, make_set

CID = "11111111-1111-4111-8111-111111111111"


class Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def run_view(rid, state="completed", **over):
    return {"protocol": "runs-reader-1", "id": rid, "conversation_id": CID, "state": state,
            "question": "q", "base_revision": 0, "version": 3, "turn_id": 1 if state == "completed" else None,
            "depth": "deep", "awaiting_reader": False, "created_at": "t", "finished_at": "t",
            "kind": "ask", "plan": None, "context": None, "compaction": None,
            "sources_available": True, "capabilities": {"manual_compaction": False}, **over}


def turn_view(rid, ordinal=1, answer="Both studies sample water [1].", kind="answer",
              citations=({"record_id": 7, "page": 3, "quote": "gauges", "revision": "1:e"},
                         {"record_id": 5, "page": 9, "quote": "ponds", "revision": "2:e"})):
    return {"id": 100 + ordinal, "run_id": rid, "ordinal": ordinal, "question": "q",
            "answer": answer, "kind": kind, "created_at": "t", "citations": list(citations),
            "facts": []}


class Seam:
    """Serves scripted responses and records every call."""

    def __init__(self, *, submit=None, polls=(), turns=None, revision=1, reopen_status=200):
        self.ids = (f"22222222-2222-4222-8222-{n:012d}" for n in itertools.count(1))
        self.submit_script = submit
        self.polls = list(polls)
        self.turns = turns
        self.revision = revision
        self.reopen_status = reopen_status
        self.calls = []
        self.issued = []

    def submit(self, body, key):
        self.calls.append(("submit", body, key))
        if self.submit_script:
            return self.submit_script
        rid = next(self.ids)
        self.issued.append(rid)
        return Response(201, run_view(rid, "queued", question=body["question"]))

    def status(self, run_id):
        self.calls.append(("status", run_id))
        state = self.polls.pop(0) if self.polls else "completed"
        return Response(200, run_view(run_id, state))

    def cancel(self, run_id):
        self.calls.append(("cancel", run_id))
        return Response(200, run_view(run_id, "cancelled"))

    def reopen(self, conversation_id):
        self.calls.append(("reopen", conversation_id))
        if self.reopen_status != 200:
            return Response(self.reopen_status)
        turns = self.turns if self.turns is not None else [
            turn_view(rid, n) for n, rid in enumerate(self.issued, 1)]
        return Response(200, {"protocol": "runs-reader-1", "id": CID, "revision": self.revision,
                              "runs": [], "turns": turns})


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


CASE = conv("d1", split="development")


def multi(cid, n):
    case = conv(cid, split="development")
    case["turns"] = case["turns"] * n
    return case


def collect(seam, case=CASE, **kw):
    clock = Clock()
    return collect_case_runtime(seam, case, clock=clock, sleep=clock.sleep, **kw)


def test_a_case_is_a_runtime_conversation_followed_to_its_saved_turn_and_reopened():
    seam = Seam(polls=["running", "running"])
    row = collect(seam)
    assert row["status"] == "complete" and row["conversation_id"] == CID
    [turn] = row["turns"]
    assert turn["outcome"] == "answered"
    assert turn["public_answer"]["answer"].startswith("Both studies")
    assert turn["citation_record_ids"] == [7, 5]  # runtime order, never re-sorted
    assert [c["page"] for c in turn["public_answer"]["citations"]] == [3, 9]
    assert turn["public_answer"]["citations"][0]["text"] == "gauges"
    assert turn["saved_turn"]["ordinal"] == 1 and row["reopened_transcript"] == [turn["saved_turn"]]
    assert [c[0] for c in seam.calls] == ["submit", "status", "status", "status", "reopen", "reopen"]
    assert seam.calls[0][1] == {"question": CASE["turns"][0]["user"], "depth": "deep"}
    assert seam.calls[0][2].startswith("eval-")
    assert [e["data"]["state"] for e in turn["public_events"]] == [
        "queued", "running", "running", "completed"]


def test_a_follow_up_names_the_conversation_and_the_revision_it_saw():
    case = multi("d2", 2)
    seam = Seam(revision=4)
    # The runtime assigns the Conversation on the first submit.
    row = collect(seam, case)
    bodies = [c[1] for c in seam.calls if c[0] == "submit"]
    assert "conversation_id" not in bodies[0]
    assert bodies[1]["conversation_id"] == CID and bodies[1]["base_revision"] == 4
    assert len(row["turns"]) == 2 and row["status"] == "complete"


def test_busy_cancelled_failed_and_overdue_runs_are_retained_not_dropped():
    busy = collect(Seam(submit=Response(503, {"status": "busy"})))
    assert busy["status"] == "incomplete" and busy["turns"][0]["outcome"] == "cap_stop"
    failed = collect(Seam(polls=["failed"]))
    assert failed["turns"][0]["outcome"] == "failure"
    cancelled = collect(Seam(polls=["cancelled"]))
    assert cancelled["turns"][0]["outcome"] == "cancellation"
    seam = Seam(polls=["running"] * 1000)
    overdue = collect(seam, deadline_seconds=5, poll_seconds=1)
    assert overdue["turns"][0]["outcome"] == "timeout"
    assert ("cancel", seam.issued[0]) in seam.calls  # the evaluation does not leave it running
    for row in (busy, failed, cancelled, overdue):
        assert row["status"] == "incomplete" and len(row["turns"]) == 1
        assert row["turns"][0]["usage_status"] == "missing"


def test_a_status_poll_that_fails_cancels_the_run_it_can_no_longer_follow():
    seam = Seam()
    seam.status = lambda rid: (seam.calls.append(("status", rid)) or Response(500))
    row = collect(seam)
    assert row["turns"][0]["outcome"] == "failure"
    assert ("cancel", seam.issued[0]) in seam.calls


def test_unauthorized_or_unavailable_submit_is_a_failure_and_a_missing_reopen_is_an_error():
    assert collect(Seam(submit=Response(401, {"status": "unauthorized"})))["turns"][0][
        "outcome"] == "failure"
    assert collect(Seam(submit=Response(503, {"status": "unavailable"})))["turns"][0][
        "outcome"] == "failure"
    with pytest.raises(ValueError, match="reopen failed with HTTP 404"):
        collect(Seam(reopen_status=404))


def test_a_clarification_is_an_answered_turn_and_an_unreadable_source_is_not_an_answer():
    clarification = Seam()
    clarification.reopen = lambda cid: Response(200, {"id": CID, "revision": 1, "runs": [], "turns": [
        turn_view(clarification.issued[0], 1, answer="Which year?", kind="clarification",
                  citations=())]})
    row = collect(clarification)
    assert row["turns"][0]["outcome"] == "answered"
    assert row["turns"][0]["public_answer"]["kind"] == "clarification"
    gone = Seam()
    gone.status = lambda rid: Response(200, run_view(rid, "completed", sources_available=False))
    gone.reopen = lambda cid: Response(200, {"id": CID, "revision": 1, "runs": [], "turns": [turn_view(
        gone.issued[0], 1, answer="This answer is unavailable because its sources changed or are "
        "no longer readable.", citations=())]})
    unavailable = collect(gone)
    assert unavailable["turns"][0]["outcome"] == "failure"
    assert unavailable["turns"][0]["citation_record_ids"] == []


class Attempts:
    """Ledger rows by run, as `RuntimeAttempts.for_run` returns them."""

    def __init__(self, rows):
        self.rows = rows

    def for_run(self, run_id):
        return list(self.rows)


def ledger(**over):
    return {"id": 1, "run_key": "airun:x", "work_key": "w", "operation": "llm", "model": "m1",
            "purpose": "agent", "purpose_version": "agent-research-3", "state": "settled",
            "sent": True, "usage_reported": True, "input_tokens": 10, "output_tokens": 5,
            "cost_usd": 0.01, "reserved_cost_usd": 0.04, "price_basis": "admission", **over}


def test_physical_attempts_and_per_turn_caps_come_from_the_runtime_ledger():
    row = collect(Seam(), attempts=Attempts([ledger(), ledger(id=2, purpose="repair")]))
    turn = row["turns"][0]
    assert [a["purpose"] for a in turn["physical_attempts"]] == ["agent", "repair"]
    assert turn["usage_status"] == "reported" and row["cost"] == pytest.approx(0.02)
    assert row["physical_attempts"] == 2 and row["cost_final"] is True
    capped = collect(Seam(), case=multi("d3", 2),
                     attempts=Attempts([ledger()]),
                     limits={"case_attempts": 1, "turn_max_attempts": 1})
    assert [t["outcome"] for t in capped["turns"]] == ["answered", "cap_stop"]
    assert capped["status"] == "incomplete"


def test_an_open_reservation_makes_the_turn_a_non_final_failure():
    row = collect(Seam(), attempts=Attempts([ledger(state="open", usage_reported=False)]))
    assert row["turns"][0]["outcome"] == "failure" and row["cost_final"] is False


def test_a_runtime_run_file_carries_its_own_identity_and_is_labelled_contract_evidence():
    data = make_set([conv("d1", split="development")])
    seam = Seam()
    clock = Clock()
    out = collect_run(
        seam, data["conversations"], set_id=data["set_id"], set_digests={"development": "d"},
        corpus={"paper_set_sha256": "p", "snapshot_id": "s"}, model_ids={"agent": "scripted"},
        limits={"case_attempts": 4}, data_policy="deterministic-fake-local", cache="cold",
        arm="runtime", engine_version=RUNTIME_ENGINE, protocol="runs-reader-1",
        identity=runtime_identity(), runtime={"depth": "deep", "declared_by": "operator"},
        case_collector=lambda reader, case, **kw: collect_case_runtime(
            reader, case, clock=clock, sleep=clock.sleep, **{k: v for k, v in kw.items()
                                                              if k in ("attempts", "limits")}),
        clock=clock)
    manifest = out["manifest"]
    assert out["arm"] == "runtime" and out["providers"] == "fake"
    assert manifest["engine_version"] == "ai-runtime-1" and manifest["identity"] == runtime_identity()
    assert manifest["protocol_version"] == "runs-reader-1"
    assert manifest["controller_version"] is None and manifest["controller_protocol_version"] is None
    assert manifest["runtime"] == {"depth": "deep", "declared_by": "operator"}
    assert out["evidence"]["kind"] == "contract"
    assert out["evidence"]["human_reviewed"] is False and out["evidence"]["quality_evidence"] is False
    assert out["conversations"][0]["cache"] == "cold"


def test_the_exported_row_builds_a_review_packet_and_withholds_what_the_reviewer_cannot_read():
    row = collect(Seam())
    run = {"run_id": "r", "arm": "runtime", "manifest": {"rubric_version": 1}, "conversations": [row]}
    packet = build_packets(run, reviewer="Rev One", readable={7, 5})["packets"][0]
    assert packet["turns"][0]["withheld"] is False
    assert [c["record_id"] for c in packet["turns"][0]["citations"]] == [7, 5]
    assert packet["authorized_record_ids"] == [5, 7]
    withheld = build_packets(run, reviewer="Rev One", readable={7})["packets"][0]
    assert withheld["turns"][0]["withheld"] is True and "answer" not in withheld["turns"][0]
    assert withheld["turns"][0]["citations"] == []


def test_the_seam_builds_the_edge_and_the_granted_requests_from_one_client():
    class Client:
        def __init__(self):
            self.calls = []

        def post(self, path, json=None, headers=None):
            self.calls.append(("post", path, json, headers))
            return Response(201, {})

        def get(self, path, headers=None):
            self.calls.append(("get", path, headers))
            return Response(200, {})

    client = Client()
    edge = RuntimeSeam(client)
    edge.submit({"question": "q"}, "k1")
    edge.status("r1")
    edge.cancel("r1")
    edge.reopen("c1")
    assert [(c[0], c[1]) for c in client.calls] == [
        ("post", "/api/v1/ai/runtime/runs"), ("get", "/api/v1/ai/runtime/runs/r1"),
        ("post", "/api/v1/ai/runtime/runs/r1/cancel"),
        ("get", "/api/v1/ai/runtime/conversations/c1")]
    assert client.calls[0][3] == {"Idempotency-Key": "k1"}
    direct = Client()
    RuntimeSeam(direct, prefix="/api/v1/ai",
                headers=lambda: {"X-IRIS-Reader-Grant": "g", "X-IRIS-Protocol": "runs-reader-1"}
                ).submit({"question": "q"}, "k2")
    assert direct.calls[0][1] == "/api/v1/ai/runs"
    assert direct.calls[0][3] == {"X-IRIS-Reader-Grant": "g", "X-IRIS-Protocol": "runs-reader-1",
                                  "Idempotency-Key": "k2"}


def compaction_case():
    case = conv("c1", split="development")
    case["turns"] = [case["turns"][0], {"action": "compact"}, case["turns"][0]]
    return case


def test_a_compaction_step_is_unsupported_sends_nothing_and_ends_the_case():
    seam = Seam()
    row = collect(seam, compaction_case())
    assert [t["outcome"] for t in row["turns"]] == ["answered", "unsupported"]
    assert row["status"] == "incomplete"
    assert sum(c[0] == "submit" for c in seam.calls) == 1
    assert not any(c[0] == "compact" for c in seam.calls)


class Client:
    def __init__(self):
        self.headers = []

    def post(self, path, json=None, headers=None):
        self.headers.append(headers)
        return Response(201, run_view("22222222-2222-4222-8222-000000000009", "completed"))

    def get(self, path, headers=None):
        self.headers.append(headers)
        return Response(200, {})


def test_a_scoped_seam_asks_through_paper_chat_for_one_record():
    client = Client()
    seam = RuntimeSeam(client).scoped(53)
    seam.submit({"question": "q"}, "eval-key")
    seam.status("x")
    seam.reopen(CID)
    assert all(h and h["X-IRIS-Record"] == "53" for h in client.headers)
    assert client.headers[0]["Idempotency-Key"] == "eval-key"
