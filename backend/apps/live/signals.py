"""
Where hints are published (ADR-073 decision 3).

Model signals rather than calls in each service, so every write is covered,
including ones a future act adds without remembering to publish:

- a Notification reaches its recipient, or the role it is broadcast to:
  `notifications`, plus `reviews`, `library` and `record:<id>` when it names a
  record (that person was told about the record, so they may see it);
- an office's assignment (routed, reopened, closed) or seat (claimed, assigned,
  opened, withdrawn) changes: the office's role hears `reviews`, with no record
  id; a seat's holder hears `reviews` and the record on their own channel;
- a role, download, delete or call request is made or decided: RDCO hears
  `queues`;
- a review comment is posted, edited, answered, resolved, reopened, closed or
  deleted (IR-1284): everyone `may_read_review` admits hears `record:<id>` on
  their own channel, never a role's, so nobody outside the review learns of
  it. A draft is its writer's alone, so a draft's change goes to them only.
  The bulk writes that skip signals (Finish review, a Decision) call
  `review_changed` themselves.
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.enums import RoleName

from . import channels as ch
from .publish import publish


@receiver(post_save, sender="notifications.Notification")
def notification_saved(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.recipient_id:
        targets = [ch.user_channel(instance.recipient_id)]
    elif instance.broadcast_to_role_id and instance.broadcast_to_role is not None:
        targets = [ch.role_channel(instance.broadcast_to_role.name)]
    else:
        return
    topics = [ch.NOTIFICATIONS]
    if instance.record_id:
        topics += [ch.REVIEWS, ch.LIBRARY, ch.record_topic(instance.record_id)]
    publish(targets, topics)


@receiver(post_save, sender="reviews.RecordAssignment")
def assignment_saved(sender, instance, **kwargs):
    party = str(instance.party)
    if party in ch.OFFICE_PARTIES:
        publish([ch.role_channel(party)], [ch.REVIEWS])


@receiver(post_save, sender="reviews.ReviewerSeat")
def seat_saved(sender, instance, **kwargs):
    assignment = instance.assignment
    targets, topics = [], [ch.REVIEWS]
    party = str(assignment.party)
    if party in ch.OFFICE_PARTIES:
        publish([ch.role_channel(party)], [ch.REVIEWS])
    if instance.reviewer_id:
        targets.append(ch.user_channel(instance.reviewer_id))
        topics.append(ch.record_topic(assignment.record_id))
        publish(targets, topics)


def _rdco_queue_changed(sender, instance, **kwargs):
    publish([ch.role_channel(RoleName.RDCO)], [ch.QUEUES])


for _model in ("accounts.RoleRequest", "records.DownloadRequest", "records.DeleteRequest",
               "opportunities.Opportunity"):
    post_save.connect(_rdco_queue_changed, sender=_model, dispatch_uid=f"live-queue-{_model}")


def _review_readers(record_id) -> list[str]:
    """The own channels of everyone who may read the review now (IR-1284)."""
    from apps.records.models import Record
    from apps.reviews.mentions import candidates

    record = Record.objects.filter(pk=record_id).first()
    if record is None:  # deleted with the record: nobody is left to tell
        return []
    return [ch.user_channel(u.pk) for u in candidates(record)]


def review_changed(record_id) -> None:
    """
    Tell everyone reading `record_id`'s review to read it again (IR-1284).

    Readers are worked out once the write commits, from the committed state:
    a rolled-back write costs nothing, and an office whose assignment the same
    act ended is not told.
    """
    transaction.on_commit(lambda: publish(_review_readers(record_id), [ch.record_topic(record_id)]))


def _review_comment_changed(sender, instance, **kwargs):
    if instance.is_draft:
        if instance.author_id:
            publish([ch.user_channel(instance.author_id)], [ch.record_topic(instance.record_id)])
        return
    review_changed(instance.record_id)


post_save.connect(_review_comment_changed, sender="reviews.ReviewComment",
                  dispatch_uid="live-review-comment-saved")
post_delete.connect(_review_comment_changed, sender="reviews.ReviewComment",
                    dispatch_uid="live-review-comment-deleted")
