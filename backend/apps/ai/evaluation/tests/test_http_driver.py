"""IR-550: the driver that submits questions to a running Ask IRIS over HTTP.

No server: httpx's mock transport stands where Django would. The clock is
injected, so latency is measured from the original submission.
"""

import asyncio
import json

import httpx

from apps.ai.evaluation.http_driver import burst, parse_sse, sanitize_done, submit_all


def _sse(*events):
    return "".join(f"id: {i}\nevent: {name}\ndata: {json.dumps(data)}\n\n"
                   for i, (name, data) in enumerate(events, 1))


def test_parse_sse_reads_named_events_and_ignores_comments():
    text = ": keepalive\n\n" + _sse(("run_queued", {"run_id": "r"}), ("done", {"mode": "generative"}))
    assert parse_sse(text) == [("run_queued", {"run_id": "r"}), ("done", {"mode": "generative"})]


def test_a_burst_sends_every_question_together_and_classifies_each_from_its_stream():
    seen = []

    def handler(request):
        question = json.loads(request.content)["question"]
        seen.append(question)
        assert request.headers["authorization"] == "Bearer t"
        if question == "busy":
            return httpx.Response(503, json={"status": "busy"})
        return httpx.Response(200, text=_sse(("done", {"mode": "generative", "answer": "x"})))

    ticks = iter(range(0, 10_000, 100))
    submissions = asyncio.run(burst(
        ["a", "b", "busy"], base_url="http://iris", path="/api/v1/ai/ask/stream/",
        token="t", transport=httpx.MockTransport(handler), clock=lambda: next(ticks) / 1000,
    ))
    assert sorted(seen) == ["a", "b", "busy"]
    by_question = {s.question: s for s in submissions}
    assert by_question["a"].result == "generated"
    assert by_question["busy"].result == "refused"
    assert all(s.final_ms is None or s.final_ms >= s.submitted_ms for s in submissions)


def test_each_question_carries_its_own_payload_fields():
    seen = {}

    def handler(request):
        body = json.loads(request.content)
        seen[body["question"]] = body.get("conversation_id")
        return httpx.Response(200, text=_sse(("run_queued", {}), ("done", {
            "mode": "generative", "listing": {"observed": {"cache_hits": 2}}})))

    results = asyncio.run(submit_all(
        ["a", "b"], base_url="http://iris", path="/p", token="t",
        extras=[{"conversation_id": 1}, {"conversation_id": 2}],
        transport=httpx.MockTransport(handler)))
    assert seen == {"a": 1, "b": 2}
    assert [s.cache_hits for s, _ in results] == [2, 2]


def test_a_stream_that_outlives_the_client_bound_is_a_timeout(monkeypatch):
    monkeypatch.setattr("apps.ai.evaluation.http_driver.CLIENT_TIMEOUT_S", 0.05)

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, text="")

    submissions = asyncio.run(burst(["a"], base_url="http://iris", path="/p", token="t",
                                    transport=httpx.MockTransport(slow)))
    assert submissions[0].result == "timeout"


def test_a_transport_error_or_timeout_is_a_submission_that_did_not_succeed():
    def handler(request):
        if json.loads(request.content)["question"] == "slow":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("down", request=request)

    submissions = asyncio.run(burst(
        ["slow", "down"], base_url="http://iris", path="/p", token="t",
        transport=httpx.MockTransport(handler),
    ))
    assert {s.question: s.result for s in submissions} == {"slow": "timeout", "down": "failed"}


def test_sanitize_keeps_figures_and_states_and_drops_text_quotes_and_reasoning():
    done = {
        "mode": "generative", "answer": "secret answer", "reasoning": "private",
        "citations": [{"record_id": 1, "quote": "verbatim"}],
        "routing": {"lane": "count", "probabilities": {"count": 0.9}},
        "listing": {
            "completeness": "matches_found", "wording": "2 matches among ...",
            "candidates": [{"record_id": 1, "title": "T", "state": "included",
                            "quote": "q", "source": {"page": 2}},
                           {"record_id": 2, "state": "unassessed", "restricted": True}],
            "coverage": {"selected": 2}, "topic_count": {"matches": 1, "criterion": "c"},
            "observed": {"model_calls": 1},
        },
    }
    clean = sanitize_done(done, keys={1: "flood-gauges", 2: "flood-warning"})
    assert clean == {
        "mode": "generative", "routing_lane": "count", "citation_count": 1,
        "listing": {
            "completeness": "matches_found", "wording": "2 matches among ...",
            "candidates": [{"record_key": "flood-gauges", "state": "included"},
                           {"record_key": "flood-warning", "state": "unassessed",
                            "restricted": True}],
            "coverage": {"selected": 2}, "topic_count": {"matches": 1, "criterion": "c"},
            "observed": {"model_calls": 1},
        },
    }
