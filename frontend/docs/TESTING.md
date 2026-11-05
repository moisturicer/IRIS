# Frontend test conventions and flake policy

Applies to everything under `frontend/src` run by Vitest (IR-210). Linked from [FRONTEND_IMPLEMENTATION.md](FRONTEND_IMPLEMENTATION.md). CI (the `frontend` job) is the gate; this page is how to write tests that pass it for the right reasons.

## Running tests

| Command | Use |
|---|---|
| `npm test` | `vitest run`: non-interactive, what CI runs. |
| `npm run test:changed` | `vitest run --changed origin/main` (IR-922): every test that imports a changed file, directly or through the route table. Run it before pushing; a single-file run can miss a router test. |
| `npm run test:watch` | Watch mode while developing. |
| `npx vitest run --coverage` | Coverage report (see below). CI does this; locally it is optional. |

During development run the one file you are changing. CI still runs the whole suite.

## Queries: role and accessible name, never class or test id

Find elements the way a user or a screen reader does: `getByRole("button", { name: /sign in/i })`, `getByLabelText`, `findByRole`. Do not query by CSS class, tag structure or `data-testid`.

- **Why:** a class or test id passes while the control is unlabelled or unreachable. A role-and-name query fails exactly when accessibility breaks, so the test doubles as a check.
- **Cost:** if a control has no accessible name, the test is hard to write. Fix the component (add the label), not the query.
- Prefer `userEvent`/`user-event` interactions over `fireEvent` where behaviour depends on focus or keyboard.

## Rendering

Render screens through `renderScreen` in `src/test/render.tsx`, not bare `render`, so providers (today the router) live in one place. Pass `route` and `state` to start on a given entry. `src/test/setup.ts` runs `cleanup()` after each test; do not leak DOM between tests.

## Accessibility (axe)

`src/test/axe.ts` runs axe-core on a rendered container and fails on **serious and critical** violations only. `moderate` and `minor` are reported, not fatal. It **cannot check colour contrast**: jsdom computes no layout, so the `color-contrast` rule is disabled. Contrast stays a manual check, and a green axe run is not evidence a screen is accessible.

## Timers: fake them, never sleep

Use `vi.useFakeTimers()` and advance with `vi.advanceTimersByTime` / `vi.runOnlyPendingTimers` (wrapped in `act` when React state updates). Never `await new Promise(r => setTimeout(r, n))` and never raise a timeout to make a test pass. Restore real timers in `afterEach` (`vi.useRealTimers()`). Polling and debounce code (for example the `PaperAiOverview` poll) is the main place this matters.

## What to mock

Mock at the boundary the code under test owns, and nothing nearer:

- **Mock:** the HTTP client (`vi.mock("@/api/client", ...)` returning `vi.fn()` for `get`/`post`), the session-expiry redirect (`@/lib/authSession`), timers, and browser APIs jsdom lacks.
- **Do not mock:** React, the router (use `renderScreen`), Zustand stores (set real state, reset it between tests), or the component under test's own children.
- Mocks are restored automatically (`restoreMocks: true`), but module-level state, store state and timers are not: reset them yourself.
- No test calls a real backend or vendor.

## Where hooks and stores are tested

- **Stores:** next to the store, `src/store/<name>.store.test.ts`, driving the real store through its actions and asserting state. No component needed.
- **Hooks:** next to the hook in `src/hooks/`, via `renderHook`; or, when a hook is only meaningful inside one screen, through that screen's test.
- **Pure helpers in `lib/`:** a `.test.ts` beside the file.
- **Screens and components:** a `.test.tsx` beside the component, through the accessible tree.

## Config facts that bite

- **`globals` is off** (`vitest.config.ts`). Import `describe`, `it`, `expect`, `vi` from `vitest` explicitly. `tsc` runs over `src` in `npm run build` and must not depend on ambient test types.
- **`pool: "forks"` is required on Windows**, not a preference: the default `threads` pool died with `Timeout calling "fetch"` before collecting any test. Do not remove it; Linux CI is fine either way.
- `testTimeout` is 15 s so a hung render fails instead of consuming the job timeout.

## Coverage

CI's `frontend` job runs `vitest run --coverage` (v8 provider), writes totals to the job summary on every PR run and uploads the full HTML report as the `frontend-coverage` artifact.

**There is a floor, and it fails the build.** `coverage.thresholds` in `vitest.config.ts` is 80% for lines, statements and functions. A run under any of the three exits non-zero, so the `frontend` job fails on the `Test` step. Branches are reported with no floor.

**Source:** the team's decision on IR-912 (2026-11-06), enforced by IR-932. At 2026-11-05 the suite measured lines 89.75%, statements 87.38%, branches 83.83%, functions 83.21%.

**A low run is fixed by a ticket, never by lowering the number.** If a PR drops under the floor, add the tests it needs, or open a ticket for the gap. Do not edit the thresholds to make a run pass, and do not rerun a red coverage job hoping it clears (see the flake policy below). Raising the floor is a ticket the team approves. Coverage measures lines executed, not behaviour asserted, so a number is not a substitute for the accessible-name tests above.

## Flaky-test policy

A flake is a test that passes and fails on the same code. **A flake is a ticket with an owner. It is never a retry.**

- Do not add retries (`retry:`, CI re-run loops, "re-run until green"), do not raise timeouts to hide it, and do not `skip` it silently.
- When a test flakes, open a Jira issue naming the test and the failing run, assign an owner, and link it from the PR that hit it.
- Find the cause (unawaited async work, real timers, leaked store or DOM state, order dependence). Fix the test or the code, and say which in the PR.
- If it must be quarantined while the fix is pending, use `it.skip` with the ticket key in a comment, and the ticket stays open until the skip is removed.
- Precedent: IR-541, the `PaperAiOverview` poll test, which failed once in CI on `main` and passed on a re-run. The re-run only unblocked the merge; the cause was written up on a ticket with an owner and acceptance criteria (stable over repeated runs, no test weakened), and the ticket was closed only once that was met.
