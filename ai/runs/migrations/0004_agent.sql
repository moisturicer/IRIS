-- One bounded AGENT Conversation (IR-728, ADR-049 §13, §16).

-- Shown order, selections and exclusions as Record ids, advanced only by a delivered Turn.
ALTER TABLE iris_ai.conversation ADD COLUMN state jsonb NOT NULL DEFAULT '{}'::jsonb;

-- A Turn either answers or asks the reader one clarifying question.
ALTER TABLE iris_ai.turn ADD COLUMN kind text NOT NULL DEFAULT 'answer'
    CHECK (kind IN ('answer', 'clarification'));
