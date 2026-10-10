"""Report in-flight intake records that IR-260 cannot assign to an Adviser."""

from django.core.management.base import BaseCommand

from apps.records.models import Record
from apps.reviews.models import RecordAssignment


class Command(BaseCommand):
    help = "List intake records lacking an eligible Adviser; changes nothing."

    def handle(self, *args, **options):
        count = 0
        intake_ids = set(RecordAssignment.objects.filter(
            party="intake", state="active"
        ).values_list("record_id", flat=True))
        intake_ids.update(Record.objects.filter(
            pipeline_status="rdco_intake"
        ).values_list("pk", flat=True))
        for record in Record.objects.filter(pk__in=intake_ids).order_by("pk"):
            if record.adviser_id is None:
                reason = "no adviser"
            elif record.owners.filter(user_id=record.adviser_id).exists():
                reason = "adviser is an owner"
            else:
                continue
            self.stdout.write(f"{record.pk}\t{record.title}\t{reason}")
            count += 1
        self.stdout.write(f"{count} intake record(s) need an Adviser decision.")
