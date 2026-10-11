import pytest

from apps.ai.inference import api_key_variables, model_variables, profile_for

pytestmark = pytest.mark.django_required


def test_screen_is_off_until_its_own_model_and_account_are_configured(settings):
    settings.LLM_SCREEN_MODEL = ""
    settings.LLM_ANSWER_MODEL = "answer-model"
    settings.LLM_API_KEY = "answer-account"
    profile = profile_for("screen")
    assert not profile.is_configured
    assert profile.api_key == ""
    assert model_variables("screen") == ("LLM_SCREEN_MODEL",)
    assert api_key_variables("screen") == ("LLM_SCREEN_API_KEY",)

    settings.LLM_SCREEN_VENDOR = "openrouter"
    settings.LLM_SCREEN_MODEL = "screen-model"
    settings.LLM_SCREEN_API_KEY = "screen-account"
    profile = profile_for("screen")
    assert profile.is_configured
    assert profile.model == "screen-model"
    assert profile.api_key == "screen-account"
    assert profile.reasoning_visible is False
