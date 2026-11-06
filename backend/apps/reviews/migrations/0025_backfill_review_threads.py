"""
Existing review comments become general threads (ADR-032 §7, 2026-11-04; IR-874).

Each top-level comment gets severity *Suggestion*, so no history blocks
anything, and the party it belongs to: blank for an owner's, else the party of
the Seat its writer held on that record (the latest one opened by the time
they wrote it, or failing that any). A writer with neither -- an account since
removed -- leaves the party blank. Replies, bodies, times and versions are not
touched: nothing is rewritten. Every comment was posted, so none is a draft.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    ReviewComment = apps.get_model("reviews", "ReviewComment")
    RecordOwner = apps.get_model("records", "RecordOwner")
    ReviewerSeat = apps.get_model("reviews", "ReviewerSeat")

    for comment in ReviewComment.objects.filter(reply_to__isnull=True).iterator():
        party = ""
        if comment.author_id is not None and not RecordOwner.objects.filter(
            record_id=comment.record_id, user_id=comment.author_id,
        ).exists():
            seats = ReviewerSeat.objects.filter(
                assignment__record_id=comment.record_id, reviewer_id=comment.author_id,
            )
            seat = (
                seats.filter(assigned_at__lte=comment.created_at).order_by("-assigned_at", "-pk").first()
                or seats.order_by("-assigned_at", "-pk").first()
            )
            if seat is not None:
                party = seat.assignment.party
        ReviewComment.objects.filter(pk=comment.pk).update(severity="suggestion", party=party)


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0033_version_review_text"),
        ("reviews", "0024_review_threads"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
