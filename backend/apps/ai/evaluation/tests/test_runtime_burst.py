"""A burst through the runtime counts every submission and starts them together (IR-1007)."""

import threading

from apps.ai.evaluation import runtime_burst as burst


class Response:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


class Gateway:
    """One shared fake runtime: a reader past `busy_after` active runs is refused `503 busy`."""

    def __init__(self, busy_after=None, fail=()):
        self.busy_after, self.fail = busy_after, set(fail)
        self.lock = threading.Lock()
        self.submitted = []
        self.active = {}

    def seam(self, reader):
        return Seam(self, reader)


class Seam:
    def __init__(self, gateway, reader):
        self.gateway, self.reader = gateway, reader

    def submit(self, body, key):
        g = self.gateway
        with g.lock:
            g.submitted.append((self.reader, body["question"], body["depth"]))
            n = len(g.submitted)
            if g.busy_after is not None and g.active.get(self.reader, 0) >= g.busy_after:
                return Response(503, {"status": "busy"})
            g.active[self.reader] = g.active.get(self.reader, 0) + 1
        return Response(201, {"id": f"run-{n}", "conversation_id": f"c-{n}", "state": "queued",
                              "question": body["question"]})

    def status(self, run_id):
        question = next(q for i, (_, q, _) in enumerate(self.gateway.submitted, 1) if f"run-{i}" == run_id)
        state = "failed" if question in self.gateway.fail else "completed"
        return Response(200, {"id": run_id, "state": state, "sources_available": True})

    def cancel(self, run_id):
        return Response(202, {})

    def reopen(self, conversation_id):
        n = conversation_id.split("-")[1]
        return Response(200, {"revision": 1, "turns": [
            {"run_id": f"run-{n}", "answer": "An answer.", "kind": "answer", "citations": []}]})


def items(n, readers=("a", "b"), deep_share=0.25):
    return burst.plan_items([f"question {i}" for i in range(n)], readers=readers, deep_share=deep_share)


def test_items_spread_over_readers_and_mix_depths_deterministically():
    planned = items(8)
    assert [i["reader"] for i in planned] == ["a", "b"] * 4
    assert [i["depth"] for i in planned].count("deep") == 2
    assert planned == items(8)


def test_every_submission_is_counted_and_a_busy_refusal_stays_in_the_denominator():
    gateway = Gateway(busy_after=2)
    rows = burst.run_burst(items(6, readers=("a",)), gateway.seam, deadline_seconds=5, poll_seconds=0)
    assert len(rows) == 6
    summary = burst.summarize(rows, provider="fake", cache="cold", wall_ms=1000)
    assert summary["submissions"] == 6
    assert summary["outcomes"] == {"answered": 2, "refused": 4}
    assert summary["answered_share"] == 2 / 6


def test_a_failed_run_is_a_failure_not_dropped():
    gateway = Gateway(fail={"question 1"})
    rows = burst.run_burst(items(3), gateway.seam, deadline_seconds=5, poll_seconds=0)
    assert [r["outcome"] for r in rows] == ["answered", "failure", "answered"]


def test_a_seam_that_raises_is_a_failure_and_the_burst_goes_on():
    def broken(reader):
        raise RuntimeError("edge down")
    rows = burst.run_burst(items(2), broken, deadline_seconds=5, poll_seconds=0)
    assert [r["outcome"] for r in rows] == ["failure", "failure"]
    assert rows[0]["error"] == "RuntimeError"


def test_no_submission_is_sent_until_every_one_is_ready():
    gate = threading.Event()
    sent = []

    class Slow(Gateway):
        def seam(self, reader):
            if reader == "b":
                gate.wait(2)  # the last seam to be built holds every submission back
            return super().seam(reader)

    gateway = Slow()
    original = Seam.submit

    def recording(self, body, key):
        sent.append(gate.is_set())
        return original(self, body, key)
    Seam.submit = recording
    try:
        timer = threading.Timer(0.3, gate.set)
        timer.start()
        burst.run_burst(items(4), gateway.seam, deadline_seconds=5, poll_seconds=0)
    finally:
        Seam.submit = original
    assert sent == [True] * 4


def test_only_a_real_simultaneous_burst_of_enough_distinct_questions_is_a_measurement():
    gateway = Gateway()
    rows = burst.run_burst(items(4), gateway.seam, deadline_seconds=5, poll_seconds=0)
    assert burst.summarize(rows, provider="fake", cache="cold", wall_ms=1)["claim"] == "control_only"
    assert burst.summarize(rows, provider="real", cache="cold", wall_ms=1)["claim"] == "unverified"
    many = [{**rows[0], "question": f"q{i}"} for i in range(burst.MIN_BURST)]
    assert burst.summarize(many, provider="real", cache="cold", wall_ms=1)["claim"] == "measured"
    assert burst.summarize(many, provider="real", cache="warm", wall_ms=1)["claim"] == "control_only"


def test_latency_is_reported_per_depth_from_submission():
    rows = [{"question": "q1", "depth": "ordinary", "outcome": "answered", "latency_ms": 100},
            {"question": "q2", "depth": "ordinary", "outcome": "refused", "latency_ms": 5},
            {"question": "q3", "depth": "deep", "outcome": "answered", "latency_ms": 900}]
    summary = burst.summarize(rows, provider="real", cache="cold", wall_ms=60_000)
    assert summary["latency_ms"]["ordinary"]["answered"] == {"n": 1, "p50": 100, "p95": 100, "max": 100}
    assert summary["latency_ms"]["deep"]["answered"]["p50"] == 900
    assert summary["answered_per_minute"] == 2.0
