# IR-752 verification

Authority: ADR-049 §23, ADR-015, ticket IR-752 (blocker IR-751 confirmed Done in Jira on 2026-11-05). Branch `feature/IR-752-pending-embedding-space` from `origin/main` at `67f0df6c`. Local runs used the backend image of another worktree against a private throwaway pgvector PostgreSQL container, deterministic fakes only. No live provider, no paid embedding, no deployment.

## Executed

- **New tests, 29 passed** (run on the local PostgreSQL): `test_pending_space_build.py` (27 behavioural cases) and `test_record_space_embedding_migration.py` (2). First run: 4 failed. Three were defects in my test helper (the base fake builds chunk vectors through `embed_documents`, so the helper double-counted sends and admission attempts; and the allowed-reader list omitted `backfill.py`); one was a real defect (the command's provider lookup bound `build_embedding_provider` at import, so a patch of `apps.ai.indexing` did not reach it; fixed by calling it through the module). The second run passed all 29. No existing test was modified.
- **Migration on a realistic copy.** A custom-format dump of the development database (21 Records, `ai` at `0038`, spaces: retired `text-embedding-3-small`, active `voyage-context-4`) was restored into a separate throwaway database; the original was only read. It held no Record vectors, so 21 synthetic 1024-d legacy vectors were inserted (18 `voyage-context-4`, 2 `text-embedding-3-small`, 1 `unknown-model`). `manage.py migrate` applied everything pending including `ai/0040`: Records 21 → 21, legacy rows 21 → 21 with an identical `md5` over `(record_id, model_name, embedding)`; `ai_recordspaceembedding` held 20 rows (18 under the active space, 2 under the retired one, all `source_hash = ''`; the unknown-model row stayed legacy-only). `makemigrations --check --dry-run`: no changes. `migrate ai 0039` unapplied cleanly (table gone, legacy still 21); re-applying gave 20 again.

## Review fixes after the first green run

Two reviews (standards, spec) of the first commit found real gaps, fixed and re-tested: the default provider ignored the pending space's model (`build_embedding_provider(model=...)` now builds it for the space, so the live `VOYAGE_EMBED_MODEL` that readers embed queries with does not have to move); a space promoted mid-run kept being written (each record now rechecks the space is still pending and the run stops `space_not_pending`); a record held by another worker consumed the `max_records` bound; a record larger than `token_budget` stalled every slice (a slice now always takes its first record); a dead helper, an inline import and a duplicate import were removed. Four new tests cover the first four.

## Final runs (2026-11-05, after Docker Desktop was restarted)

- **New tests: 33 passed** on a freshly created test database (31 in `test_pending_space_build.py`, 2 migration tests).
- **Regression: all passed, none failed or errored** (one expected-failure marker) across backfill/promotion, similarity, chunk embedding, index health, vector dimensions, embedding space, celery routing, gateway guard, one-retrieval-stack, research read policy and grants, embargo, retrieval, providers, the three older embedding migration tests, proposal visibility, ingestion jobs and the chunk repository (about 580 tests).
- An earlier, interrupted run of the same set showed `F`/`E` marks; they disappeared on a freshly created database. That run used a reused test database that a killed session had left dirty (leftover Records without an embargo answer), and one rerun on it showed exactly that signature. A run in which **every** test skipped (Postgres not yet up after the restart) was discarded, not counted.

## Not verified

- The full `apps/ai` and backend suites were not run locally; CI is the gate.
- `flake8` itself was unavailable; `pyflakes` on the changed Python files is clean.
- Real two-process concurrency is shown with an advisory lock held by a second connection, not two workers. The Voyage adapter's `model_id`/`model=` path and the real admission ledger are not exercised; admission is shown through `AdmissionDenied` and the `ingestion` lane marker.
- A summary vector is written without re-reading the Record inside the write transaction: the disclosure gate is evaluated before the send and again inside the outbound fence, and `source_hash` is of the text sent, so an edit during the send leaves a stale hash that the next build re-embeds, but a vector of text withdrawn in that window is stored until then. It is in a pending space no reader uses.
- The session lock needs a direct or session-pooled database connection.
- Independent human review and CI remain required.
