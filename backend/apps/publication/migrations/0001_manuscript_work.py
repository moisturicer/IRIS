"""Institutional outbox: the source and its work commit together (IR-737)."""
import uuid
from django.db import migrations, models
import django.db.models.deletion

TRIGGER = r"""
CREATE FUNCTION public.publish_manuscript_work() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE changed boolean; rev uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN changed := true;
    ELSE
        changed := NEW.abstract_file IS DISTINCT FROM OLD.abstract_file
          OR (to_jsonb(NEW)->>'manuscript_revision') IS DISTINCT FROM
             (to_jsonb(OLD)->>'manuscript_revision');
    END IF;
    IF changed OR NEW.is_deleted THEN
        UPDATE public.publication_manuscriptwork SET revoked_at = clock_timestamp(),
            grant_token = '', grant_expires_at = NULL
          WHERE record_id = NEW.id AND revoked_at IS NULL;
    END IF;
    IF changed AND NOT NEW.is_deleted AND coalesce(NEW.abstract_file, '') <> '' THEN
        rev := coalesce((to_jsonb(NEW)->>'manuscript_revision')::uuid, gen_random_uuid());
        INSERT INTO public.publication_manuscriptwork
          (id, record_id, revision, source_file, operation, created_at, grant_token)
        VALUES (gen_random_uuid(), NEW.id, rev, NEW.abstract_file,
                'local_extraction', clock_timestamp(), '');
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER manuscript_committed_work AFTER INSERT OR UPDATE ON public.records_record
FOR EACH ROW EXECUTE FUNCTION public.publish_manuscript_work();
REVOKE ALL ON FUNCTION public.publish_manuscript_work() FROM PUBLIC;
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("records", "0025_record_embargo")]
    operations = [
        migrations.CreateModel(name="ManuscriptWork", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("revision", models.UUIDField(editable=False)),
            ("source_file", models.TextField()),
            ("operation", models.CharField(max_length=32, default="local_extraction")),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("revoked_at", models.DateTimeField(null=True)),
            ("grant_token", models.TextField(default="", editable=False)),
            ("grant_expires_at", models.DateTimeField(null=True, editable=False)),
            ("record", models.ForeignKey(to="records.record", on_delete=django.db.models.deletion.CASCADE)),
        ], options={"constraints": [models.UniqueConstraint(fields=["record"],
            condition=models.Q(revoked_at=None), name="one_current_manuscript_work")]}),
        migrations.RunSQL(TRIGGER, "DROP TRIGGER manuscript_committed_work ON public.records_record;"
                          " DROP FUNCTION public.publish_manuscript_work();"),
    ]
