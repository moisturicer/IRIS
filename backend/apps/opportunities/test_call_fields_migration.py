"""Migration 0002 moves existing Calls to the new types (ADR-050 decision 16, IR-760).

A Conference Deadline becomes a Conference and keeps its title, about, link,
deadline, Featured and poster; its new required fields stay blank. An Internal
Call, Funding Window or Institutional Grant is deleted, and each leaves a
CALL_DELETED audit event, no actor, carrying a copy of the Call.

Mechanics follow ``apps/accounts/test_session_end_reason_migration.py``.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import User


pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("opportunities", "0001_initial")]
_MIGRATE_TO = [("opportunities", "0002_call_fields")]


def _old_call(OldOpportunity, opportunity_type, title, **extra):
    fields = {
        "opportunity_type": opportunity_type,
        "title": title,
        "posting_office": "Research & Development Coordinating Office (RDCO)",
        "audience": "CIT-U Faculty",
        "description": f"About {title}.",
        "external_url": "https://example.org/call",
        "due_date": date(2026, 12, 1),
        "tags": ["Seed Grant"],
    }
    fields.update(extra)
    return OldOpportunity.objects.create(**fields)


def test_existing_calls_move_to_the_new_types():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldOpportunity = old_apps.get_model("opportunities", "Opportunity")
        # Accounts is not rewound, so the poster is today's User: the
        # historical one at this point still has a `username` column.
        poster = User.objects.create_user(email="poster@cit.edu", password="pw12345!")

        conference = _old_call(
            OldOpportunity, "conference_deadline", "ICAC 2027",
            is_featured=True, posted_by_id=poster.pk,
        )
        grant = _old_call(
            OldOpportunity, "institutional_grant", "Seed Grant",
            funding_ceiling=Decimal("150000.00"), source="internal", posted_by_id=poster.pk,
        )
        internal = _old_call(OldOpportunity, "internal_call", "Capstone Call")
        window = _old_call(OldOpportunity, "funding_window", "DOST Window", source="external")

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps
        Opportunity = new_apps.get_model("opportunities", "Opportunity")
        AuditEvent = new_apps.get_model("audit", "AuditEvent")

        assert list(Opportunity.objects.values_list("pk", flat=True)) == [conference.pk]
        moved = Opportunity.objects.get(pk=conference.pk)
        assert moved.opportunity_type == "conference"
        assert (moved.title, moved.description, moved.external_url) == (
            "ICAC 2027", "About ICAC 2027.", "https://example.org/call",
        )
        assert moved.due_date == date(2026, 12, 1)
        assert moved.is_featured is True
        assert moved.posted_by_id == poster.pk
        assert moved.location == ""
        assert moved.registration_fee == ""
        assert moved.start_date is None and moved.end_date is None
        assert moved.areas.count() == 0

        events = {
            event.metadata["call"]["id"]: event
            for event in AuditEvent.objects.filter(event_type="CALL_DELETED")
        }
        assert set(events) == {grant.pk, internal.pk, window.pk}
        for event in events.values():
            assert event.user_id is None
            assert event.record_id is None
            assert "no longer a type of Call" in event.metadata["reason"]

        assert events[grant.pk].metadata["reason"].startswith("Institutional Grant ")
        assert events[grant.pk].metadata["call"] == {
            "id": grant.pk,
            "opportunity_type": "institutional_grant",
            "title": "Seed Grant",
            "posting_office": "Research & Development Coordinating Office (RDCO)",
            "audience": "CIT-U Faculty",
            "description": "About Seed Grant.",
            "funding_ceiling": "150000.00",
            "external_url": "https://example.org/call",
            "due_date": "2026-12-01",
            "is_featured": False,
            "tags": ["Seed Grant"],
            "source": "internal",
            "posted_by": poster.pk,
            "created_at": grant.created_at.isoformat(),
            "updated_at": grant.updated_at.isoformat(),
        }
        assert events[window.pk].metadata["call"]["source"] == "external"
        assert events[internal.pk].metadata["call"]["funding_ceiling"] is None

        # Reversing brings the Conference back as a Conference Deadline. The
        # deleted Calls stay deleted; their copies stay in the Audit Log.
        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_FROM)
        back = old_apps.get_model("opportunities", "Opportunity")
        assert list(back.objects.values_list("opportunity_type", "title")) == [
            ("conference_deadline", "ICAC 2027"),
        ]
        assert AuditEvent.objects.filter(event_type="CALL_DELETED").count() == 3
    finally:
        call_command("migrate", verbosity=0)
