-- A reader's explicit Retry links a new run to the one that ended without an answer (IR-726, ADR-049 §11).

-- The run this one retries. A new AskRun with its own identity, deadline, allowance
-- and accounting: the link is the only thing it inherits, so a retry can never
-- renew the allowance of the run it follows. Additive: older rows have none.
ALTER TABLE iris_ai.ask_run ADD COLUMN retry_of uuid REFERENCES iris_ai.ask_run (id);

-- One retry per run, so asking twice finds the first instead of starting another.
CREATE UNIQUE INDEX ask_run_one_retry ON iris_ai.ask_run (retry_of) WHERE retry_of IS NOT NULL;
