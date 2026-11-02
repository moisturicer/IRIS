-- AI receipts acknowledge committed work, not extraction/index publication (IR-737).
CREATE TABLE iris_ai.manuscript_receipt (
    work_id uuid PRIMARY KEY,
    record_id bigint NOT NULL,
    revision uuid NOT NULL,
    acknowledged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON iris_ai.manuscript_receipt FROM PUBLIC;

CREATE FUNCTION iris_ai.manuscript_acknowledged(p_work uuid) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM iris_ai.manuscript_receipt WHERE work_id = p_work)
$$;
REVOKE ALL ON FUNCTION iris_ai.manuscript_acknowledged(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA iris_ai TO iris_django_runtime;
GRANT EXECUTE ON FUNCTION iris_ai.manuscript_acknowledged(uuid) TO iris_django_runtime;
