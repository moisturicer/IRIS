# IR-730 reader progress verification — 2 November 2026

## Outcome

Ask IRIS and Paper Chat share `runs-reader-1`: durable task IDs/status/revisions,
separate run activity and labelled context estimates, reconnect, Stop and ordinary/deep
requests. The browser receives an explicit public allowlist rather than the internal
run journal. Source revisions and current RLS access are rechecked before delivering
stored answers, quotes or dependent task plans. Legacy internal responses remain separate.

The UI is off by default (`VITE_AI_RUNTIME_READER_ENABLED=false`). The production
frontend build accepts that flag as a build argument. Its nginx startup requires
`AI_GATEWAY_SERVICE_SECRET` when enabled; the secret must match the private gateway's
service secret and stays in server configuration. Requests use the same-origin edge,
whose Django subrequest issues the current reader's optionally Record-scoped grant.
The browser cannot supply the service credential or override its effective grant.

The shipped worker still composes the operator-only deterministic executor. The new
reader protocol explicitly refuses that executor as unavailable. A production AGENT
composition, approved limits/capacity and paid enablement remain unavailable; this
change neither substitutes an echo answer nor enables paid inference or live cutover.
Compaction is absent until its manual capability is implemented (IR-754).

## Evidence

- `public-state.json` records **actual authenticated HTTP projections** from a bounded
  recording-provider AGENT on restricted-role PostgreSQL. It contains a queued run,
  live plan, completed two-paper answer, a new deep run and cancellation. The provider
  pauses while the HTTP reader inspects running/reopened state; it is then released to
  deliver the checked answer. All data is synthetic. No paid provider is called.
- The browser replay used the compiled production reader component and these recorded
  public snapshots through its HTTP adapter. A reload reproduced the same live plan;
  a new request sent `deep`; keyboard Enter operated Stop; two citation passages and the
  mistake notice were visible. At **320 × 740**, document width did not exceed viewport
  width. `narrow-reader.png` is the resulting screenshot. This is a recorded contract
  replay, not a browser connected to a deployed worker or evidence of paid model quality.
- The focused reader tests cover real loop plans/context, no invented plan for a queued
  question, Stop/reopen, owner refusal, protocol refusal, revoked-source withholding,
  queued multi-paper progress, and the identity-only edge grant. Four reader-progress
  tests passed in a dedicated database; the edge and prerequisite suites passed too,
  with the Redis wakeup test skipped because that fixture expects localhost:6379.
- **73 frontend tests passed** across the new reader, existing Ask IRIS/Paper Chat and
  persistent notice suites. New tests cover keyboard Stop, same-scope deep requests,
  idempotent reconnect after busy/network failure, revision-conflict recovery and axe.
- **42 standalone gateway tests passed**. Lint passed for the reader integration files.
- The production nginx image passed `nginx -t`; an enabled reader without its credential
  failed startup as required, and one with a test credential passed configuration validation.

## Broader checks and limits

- Full frontend run: **127 files passed, 3 failed; 1,649 tests passed, 8 failed** plus
  7 unhandled errors. Failing files: `PublishDialog.test.tsx`, `Sidebar.test.tsx` and
  `errorScreens.test.tsx`. Error-screen failures include the Node/jsdom AbortSignal
  mismatch. None is in the new reader suite.
- Typechecking reports existing errors in `src/api/client.test.ts:15` and
  `src/features/records/metadata/metadataSchema.ts:32,53`; no reader-file type errors.
- The full backend selection in its own `test_ir730_full` database stopped at
  `ProductionSettingTests.test_production_starts_with_a_count`: the container inherits
  `AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT`, which production correctly refuses with DEBUG
  off. The earlier broad run overlapped a focused session on the shared test database;
  it was stopped and its results discarded. Final focused evidence uses
  `test_ir730_reader`; the broad check uses a separate database.
- No schema migration, live traffic switch, provider campaign, deployment or history
  migration was performed. Review is automated assistance, not independent human approval.
