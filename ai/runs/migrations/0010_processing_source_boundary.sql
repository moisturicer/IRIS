-- Keep institutional schema rollback independent of the AI-owned dataset.
-- PL/pgSQL resolves the authority function at execution, rather than leaving
-- AI row policies with a durable dependency on a Django-owned function.
CREATE FUNCTION iris_ai.processing_source() RETURNS TABLE
    (work_id uuid, record_id bigint, revision uuid, source_file text)
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    IF to_regprocedure('iris_authz.processing_source()') IS NULL THEN RETURN; END IF;
    RETURN QUERY SELECT * FROM iris_authz.processing_source();
EXCEPTION WHEN undefined_function OR invalid_schema_name THEN
    RETURN;
END $$;
REVOKE ALL ON FUNCTION iris_ai.processing_source() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.processing_source() TO iris_ai_runtime;

DROP POLICY processing_job ON iris_ai.extraction_job;
CREATE POLICY processing_job ON iris_ai.extraction_job TO iris_ai_runtime
    USING (work_id IN (SELECT s.work_id FROM iris_ai.processing_source() s))
    WITH CHECK (work_id IN (SELECT s.work_id FROM iris_ai.processing_source() s));
DROP POLICY processing_revision ON iris_ai.extraction_revision;
CREATE POLICY processing_revision ON iris_ai.extraction_revision TO iris_ai_runtime
    USING (work_id IN (SELECT s.work_id FROM iris_ai.processing_source() s))
    WITH CHECK (EXISTS (SELECT 1 FROM iris_ai.processing_source() s
        WHERE s.work_id = extraction_revision.work_id AND s.revision = extraction_revision.revision
          AND s.record_id = extraction_revision.record_id));
