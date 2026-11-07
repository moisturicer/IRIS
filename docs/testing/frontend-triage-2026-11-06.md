# IRIS Repository Triage — 6 November 2026 (updated against Jira, GitHub and `main`)

**NOT READY FOR RELEASE.** Active development.

The first version of this triage was written from the repository alone. This version checks every claim against Jira (`citiris.atlassian.net`), open and merged pull requests, and `main` at `14c0a667`. **Several headline findings were already closed.** The remaining problem is still integration and evidence, not missing features, but the frontend backlog is much smaller than first reported.

## 1. What changed from the first version

| Claim in the first version | What the evidence shows |
|---|---|
| IR-934 is P0, In Progress: Discover overflows 59px at 360px | **Done.** The Filters label fix and a contrast fix (manuscript cover placeholder, 4.39:1 → `stone-600`) shipped. **The overflow was not a Discover defect**: the app shell animates its left margin 240px → 0 over ~200 ms after a resize, and the check measured mid-transition. A reader at 360px never sees it. The helper now waits for transitions to settle. Evidence: `docs/testing/traceability/IR-934.md`, pinned-build run 42184097719, 11 passed |
| IR-930 In Progress, needs a decision on the parser | **Done**, merged as PR #585. Decision made and recorded: break any unspaced run over 512 characters (no newer `remark-gfm` exists). Regression tests compare 5k vs 20k character renders, so they do not depend on machine speed. Known cut-offs are documented in `traceability/IR-930.md` |
| IR-893 still needs test conventions, coverage reports, coverage policy | **All five children Done** (IR-541, 912, 916, 922, 932). Coverage floor of 80% (lines, statements, functions) is enforced in CI. The story itself can close after review |
| IR-897 responsive regression not started | **IR-910 Done** (PR #580): every routed screen at 360, 768, 1280 and 1745 px, with a matrix in the CI summary. Story can close |
| IR-898 forms not started | IR-911 Done (approach decided, unused libraries removed). **IR-585 In Review.** One review away from closing |
| IR-899 not started | IR-913 (audit filters from the API) and IR-914 (timeout, cancellation, retry) Done. IR-915 contract check: **slice 1 merged (PR #593)**; AI endpoints are IR-940, the remaining reads IR-941 |
| IR-894 browser automation, "workflow exists" | IR-902 (Discover) and IR-904 (smoke tier on PRs) Done. **IR-903 and IR-905 remain** |
| IR-900 CSP and credential handling not started | IR-917, IR-930, IR-931 Done. IR-918 In Review (PR #582). IR-935 and IR-936 To Do |
| IR-631 listed as Phase 4 work | **Done.** IR-629 is still In Progress |

## 2. What is genuinely open

**Frontend engineering (IR-518):**

| Ticket | Open work | State |
|---|---|---|
| IR-867 | Publish sharing restrictions (layout B approved 4 Nov) | In Progress, **no assignee in Jira, no pushed branch found with this key** |
| IR-906 | States matrix for Discover, Paper View, My Library, Ask IRIS, Review (loading, empty, error, interrupted, revoked), gaps implemented | To Do |
| IR-907 | Playwright test per matrix cell (delay, empty, 4xx/5xx, aborted stream, revoked) | To Do, needs IR-906 |
| IR-908 | Axe in a real browser on every route and dialog | To Do |
| IR-909 | Keyboard-only and zoom checks on the core journeys | To Do |
| IR-903 | Ask IRIS browser test | To Do, **blocked on a decision for Jive** (see §5) |
| IR-905 | Scheduled core-journeys run on `main` | To Do |
| IR-915 | Frontend/backend contract check | **Slice 1 merged (PR #593), card In Review, not Done**: no reviewer approval is recorded. AI endpoints: IR-940 (not-ready). Remaining reads: IR-941 |
| IR-585 | Selects and required-field marking | In Review |
| IR-918 | Bundle secret and personal-data scan (PR #582) | In Review |
| IR-935 | Remove unused Tiptap dependencies | To Do |
| IR-936 | Plan and migrate to react-router 7 | To Do |
| IR-919 | Bundle composition report (entry chunk ~1 MB) | To Do |
| IR-520 | Paper View Overview declutter | To Do |
| IR-96 | Usability evidence with participants and a screen-reader pass | To Do, needs people |

**Not duplicated, still open as pull requests (all by `duckola`, none merged):** #546 (IR-721), #547 (IR-797), #548 (IR-789), #550 (IR-794), #551 (IR-786), #582 (IR-918); drafts #544 (IR-741) and #553 (IR-889). An open PR is not accepted work.

## 3. CI facts, corrected

- `frontend-smoke.yml` runs on **every** pull request and passes at once when `frontend/` was not touched. It is only a gate if "Frontend smoke" is a required check in branch protection. **Not verified**: the branch-protection API returned 404 to my account, and no repository rulesets exist. A repository admin has to confirm.
- `core-journeys.yml` is manual (`workflow_dispatch`) only. IR-905 is the ticket that adds a schedule. The cadence is a team choice.
- `docs/testing/traceability/IR-904.md` still lists the smoke tier as **PARTIAL**.
- IR-901's description mentions nginx smoke tests and performance reporting, but Jira has only IR-919 under it. **Missing sub-tasks, confirmed against IR-901's own scope**: the built-image nginx smoke check and the observed load timings had none. Filed as IR-942 and IR-943 (§8).

## 4. Release gate

The next milestone is frontend engineering completion, then **one more pinned integrated run** on the final build (IR-629, repeating IR-631). IR-631's run predates IR-867, IR-906/907 and the PRs above, so it does not cover them.

## 5. Questions to settle before the tickets they block

| Question | Blocks | Who | Options |
|---|---|---|---|
| How does Ask IRIS answer in an e2e run without paid provider calls? Under production settings the stack has no fake provider (the Django one is test-only) | IR-903, and IR-631 AC6 stays unmeasured | **Jive** | *Mock `/api/v1/ai/*` in the smoke tier*: free, fast, runs on every PR; proves the UI, not the real pipeline. *A test-only provider in the e2e compose overlay*: tests the real route and streaming; adds a provider that must never reach production. *Record real answers once and replay*: realistic; goes stale when the answer shape changes |
| Contract source: generated OpenAPI schema from the backend, or recorded fixtures verified in a backend test run. **Settled 2026-11-06: recorded fixtures (§7)** | IR-915 | Team (an ADR if it changes how types are produced) | *Generated schema*: drift is caught at the source; adds a backend dependency and work for Jive. *Recorded fixtures*: frontend can start now; only as good as the fixtures, and someone must refresh them |
| Is "Frontend smoke" a required check on `main`? | The value of IR-904 | Repository admin | Required: a red smoke run blocks merging. Not required: it is advice |
| Who owns IR-867 and where is its branch? | IR-867 | You | Nothing is pushed under that key |
| Schedule cadence for IR-905 | IR-905 | Team | Nightly: catches regressions fast, spends runner minutes (the job builds every worker, up to 75 min). Weekly: cheaper, slower to notice |

## 6. Workflow: what to do first, and what can run in parallel

### Before any ticket (once, today)

1. Fetch and cut every branch from `main`: `<type>/IR-XXX-short-description`.
2. Send the two questions in §5 that are not yours (IR-903 to Jive, IR-915 to the team). They have the longest lead time and cost nothing to ask.
3. Confirm IR-867's owner and branch.
4. Baseline once: `cd frontend && npm ci && npm run test:changed`, and `cd e2e && npm ci && npx playwright install chromium`. For Playwright work, build the frontend first (`npm run build` in `frontend/`), then `npm run test:smoke` in `e2e/`.

### Before each ticket

Read the ticket and its acceptance criteria. Move it to In Progress. Add `docs/testing/traceability/IR-XXX.md` when it changes a requirement. **Red first**: see the new test fail, then fix. Run the new test alone while working; one `npm run test:changed` before pushing; CI is the gate for the rest. Commit as `type(IR-XXX): ...`, no AI attribution. Push and open the PR in the same step, then move Jira to In Review. Done is a person's.

### The order

```
Wave 1 (parallel; no shared files)
  IR-867  Publish sharing restrictions            frontend/src/features/publish
  IR-906  States matrix + implement the gaps      frontend features + a matrix doc
  IR-908  Axe on every route (routes first)       e2e/support/a11y.ts, reuses smoke/support/screens.ts
  IR-905  Scheduled core-journeys                 .github/workflows/core-journeys.yml only
  IR-935  Remove Tiptap                           package.json / lock only

Wave 2 (needs wave 1)
  IR-907  Forced-state tests            needs IR-906 (one test per matrix cell)
  IR-908  Dialogs and states            needs IR-906 (scans the matrix's states)
  IR-909  Keyboard and zoom checks      after IR-908 merges, or in its own file
  IR-915  Contract check                slice 1 merged; IR-940, IR-941 follow

Wave 3
  IR-903  Ask IRIS journey              needs Jive's answer
  Close stories: IR-893, IR-897 now; IR-898 after IR-585 merges; IR-895 after 906+907;
  IR-896 after 908+909; IR-899 after 915; IR-894 after 903+905; IR-900 after 918, 935, 936 decision

Wave 4
  IR-629 / repeat IR-631 on one pinned build; IR-96 with participants
```

**Conflict risks:** IR-906 edits Paper View, so land or coordinate with IR-520 first, or the same person does both. IR-908 and IR-909 both touch `e2e/support`. IR-906's "access revoked" cell for Ask IRIS depends on PR #546 (IR-721) being merged. Do not start IR-936 (router 7) while anything else touches routes: it changes every test that renders a router.

### MVP-required frontend, in order

1. **IR-867** — the Publish journey is the entry point of the thesis workflow.
2. **IR-906 then IR-907** — a hidden Record and a missing id must look identical, and revoked access must not leak. This is an access-control property, not polish.
3. **IR-908** — axe over every route and dialog, because accessibility is currently proven on Discover and the paper page only.
4. **IR-903** — Ask IRIS is thesis-critical and is the one core journey with no browser test (blocked, §5).
5. **IR-915** — catches a backend change that silently breaks a screen.
6. **IR-905** — turns the pinned run from a one-off into a regression check.

Defer: IR-936, IR-919, IR-96, IR-552.

### Benefits and costs of this order

- *States before axe-on-dialogs and forced-state tests*: the matrix tells those tickets what to cover, so they are not redone. Cost: IR-907 and the dialog half of IR-908 wait on IR-906, which is the largest ticket.
- *Starting IR-908 on routes only*: unblocks you now. Cost: a second pass for dialogs, so keep the route list and the dialog list in separate files to avoid conflicts.
- *Leaving IR-903 until Jive answers*: avoids building a test around a provider strategy that gets rejected. Cost: it is the longest-lived gap, so ask first.

## 7. IR-915 decision (settled 2026-11-06, in a design session with the frontend owner)

**Recorded fixtures checked by a backend test. No `drf-spectacular`, no ADR** (the types stay hand-written, which is the ticket's own test for an ADR).

- Backend: `backend/apps/tests/contract/` reuses the access matrix's `build_world`, calls the real endpoints and compares structure only (names, JSON types, nullability, array element shape). A `null` in the sample checks only that the key exists.
- Refresh only by `UPDATE_CONTRACTS=1 pytest apps/tests/contract`. CI never rewrites a fixture.
- Fixtures live in repo-root `contracts/`. The frontend validates them against a JSON Schema derived from `frontend/src/types` (`ts-json-schema-generator` + `ajv`, dev-only), after a spike; the fallback is a hand-kept key list.
- PR 1 covers `record-list`, `record-detail`, `record-tracker`, `record-mine`, `record-facets`, `classifications`, `record-document-requests`, `auth-login`, `user-me`, library saves and `reviews-mine`. PR 2 adds the non-streaming AI endpoints through the deterministic fake provider, after Jive is told. Streamed Ask IRIS events stay with IR-903.
- Everything stays on IR-915; traceability is PARTIAL after PR 1. Cost accepted: structure-only checks miss a type change on a field that is `null` in the sample.

**Outcome.** PR #593 merged slice 1: 11 endpoints, 12 fixtures, `traceability/IR-915.md` (PARTIAL). The first run caught a real mismatch (`classification_name` is omitted, not `null`, so the type became optional). The decision comment is on IR-915. The card is In Review and **not Done**: the PR was merged with no reviewer approval recorded, which `DEFINITION_OF_DONE.md` §4 requires.

## 8. Tickets filed from this triage (2026-11-06)

Every key below was created in Jira on this date; none is invented. All are unassigned.

| Ticket | Under | What | Why now |
|---|---|---|---|
| IR-940 | IR-899 | Contract check slice 2: the non-streaming AI endpoints, through the deterministic fake provider | `not-ready`: Jive must be told first, the AI area is theirs |
| IR-941 | IR-899 | Contract check slice 3: the remaining read endpoints | Ready to pull, low priority |
| IR-942 | IR-901 | Smoke check of the built frontend image behind nginx | IR-901's acceptance criterion had no sub-task; also IR-200 |
| IR-943 | IR-901 | Record observed load timings for the key screens, no verdict | Same: IR-901's criterion had no sub-task; no target until IR-95 |
| IR-944 | IR-894 | Verify and set the required CI checks in branch protection on `main` | Needs a repository admin. Until done, IR-904's gate is advice |
| IR-945 | IR-518 | Record this triage | Carries this document |

**Not filed, on purpose:** a ticket for request bodies and write endpoints (the fixtures record responses, so they need a different check; a team decision, noted in IR-941), and any change to IR-903, which stays blocked on the question for Jive in §5.
