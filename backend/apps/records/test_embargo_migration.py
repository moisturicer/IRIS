"""The embargo migrations, on rows written before each (ADR-052 §15, IR-811, IR-882).

0025 added the embargo with no default and no backfill, so no existing paper was
cleared by it. 0032 makes every paper embargoed by default: "no embargo" answers
become releases by whoever answered, and every other paper stays embargoed.

A published, consented paper with no IP mark is the row a careless default would
clear, so it is the row these check. Mechanics follow
``apps/accounts/test_session_end_reason_migration.py``.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True), pytest.mark.slow]


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps


def test_0025_leaves_every_existing_paper_unanswered():
    before = [("records", "0024_delete_budget_and_collaboration")]
    after = [("records", "0025_record_embargo")]
    old_apps = _migrate(before)
    try:
        OldRecord = old_apps.get_model("records", "Record")
        published = OldRecord.objects.create(
            title="Published and consented", abstract="An abstract.", is_ip=False,
            pipeline_status=PipelineStatus.PUBLISHED, dpa_accepted_at=timezone.now(),
        )

        row = _migrate(after).get_model("records", "Record").objects.filter(pk=published.pk).values().get()

        assert row["embargo_answered_at"] is None
        assert row["embargoed_until"] is None
        assert row["embargo_released_at"] is None
    finally:
        call_command("migrate", verbosity=0)


BEFORE = [("records", "0031_version_documents")]
AFTER = [("records", "0032_embargoed_by_default")]


def test_0032_releases_no_embargo_answers_and_embargoes_the_rest():
    old_apps = _migrate(BEFORE)
    try:
        from apps.accounts.models import User  # accounts stays migrated; only records moves

        OldRecord = old_apps.get_model("records", "Record")
        person = User.objects.create_user(email="migration-0032@cit.edu", password="x")
        answered_at = timezone.now() - timedelta(days=5)
        released_at = timezone.now() - timedelta(days=2)
        until = timezone.localdate() + timedelta(days=60)

        def paper(title, **stamps):
            return OldRecord.objects.create(
                title=title, abstract="An abstract.", is_ip=False,
                pipeline_status=PipelineStatus.PUBLISHED, dpa_accepted_at=timezone.now(), **stamps,
            ).pk

        unknown = paper("Never answered")
        none = paper("Answered no", embargo_answered_at=answered_at, embargo_answered_by_id=person.pk)
        active = paper("Dated", embargo_answered_at=answered_at, embargo_answered_by_id=person.pk,
                       embargoed_until=until)
        released = paper("Released", embargo_answered_at=answered_at, embargo_answered_by_id=person.pk,
                         embargoed_until=until, embargo_released_at=released_at,
                         embargo_released_by_id=person.pk)

        rows = {
            row["id"]: row
            for row in _migrate(AFTER).get_model("records", "Record").objects.values()
        }

        assert rows[unknown]["is_embargoed"] is True
        assert rows[unknown]["embargo_released_at"] is None
        assert rows[unknown]["embargo_date_set_at"] is None

        assert rows[none]["is_embargoed"] is False
        assert rows[none]["embargo_released_at"] == answered_at
        assert rows[none]["embargo_released_by_id"] == person.pk
        assert rows[none]["embargo_date_set_at"] is None
        assert rows[none]["embargoed_until"] is None

        assert rows[active]["is_embargoed"] is True
        assert rows[active]["embargoed_until"] == until
        assert rows[active]["embargo_date_set_at"] == answered_at
        assert rows[active]["embargo_date_set_by_id"] == person.pk
        assert rows[active]["embargo_released_at"] is None

        assert rows[released]["is_embargoed"] is False
        assert rows[released]["embargo_released_at"] == released_at
        assert rows[released]["embargoed_until"] == until
        assert rows[released]["embargo_date_set_at"] == answered_at

        # Back again: each reads as the old state it came from.
        back = {
            row["id"]: row
            for row in _migrate(BEFORE).get_model("records", "Record").objects.values()
        }
        assert back[unknown]["embargo_answered_at"] is None
        assert back[none]["embargo_answered_at"] == answered_at
        assert back[none]["embargo_released_at"] is None
        assert back[active]["embargoed_until"] == until
        assert back[active]["embargo_released_at"] is None
        assert back[released]["embargo_released_at"] == released_at
    finally:
        call_command("migrate", verbosity=0)
