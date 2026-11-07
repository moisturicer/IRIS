-- Reading one whole Manuscript in document order (IR-733, ADR-049 §9).

-- One chunk set's passages with their element kinds, from whichever source is
-- active; invoker rights, so the row policy decides what is readable.
CREATE FUNCTION iris_ai.research_manuscript(p_chunk_set bigint) RETURNS TABLE
    (id bigint,record_id bigint,source_page integer,content text,context_path text[],
     sequence integer,element_kinds text[])
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    IF p_chunk_set < 0 THEN
        RETURN QUERY SELECT -(j.id*1000000+c.n),j.record_id,(c.value->>'source_page')::integer,
          c.value->>'content',ARRAY(SELECT jsonb_array_elements_text(c.value->'context_path')),
          (c.n-1)::integer,ARRAY(SELECT jsonb_array_elements_text(coalesce(c.value->'element_kinds','[]')))
          FROM iris_ai.research_chunksets() cs
          JOIN iris_ai.index_job j ON j.id=-cs.id,
          LATERAL jsonb_array_elements(j.payload->'chunks') WITH ORDINALITY c(value,n)
          WHERE cs.id=p_chunk_set AND cs.is_active;
    ELSE
        RETURN QUERY SELECT c.id,c.record_id,c.source_page,c.content,c.context_path::text[],
          c.sequence::integer,c.element_kinds::text[]
          FROM public.ai_documentchunk c
          WHERE c.chunk_set_id=p_chunk_set AND c.deleted_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=c.record_id);
    END IF;
END $$;

-- How many pages the extraction reported for a chunk set; NULL when it did not say.
CREATE FUNCTION iris_ai.research_manuscript_pages(p_chunk_set bigint) RETURNS integer
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
DECLARE sizes jsonb;
BEGIN
    IF p_chunk_set < 0 THEN
        SELECT j.payload->'document'->'page_sizes' INTO sizes
          FROM iris_ai.research_chunksets() cs JOIN iris_ai.index_job j ON j.id=-cs.id
         WHERE cs.id=p_chunk_set AND cs.is_active;
    ELSE
        SELECT cs.page_sizes INTO sizes FROM public.ai_chunkset cs
         WHERE cs.id=p_chunk_set AND cs.is_active
           AND NOT EXISTS (SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=cs.record_id);
    END IF;
    IF sizes IS NULL OR jsonb_typeof(sizes)<>'object' OR sizes='{}'::jsonb THEN RETURN NULL; END IF;
    RETURN (SELECT max(key::integer) FROM jsonb_object_keys(sizes) key WHERE key ~ '^[0-9]+$');
END $$;

REVOKE ALL ON FUNCTION iris_ai.research_manuscript(bigint),iris_ai.research_manuscript_pages(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_manuscript(bigint),iris_ai.research_manuscript_pages(bigint)
    TO iris_ai_runtime;
