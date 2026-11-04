-- Compact handoffs that let a long Conversation continue (IR-734, ADR-049 §19, §21).

-- One row per committed compaction, numbered within its Conversation. A
-- handoff is derived content: written only under its run's current fence while
-- the Conversation stands at the revision the run started from, and removed
-- with the Conversation. The original Turns it compacts stay where they are.
CREATE TABLE iris_ai.conversation_handoff (
    conversation_id  uuid NOT NULL REFERENCES iris_ai.conversation (id),
    revision         integer NOT NULL CHECK (revision >= 1),
    run_id           uuid NOT NULL REFERENCES iris_ai.ask_run (id),
    fence            bigint NOT NULL,
    -- The Conversation revision it was built at; a later Turn stays in the suffix.
    base_revision    integer NOT NULL CHECK (base_revision >= 0),
    -- The newest original Turn it compacts; 0 when only its run's exchanges.
    through_ordinal  integer NOT NULL CHECK (through_ordinal >= 0),
    turns            integer[] NOT NULL,
    -- Manuscript revisions its findings depend on, as `chunk_set:extraction_hash`.
    sources          text[] NOT NULL,
    format           text NOT NULL,
    -- Model, endpoint, dialect and versions it was written under; never replayed as native state.
    binding          jsonb NOT NULL,
    usage            jsonb NOT NULL,
    body             jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, revision)
);
CREATE INDEX conversation_handoff_run ON iris_ai.conversation_handoff (run_id);
