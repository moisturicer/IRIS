import pytest

from apps.ai.inference import api_key_variables, model_variables, profile_for

pytestmark = pytest.mark.django_required


def test_plan_inherits_the_answer_profile_without_sharing_its_task(settings):
    settings.LLM_ANSWER_MODEL = "answer-model"
    settings.LLM_ANSWER_VENDOR = "openrouter"
    settings.LLM_ANSWER_API_KEY = "test-answer-key"
    settings.LLM_ANSWER_PROVIDER_ONLY = "endpoint"
    plan = profile_for("plan")
    assert plan.model == "answer-model"
    assert plan.api_key == "test-answer-key"
    assert plan.provider_only == ("endpoint",)
    assert plan.task.value == "plan"
    assert plan.reasoning_visible is False
    assert "LLM_ANSWER_MODEL" in model_variables("plan")
    assert "LLM_ANSWER_API_KEY" in api_key_variables("plan")


def test_a_plan_vendor_override_never_borrows_the_answers_key(settings):
    settings.LLM_PLAN_VENDOR = "groq"
    settings.LLM_ANSWER_API_KEY = "other-vendor-key"
    settings.LLM_PLAN_API_KEY = ""
    assert profile_for("plan").api_key == ""
    assert api_key_variables("plan") == ("LLM_PLAN_API_KEY",)
