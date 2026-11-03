"""Serialize pending AI writes with canonical source and access changes."""
from django.db import migrations


SQL = r"""
CREATE FUNCTION iris_authz.lock_processing_source() RETURNS TABLE
    (work_id uuid, record_id bigint, revision uuid, source_file text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE source_record bigint;
BEGIN
    SELECT s.record_id INTO source_record FROM iris_authz.processing_source() s;
    IF source_record IS NULL THEN RETURN; END IF;
    PERFORM 1 FROM public.records_record WHERE id = source_record FOR UPDATE;
    -- A fresh statement after the lock observes any invalidation we waited for.
    RETURN QUERY SELECT * FROM iris_authz.processing_source();
END $$;
REVOKE ALL ON FUNCTION iris_authz.lock_processing_source() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_ai_runtime') THEN
        GRANT EXECUTE ON FUNCTION iris_authz.lock_processing_source() TO iris_ai_runtime;
    END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [('publication', '0005_canonical_embargo_stamps')]
    operations = [migrations.RunSQL(SQL, 'DROP FUNCTION iris_authz.lock_processing_source();')]
