"""Monotonic source/access fences and durable non-content cleanup facts."""
import uuid
from importlib import import_module
from django.db import migrations, models

initial = import_module("apps.publication.migrations.0001_manuscript_work")
PUBLISH = initial.TRIGGER.split("CREATE TRIGGER")[0].replace(
    "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION").replace(
    "'local_extraction', clock_timestamp(), '');",
    "'local_extraction', clock_timestamp(), '') ON CONFLICT (record_id, revision, operation) DO NOTHING;")

FENCES = r"""
CREATE FUNCTION public.invalidate_manuscript_work() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
DECLARE target bigint; why text;
BEGIN
    IF TG_TABLE_NAME = 'publication_manuscriptwork' THEN
        INSERT INTO public.publication_manuscriptinvalidation(id, record_id, work_id, reason, created_at)
        VALUES (gen_random_uuid(), OLD.record_id, OLD.id, 'deleted', clock_timestamp())
        ON CONFLICT (work_id, reason) DO NOTHING;
        RETURN OLD;
    END IF;
    IF TG_TABLE_NAME = 'records_recordowner' THEN
        IF TG_OP = 'UPDATE' AND OLD.user_id = NEW.user_id AND OLD.record_id = NEW.record_id THEN
            RETURN NEW;
        END IF;
        target := OLD.record_id; why := 'access';
        PERFORM 1 FROM public.records_record WHERE id = target FOR UPDATE;
    ELSE
        target := OLD.id;
        IF TG_OP = 'DELETE' THEN why := 'deleted';
        ELSIF NEW.is_deleted THEN why := 'deleted';
        ELSIF NEW.abstract_file IS DISTINCT FROM OLD.abstract_file
           OR to_jsonb(NEW)->>'manuscript_revision' IS DISTINCT FROM to_jsonb(OLD)->>'manuscript_revision'
           THEN why := 'replaced';
        ELSIF NEW.pipeline_status IS DISTINCT FROM OLD.pipeline_status
           OR NEW.adviser_id IS DISTINCT FROM OLD.adviser_id
           OR to_jsonb(NEW)->'embargo_state' IS DISTINCT FROM to_jsonb(OLD)->'embargo_state'
           THEN why := 'access';
        ELSE RETURN NEW;
        END IF;
    END IF;
    INSERT INTO public.publication_manuscriptinvalidation(id, record_id, work_id, reason, created_at)
        SELECT gen_random_uuid(), w.record_id, w.id, why, clock_timestamp()
        FROM public.publication_manuscriptwork w WHERE w.record_id = target
          AND (w.revoked_at IS NULL OR why = 'deleted')
        ON CONFLICT (work_id, reason) DO NOTHING;
    UPDATE public.publication_manuscriptwork SET revoked_at = clock_timestamp(),
        grant_token = '', grant_expires_at = NULL WHERE record_id = target AND revoked_at IS NULL;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER manuscript_access_fence BEFORE UPDATE OR DELETE ON public.records_record
FOR EACH ROW EXECUTE FUNCTION public.invalidate_manuscript_work();
CREATE TRIGGER manuscript_owner_fence AFTER UPDATE OR DELETE ON public.records_recordowner
FOR EACH ROW EXECUTE FUNCTION public.invalidate_manuscript_work();
CREATE TRIGGER manuscript_work_delete BEFORE DELETE ON public.publication_manuscriptwork
FOR EACH ROW EXECUTE FUNCTION public.invalidate_manuscript_work();
REVOKE ALL ON FUNCTION public.invalidate_manuscript_work() FROM PUBLIC;

CREATE FUNCTION iris_authz.manuscript_invalidations(p_limit integer, p_after uuid) RETURNS TABLE
    (event_id uuid, record_id bigint, work_id uuid, reason text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT i.id, i.record_id, i.work_id, i.reason::text
    FROM public.publication_manuscriptinvalidation i
    WHERE p_after IS NULL OR i.id > p_after
    ORDER BY i.id LIMIT greatest(0, least(p_limit, 1000))
$$;
REVOKE ALL ON FUNCTION iris_authz.manuscript_invalidations(integer, uuid) FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0002_processing_authority")]
    operations = [
        migrations.AddConstraint(model_name="manuscriptwork", constraint=models.UniqueConstraint(
            fields=["record", "revision", "operation"], name="unique_manuscript_work_revision")),
        migrations.CreateModel(name="ManuscriptInvalidation", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("record_id", models.BigIntegerField()), ("work_id", models.UUIDField()),
            ("reason", models.CharField(max_length=32)), ("created_at", models.DateTimeField(auto_now_add=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=["work_id", "reason"],
            name="unique_manuscript_invalidation")]}),
        migrations.RunSQL(PUBLISH, initial.TRIGGER.split("CREATE TRIGGER")[0].replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")),
        migrations.RunSQL(FENCES, "DROP FUNCTION iris_authz.manuscript_invalidations(integer, uuid);"
            " DROP TRIGGER manuscript_access_fence ON public.records_record;"
            " DROP TRIGGER manuscript_owner_fence ON public.records_recordowner;"
            " DROP TRIGGER manuscript_work_delete ON public.publication_manuscriptwork;"
            " DROP FUNCTION public.invalidate_manuscript_work();"),
    ]
