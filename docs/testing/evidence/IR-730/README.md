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
  with Redis initially unavailable. The final full run below supplies isolated Redis
  and executes that wakeup fixture as well.
- **73 frontend tests passed** across the new reader, existing Ask IRIS/Paper Chat and
  persistent notice suites. New tests cover keyboard Stop, same-scope deep requests,
  idempotent reconnect after busy/network failure, revision-conflict recovery and axe.
- **42 standalone gateway tests passed**. Lint passed for the reader integration files.
- The production nginx image passed `nginx -t`; an enabled reader without its credential
  failed startup as required, and one with a test credential passed configuration validation.

## Publication verification

The PR was rebuilt on a clean checkout of `origin/main` at `a472a87d`, with only
IR-730's commit applied. Other local work remains in the original checkout.

- `npm ci --no-audit --no-fund` installed the exact lockfile. The original checkout
  had Zod 3 and Vitest 2 installed despite requiring Zod 4 and Vitest 5. The earlier
  type errors and frontend failures did not reproduce with the locked dependencies.
- **Full frontend: 131 files and 1,706 tests passed.** `npm run build` passed,
  including TypeScript. `npm run lint` passed with three existing warnings.
- The backend static gate exposed unused fixture imports in this ticket's new test.
  They now follow the existing module-alias fixture pattern; the full backend
  `flake8 apps/ config/ core/ testing/` gate passes. Runtime static checks pass too.
- **42 standalone gateway tests passed** on the clean PR branch. Development and
  production `docker compose config --quiet` validation both passed using CI's
  throwaway configuration.
- Final backend fixes preserve the existing safeguards: the edge uses the single
  `research_records` entry point; its header-based authentication route is declared
  in the authorization matrix; configured scope issuance and hidden-Record refusal
  have direct HTTP coverage. The matrix now supports request headers without
  changing any existing role outcome.
- The nginx checks were deliberately corrected: quoted regex braces are parsed as
  text, the smaller JSON-only reader limit is distinguished from the unchanged
  global PDF limit, and the FastAPI proxy must add the headers Django supplies on
  its own proxies. Those twelve existing configuration checks passed after the fix.
- The proxy fixture is byte-pinned. Its committed blob matches the existing audit
  SHA; a one-file LF attribute preserves those exact bytes on Windows and Linux
  without changing the fixture data or audit hash.
- The focused backend regression selection passed **53 tests**, and both property
  regressions passed under the existing `ci` Hypothesis profile. Final full-suite
  verification uses that profile, as GitHub Actions does.
- **Final full backend: 5,696 passed, one pre-existing non-strict XPASS.** All four
  shards exited successfully, with zero JUnit errors, failures or skips. Each shard
  passed 1,424 tests; their authorization subtests also passed. This supersedes the
  earlier failed/overlapping runs and the focused-only results above.
- **47 security regression tests passed.** The rebased nginx configuration and
  missing-secret startup guard passed again in the production nginx image.
- Backend verification uses one temporary PostgreSQL server per CI shard, plus a
  test-only Redis. It does not share the development server or its advisory run
  lock. The inherited development disclosure bypass is explicitly disabled, matching
  production's required gate rather than weakening startup validation.
- Production AGENT composition remains unavailable, so the new reader remains off
  by default and refuses operator echoes. No paid inference, deployment or traffic
  cutover was performed. Automated reviews do not replace human approval.

## CI startup harness follow-up — 3 November 2026

The first GitHub run passed Backend, Frontend, Security and AI gateway, but its
Compose job booted a stock nginx image with only the older startup script mounted.
The missing generated `/tmp/iris-runtime-reader.conf` failure was reproduced locally.
Both bare-nginx harnesses now mount the reader startup script and its disabled-reader
marker, resolve the private gateway to loopback, and execute the script on Linux.
The application defaults and enabled-reader credential requirement are unchanged.

The corrected real nginx startup/header smoke test passed for the SPA, assets, a 404,
activation route and JavaScript module-worker MIME type. The full admin-allowlist
smoke script passed, including forwarded-address and invalid-configuration cases.
Automated standards/spec reviews found no material issue in this CI-only change.
