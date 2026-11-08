"""The AGENT deployment profile is explicit and read at worker start (IR-862).

`RUNS_EXECUTOR=agent` makes new runs AGENT runs; it requires the whole
profile, and an absent or invalid value refuses to start, naming the key
and never a secret. No value here is a production value.
"""

import json

import pytest

from ai.infrastructure.settings import Settings
from ai.runs import config
from ai.runs.worker import build

from .test_runs_config import COMPLETE

API_KEY = "sk-NEVER-IN-A-MESSAGE"
CAPACITY = dict(context_tokens=128_000, max_output_tokens=8_000, max_reasoning_tokens=None,
                max_request_bytes=1_000_000, min_bytes_per_token=1.0, framing_tokens_per_message=4)
BOUNDS = dict(max_steps=4, max_tool_calls=6, max_no_progress=2, final_seconds=5, history_turns=4)
AGENT = dict(
    RUNS_EXECUTOR="agent",
    RUNS_AGENT_MODEL="model-a",
    RUNS_AGENT_BOUNDS=json.dumps({"ordinary": BOUNDS, "deep": {**BOUNDS, "max_steps": 8}}),
    RUNS_AGENT_RESERVES=json.dumps(dict(output_tokens=60, reasoning_tokens=40, next_result_tokens=300,
                                        repair_tokens=100)),
    AGENT_LLM_ENDPOINT="https://llm.example.test/v1",
    AGENT_LLM_API_KEY=API_KEY,
    AGENT_LLM_MODELS="model-a,model-b",
    AGENT_LLM_CAPABILITIES="tools",
    AGENT_LLM_DATA_POLICY="no-training",
    AGENT_LLM_CAPACITIES=json.dumps({"model-a": CAPACITY}),
    AI_ADMISSION_CAMPAIGN="ir862-test",
    AI_ADMISSION_CAMPAIGN_MAX_ATTEMPTS="100",
    AI_ADMISSION_CAMPAIGN_MAX_INPUT_TOKENS="1000000",
    AI_ADMISSION_CAMPAIGN_MAX_OUTPUT_TOKENS="1000000",
    AI_ADMISSION_CAMPAIGN_MAX_COST_USD="10",
    AI_ADMISSION_CAMPAIGN_MAX_ACTIVE_MINUTES="600",
    AI_ADMISSION_RESERVE_FRACTION="0.1",
    AI_ADMISSION_LANE_CONCURRENCY=json.dumps({"research": 2}),
    AI_ADMISSION_ACCOUNT_CONCURRENCY="2",
    AI_ADMISSION_PRICES=json.dumps({"model-a": {"input": 1.0, "output": 2.0}}),
    AI_ADMISSION_MAX_OUTPUT_TOKENS="100",
)


def settings(**overrides):
    return Settings(_env_file=None, **{**COMPLETE, **AGENT, **overrides})


def refusal(**overrides) -> str:
    with pytest.raises(config.RunsUnavailable) as refused:
        build(settings(**overrides))
    message = str(refused.value)
    assert API_KEY not in message
    return message


def test_a_complete_agent_profile_pins_new_runs_to_the_agent_and_still_serves_deterministic_runs():
    service = build(settings())

    assert service.executor.name == "agent"
    assert set(service.executors) == {"agent", "deterministic"}
    agent = service.pinned("ordinary")["agent"]
    assert (agent["model"], agent["endpoint"], agent["adapter"]) == (
        "model-a", "https://llm.example.test/v1", "openai-compatible")
    assert (agent["prompt_version"], agent["tool_version"]) == ("agent-research-6", "research-6")
    assert service.pinned("deep")["bounds"]["max_steps"] == 8
    assert service.pinned("ordinary")["bounds"]["max_steps"] == 4


def test_the_deterministic_profile_needs_no_agent_setting():
    blank = {name: "" for name in AGENT}
    service = build(settings(**{**blank, "RUNS_EXECUTOR": "deterministic"}))
    assert service.executor.name == "deterministic"
    assert set(service.executors) == {"deterministic"}
    assert "agent" not in service.pinned("ordinary")


@pytest.mark.parametrize("name", [n for n in AGENT if n != "RUNS_EXECUTOR"])
def test_an_absent_agent_setting_refuses_to_start_and_names_it(name):
    assert name in refusal(**{name: ""})


def test_an_unknown_executor_refuses_to_start():
    assert "RUNS_EXECUTOR" in refusal(RUNS_EXECUTOR="openai")


@pytest.mark.parametrize(("overrides", "named"), [
    ({"RUNS_AGENT_MODEL": "model-z"}, "RUNS_AGENT_MODEL"),
    # Listed, but no capacity declared: it could only ever be refused.
    ({"RUNS_AGENT_MODEL": "model-b"}, "RUNS_AGENT_MODEL"),
    ({"AI_ADMISSION_PRICES": json.dumps({"model-b": {"input": 1, "output": 1}})}, "RUNS_AGENT_MODEL"),
    ({"RUNS_AGENT_BOUNDS": json.dumps({"ordinary": BOUNDS})}, "RUNS_AGENT_BOUNDS"),
    ({"RUNS_AGENT_BOUNDS": json.dumps({"ordinary": BOUNDS, "deep": {**BOUNDS, "max_steps": 0}})},
     "RUNS_AGENT_BOUNDS"),
    ({"RUNS_AGENT_BOUNDS": json.dumps({"ordinary": BOUNDS, "deep": {"max_steps": 1}})}, "RUNS_AGENT_BOUNDS"),
    ({"RUNS_AGENT_BOUNDS": "not json"}, "RUNS_AGENT_BOUNDS"),
    ({"RUNS_AGENT_RESERVES": json.dumps({"output_tokens": 0, "reasoning_tokens": 0,
                                         "next_result_tokens": 0, "repair_tokens": 0})},
     "RUNS_AGENT_RESERVES"),
    ({"RUNS_AGENT_RESERVES": json.dumps({"output_tokens": 10})}, "RUNS_AGENT_RESERVES"),
    ({"AGENT_LLM_ENDPOINT": "ftp://llm.example.test"}, "AGENT_LLM_ENDPOINT"),
    ({"AGENT_LLM_DATA_POLICY": "vendor-default"}, "AGENT_LLM_DATA_POLICY"),
])
def test_an_invalid_agent_profile_refuses_to_start_and_names_it(overrides, named):
    assert named in refusal(**overrides)


# --- Compaction (IR-734) --------------------------------------------------------

COMPACTION = dict(threshold_tokens=100_000, summary_tokens=2_000, keep_exchanges=2, max_attempts=2)


def test_compaction_is_off_unless_configured():
    assert build(settings()).executor.compaction is None


def test_a_configured_compaction_reaches_the_agent():
    service = build(settings(RUNS_AGENT_COMPACTION=json.dumps(COMPACTION)))
    assert service.executor.compaction.threshold_tokens == 100_000


@pytest.mark.parametrize("compaction", [
    {**COMPACTION, "max_attempts": 0},
    {"threshold_tokens": 100_000},
    # No room left to summarize or to finish under the model's verified capacity.
    {**COMPACTION, "threshold_tokens": 127_900},
    {**COMPACTION, "summary_tokens": 9_000},
])
def test_an_invalid_compaction_refuses_to_start_and_names_it(compaction):
    assert "RUNS_AGENT_COMPACTION" in refusal(RUNS_AGENT_COMPACTION=json.dumps(compaction))
