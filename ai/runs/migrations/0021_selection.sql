-- Ask about a verified text selection (IR-581).
-- The passage a reader asked about: Record, Manuscript revision, page and quote,
-- stored once the runtime found the quote on that page of the indexed text.
-- Content: cleared with the Conversation's other content on deletion.
ALTER TABLE iris_ai.ask_run ADD COLUMN selection jsonb;
ALTER TABLE iris_ai.turn ADD COLUMN selection jsonb;

-- The Manuscript revision a Record's indexed text was read from, for this reader;
-- NULL when they cannot read it or nothing current is indexed. Mirrors
-- research_chunksets(): an active source wins, and the legacy chunk set
-- answers only for a Record that has none.
CREATE FUNCTION iris_ai.research_source_revision(p_record bigint) RETURNS text
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
DECLARE
    found text;
BEGIN
    IF EXISTS (SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=p_record) THEN
        SELECT j.revision::text INTO found
          FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id
         WHERE a.record_id=p_record AND j.state='complete'
           AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
           AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                      AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
        RETURN found;
    END IF;
    SELECT cs.source_revision::text INTO found
      FROM public.ai_chunkset cs WHERE cs.record_id=p_record AND cs.is_active;
    RETURN found;
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_source_revision(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_source_revision(bigint) TO iris_ai_runtime;
