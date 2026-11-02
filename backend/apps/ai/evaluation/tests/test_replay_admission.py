"""IR-606: charged retry/fallback attempts remain separate run evidence."""

import pytest

from apps.ai.admission import scope
from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.admission.tests.support import MeteredAdapter, enforce
from apps.ai.evaluation.replay import CampaignAttempts


pytestmark = [pytest.mark.db_required,
              pytest.mark.django_db(transaction=True, databases=["default", "admission"])]


def test_dedicated_campaign_cursor_keeps_reported_and_missing_usage(settings):
    enforce(settings)
    collector = CampaignAttempts("test-campaign")
    before = collector.snapshot()
    with scope.run(scope.new_run("eval:case-1")):
        AdmittedLLMProvider(MeteredAdapter(model="cheap", usage=(120, 30))).generate("s", "q")
        AdmittedLLMProvider(MeteredAdapter(model="dear", usage=None)).generate("s", "q")
    attempts = collector.since(before)
    assert [(row["model"], row["run_key"], row["usage_reported"]) for row in attempts] == [
        ("cheap", "eval:case-1", True), ("dear", "eval:case-1", False),
    ]
    assert attempts[0]["cost_usd"] > 0
    assert attempts[1]["cost_usd"] > attempts[0]["cost_usd"]
    assert attempts[1]["price_basis"] == "reservation"
