"""
Seed a record mid-clearance so the paper view's clearance track has real state.

Builds the case the thesis contribution is about: a record that was declined by
one office, resubmitted, and is now back in parallel review with the *other*
offices' clearances still intact. On the paper view those intact rows render
with a "Preserved" badge, because they were decided before the latest decline.

Resulting shape on the target record:
  ITSO  cleared   (decided before the decline  -> Preserved)
  IERC  cleared   (decided before the decline  -> Preserved)
  KTTO  pending   (the office that declined; reset by resubmit)
  reviews: one approved ITSO, one approved IERC, one declined KTTO

Run with:  python manage.py shell < scripts/seed_demo_clearances.py
Dev only. Idempotent — re-running resets the same record to the same state.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.records.models import Record
from apps.reviews.models import RecordClearance, Review

User = get_user_model()

# The record to put mid-clearance. Any published demo record will do; this one
# is a Thesis/Research work, which routes IERC + KTTO.
TARGET_TITLE = "A Low-Cost IoT Flood Sensor Network for Cebu Barangays"

record = Record.objects.filter(title=TARGET_TITLE).first()
if record is None:
    record = Record.objects.order_by("id").first()

if record is None:
    print("No records exist. Run scripts/seed_demo_records.py first.")
else:
    itso_user = User.objects.filter(email="itso@cit.edu").first()
    ierc_user = User.objects.filter(email="ierc@cit.edu").first()
    ktto_user = User.objects.filter(email="ktto@cit.edu").first()

    if not all([itso_user, ierc_user, ktto_user]):
        print("Office users missing. Run scripts/seed_demo_users.py first.")
    else:
        now = timezone.now()
        cleared_at = now - timedelta(days=12)   # before the decline
        declined_at = now - timedelta(days=5)   # the decline that reset KTTO

        record.pipeline_status = "parallel_review"
        record.save(update_fields=["pipeline_status", "updated_at"])

        Review.objects.filter(record=record).delete()
        RecordClearance.objects.filter(record=record).delete()

        rows = [
            ("itso", "cleared", itso_user,
             "No information-security concerns. Dataset is anonymised at source.",
             cleared_at),
            ("ierc", "cleared", ierc_user,
             "Ethics clearance granted. Barangay consent documentation is complete.",
             cleared_at),
            ("ktto", "pending", None, "", declined_at),
        ]
        for office, status, user, comment, stamp in rows:
            clearance = RecordClearance.objects.create(
                record=record,
                office=office,
                status=status,
                reviewed_by=user,
                comment=comment,
            )
            # updated_at is auto_now, so it must be written past the ORM to
            # backdate it. This is what makes "preserved" observable.
            RecordClearance.objects.filter(pk=clearance.pk).update(updated_at=stamp)

        reviews = [
            ("itso", "approved", itso_user,
             "Cleared. Sensor telemetry carries no personally identifying data.",
             cleared_at),
            ("ierc", "approved", ierc_user,
             "Cleared. Consent forms and the data-retention plan are in order.",
             cleared_at),
            ("ktto", "declined", ktto_user,
             "Revision requested: the commercialisation section needs a prior-art "
             "search before we can assess patentability.",
             declined_at),
        ]
        for stage, status, user, comment, stamp in reviews:
            review = Review.objects.create(
                record=record,
                reviewed_by=user,
                stage=stage,
                status=status,
                comment=comment,
            )
            Review.objects.filter(pk=review.pk).update(created_at=stamp)

        print(f"Seeded clearance state on record #{record.id}: {record.title}")
        print("  ITSO cleared (preserved) / IERC cleared (preserved) / KTTO pending")
        print(f"  View at /records/{record.id}")
