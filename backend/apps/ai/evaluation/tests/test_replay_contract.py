"""The collection file remains useful when a run stops before a Turn exists."""

import json

from apps.ai.evaluation.replay import ASK_STREAM, CONVERSATIONS, collect_case, collect_run


class Reply:
    def __init__(self, status, body=None, events=""):
        self.status_code = status
        self.body = body or {}
        self.text = events

    def json(self):
        return self.body


class Reader:
    def __init__(self):
        self.next_id = 0
        self.transcripts = {}
        self.requests = []

    def post(self, path, payload):
        self.requests.append((path, payload))
        if path == CONVERSATIONS:
            self.next_id += 1
            self.transcripts[self.next_id] = []
            return Reply(201, {"id": self.next_id})
        assert path == ASK_STREAM
        cid = payload["conversation_id"]
        turn = {"id": len(self.transcripts[cid]) + 1, "question": payload["question"],
                "answer": "An answer", "citations": []}
        self.transcripts[cid].append(turn)
        return Reply(200, events=("event: done\ndata: " + json.dumps({
            "answer": "An answer", "mode": "generative", "citations": [],
            "sources": [], "conversation_id": cid,
        }) + "\n\n"))

    def get(self, path):
        cid = int(path.removeprefix(CONVERSATIONS).strip("/"))
        return Reply(200, {"turns": list(self.transcripts[cid])})


def case():
    return {"id": "d1", "family": "A01", "split": "development", "turns": [
        {"user": "first"}, {"user": "second"},
    ]}


def test_order_and_independence_at_the_reader_transport():
    reader = Reader()
    one = collect_case(reader, case())
    two = collect_case(reader, case())
    assert one["conversation_id"] != two["conversation_id"]
    assert [row["question"] for row in one["reopened_transcript"]] == ["first", "second"]
    assert [row["saved_turn"]["question"] for row in two["turns"]] == ["first", "second"]
    assert all(payload.get("protocol") == "public-1" for path, payload in reader.requests
               if path == ASK_STREAM)


def test_an_interrupted_turn_is_counted_even_without_a_saved_turn():
    reader = Reader()
    original = reader.post

    def interrupted(path, payload):
        if path == ASK_STREAM:
            raise TimeoutError("interrupted")
        return original(path, payload)

    reader.post = interrupted
    result = collect_case(reader, case())
    assert result["status"] == "incomplete"
    assert len(result["turns"]) == 1
    assert result["turns"][0]["saved_turn"] is None
    assert result["turns"][0]["outcome"] == "timeout"


def test_empty_answer_is_incomplete_and_does_not_ask_follow_up():
    reader = Reader()
    original = reader.post

    def empty(path, payload):
        if path == ASK_STREAM:
            return Reply(200, events='event: done\ndata: {"mode":"unavailable"}\n\n')
        return original(path, payload)

    reader.post = empty
    result = collect_case(reader, case())
    assert result["status"] == "incomplete"
    assert [turn["outcome"] for turn in result["turns"]] == ["failure"]
    assert [path for path, _ in reader.requests] == [CONVERSATIONS]


def test_case_cap_stops_before_the_next_request():
    reader = Reader()
    result = collect_case(reader, case(), limits={"case_attempts": 0})
    assert [turn["outcome"] for turn in result["turns"]] == ["cap_stop"]
    assert [path for path, _ in reader.requests] == [CONVERSATIONS]


def test_case_reserves_a_whole_turn_before_starting_it():
    reader = Reader()
    result = collect_case(reader, case(), limits={"case_attempts": 2,
                                                 "turn_max_attempts": 3})
    assert result["turns"][0]["outcome"] == "cap_stop"
    assert [path for path, _ in reader.requests] == [CONVERSATIONS]


def test_a_failed_conversation_create_stays_in_the_run_file():
    reader = Reader()

    def unavailable(path, payload):
        raise ConnectionError("network details must not enter the run file")

    reader.post = unavailable
    result = collect_run(reader, [case()], set_id="s", set_digests={"development": "x"},
                         corpus={"snapshot_id": "c", "paper_set_sha256": "d"},
                         model_ids={"answer": "fake"}, limits={}, data_policy="fake",
                         cache="cold")
    assert result["conversations"][0]["status"] == "incomplete"
    assert result["conversations"][0]["turns"][0]["outcome"] == "failure"
    assert "network details" not in json.dumps(result)


def test_only_development_cases_enter_the_run_file():
    held = {**case(), "split": "held_out"}
    try:
        collect_run(Reader(), [held], set_id="s", set_digests={},
                    corpus={"snapshot_id": "c", "paper_set_sha256": "d"},
                    model_ids={"answer": "fake"}, limits={}, data_policy="fake",
                    cache="cold")
    except ValueError as exc:
        assert "development" in str(exc)
    else:
        raise AssertionError("held-out case reached the collector")
