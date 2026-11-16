"""
Existing replies keep the party their writer held when they wrote them
(IR-1192), so a reply in a thread can say who wrote it.

The same rule `0025` used for threads: blank for an owner's reply, else the
party of the Seat its writer held on that record (the latest one opened by the
time they wrote it, or failing that any). A writer with neither -- an account
since removed -- leaves the party blank, and the reply then shows no label.
Only `party` is written: bodies, times, versions and threads are untouched.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    ReviewComment = apps.get_model("reviews", "ReviewComment")
    RecordOwner = apps.get_model("records", "RecordOwner")
    ReviewerSeat = apps.get_model("reviews", "ReviewerSeat")

    replies = ReviewComment.objects.filter(reply_to__isnull=False, party="", author__isnull=False)
    for reply in replies.iterator():
        if RecordOwner.objects.filter(record_id=reply.record_id, user_id=reply.author_id).exists():
            continue
        seats = ReviewerSeat.objects.select_related("assignment").filter(
            assignment__record_id=reply.record_id, reviewer_id=reply.author_id,
        )
        seat = (
            seats.filter(assigned_at__lte=reply.created_at).order_by("-assigned_at", "-pk").first()
            or seats.order_by("-assigned_at", "-pk").first()
        )
        if seat is not None:
            ReviewComment.objects.filter(pk=reply.pk).update(party=seat.assignment.party)


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0029_review_mentions"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
