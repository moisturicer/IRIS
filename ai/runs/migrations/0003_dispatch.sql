-- Durable queue dispatch (IR-723, ADR-049 §2, §3, §12).
-- A queued run row is the durable work; a Redis wakeup only hints at it.

ALTER TABLE iris_ai.ask_run
    ADD COLUMN depth text NOT NULL DEFAULT 'ordinary' CHECK (depth IN ('ordinary', 'deep')),
    -- First claim; queue wait is started_at - created_at.
    ADD COLUMN started_at timestamptz,
    -- The submitting reader_session grant, renewed on reconnect and cleared
    -- when the run ends. A worker reads as the reader only while it is valid.
    ADD COLUMN reader_grant text,
    ADD COLUMN grant_expires_at timestamptz;

CREATE INDEX ask_run_dispatch ON iris_ai.ask_run (created_at)
    WHERE state IN ('queued', 'running');
