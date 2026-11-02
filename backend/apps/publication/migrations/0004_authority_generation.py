"""Invalidate old authority without discarding current revision work (IR-737)."""
from importlib import import_module
from django.db import migrations, models

access = import_module("apps.publication.migrations.0003_access_and_invalidation")
authority = import_module("apps.publication.migrations.0002_processing_authority")

OLD_UPDATE = """    UPDATE public.publication_manuscriptwork SET revoked_at = clock_timestamp(),
        grant_token = '', grant_expires_at = NULL WHERE record_id = target AND revoked_at IS NULL;"""
NEW_UPDATE = """    IF why = 'access' THEN
        UPDATE public.publication_manuscriptwork SET authority_generation = authority_generation + 1,
            grant_token = '', grant_expires_at = NULL WHERE record_id = target AND revoked_at IS NULL;
    ELSE
""" + OLD_UPDATE + "\n    END IF;"

PREVIOUS_FENCE = access.FENCES.split("CREATE TRIGGER")[0].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
FENCE = PREVIOUS_FENCE.replace(OLD_UPDATE, NEW_UPDATE).replace(
    "work_id, reason, created_at)", "work_id, reason, authority_generation, created_at)").replace(
    "OLD.id, 'deleted', clock_timestamp()", "OLD.id, 'deleted', OLD.authority_generation, clock_timestamp()").replace(
    "w.id, why, clock_timestamp()", "w.id, why, w.authority_generation, clock_timestamp()").replace(
    "ON CONFLICT (work_id, reason)", "ON CONFLICT (work_id, authority_generation, reason)")

VERIFY = authority.VERIFY.replace("AND w.operation = claims->>'op'",
    "AND w.operation = claims->>'op' AND w.authority_generation = (claims->>'wgen')::bigint")
PUBLISH = access.PUBLISH.replace("operation, created_at, grant_token)",
    "operation, created_at, grant_token, authority_generation)").replace(
    "'local_extraction', clock_timestamp(), '') ON", "'local_extraction', clock_timestamp(), '', 0) ON")

FACTS = r"""
DROP FUNCTION iris_authz.manuscript_invalidations(integer, uuid);
CREATE FUNCTION iris_authz.manuscript_invalidations(p_limit integer, p_after uuid) RETURNS TABLE
    (event_id uuid, record_id bigint, work_id uuid, reason text, authority_generation bigint)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT i.id, i.record_id, i.work_id, i.reason::text, i.authority_generation
    FROM public.publication_manuscriptinvalidation i
    WHERE p_after IS NULL OR i.id > p_after
    ORDER BY i.id LIMIT greatest(0, least(p_limit, 1000))
$$;
REVOKE ALL ON FUNCTION iris_authz.manuscript_invalidations(integer, uuid) FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0003_access_and_invalidation")]
    operations = [
        migrations.AddField(model_name="manuscriptwork", name="authority_generation",
                            field=models.PositiveBigIntegerField(default=0, editable=False)),
        migrations.AddField(model_name="manuscriptinvalidation", name="authority_generation",
                            field=models.PositiveBigIntegerField(default=0, editable=False)),
        migrations.RemoveConstraint(model_name="manuscriptinvalidation", name="unique_manuscript_invalidation"),
        migrations.AddConstraint(model_name="manuscriptinvalidation", constraint=models.UniqueConstraint(
            fields=["work_id", "authority_generation", "reason"], name="unique_manuscript_invalidation")),
        migrations.RunSQL(FENCE, PREVIOUS_FENCE),
        migrations.RunSQL(PUBLISH, access.PUBLISH),
        migrations.RunSQL(VERIFY, authority.VERIFY),
        migrations.RunSQL(FACTS, "DROP FUNCTION iris_authz.manuscript_invalidations(integer, uuid);" +
            access.FENCES[access.FENCES.index("CREATE FUNCTION iris_authz.manuscript_invalidations"):]),
    ]
