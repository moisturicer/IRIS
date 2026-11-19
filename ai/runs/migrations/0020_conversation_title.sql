-- A reader's own name for a Conversation (IR-1160). NULL shows the first question.
-- Content: cleared with the Conversation's other content on deletion.
ALTER TABLE iris_ai.conversation
    ADD COLUMN title text CHECK (title IS NULL OR (length(title) BETWEEN 1 AND 200 AND title = btrim(title)));
