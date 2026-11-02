"""Extend the pinned verifier; leave legacy ingestion and reader contracts intact."""
from importlib import import_module
from django.db import migrations

previous = import_module("apps.ai.migrations.0037_reader_session_reads")
OLD = """    ELSIF p_purpose = 'ingestion' THEN
        IF claims->>'sub' IS NOT NULL OR claims->>'run' IS NOT NULL THEN RETURN NULL; END IF;"""
NEW = """    ELSIF p_purpose = 'ingestion' AND claims->>'wrk' IS NOT NULL THEN
        IF claims->>'sub' IS NOT NULL OR claims->>'run' IS NOT NULL
           OR claims->>'cnv' IS NOT NULL OR claims->>'job' IS NOT NULL
           OR claims->>'op' IS DISTINCT FROM 'local_extraction' THEN RETURN NULL; END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.publication_manuscriptwork w
            JOIN public.records_record canonical ON canonical.id = w.record_id
            WHERE w.id = (claims->>'wrk')::uuid AND w.revoked_at IS NULL
              AND w.record_id = (claims->>'rec')::bigint
              AND w.revision = (claims->>'rev')::uuid
              AND w.operation = claims->>'op'
              AND NOT canonical.is_deleted AND canonical.abstract_file = w.source_file
        ) THEN RETURN NULL; END IF;
""" + OLD
if previous.VERIFY.count(OLD) != 1:
    raise RuntimeError("IR-737 expected one ingestion verifier branch")
VERIFY = previous.VERIFY.replace(OLD, NEW)

FUNCTIONS = r"""
CREATE FUNCTION iris_authz.processing_source() RETURNS TABLE
    (work_id uuid, record_id bigint, revision uuid, source_file text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT w.id, w.record_id, w.revision, w.source_file
    FROM public.publication_manuscriptwork w,
         LATERAL (SELECT iris_authz.current_research_claims() AS c) bound
    WHERE bound.c->>'pur' = 'ingestion' AND bound.c->>'op' = 'local_extraction'
      AND w.id = (bound.c->>'wrk')::uuid AND w.revoked_at IS NULL
$$;
CREATE FUNCTION iris_authz.pending_manuscript_work(p_limit integer, p_after uuid) RETURNS TABLE
    (work_id uuid, grant_token text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT w.id, w.grant_token FROM public.publication_manuscriptwork w
    WHERE w.revoked_at IS NULL AND w.grant_expires_at > clock_timestamp()
      AND w.grant_token <> ''
      AND (p_after IS NULL OR w.id > p_after)
    ORDER BY w.id LIMIT greatest(0, least(p_limit, 1000))
$$;
REVOKE ALL ON FUNCTION iris_authz.processing_source() FROM PUBLIC;
REVOKE ALL ON FUNCTION iris_authz.pending_manuscript_work(integer, uuid) FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [("publication", "0001_manuscript_work"), ("ai", "0038_providerreservation_owner")]
    operations = [migrations.RunSQL(VERIFY, previous.VERIFY), migrations.RunSQL(FUNCTIONS,
        "DROP FUNCTION iris_authz.processing_source();"
        " DROP FUNCTION iris_authz.pending_manuscript_work(integer, uuid);")]
