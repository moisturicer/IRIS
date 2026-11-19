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
  `queues`.
"""
from django.db.models.signals import post_save
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
