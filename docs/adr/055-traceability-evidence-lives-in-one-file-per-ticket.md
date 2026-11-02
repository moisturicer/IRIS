# ADR-055: Traceability evidence lives in one file per ticket

## Status

**Accepted** — 2026-11-02 by Ashlee Sean, who chose this option for [IR-276](https://citiris.atlassian.net/browse/IR-276). Drafted by an AI agent.

## Context

`docs/testing/TRACEABILITY.md` held every requirement's status and every ticket's notes in one 730 KB file. Git merges by line, so branches adding notes to it collided.

Of 150 merges in the 30 days to 2026-11-02, 25 conflicted on this file: 18 at sections added to the end of the file, and 7 on table rows up to 48,000 characters long. `scripts/resolve_traceability.py` (IR-275) handled only the rows.

## Decision

- `TRACEABILITY.md` holds the status vocabulary, the matrix and open defects. Each row has its requirement, a link and a short status.
- `docs/testing/traceability/` holds the detail, one file per ticket or row. A new ticket adds `IR-XXX.md` and names the requirements it affects.
- A row changes only when a requirement's status changes, so a conflict there is a real disagreement.
- `scripts/resolve_traceability.py` is deleted, because nothing it resolved remains.
- `backend/apps/tests/test_traceability_shape.py` fails if notes return to the matrix or a row's link breaks.

The full status text stays in the detail file, and the matrix shows its first word or phrase. Where a row's status text had no short form, the matrix says "See details".

## Consequences

**Gains:**

- Two branches adding notes to one requirement don't conflict.
- The matrix can be read in one sitting.

**Costs:**

- Evidence is spread over more than 200 files. `git grep -l FR-M3-02 docs/testing/traceability` lists a requirement's notes.
- The team changes a habit, and open branches that appended to the old file conflict once when they next merge.
- The matrix's short status loses qualifiers such as "human review pending". They remain in the detail file.

**Rejected:**

- **One note per line in the same file:** it leaves the end-of-file collisions, and two notes added at the same spot still conflict.
- **Extending the resolver:** conflicts would still appear, and someone would run a script each time.
- **Leaving the file as it was:** about one merge in six kept conflicting.
