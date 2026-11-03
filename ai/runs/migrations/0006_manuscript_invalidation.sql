-- Non-content durable facts remain deliverable after source/Record deletion.
CREATE TABLE iris_ai.manuscript_invalidation_receipt (
    event_id uuid PRIMARY KEY,
    acknowledged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
REVOKE ALL ON iris_ai.manuscript_invalidation_receipt FROM PUBLIC;
