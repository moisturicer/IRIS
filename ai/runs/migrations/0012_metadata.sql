-- Named papers and exact metadata counts (IR-750, ADR-049 §5, §9).

-- A paper handle may name a Record with no Manuscript read yet; a passage handle never can.
ALTER TABLE iris_ai.research_handle ALTER COLUMN chunk_set_id DROP NOT NULL;
ALTER TABLE iris_ai.research_handle ADD CHECK (left(handle, 1) = 'R' OR chunk_set_id IS NOT NULL);

-- The typed facts a Turn stated: exact counts with the Records they counted, kept
-- private for the reopen recheck, and keyword samples, which are never totals.
ALTER TABLE iris_ai.turn ADD COLUMN facts jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Catalogue vocabulary only: names, no Record and no per-reader rows.
GRANT SELECT ON public.records_classification, public.records_pscedclassification,
    public.records_recordtype TO iris_ai_runtime;
