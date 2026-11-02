"""Django signs only current committed local processing work (IR-737)."""
from django.db import transaction
from apps.ai.grants import config
from apps.ai.grants.issue import Grant, committed_work_grant
from apps.records.models import Record
from .models import ManuscriptWork


class WorkRefused(Exception):
    pass


@transaction.atomic
def issue_grant(work_id) -> Grant:
    config.read()
    work = ManuscriptWork.objects.filter(pk=work_id).first()
    if work is None:
        raise WorkRefused()
    record = Record.objects.select_for_update().filter(pk=work.record_id, is_deleted=False).first()
    work = ManuscriptWork.objects.select_for_update().filter(pk=work_id).first()
    if (record is None or work is None or work.revoked_at is not None or not record.abstract_file
            or record.abstract_file.name != work.source_file or work.operation != "local_extraction"):
        raise WorkRefused()
    grant = committed_work_grant(work)
    work.grant_token, work.grant_expires_at = grant.token, grant.expires_at
    work.save(update_fields=["grant_token", "grant_expires_at"])
    return grant
