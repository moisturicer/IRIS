-- Resume an interrupted AGENT investigation from its completed steps (IR-724, ADR-049 §12, §14).

-- The last completed step of a running run: the ordered Conversation with its
-- call ids, the Investigation's source pointers, the task and context it answers,
-- its pin and what it spent. Content; written only under the run's current fence
-- and removed when the run ends or its Conversation is deleted.
CREATE TABLE iris_ai.run_checkpoint (
    run_id    uuid PRIMARY KEY REFERENCES iris_ai.ask_run (id),
    -- The fence that wrote it; a later holder may only replace it.
    fence     bigint NOT NULL,
    step      integer NOT NULL CHECK (step >= 1),
    body      jsonb NOT NULL,
    saved_at  timestamptz NOT NULL DEFAULT now()
);
