"""Prompt-cache hits are read and recorded, and a cache key is sent only when asked (IR-953)."""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.admission.scope import RunBinding, bound  # noqa: E402
from ai.agent.dialect import ChatCompletions  # noqa: E402
from ai.agent.protocol import AgentRequest, Pin, User  # noqa: E402
from ai.infrastructure import agent_config  # noqa: E402
from ai.admission.limits import NotConfigured  # noqa: E402
from ai.infrastructure.agent_config import AgentProviderConfig  # noqa: E402
from ai.infrastructure.openai_adapter import OpenAICompatibleAgentProvider  # noqa: E402
from ai.runs import config as runs_config  # noqa: E402

PIN = Pin(model="m", endpoint="https://vendor.test/v1", adapter="openai-compatible",
          dialect=ChatCompletions.name, prompt_version="direct-1", tool_version="none-1",
          public_version="runs-reader-1", state_version="state-1", data_policy="no-training")


def reply(usage):
    return {"choices": [{"message": {"role": "assistant", "content": "An answer."}, "finish_reason": "stop"}],
            "usage": usage}


def test_cached_prompt_tokens_are_read_from_the_usage_details():
    turn = ChatCompletions.decode(reply({"prompt_tokens": 9000, "completion_tokens": 30,
                                         "prompt_tokens_details": {"cached_tokens": 8192}}), PIN)
    assert (turn.input_tokens, turn.cached_input_tokens) == (9000, 8192)


@pytest.mark.parametrize("details", [None, {}, {"cached_tokens": -1}, {"cached_tokens": "8"}, "8192"])
def test_an_absent_or_malformed_cache_count_is_unknown_not_zero(details):
    usage = {"prompt_tokens": 9, "completion_tokens": 3}
    if details is not None:
        usage["prompt_tokens_details"] = details
    assert ChatCompletions.decode(reply(usage), PIN).cached_input_tokens is None


def provider(prompt_cache="off"):
    return OpenAICompatibleAgentProvider(AgentProviderConfig(
        PIN.endpoint, "key", frozenset({"m"}), frozenset(), "no-training", {}, prompt_cache=prompt_cache))


def request():
    return AgentRequest(pin=PIN, instructions="Answer.", history=(User("Which papers?"),))


def test_off_sends_no_cache_key():
    run_id = uuid.uuid4()
    with bound(RunBinding(run_id, 1)):
        assert "prompt_cache_key" not in provider().encode(request())


def test_run_keys_the_cache_to_this_run_alone():
    first, second = uuid.uuid4(), uuid.uuid4()
    with bound(RunBinding(first, 1)):
        one = provider("run").encode(request())["prompt_cache_key"]
    with bound(RunBinding(second, 1)):
        other = provider("run").encode(request())["prompt_cache_key"]
    assert one == f"iris-run-{first}" and other == f"iris-run-{second}"


def test_outside_a_run_no_key_is_sent_even_when_on():
    assert "prompt_cache_key" not in provider("run").encode(request())


def declared(**over):
    values = {"AGENT_LLM_ENDPOINT": "https://vendor.test/v1", "AGENT_LLM_API_KEY": "k",
              "AGENT_LLM_MODELS": "m", "AGENT_LLM_CAPABILITIES": "tools", "AGENT_LLM_DATA_POLICY": "no-training",
              "AGENT_LLM_CAPACITIES": "{}", **over}
    return SimpleNamespace(**values)


def test_the_prompt_cache_is_off_unless_set_and_refuses_anything_else():
    assert agent_config.read(declared()).prompt_cache == "off"
    assert agent_config.read(declared(AGENT_LLM_PROMPT_CACHE="run")).prompt_cache == "run"
    with pytest.raises(NotConfigured, match="AGENT_LLM_PROMPT_CACHE"):
        agent_config.read(declared(AGENT_LLM_PROMPT_CACHE="always"))


def test_the_query_vector_cache_is_on_unless_off_and_refuses_anything_else():
    def problems(value):
        return [p for p in runs_config.problems(SimpleNamespace(RUNS_QUERY_VECTOR_CACHE=value))
                if "RUNS_QUERY_VECTOR_CACHE" in p]
    assert problems("") == problems("on") == problems("off") == []
    assert problems("yes")
    on = runs_config.query_vector_cache
    assert on(SimpleNamespace(RUNS_QUERY_VECTOR_CACHE="")) and on(SimpleNamespace(RUNS_QUERY_VECTOR_CACHE="on"))
    assert not on(SimpleNamespace(RUNS_QUERY_VECTOR_CACHE="off"))
