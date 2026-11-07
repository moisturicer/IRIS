-- Pending local output only. No active pointer, embeddings or legacy writer transfer.
CREATE TABLE iris_ai.extraction_job (
    work_id uuid NOT NULL,
    pipeline text NOT NULL,
    generation bigint NOT NULL,
    attempt uuid NOT NULL,
    state text NOT NULL CHECK (state IN ('running', 'extracted', 'incomplete', 'failed')),
    lease_until timestamptz NOT NULL,
    PRIMARY KEY (work_id, pipeline)
);
CREATE TABLE iris_ai.extraction_revision (
    work_id uuid NOT NULL,
    pipeline text NOT NULL,
    revision uuid NOT NULL,
    record_id bigint NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (work_id, pipeline)
);
REVOKE ALL ON iris_ai.extraction_job, iris_ai.extraction_revision FROM PUBLIC;
ALTER TABLE iris_ai.extraction_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE iris_ai.extraction_revision ENABLE ROW LEVEL SECURITY;
CREATE POLICY processing_job ON iris_ai.extraction_job TO iris_ai_runtime
    USING (work_id IN (SELECT s.work_id FROM iris_authz.processing_source() s))
    WITH CHECK (work_id IN (SELECT s.work_id FROM iris_authz.processing_source() s));
CREATE POLICY processing_revision ON iris_ai.extraction_revision TO iris_ai_runtime
    USING (work_id IN (SELECT s.work_id FROM iris_authz.processing_source() s))
    WITH CHECK (EXISTS (SELECT 1 FROM iris_authz.processing_source() s
        WHERE s.work_id = extraction_revision.work_id AND s.revision = extraction_revision.revision
          AND s.record_id = extraction_revision.record_id));

CREATE FUNCTION iris_ai.manuscript_processing(p_work uuid, p_generation bigint) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT CASE WHEN state = 'extracted' THEN 'extracted_pending'
                WHEN state = 'running' THEN 'processing'
                ELSE state END
    FROM iris_ai.extraction_job
    WHERE work_id = p_work AND generation = p_generation
    ORDER BY lease_until DESC, pipeline LIMIT 1
$$;
REVOKE ALL ON FUNCTION iris_ai.manuscript_processing(uuid, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.manuscript_processing(uuid, bigint) TO iris_django_runtime;
