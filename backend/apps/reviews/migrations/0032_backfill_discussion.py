"""
Existing comments that nobody treated as a review item become discussion, so
they show in Conversation again (ADR-032 §7 as amended 2026-11-16, IR-1194,
point 2).

A top-level comment becomes discussion when it has no passage, is not *Must
fix*, was sent by no review round, has no answer and no recorded event, and is
not a draft. Its severity -- `0025` gave every older comment *Suggestion* -- is
cleared, since a discussion carries none. Everything else stays a thread.
Replies then take their parent's kind. Bodies, times, authors and parties are
untouched. Reversing returns every row to a thread but leaves the cleared
severities blank.
"""

from django.db import migrations


def to_discussion(apps, schema_editor):
    ReviewComment = apps.get_model("reviews", "ReviewComment")
    ReviewThreadEvent = apps.get_model("reviews", "ReviewThreadEvent")

    acted_on = ReviewThreadEvent.objects.values("thread_id")
    plain = (
        ReviewComment.objects.filter(
            reply_to__isnull=True, anchor_version__isnull=True, round__isnull=True,
            answer="", is_draft=False,
        )
        .exclude(severity="must_fix")
        .exclude(pk__in=acted_on)
    )
    plain.update(kind="discussion", severity=None)
    ReviewComment.objects.filter(reply_to__kind="discussion").update(kind="discussion")


def to_threads(apps, schema_editor):
    ReviewComment = apps.get_model("reviews", "ReviewComment")
    ReviewComment.objects.filter(kind="discussion").update(kind="thread")


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0031_reviewcomment_kind"),
    ]

    operations = [
        migrations.RunPython(to_discussion, to_threads),
    ]
