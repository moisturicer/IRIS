"""Rate configuration through a fresh settings import, independent of local .env."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


RATE_KEYS = ("API_THROTTLE_ANON", "API_THROTTLE_USER", "API_THROTTLE_AI_QUERY")


def boot_settings(module="base", **overrides):
    env = {key: value for key, value in os.environ.items() if key not in RATE_KEYS}
    env.update(SECRET_KEY="test-only", DB_NAME="test", DB_USER="test", DB_PASSWORD="test")
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", (
            "import decouple; decouple.config = decouple.Config(decouple.RepositoryEmpty()); "
            f"from config.settings.{module} import REST_FRAMEWORK; import json; "
            "print(json.dumps(REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']))"
        )],
        cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True,
    )


@pytest.mark.parametrize("debug", ["True", "False"])
@pytest.mark.parametrize("module", ["base", "development"])
def test_unset_rates_keep_existing_defaults_even_in_debug(debug, module):
    result = boot_settings(module, DEBUG=debug)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "anon": "100/day", "user": "1000/day", "ai_query": "60/hour",
        "ai_overview": "600/hour",
    }


@pytest.mark.parametrize("key,scope,value", [
    ("API_THROTTLE_ANON", "anon", "10000/day"),
    ("API_THROTTLE_USER", "user", "100000/day"),
    ("API_THROTTLE_AI_QUERY", "ai_query", "6000/hour"),
])
@pytest.mark.parametrize("module", ["base", "development"])
def test_each_rate_can_be_overridden_independently(key, scope, value, module):
    result = boot_settings(module, **{key: value})
    assert result.returncode == 0, result.stderr
    expected = {
        "anon": "100/day", "user": "1000/day", "ai_query": "60/hour",
        "ai_overview": "600/hour",
    }
    expected[scope] = value
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize("key", RATE_KEYS)
@pytest.mark.parametrize("value", ["", "lots", "-1/day", "0/hour", "1/week", "1/", "1.5/hour"])
def test_malformed_rates_refuse_startup_and_name_the_setting(key, value):
    result = boot_settings(**{key: value})
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert f"{key} must be a positive rate" in result.stderr
