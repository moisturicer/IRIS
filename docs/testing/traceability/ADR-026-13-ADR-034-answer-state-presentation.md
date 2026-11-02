# ADR-026-13-ADR-034-answer-state-presentation

[Back to the matrix](../TRACEABILITY.md)

## ADR-026 §13 · ADR-034 (answer-state presentation)

**Requirement:** **Every answer state has an explicit wire presentation, and an unknown one fails safe** — no FR- id; a live defect found under IR-456, fixed by IR-458. `presentation._WIRE_MODE` held two of `Turn.state`'s four values and `answer_mode` fell through to `generative` for the rest, so a cut-off `partial` Turn was served as a finished answer

**Design:** Supports ADR-034's rule that a state added later must never read as a finding

**Implementation:** `apps/ai/presentation.py` — all four states mapped (`partial` → `partial`, `answer` null, fragment in `message`); an unrecognised state → `unavailable`

**Test:** `apps/ai/tests/test_answer_states.py` enumerates `Turn.state`'s choices and fails if one lacks a mapping or the map names a state a Turn cannot hold; `test_conversations_http.py::test_a_partial_turn_replays_with_its_partial_flag_set` (replay)

**Evidence:** Mapping tests run without a database. Executed 2026-10-06 against the compose Postgres/pgvector: the replay test and the neighbouring ask, stream, failed-turn and conversation suites pass. No frontend change: `turnToMessages` already falls back from `answer` to `message` and keeps the `partial` flag

**Status:** **BUILT and executed.** The earlier test asserting a partial Turn replays with `state == "generative"` was changed deliberately — that assertion was the defect
