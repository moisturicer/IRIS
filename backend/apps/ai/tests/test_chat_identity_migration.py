"""The additive identity migration preserves existing conversation history."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from .corpus import make_user
from apps.reviews.workflow_test_helpers import model_at_current_state

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def test_existing_multiple_conversations_and_turns_survive():
    user = make_user("migration-identity@cit.edu")
    old, new = ("ai", "0032_turn_reasoning_summary"), ("ai", "0033_chat_request_identity")
    executor = MigrationExecutor(connection)
    executor.migrate([old])
    try:
        apps = executor.loader.project_state([old]).apps
        record = model_at_current_state("records", "Record").objects.create(title="Existing paper")
        conversations = apps.get_model("ai", "Conversation")
        first = conversations.objects.create(user_id=user.pk, record_id=record.pk)
        second = conversations.objects.create(user_id=user.pk, record_id=record.pk)
        turn = apps.get_model("ai", "Turn").objects.create(
            conversation_id=first.pk, question="Existing question", answer="Existing answer", state="generated",
        )
        executor = MigrationExecutor(connection)
        executor.migrate([new])
        apps = executor.loader.project_state([new]).apps
        migrated = apps.get_model("ai", "Conversation").objects.filter(pk__in=[first.pk, second.pk])
        assert migrated.count() == 2
        assert not migrated.filter(is_default=True).exists()
        saved = apps.get_model("ai", "Turn").objects.get(pk=turn.pk)
        assert saved.conversation_id == first.pk and saved.answer == "Existing answer"
    finally:
        MigrationExecutor(connection).migrate([new])
