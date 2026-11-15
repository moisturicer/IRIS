# Written for IR-760: a Call's new fields and types (ADR-050 decisions 2-3, 16).
#
# Adds location, Areas, event dates and the fee; moves existing Calls; then
# drops posting office, audience, funding ceiling, tags and source.
#
# Moving existing Calls (decision 16):
#   Conference Deadline  -> Conference. Its new required fields stay blank
#                           until it is next saved, which the serializer
#                           refuses without them.
#   Internal Call, Funding Window, Institutional Grant -> deleted, each with a
#                           CALL_DELETED audit event, no actor, carrying a copy.
#
# Reversing turns every Call back into a Conference Deadline with a blank
# posting office. Deleted Calls are not restored: their copies stay in the
# Audit Log, which is insert-only.

from django.db import migrations, models

OLD_CONFERENCE = "conference_deadline"
RETIRED = {
    "internal_call":       "Internal Call",
    "funding_window":      "Funding Window",
    "institutional_grant": "Institutional Grant",
}


def _copy(call):
    """Every field the Call had, as JSON the audit row can hold."""
    return {
        "id":               call.pk,
        "opportunity_type": call.opportunity_type,
        "title":            call.title,
        "posting_office":   call.posting_office,
        "audience":         call.audience,
        "description":      call.description,
        "funding_ceiling":  None if call.funding_ceiling is None else str(call.funding_ceiling),
        "external_url":     call.external_url,
        "due_date":         call.due_date.isoformat(),
        "is_featured":      call.is_featured,
        "tags":             call.tags,
        "source":           call.source,
        "posted_by":        call.posted_by_id,
        "created_at":       call.created_at.isoformat(),
        "updated_at":       call.updated_at.isoformat(),
    }


def move_calls(apps, schema_editor):
    Opportunity = apps.get_model("opportunities", "Opportunity")
    AuditEvent = apps.get_model("audit", "AuditEvent")

    Opportunity.objects.filter(opportunity_type=OLD_CONFERENCE).update(opportunity_type="conference")

    retired = Opportunity.objects.filter(opportunity_type__in=RETIRED).order_by("pk")
    AuditEvent.objects.bulk_create([
        AuditEvent(
            event_type="CALL_DELETED",
            user=None,
            metadata={
                "reason": (
                    f"{RETIRED[call.opportunity_type]} is no longer a type of Call "
                    "(ADR-050 decision 16)."
                ),
                "call": _copy(call),
            },
        )
        for call in retired
    ])
    retired.delete()


def unmove_calls(apps, schema_editor):
    Opportunity = apps.get_model("opportunities", "Opportunity")
    Opportunity.objects.update(opportunity_type=OLD_CONFERENCE)


class Migration(migrations.Migration):

    dependencies = [
        ('opportunities', '0001_initial'),
        ('records', '0041_deleterequest_rdco_note'),
        ('audit', '0028_call_deleted_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='opportunity',
            name='areas',
            field=models.ManyToManyField(blank=True, related_name='calls', to='records.classification'),
        ),
        migrations.AddField(
            model_name='opportunity',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='opportunity',
            name='location',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name='opportunity',
            name='registration_fee',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='opportunity',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(move_calls, unmove_calls),
        migrations.RemoveField(
            model_name='opportunity',
            name='audience',
        ),
        migrations.RemoveField(
            model_name='opportunity',
            name='funding_ceiling',
        ),
        # A default first, so that reversing can add the column back over the
        # Calls that exist then.
        migrations.AlterField(
            model_name='opportunity',
            name='posting_office',
            field=models.CharField(default='', max_length=200),
        ),
        migrations.RemoveField(
            model_name='opportunity',
            name='posting_office',
        ),
        migrations.RemoveField(
            model_name='opportunity',
            name='source',
        ),
        migrations.RemoveField(
            model_name='opportunity',
            name='tags',
        ),
        migrations.AlterField(
            model_name='opportunity',
            name='opportunity_type',
            field=models.CharField(choices=[('conference', 'Conference'), ('congress', 'Congress'), ('symposium', 'Symposium'), ('workshop', 'Workshop'), ('journal', 'Journal'), ('book_chapter', 'Book Chapter')], max_length=32),
        ),
    ]
