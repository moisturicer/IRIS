# e2e — core-journey verification (IR-631)

Playwright journeys against **one integrated build** under production
settings. The plan, the acceptance-criterion mapping and the status rules are
in [`docs/testing/CORE_JOURNEYS.md`](../docs/testing/CORE_JOURNEYS.md).

The journeys are not a PR gate. The pinned run is the workflow
`.github/workflows/core-journeys.yml`, started by hand or on a schedule against
the head of `main` (IR-905); this folder is also runnable locally.

## Smoke tier (IR-904)

`smoke/` is a different, small set that **does** run on every pull request that
touches `frontend/` (`.github/workflows/frontend-smoke.yml`). It needs no stack:
it serves the built `frontend/dist` and answers every `/api` request from the
test (`smoke/support/mock-api.ts`). A request a test did not mock is answered
501 and fails the test, so the set cannot go green while the page calls
something nobody looked at. Because the API is mocked, it says nothing about the
backend; the journeys above do.

```bash
cd ../frontend && npm ci && npm run build   # the smoke tier does not build for you
cd ../e2e && npm ci && npx playwright install chromium
npm run test:smoke
```

The smoke tier also holds the **viewport matrix** (IR-910): every routed screen at
360, 768, 1280 and 1745 px, asserting the page does not scroll sideways and the
screen's primary action can be reached. Each run writes the per-screen, per-width
table to `test-results-smoke/viewport-matrix.md`; CI prints it in the run summary.
The screens are listed in `smoke/support/screens.ts`; see
[`docs/engineering/RESPONSIVE_LAYOUT.md`](../docs/engineering/RESPONSIVE_LAYOUT.md).

The smoke tier also runs **axe in a real browser** (IR-908): on every routed screen (`axe-routes.spec.ts`), on every state of the UI states matrix (`axe-states.spec.ts`, cells in `smoke/support/states.ts`), and with every dialog open (`axe-dialogs.spec.ts`, cases in `smoke/support/dialogs.ts`). WCAG 2.0/2.1 A and AA, contrast included; serious and critical findings fail the test, with each screen's full axe result attached. A new route needs a row in `screens.ts`, and `dialog-coverage.spec.ts` fails when a dialog source file is neither opened by a case nor listed in `UNSCANNED` with a reason.

The smoke tier also **forces each state of the UI states matrix** (IR-907) by intercepting the one request that decides it, and asserts what the reader sees and can do next. `forced-states.spec.ts` runs every state in `smoke/support/states.ts` (loading is a held read that is then released, empty, a 500 with Try again, a real request timeout with Retry and no automatic retry, a 403 and a 404 that must read the same with no retry), and two withdrawals while the reader is already in the product. `forced-cells.spec.ts` holds the cells that need a second read or a different fixture (Discover's filtered-empty and failed or timed-out Load more, Saved, My Reviews' tabs, Ask IRIS's list failure and no-sources, the review tracker and timeline). `ask-iris-stream.spec.ts` cuts, fails and ends the Ask IRIS event stream. `forced-coverage.spec.ts` reads `docs/ui-ux/17-ui-states-matrix.md` and fails when a cell the document does not mark N/A has no forced-state test (`smoke/support/matrix-proofs.ts`), so editing the matrix without a test fails the build.

Output goes to `playwright-report-smoke/` and `test-results-smoke/` (trace and
video for a failure only). Mark the "Frontend smoke" check required in the
branch protection rules for `main` to make a failure block the merge.

## Run it locally

From `e2e/`:

```bash
npm ci
npx playwright install chromium
npm run env          # writes e2e/.env.e2e: fresh throwaway secrets, port 8090
npm run stack:up     # production compose + docker-compose.e2e.yml, project iris-e2e
npm test             # seeds accounts and Turnarounds, then runs every journey
npm run stack:down   # removes the stack and its volumes
```

The stack is its own Compose project (`iris-e2e`) with its own volumes and
ports — frontend on 8090, Mailpit on 8026 — so it runs beside the development
stack without touching its database. It never reads `backend/.env`: provider
keys for a later, approved Ask IRIS run go in `e2e/.env.e2e.local`
(gitignored), which `npm run env -- --force` appends.

## What the journeys use that the application does not offer a screen for

- `seed_demo --accounts-only --force` — the demo accounts (`<role>@cit.edu`).
- `review_clock_for_testing --force` — a Turnaround per party (what an
  administrator enters in Django admin, unreachable here because production
  CSRF checks an HTTPS origin), moving an active assignment's Due date into
  the past, and one tick of the hourly reminder job. Test data only.

Both run inside the backend container (`support/stack.ts`).

## Limitations

- **TLS.** Production settings redirect any request not marked HTTPS, and
  this stack turns Caddy off (IR-847) and publishes nginx directly. The run sends
  `X-Forwarded-Proto: https`, which nginx passes through as a fronting proxy
  would. Emailed links name the `https://` `FRONTEND_URL`; the run follows
  their path on the plain-HTTP address.
- **Inactivity expiry** is enforced by the server at 30 minutes. Its check
  runs only in a separate pass with `SESSION_IDLE_TIMEOUT_MINUTES=2`
  (`E2E_IDLE_PASS=1`).
- **Request throttles.** DRF's per-minute bursts are raised to 6000/minute
  (`API_THROTTLE_ANON_BURST`, `API_THROTTLE_USER_BURST`,
  `API_THROTTLE_LOGIN_BURST`, `API_THROTTLE_REGISTER_BURST`; IR-999). Behind
  nginx every signed-out request comes from one address, and a run is faster
  than a person. The daily backstops keep their defaults. No acceptance
  criterion measures them. The lockout under test is axes', left at its
  default of three failures.
- **Ask IRIS** is not driven here. IR-631 reuses IR-630 and IR-605/IR-608
  evidence from the same SHA. IR-250 (the embargo field) is Done, but a paper
  still reaches the AI only once someone has answered for it (ADR-052), and a
  real answer needs an approved provider run. The Ask IRIS browser journey
  waits on IR-903, which is a decision for Jive.
- **Latency** is recorded, never judged: no application target is agreed
  (IR-95).
