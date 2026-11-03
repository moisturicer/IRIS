-- One AI writer; pending output and completed paid batches are immutable.
CREATE TABLE iris_ai.index_job (
    id bigserial PRIMARY KEY,
    work_id uuid NOT NULL, revision uuid NOT NULL, record_id bigint NOT NULL,
    generation bigint NOT NULL, pipeline text NOT NULL,
    space_id bigint NOT NULL, model text NOT NULL, dimensions integer NOT NULL CHECK(dimensions=1024),
    input_hash text NOT NULL, payload jsonb NOT NULL, allowance jsonb NOT NULL,
    state text NOT NULL CHECK(state IN ('running','complete')),
    attempt uuid NOT NULL, lease_until timestamptz NOT NULL,
    UNIQUE(work_id,generation,pipeline,space_id,input_hash)
);
CREATE TABLE iris_ai.embedding_batch (
    job_id bigint NOT NULL REFERENCES iris_ai.index_job(id), ordinal integer NOT NULL,
    vectors jsonb NOT NULL, reservation_id bigint NOT NULL,
    PRIMARY KEY(job_id,ordinal)
);
CREATE TABLE iris_ai.active_source (
    record_id bigint PRIMARY KEY, job_id bigint NOT NULL REFERENCES iris_ai.index_job(id)
);

-- Resolve institutional authority at execution, allowing independent schema rollback.
CREATE FUNCTION iris_ai.indexed_source_current(w uuid,r uuid,g bigint) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    IF to_regprocedure('iris_authz.indexed_source_current(uuid,uuid,bigint)') IS NULL THEN RETURN false; END IF;
    RETURN iris_authz.indexed_source_current(w,r,g);
EXCEPTION WHEN undefined_function OR invalid_schema_name THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION iris_ai.indexed_source_current(uuid,uuid,bigint) FROM PUBLIC;

ALTER TABLE iris_ai.index_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE iris_ai.embedding_batch ENABLE ROW LEVEL SECURITY;
ALTER TABLE iris_ai.active_source ENABLE ROW LEVEL SECURITY;
CREATE POLICY job_processing ON iris_ai.index_job TO iris_ai_runtime
    USING(work_id IN (SELECT s.work_id FROM iris_ai.processing_source() s))
    WITH CHECK(work_id IN (SELECT s.work_id FROM iris_ai.processing_source() s));
CREATE POLICY job_read ON iris_ai.index_job FOR SELECT TO iris_ai_runtime
    USING(state='complete' AND iris_ai.indexed_source_current(work_id,revision,generation));
CREATE POLICY batch_read ON iris_ai.embedding_batch FOR SELECT TO iris_ai_runtime
    USING(job_id IN (SELECT id FROM iris_ai.index_job));
CREATE POLICY batch_processing ON iris_ai.embedding_batch FOR INSERT TO iris_ai_runtime
    WITH CHECK(job_id IN (SELECT j.id FROM iris_ai.index_job j
        JOIN iris_ai.processing_source() s ON s.work_id=j.work_id));
-- Completion is checked by the database as well as the worker.
CREATE FUNCTION iris_ai.complete_index(p_job bigint) RETURNS boolean
LANGUAGE sql SET search_path=pg_catalog,pg_temp AS $$
    SELECT EXISTS(SELECT 1 FROM iris_ai.index_job j WHERE j.id=p_job AND j.state='complete'
      AND jsonb_array_length(j.payload->'windows')>1
      AND (j.payload->'windows'->>0)::integer=1
      AND (SELECT sum(x::integer) FROM jsonb_array_elements_text(j.payload->'windows') x)
          =jsonb_array_length(j.payload->'chunks')+1
      AND (SELECT count(*) FROM iris_ai.embedding_batch b WHERE b.job_id=j.id)
          =jsonb_array_length(j.payload->'windows')
      AND NOT EXISTS(SELECT 1 FROM iris_ai.embedding_batch b WHERE b.job_id=j.id AND
        (b.ordinal<0 OR b.ordinal>=jsonb_array_length(j.payload->'windows')
         OR jsonb_array_length(b.vectors)<>(j.payload->'windows'->>b.ordinal)::integer
         OR EXISTS(SELECT 1 FROM jsonb_array_elements(b.vectors) v
                   WHERE public.vector_dims(v::text::public.vector)<>j.dimensions
                      OR public.vector_norm(v::text::public.vector)=0))))
$$;
REVOKE ALL ON FUNCTION iris_ai.complete_index(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.complete_index(bigint) TO iris_ai_runtime;
CREATE POLICY source_processing ON iris_ai.active_source TO iris_ai_runtime
    USING(record_id IN (SELECT s.record_id FROM iris_ai.processing_source() s))
    WITH CHECK(EXISTS(SELECT 1 FROM iris_ai.index_job j WHERE j.id=job_id
        AND j.record_id=active_source.record_id AND iris_ai.complete_index(j.id)
        AND EXISTS(SELECT 1 FROM iris_ai.processing_source() s WHERE s.work_id=j.work_id)
        AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)));
REVOKE ALL ON iris_ai.index_job,iris_ai.embedding_batch,iris_ai.active_source FROM PUBLIC;
GRANT SELECT,INSERT ON iris_ai.index_job,iris_ai.embedding_batch TO iris_ai_runtime;
GRANT UPDATE(state,attempt,lease_until) ON iris_ai.index_job TO iris_ai_runtime;
GRANT SELECT,INSERT ON iris_ai.active_source TO iris_ai_runtime;
GRANT UPDATE(job_id) ON iris_ai.active_source TO iris_ai_runtime;
GRANT USAGE ON SEQUENCE iris_ai.index_job_id_seq TO iris_ai_runtime;
GRANT EXECUTE ON FUNCTION iris_ai.indexed_source_current(uuid,uuid,bigint) TO iris_ai_runtime;

-- Transitional read projection, never a second writer into Django's tables.
-- Negative derived identifiers cannot collide with the existing positive IDs.
CREATE FUNCTION iris_ai.research_chunksets() RETURNS TABLE
    (id bigint,record_id bigint,extraction_hash text,is_active boolean)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY SELECT -j.id,j.record_id,j.payload->>'extraction_hash',true
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id
      WHERE j.state='complete' AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
      AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                 AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
    RETURN QUERY SELECT cs.id,cs.record_id,cs.extraction_hash::text,cs.is_active
      FROM public.ai_chunkset cs WHERE NOT EXISTS (
        SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=cs.record_id);
END $$;
CREATE FUNCTION iris_ai.research_chunks() RETURNS TABLE
    (id bigint,record_id bigint,chunk_set_id bigint,source_page integer,content text,
     context_path text[],search_vector tsvector,sequence integer,deleted_at timestamptz)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY SELECT -(j.id*1000000+c.n),j.record_id,-j.id,(c.value->>'source_page')::integer,
      c.value->>'content',ARRAY(SELECT jsonb_array_elements_text(c.value->'context_path')),
      to_tsvector('english',c.value->>'content'),(c.n-1)::integer,NULL::timestamptz
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id,
      LATERAL jsonb_array_elements(j.payload->'chunks') WITH ORDINALITY c(value,n)
      WHERE j.state='complete' AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
      AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                 AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
    RETURN QUERY SELECT c.id,c.record_id,c.chunk_set_id,c.source_page,c.content,c.context_path::text[],
      c.search_vector,c.sequence,c.deleted_at FROM public.ai_documentchunk c
      WHERE NOT EXISTS (SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=c.record_id);
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_chunksets(),iris_ai.research_chunks() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_chunksets(),iris_ai.research_chunks() TO iris_ai_runtime;

CREATE OR REPLACE FUNCTION iris_ai.manuscript_processing(p_work uuid,p_generation bigint) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
    SELECT coalesce(
      (SELECT CASE WHEN j.state='complete' AND EXISTS(SELECT 1 FROM iris_ai.active_source a WHERE a.job_id=j.id)
                   THEN 'ready' WHEN j.lease_until>clock_timestamp() THEN 'indexing'
                   ELSE 'extracted_pending' END
       FROM iris_ai.index_job j WHERE j.work_id=p_work AND j.generation=p_generation ORDER BY j.id DESC LIMIT 1),
      (SELECT CASE WHEN state='extracted' THEN 'extracted_pending'
                   WHEN state='running' AND lease_until>clock_timestamp() THEN 'processing'
                   WHEN state='running' THEN 'pending_processing' ELSE state END
       FROM iris_ai.extraction_job WHERE work_id=p_work AND generation=p_generation
       ORDER BY started_at DESC,pipeline LIMIT 1))
$$;

CREATE FUNCTION iris_ai.readable_record_ids() RETURNS bigint[]
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    IF to_regprocedure('iris_authz.research_record_ids()') IS NULL THEN RETURN '{}'; END IF;
    RETURN iris_authz.research_record_ids();
EXCEPTION WHEN undefined_function OR invalid_schema_name THEN RETURN '{}';
END $$;
REVOKE ALL ON FUNCTION iris_ai.readable_record_ids() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.readable_record_ids() TO iris_ai_runtime;
CREATE POLICY source_reader ON iris_ai.active_source FOR SELECT TO iris_ai_runtime
    USING(record_id=ANY(iris_ai.readable_record_ids()));
GRANT SELECT ON public.ai_embeddingspace TO iris_ai_runtime;

CREATE FUNCTION iris_ai.research_vectors(p_space bigint) RETURNS TABLE(chunk_id bigint,embedding public.vector)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY WITH flattened AS (
      SELECT j.id, v.value, row_number() OVER(PARTITION BY j.id ORDER BY b.ordinal,v.n) AS n
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id
      JOIN iris_ai.embedding_batch b ON b.job_id=j.id AND b.ordinal>0,
           LATERAL jsonb_array_elements(b.vectors) WITH ORDINALITY v(value,n)
      WHERE j.space_id=p_space AND j.state='complete'
        AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
        AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                   AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine'))
      SELECT -(f.id*1000000+f.n),f.value::text::public.vector FROM flattened f;
    RETURN QUERY SELECT e.chunk_id,e.embedding FROM public.ai_chunkembedding e
      JOIN public.ai_documentchunk c ON c.id=e.chunk_id WHERE e.space_id=p_space
      AND NOT EXISTS(SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=c.record_id);
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_vectors(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_vectors(bigint) TO iris_ai_runtime;

CREATE FUNCTION iris_ai.research_record_vectors(p_space bigint) RETURNS TABLE(record_id bigint,embedding public.vector)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY SELECT j.record_id,(b.vectors->0)::text::public.vector
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id
      JOIN iris_ai.embedding_batch b ON b.job_id=j.id AND b.ordinal=0
      WHERE j.space_id=p_space AND j.state='complete'
        AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
        AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                   AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
    RETURN QUERY SELECT e.record_id,e.embedding FROM public.ai_recordembedding e
      JOIN public.ai_embeddingspace es ON es.model_id=e.model_name AND es.id=p_space AND es.state='active'
      WHERE NOT EXISTS(SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=e.record_id);
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_record_vectors(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_record_vectors(bigint) TO iris_ai_runtime;
