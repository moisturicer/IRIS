-- Token counts and section keys for passage selection (IR-397, IR-1055). Same rows, same policy.

DROP FUNCTION iris_ai.research_chunks();
CREATE FUNCTION iris_ai.research_chunks() RETURNS TABLE
    (id bigint,record_id bigint,chunk_set_id bigint,source_page integer,content text,
     context_path text[],search_vector tsvector,sequence integer,deleted_at timestamptz,
     token_count integer,section_key jsonb)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY SELECT -(j.id*1000000+c.n),j.record_id,-j.id,(c.value->>'source_page')::integer,
      c.value->>'content',ARRAY(SELECT jsonb_array_elements_text(c.value->'context_path')),
      to_tsvector('english',c.value->>'content'),(c.n-1)::integer,NULL::timestamptz,
      (c.value->>'token_count')::integer,c.value->'section_key'
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id,
      LATERAL jsonb_array_elements(j.payload->'chunks') WITH ORDINALITY c(value,n)
      WHERE j.state='complete' AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
      AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                 AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
    RETURN QUERY SELECT c.id,c.record_id,c.chunk_set_id,c.source_page,c.content,c.context_path::text[],
      c.search_vector,c.sequence,c.deleted_at,c.token_count::integer,c.section_key
      FROM public.ai_documentchunk c
      WHERE NOT EXISTS (SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=c.record_id);
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_chunks() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_chunks() TO iris_ai_runtime;
