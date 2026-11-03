ALTER TABLE iris_ai.manuscript_receipt ADD COLUMN authority_generation bigint NOT NULL DEFAULT 0;
CREATE FUNCTION iris_ai.manuscript_acknowledged(p_work uuid, p_generation bigint) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM iris_ai.manuscript_receipt
                   WHERE work_id = p_work AND authority_generation = p_generation)
$$;
REVOKE ALL ON FUNCTION iris_ai.manuscript_acknowledged(uuid, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.manuscript_acknowledged(uuid, bigint) TO iris_django_runtime;
