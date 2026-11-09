"""End every Django question still queued or running at the switch (IR-957).

Django stopped answering; the AI runtime answers every question now. A run
left `queued` or `running` would never finish, so each ends `failed` with
reason `retired` and one `run_failed` journal event, the terminal shape a
follower already reads. Turns and finished runs are untouched.

Reversing it does nothing: the runs stay ended, as they would have under the
old code once their deadline passed.
"""
from django.db import migrations
from django.utils import timezone

OPEN = ("queued", "running")


def retire_open_runs(apps, schema_editor):
    AskRun = apps.get_model("ai", "AskRun")
    AskRunAttempt = apps.get_model("ai", "AskRunAttempt")
    AskRunEvent = apps.get_model("ai", "AskRunEvent")
    now = timezone.now()
    for run in AskRun.objects.select_for_update().filter(state__in=OPEN).iterator():
        if run.current_attempt_id is not None:
            AskRunAttempt.objects.filter(pk=run.current_attempt_id).update(
                state="finished", finished_at=now,
            )
        sequence = run.last_sequence + 1
        AskRun.objects.filter(pk=run.pk).update(
            state="failed", end_reason="retired", finished_at=now,
            current_attempt=None, last_sequence=sequence,
        )
        AskRunEvent.objects.create(
            run_id=run.pk, sequence=sequence, name="run_failed",
            data={"run_id": str(run.pk), "state": "failed", "reason": "retired"},
        )


class Migration(migrations.Migration):

    dependencies = [("ai", "0043_reader_status_deleted_account")]

    operations = [migrations.RunPython(retire_open_runs, migrations.RunPython.noop)]
