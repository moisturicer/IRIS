# 03 — Frontend

Five tasks. The frontend is feature-complete relative to the pilot; the work is **removing surface**, not adding features. Deliberately excluded: TanStack Query, shared table modules, form-stack consolidation, component splitting — all `DO NOT BUILD YET` under [ADR-001](../adr/001-mvp-scope-boundary.md).

---

# FE-01 · Consolidate token storage and fix the refresh path

## Objective
Give the auth token one owner, stop the refresh loop, and stop leaving a valid access token in browser storage after logout.

## Problem
Auth state lives in three places that disagree. The refresh interceptor repairs exactly one request, writes to storage nothing reads, never clears one of the keys it writes, and has no in-flight deduplication against a rotating refresh token.

## Evidence
`src/api/client.ts:22-40` writes `localStorage["access_token"]` and `["refresh_token"]`; the request interceptor at `:12` reads `useAuthStore.getState().accessToken`; `lib/authStorage.ts` persists to `sessionStorage["iris_refresh_token"]`. `setTokens` is never called, so the store keeps the stale token and every subsequent request 401s and refreshes again.

Two further defects: `settings/base.py:139-140` sets `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION`, and with no deduplication two concurrent 401s issue two refreshes — the second presents a token the first blacklisted, forcing a hard logout. And `lib/authStorage.ts:16-20` removes `localStorage["refresh_token"]` but **not** `["access_token"]`, so a valid 30-minute bearer token survives logout on a shared machine.

## Current State
Refresh loop, mid-session logouts, post-logout token leak.

## Proposed State
`lib/authStorage.ts` is the only module touching storage; the store is the only holder of the live access token; the interceptor calls `setTokens` and nothing else; one shared in-flight refresh promise.

## Scope
Remove both `localStorage` writes; call `store.setTokens(...)`; module-level in-flight promise; use `authApi.refreshToken`; clear legacy keys on boot.

## Out of Scope
httpOnly refresh cookies (Phase 2). Session-inactivity expiry (`S-06`).

## Technical Approach
Standard shared-refresh-promise: queue failed requests behind it, replay on resolve.

## Dependencies
None.

## Risks
Low. Test the concurrent case explicitly — it is the one that currently fails.

## Security Impact
Direct. Removes a persistent post-logout bearer token and honours the application's own stated design (`authStorage.ts:1-4`).

## Performance Impact
Removes a refresh-per-request loop after any token expiry.

## SaaS Impact
None.

## Research/Thesis Impact
Session instability during a pilot would contaminate usability data (`V-11`).

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
S

## Acceptance Criteria
- [ ] After a 401-triggered refresh, the **next** request carries the new token.
- [ ] Ten concurrent 401s trigger exactly **one** refresh call.
- [ ] After `logout()`, `localStorage` contains no `access_token` or `refresh_token`.
- [ ] `grep -rn "localStorage" src/api/client.ts` returns nothing.
- [ ] A user idle past access-token expiry continues working without being logged out.

## Testing Requirements
Unit tests for single-refresh and post-logout clearing (`T-04`). Manual DevTools verification.

## Documentation Requirements
Token lifecycle recorded in `DOC-05`.

## Definition of Done
Merged with tests; storage verified empty after logout.

---

# FE-02 · Reduce the pilot surface — hide non-pilot screens

## Objective
Expose only the screens the pilot workflow needs, reducing what must be secured, tested and supported.

## Problem
Every routed page is attack surface, test surface and support surface. Most contribute nothing to the pilot.

## Evidence
The pilot workflow is: login → submit record with PDF → submission status → review → parallel clearance → clearance-aware resubmission → publication → search → audit trail. Roughly 37 page components exist; 16 serve that path.

## Current State
All pages routed, including several that call no endpoints or return 501.

## Proposed State

| | Screens |
|---|---|
| **KEEP** (16) | Login · Signup · EmailVerify · PendingApproval · Home · AddRecord + steps · MyRecords · RecordDetail · Documents · PendingRecords · Evaluation · PublishedRecords · AuditLog · Notifications · AIHub (search) · RoleRequests |
| **HIDE** (10) | Dashboard · Discover · ApprovedRecords · DeclinedRecords · ApprovedProposals · Settings · Help · DownloadToken · UserList · Sessions |
| **DEFER** (5) | DownloadRequests · DeleteRequests · DocumentReviews · ReviewAnalytics (returns 501) · ImportRecords |
| **REMOVE** | See `FE-03` |

`RoleRequests` is kept deliberately — RDCO needs it to provision pilot users.

## Scope
Remove HIDE and DEFER routes from `router/index.tsx`; remove their sidebar entries; keep the components.

## Out of Scope
Deleting HIDE/DEFER components — they return in Phase 2.

## Technical Approach
Route removal, not deletion. A feature flag is unnecessary at this scale and adds a mechanism to maintain.

## Dependencies
None.

## Risks
Low. If a pilot participant needs a hidden screen, restore one route. Confirm the KEEP list with RDCO before the pilot.

## Security Impact
Positive — fewer reachable endpoints. Note this is **not** a substitute for server-side authorization ([ADR-009](../adr/009-authorization-model.md)).

## Performance Impact
Smaller bundle.

## SaaS Impact
Per-institution screen sets are a Phase 2 configuration concern.

## Research/Thesis Impact
Focuses `V-11` usability evaluation on the workflow under study rather than incidental pages.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
XS

## Acceptance Criteria
- [ ] Only the 16 KEEP screens are reachable from the router and sidebar.
- [ ] Every pilot workflow step completes using only KEEP screens.
- [ ] Navigating directly to a hidden route redirects rather than rendering.

## Testing Requirements
One routing test asserting hidden paths do not resolve.

## Documentation Requirements
The KEEP list recorded in `12-scope-cuts.md`.

## Definition of Done
Merged; pilot walkthrough completed using only KEEP screens.

---

# FE-03 · Remove dead frontend code and unused dependencies

## Objective
Delete unreachable code and four zero-importer packages.

## Problem
Dead modules are invisible to the compiler — `noUnusedLocals` only sees imported files — and one duplicate has *different behaviour* from the module it shadows.

## Evidence

| What | Lines | Why safe |
|---|---|---|
| `features/ai/RAGChatPage.tsx` + 7 components + `lib/chatStorage.ts` + `types/chat.ts` | ~840 | Unrouted; conversational RAG deferred ([ADR-006](../adr/006-minimum-rag-pipeline.md)) |
| `features/storage/StoragePage.tsx`, `FolderBrowserPage.tsx`, `api/storage.ts` | ~320 | `apps/storage` removed (`SC-01`) |
| `router/PrivateRoute.tsx`, `router/RoleRoute.tsx`, `features/errors/ForbiddenPage.tsx` | ~120 | Superseded by `components/auth/ProtectedRoute.tsx` |
| `features/requests/AccessRequestsPage.tsx` | ~146 | Unrouted |
| `components/layout/NotificationBell.tsx`, `components/records/DownloadRequestModal.tsx`, `contexts/DiscoverSearchContext.tsx`, `hooks/useDataTable.ts`, `features/discover/discoverUtils.ts`, `lib/signupData.ts` | ~250 | Zero importers each |
| `api/dashboard.ts` | ~50 | Bypassed by an inline `apiClient.get` in `Sidebar.tsx` |

`features/discover/discoverUtils.ts` is a **conflicting duplicate** of `lib/discoverUtils.ts` with different badge rules.

**Unused dependencies, zero importers:** `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone`.

## Current State
~1,700 unreachable lines; four unused packages.

## Proposed State
Deleted; `Sidebar.tsx` uses `dashboardApi` rather than an inline call.

## Scope
Delete the listed modules and four dependencies; fix the `Sidebar.tsx` inline call.

## Out of Scope
`formik`/`yup` removal — form consolidation is `DO NOT BUILD YET`. They stay until Phase 2.

## Technical Approach
Grep for importers before each deletion; one commit per cluster so revert is easy.

## Dependencies
`FE-02`, `SC-01`. After `FE-04` so typecheck catches mistakes.

## Risks
Low. The chat UI is the only judgement call — it is deleted because conversational RAG is deferred, and it is recoverable from git if Phase 2 revives it.

## Security Impact
Removes the storage frontend alongside its unauthorized backend.

## Performance Impact
Smaller bundle.

## SaaS Impact
None.

## Research/Thesis Impact
None.

## MVP Classification
MVP RECOMMENDED

## Priority
P1

## Complexity
M

## Acceptance Criteria
- [ ] Every deletion has a documented zero-importer grep in the PR.
- [ ] `npm run build` and `npm run typecheck` pass.
- [ ] The four packages are absent from `package.json`.
- [ ] Exactly one `discoverUtils` module exists.
- [ ] `Sidebar.tsx` calls `dashboardApi.stats()`.

## Testing Requirements
Build and typecheck green in CI.

## Documentation Requirements
Bundle size before/after noted in the PR.

## Definition of Done
Merged; grep evidence recorded.

---

# FE-04 · ESLint flat config and typecheck script

## Objective
Turn on three quality tools that are installed and currently inert.

## Problem
ESLint 9 requires a flat config; there is none, so `npm run lint` cannot run. No `typecheck` script exists, so types are checked only as a side effect of `npm run build`.

## Evidence
devDependencies include `eslint ^9.6.0`, `@typescript-eslint/*`, `eslint-plugin-react-hooks ^5`. `ls -a frontend | grep -i eslint` returns nothing. Scripts: `dev`, `build`, `preview`, `lint`.

## Current State
Three installed plugins do nothing.

## Proposed State
`eslint.config.js` wired to both plugins; `"typecheck": "tsc --noEmit"`; both in CI.

## Scope
Flat config; typecheck script; wire into `F-01`.

## Out of Scope
Fixing every lint finding in one pass — record a follow-up if the count is large.

## Technical Approach
`languageOptions.parser` set to the TS parser; `plugins: { "react-hooks": … }`.

## Dependencies
Feeds `F-01`.

## Risks
Low. First run will surface findings, including the `exhaustive-deps` suppression at `PublishedRecordsPage.tsx:72`.

## Security Impact
Indirect — `react-hooks` and unused-variable rules catch the class of mistake behind several findings here.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
None.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
S

## Acceptance Criteria
- [ ] `npm run lint` runs without a configuration error.
- [ ] `npm run typecheck` exists and exits 0 on a clean tree.
- [ ] A deliberate TypeScript error makes `typecheck` exit non-zero.
- [ ] Both run in CI.

## Testing Requirements
Both commands in CI.

## Documentation Requirements
Scripts listed in the development guide.

## Definition of Done
Merged; both green in CI; deferred lint findings ticketed.

---

# FE-05 · One `useRole` module

## Objective
Collapse four non-equivalent definitions of "staff" and remove a name collision that makes a wrong import silent.

## Problem
Four definitions disagree, and two are both exported as `useRole` from different modules with different return types.

## Evidence

| Where | Definition |
|---|---|
| `hooks/useRole.ts:21` | role in `STAFF_ROLES` **or** Django staff — canonical |
| `store/auth.store.ts:100-102` | exported `useRole`, `useIsStaff`, `useIsReviewer` — **no Django-staff bypass** |
| `components/auth/ProtectedRoute.tsx:24` | private local `isDjangoStaff()` |
| `Sidebar.tsx`, `DocumentsPage.tsx:291` | re-derived inline |

`store/auth.store.ts` exports a `useRole` returning `string | null`; `hooks/useRole.ts` exports one returning an object of booleans. Both reachable via `@/`.

## Current State
A wrong import type-checks and behaves differently.

## Proposed State
`hooks/useRole()` is the only way to ask; colliding exports deleted.

## Scope
Delete the three exports from `auth.store.ts`; delete private helpers in `ProtectedRoute` and `Sidebar`; replace inline role literals with `lib/constants.ts`.

## Out of Scope
A `<Can>` component. Server-side authorization ([ADR-009](../adr/009-authorization-model.md)).

## Technical Approach
Delete the collisions first — TypeScript surfaces every broken import immediately.

## Dependencies
None.

## Risks
Low. **This is a UX-consistency fix, not a security fix.** `ProtectedRoute`'s docstring is correct: client-side RBAC is UX only; real enforcement is server-side.

## Security Impact
None directly. Prevents the UI offering actions the API will reject.

## Performance Impact
None.

## SaaS Impact
Role sets become institution-configurable in Phase 2; one module is the place to do it.

## Research/Thesis Impact
Reviewer-facing UI must match server authorization or `V-06` routing validation produces noise.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
S

## Acceptance Criteria
- [ ] `store/auth.store.ts` exports no hook named `useRole`.
- [ ] Exactly one `useRole` implementation exists.
- [ ] Role string literals appear only in `lib/constants.ts`.
- [ ] `npm run typecheck` passes.
- [ ] Sidebar, router and page agree for a superuser with no assigned role.

## Testing Requirements
Unit test covering the superuser-without-role case (`T-04`).

## Documentation Requirements
None.

## Definition of Done
Merged; one hook; typecheck green.
