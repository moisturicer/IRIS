# e2e — core-journey verification (IR-631)

Playwright journeys against **one integrated build** under production
settings. The plan, the acceptance-criterion mapping and the status rules are
in [`docs/testing/CORE_JOURNEYS.md`](../docs/testing/CORE_JOURNEYS.md).

This is not a PR gate. The pinned run is the manually started workflow
`.github/workflows/core-journeys.yml`; this folder is also runnable locally.

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
- **Request throttles.** DRF's general throttles are raised to 20000/day
  (`API_THROTTLE_ANON`, `API_THROTTLE_USER`). Behind nginx every signed-out
  request comes from one address, and the 100/day default runs out partway
  through one full run. No acceptance criterion measures them. The lockout
  under test is axes', left at its default of three failures.
- **Ask IRIS** is not driven here. IR-631 reuses IR-630 and IR-605/IR-608
  evidence from the same SHA. IR-250 (the embargo field) is Done, but a paper
  still reaches the AI only once someone has answered for it (ADR-052), and a
  real answer needs an approved provider run. The Ask IRIS browser journey
  waits on IR-903, which is a decision for Jive.
- **Latency** is recorded, never judged: no application target is agreed
  (IR-95).
