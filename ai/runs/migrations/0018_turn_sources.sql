-- Sources a Turn's answer drew on, rechecked before it is resent (IR-994). NULL: label from citations and journal.

ALTER TABLE iris_ai.turn ADD COLUMN sources jsonb;
