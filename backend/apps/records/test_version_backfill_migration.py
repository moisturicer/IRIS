"""
IR-416's version backfill, `records/0015`, over records that predate versions.

ADR-032 §13 as amended 2026-10-08: one version per non-draft record, naming
its current manuscript. v1 if it was never resubmitted; v(k + 1) if it was
resubmitted k times, with no v1 to vk made up. Every existing `Review.version`
stays null.

Mechanics follow `apps/reviews/test_seat_backfill_migration.py`: rewind
`records` only. `Record` and `RecordVersion` rows are written through their
models as of `0014`, because the live `Record` carries columns added after it
(`details_edited_at`, IR-273) that the rewound table does not have. Other
apps' rows go through the current models.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.records.models import RecordType, RecordVersion
from apps.reviews.models import Review

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_BEFORE = [("records", "0014_record_version")]
_AFTER = [("records", "0015_backfill_record_versions")]

T0 = timezone.now() - timedelta(days=30)


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", role=role, is_verified=True
    )


def _migrate(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)


def _records_model(name):
    """`records.<name>` as of `_BEFORE` (module note)."""
    executor = MigrationExecutor(connection)
    return executor.loader.project_state(_BEFORE).apps.get_model("records", name)


def _versions(record):
    return [
        (v.number, v.cause, v.manuscript.name or None, v.created_by_id, v.created_at)
        for v in RecordVersion.objects.filter(record_id=record.pk).order_by("number")
    ]


def test_the_backfill_records_one_knowable_version_per_submitted_record():
    _migrate(_BEFORE)
    try:
        owner = _user("ir416-owner@cit.edu", "Student")
        adviser = _user("ir416-adviser@cit.edu", "Adviser")
        # get_or_create: a flushing TransactionTestCase earlier in the run
        # removes the rows records/0002 seeds.
        thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]
        OldRecord = _records_model("Record")
        OldRecordVersion = _records_model("RecordVersion")

        def record(title, status, **extra):
            r = OldRecord.objects.create(
                title=title, record_type_id=thesis.pk, added_by_id=owner.pk,
                pipeline_status=status, **extra,
            )
            OldRecord.objects.filter(pk=r.pk).update(created_at=T0)
            r.refresh_from_db()
            return r

        submitted_at = T0 + timedelta(days=1)
        resubmitted_at = T0 + timedelta(days=5)

        # Never submitted: no version.
        draft = record("draft", "draft", abstract_file="abstracts/draft.pdf")

        # Submitted once, consent stamped: v1, credited to the submitter.
        once = record(
            "once", "itso_review", abstract_file="abstracts/once.pdf",
            dpa_accepted_at=submitted_at, dpa_accepted_by_id=owner.pk,
        )
        # Its earlier review is not dated against the reconstructed version.
        review = Review.objects.create(
            record_id=once.pk, reviewed_by=adviser, stage="adviser", status="approved",
        )

        # Resubmitted twice: one version, v3, no v1 or v2 made up.
        twice = record(
            "twice", "rdco_review", abstract_file="abstracts/twice.pdf",
            dpa_accepted_at=submitted_at, dpa_accepted_by_id=owner.pk,
            resubmission_count=2, last_resubmitted_at=resubmitted_at,
        )

        # Imported straight to published: never submitted, credited to nobody,
        # dated when it was created.
        imported = record("imported", "published", abstract_file="abstracts/imported.pdf")

        # Submitted with no manuscript: a version naming none.
        bare = record("bare", "adviser_review")

        # Already versioned by the live code: left alone.
        live = record("live", "in_review", abstract_file="abstracts/live.pdf")
        OldRecordVersion.objects.create(
            record_id=live.pk, number=1, cause="submission",
            manuscript="abstracts/live.pdf", created_by_id=owner.pk, created_at=submitted_at,
        )

        _migrate(_AFTER)

        assert _versions(draft) == []
        assert _versions(once) == [
            (1, "submission", "abstracts/once.pdf", owner.pk, submitted_at),
        ]
        assert _versions(twice) == [
            (3, "revision", "abstracts/twice.pdf", None, resubmitted_at),
        ]
        assert _versions(imported) == [(1, "submission", "abstracts/imported.pdf", None, T0)]
        assert _versions(bare) == [(1, "submission", None, None, T0)]
        assert _versions(live) == [
            (1, "submission", "abstracts/live.pdf", owner.pk, submitted_at),
        ]

        review.refresh_from_db()
        assert review.version_id is None

        # Re-running finds every submitted record already versioned.
        _migrate(_BEFORE)
        _migrate(_AFTER)
        assert RecordVersion.objects.filter(record_id=once.pk).count() == 1
        assert RecordVersion.objects.filter(record_id=twice.pk).count() == 1
    finally:
        call_command("migrate", verbosity=0)
