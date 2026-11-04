-- A dead lease is pending recovery. Pipeline selection follows claim order,
-- not lease length, so an older slow profile cannot mask a newer outcome.
ALTER TABLE iris_ai.extraction_job ADD COLUMN started_at timestamptz NOT NULL DEFAULT clock_timestamp();
CREATE OR REPLACE FUNCTION iris_ai.manuscript_processing(p_work uuid, p_generation bigint) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT CASE WHEN state = 'extracted' THEN 'extracted_pending'
                WHEN state = 'running' AND lease_until <= clock_timestamp() THEN 'pending_processing'
                WHEN state = 'running' THEN 'processing'
                ELSE state END
    FROM iris_ai.extraction_job
    WHERE work_id = p_work AND generation = p_generation
    ORDER BY started_at DESC, pipeline LIMIT 1
$$;
