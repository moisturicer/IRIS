"""What the OpenRouter Decisions adapter puts on the wire (IR-482).

No account and no network: an `httpx.MockTransport` answers, as with the
Docling client. The part with judgement in it -- the pinned model, the one noul
question, the failure kinds, and a response that is not the shape promised --
is tested; the HTTP call itself is not.
"""

import json

import httpx
import pytest

from apps.ai.providers.decisions import (
    DecisionMalformed,
    DecisionModel,
    DecisionUnavailable,
    NoulAnswer,
    ScriptedDecisionModel,
)
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.openrouter_decisions import (
    DECISIONS_URL,
    PINNED_MODEL,
    OpenRouterDecisionsAdapter,
)

CRITERIA = {"true": "needs the corpus", "false": "does not"}
GOOD = {
    "answers": {"needs_corpus": {"type": "noul", "noul": 0.87}},
    "id": "gen-dec-1",
    "model": "typesafe/jev-1.13-20260917",
    "provider": "TypeSafe",
    "usage": {"cost": 0.00002, "input_tokens": 120, "output_tokens": 4},
}


def adapter(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterDecisionsAdapter("sk-test", client=client, **kwargs)


def ask(a, state="the question"):
    return a.noul(state, instructions="Does it need the corpus?", criteria=CRITERIA)


def reply(body, status=200):
    return lambda request: httpx.Response(status, json=body)


class TheRequestTests:
    def test_it_posts_one_noul_question_to_the_alpha_endpoint(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=GOOD)

        ask(adapter(handler), state={"question": "q"})

        (request,) = seen
        assert str(request.url) == DECISIONS_URL == "https://openrouter.ai/api/alpha/decisions"
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer sk-test"
        body = json.loads(request.content)
        assert set(body) == {"model", "state", "questions"}
        assert body["state"] == {"question": "q"}
        (name, question), = body["questions"].items()
        assert question == {
            "type": "noul",
            "instructions": "Does it need the corpus?",
            "criteria": CRITERIA,
        }
        assert name == "needs_corpus"

    def test_the_model_is_pinned_to_a_dated_release_never_the_alias(self):
        assert PINNED_MODEL == "typesafe/jev-1.13"
        seen = []
        ask(adapter(lambda r: (seen.append(r), httpx.Response(200, json=GOOD))[1]))
        assert json.loads(seen[0].content)["model"] == "typesafe/jev-1.13"

    @pytest.mark.parametrize(
        "model", ["~typesafe/jev-latest", "typesafe/jev-latest", "typesafe/jev", ""]
    )
    def test_an_alias_or_unpinned_model_is_refused_at_construction(self, model):
        with pytest.raises(ValueError):
            OpenRouterDecisionsAdapter("sk-test", model=model)

    def test_a_missing_key_is_refused_at_construction(self):
        with pytest.raises(ValueError):
            OpenRouterDecisionsAdapter("")

    def test_no_user_or_session_identifier_is_sent(self):
        seen = []
        ask(adapter(lambda r: (seen.append(r), httpx.Response(200, json=GOOD))[1]))
        body = json.loads(seen[0].content)
        assert not {"user", "session_id", "trace", "provider"} & set(body)


class TheAnswerTests:
    def test_it_returns_the_probability_the_version_and_the_usage(self):
        answer = ask(adapter(reply(GOOD)))

        assert answer == NoulAnswer(
            probability=0.87,
            model="typesafe/jev-1.13-20260917",
            input_tokens=120,
            cost_usd=0.00002,
        )

    def test_zero_and_one_are_valid_probabilities(self):
        for p in (0, 0.0, 1, 1.0):
            body = {**GOOD, "answers": {"needs_corpus": {"type": "noul", "noul": p}}}
            assert ask(adapter(reply(body))).probability == float(p)

    def test_usage_is_optional(self):
        body = {k: v for k, v in GOOD.items() if k != "usage"}
        answer = ask(adapter(reply(body)))
        assert (answer.input_tokens, answer.cost_usd) == (None, None)


class TheMalformedResponseTests:
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"answers": {}},
            {"answers": []},
            {"answers": {"needs_corpus": {"type": "choice", "choice": "a"}}},
            {"answers": {"needs_corpus": {"type": "noul"}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": "0.9"}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": True}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": None}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": 1.2}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": -0.1}}},
            {"answers": {"needs_corpus": {"type": "noul", "noul": float("nan")}}},
            {"answers": {"other": {"type": "noul", "noul": 0.5}}},
            "just text",
            None,
        ],
        ids=lambda b: str(b)[:40],
    )
    def test_a_response_not_in_the_promised_shape_is_malformed(self, body):
        def handler(request):
            return httpx.Response(200, content=json.dumps(body))

        with pytest.raises(DecisionMalformed):
            ask(adapter(handler))

    def test_a_body_that_is_not_json_is_malformed(self):
        with pytest.raises(DecisionMalformed):
            ask(adapter(lambda r: httpx.Response(200, content=b"<html>")))

    def test_a_malformed_response_is_not_a_vendor_outage(self):
        assert not issubclass(DecisionMalformed, DecisionUnavailable)


class TheFailureTests:
    @pytest.mark.parametrize(
        "status, kind",
        [
            (429, ErrorKind.RATE_LIMIT),
            (401, ErrorKind.AUTH),
            (403, ErrorKind.AUTH),
            (402, ErrorKind.AUTH),
            (500, ErrorKind.NETWORK),
            (502, ErrorKind.NETWORK),
            (503, ErrorKind.NETWORK),
            (529, ErrorKind.NETWORK),
            (524, ErrorKind.TIMEOUT),
            (413, ErrorKind.CONTEXT_OVERFLOW),
            (400, ErrorKind.UNKNOWN),
        ],
    )
    def test_an_http_error_carries_its_kind(self, status, kind):
        body = {"error": {"code": status, "message": "nope"}}
        with pytest.raises(DecisionUnavailable) as raised:
            ask(adapter(reply(body, status)))
        assert raised.value.kind is kind

    def test_a_timeout_is_a_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(DecisionUnavailable) as raised:
            ask(adapter(handler))
        assert raised.value.kind is ErrorKind.TIMEOUT

    def test_a_dropped_connection_is_a_network_failure(self):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        with pytest.raises(DecisionUnavailable) as raised:
            ask(adapter(handler))
        assert raised.value.kind is ErrorKind.NETWORK

    def test_the_key_never_appears_in_an_error(self):
        body = {"error": {"code": 401, "message": "bad key sk-test"}}
        with pytest.raises(DecisionUnavailable) as raised:
            ask(adapter(reply(body, 401)))
        assert "sk-test" not in str(raised.value)


class TheFakeTests:
    def test_the_fake_is_a_decision_model_and_records_each_request(self):
        fake = ScriptedDecisionModel(0.3, NoulAnswer(0.9, "m"))
        assert isinstance(fake, DecisionModel)

        first = fake.noul("s1", instructions="i", criteria=CRITERIA)
        second = fake.noul("s2", instructions="i", criteria=CRITERIA)

        assert (first.probability, second.probability) == (0.3, 0.9)
        assert [call["state"] for call in fake.calls] == ["s1", "s2"]

    def test_the_fake_raises_what_it_is_scripted_to_raise(self):
        fake = ScriptedDecisionModel(DecisionUnavailable("down", kind=ErrorKind.NETWORK))
        with pytest.raises(DecisionUnavailable):
            fake.noul("s", instructions="i", criteria=CRITERIA)

    def test_the_port_is_abstract(self):
        with pytest.raises(TypeError):
            DecisionModel()
