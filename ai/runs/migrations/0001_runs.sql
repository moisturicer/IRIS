-- AI-owned runs and Conversations (IR-722, ADR-049 §1, §10, §21).
-- The AI runtime is this schema's only migration owner and writer.
-- Reader ids are Django's; no foreign key crosses owners.
-- The migrator creates the schema itself.

CREATE TABLE iris_ai.conversation (
    id          uuid PRIMARY KEY,
    reader_id   bigint NOT NULL,
    revision    integer NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- Set first on deletion: fences access and every later write.
    deleted_at  timestamptz
);
CREATE INDEX conversation_reader ON iris_ai.conversation (reader_id);

CREATE TABLE iris_ai.ask_run (
    id               uuid PRIMARY KEY,
    reader_id        bigint NOT NULL,
    conversation_id  uuid NOT NULL REFERENCES iris_ai.conversation (id),
    request_key      text NOT NULL CHECK (length(request_key) BETWEEN 8 AND 128),
    request_hash     text NOT NULL,
    -- Content; cleared on deletion.
    question         text,
    base_revision    integer NOT NULL CHECK (base_revision >= 0),
    state            text NOT NULL DEFAULT 'queued' CHECK (state IN (
                         'queued', 'running', 'completed', 'cancelled',
                         'conflict', 'expired', 'failed', 'deleted')),
    end_reason       text,
    -- Fixed at admission; recovery never moves either.
    deadline_at      timestamptz NOT NULL,
    allowance        jsonb NOT NULL,
    pinned           jsonb NOT NULL,
    -- Only the holder of the current fence may advance the run.
    fence            bigint NOT NULL DEFAULT 0,
    lease_owner      text,
    lease_expires_at timestamptz,
    version          integer NOT NULL DEFAULT 1,
    turn_id          uuid,
    created_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    UNIQUE (reader_id, request_key)
);
-- One state-advancing run per Conversation.
CREATE UNIQUE INDEX ask_run_one_active ON iris_ai.ask_run (conversation_id)
    WHERE state IN ('queued', 'running');

CREATE TABLE iris_ai.turn (
    id               uuid PRIMARY KEY,
    conversation_id  uuid NOT NULL REFERENCES iris_ai.conversation (id),
    run_id           uuid NOT NULL UNIQUE REFERENCES iris_ai.ask_run (id),
    ordinal          integer NOT NULL CHECK (ordinal >= 1),
    question         text NOT NULL,
    answer           text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, ordinal)
);
ALTER TABLE iris_ai.ask_run
    ADD CONSTRAINT ask_run_turn FOREIGN KEY (turn_id) REFERENCES iris_ai.turn (id) ON DELETE SET NULL;

CREATE TABLE iris_ai.citation (
    turn_id    uuid NOT NULL REFERENCES iris_ai.turn (id) ON DELETE CASCADE,
    position   integer NOT NULL CHECK (position >= 1),
    record_id  bigint NOT NULL,
    page       integer CHECK (page >= 1),
    quote      text NOT NULL,
    PRIMARY KEY (turn_id, position)
);

-- The run's public journal: names, codes and ids; never reasoning.
CREATE TABLE iris_ai.run_event (
    run_id      uuid NOT NULL REFERENCES iris_ai.ask_run (id),
    sequence    integer NOT NULL CHECK (sequence >= 1),
    name        text NOT NULL,
    data        jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, sequence)
);

-- Non-content attempt accounting. No foreign key: it outlives deletion.
CREATE TABLE iris_ai.attempt_accounting (
    id              bigserial PRIMARY KEY,
    run_id          uuid NOT NULL,
    fence           bigint NOT NULL,
    executor        text NOT NULL,
    reserved_units  bigint NOT NULL CHECK (reserved_units >= 0),
    reported_units  bigint CHECK (reported_units >= 0),
    outcome         text NOT NULL DEFAULT 'reserved',
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, fence)
);
