"""AI-owned AskRuns and Conversations (IR-722, ADR-049).

The `iris_ai` schema has one migration owner (`ai.runs.migrate`) and one
writer, the AI runtime. Django's runs are untouched and remain the reader
path until cutover.
"""
