-- The runtime's Record-stage vectors come from the active Embedding Space (IR-739, ADR-049 §23).

-- research_record_vectors read the legacy ai_recordembedding table, one vector per Record with no
-- space key, and matched it to the space only by model name. That cannot say which space a vector
-- belongs to, so once a second space can go live the Record stage and the Passage stage
-- (research_vectors, keyed by space) could disagree. The legacy branch now reads the space-keyed
-- ai_recordspaceembedding for exactly p_space, and only while that space is the active one, so the
-- two stages of one search are always one space and a promotion or rollback moves them together.
-- The first branch (vectors this runtime indexed itself) is unchanged. Additive: the legacy table
-- stays until the contract phase.

CREATE OR REPLACE FUNCTION iris_ai.research_record_vectors(p_space bigint) RETURNS TABLE(record_id bigint,embedding public.vector)
LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS $$
BEGIN
    RETURN QUERY SELECT j.record_id,(b.vectors->0)::text::public.vector
      FROM iris_ai.index_job j JOIN iris_ai.active_source a ON a.job_id=j.id
      JOIN iris_ai.embedding_batch b ON b.job_id=j.id AND b.ordinal=0
      WHERE j.space_id=p_space AND j.state='complete'
        AND iris_ai.indexed_source_current(j.work_id,j.revision,j.generation)
        AND EXISTS(SELECT 1 FROM public.ai_embeddingspace es WHERE es.id=j.space_id AND es.state='active'
                   AND es.model_id=j.model AND es.dimensions=j.dimensions AND es.metric='cosine');
    RETURN QUERY SELECT e.record_id,e.embedding FROM public.ai_recordspaceembedding e
      JOIN public.ai_embeddingspace es ON es.id=e.space_id AND es.id=p_space AND es.state='active'
      WHERE NOT EXISTS(SELECT 1 FROM iris_ai.active_source a WHERE a.record_id=e.record_id);
END $$;
REVOKE ALL ON FUNCTION iris_ai.research_record_vectors(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION iris_ai.research_record_vectors(bigint) TO iris_ai_runtime;
