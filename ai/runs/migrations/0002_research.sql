-- Local research tools (IR-719, ADR-049 §5, §9).

-- A Conversation keeps the Paper Chat scope it began with.
ALTER TABLE iris_ai.conversation ADD COLUMN scope_record_id bigint CHECK (scope_record_id >= 1);

-- The Manuscript revision a citation was read from: "<chunk set>:<extraction hash>".
ALTER TABLE iris_ai.citation ADD COLUMN revision text;

-- A Record or Passage the run was shown, bound to the source it was read from.
-- Resolves only within its run, until it expires, and while that source is active.
CREATE TABLE iris_ai.research_handle (
    handle         text PRIMARY KEY CHECK (handle ~ '^[RP][0-9a-f]{20}$'),
    run_id         uuid NOT NULL REFERENCES iris_ai.ask_run (id),
    record_id      bigint NOT NULL,
    chunk_set_id   bigint NOT NULL,
    chunk_id       bigint,
    CHECK ((left(handle, 1) = 'P') = (chunk_id IS NOT NULL)),
    expires_at     timestamptz NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX research_handle_run ON iris_ai.research_handle (run_id);
