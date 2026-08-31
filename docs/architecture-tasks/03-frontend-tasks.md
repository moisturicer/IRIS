# 03 — Frontend Tasks

Eight tasks. No boot blockers, but `FE-01` fixes a security defect and `FE-02` is the guardrail everything else depends on.

---

# FE-01 · Consolidate token storage and fix the refresh path

## Objective
Give the auth token one owner, stop the refresh loop, and stop leaving a valid access token in browser storage after logout.

## Problem
Auth state lives in three places that disagree. The refresh interceptor repairs exactly one request, writes to storage nothing reads, never clears one of the keys it writes, and has no in-flight deduplication against a rotating refresh token.

## Current State
`src/api/client.ts:22-40`:

```ts
const { data } = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
localStorage.setItem("access_token",  data.access);    // read by nothing
localStorage.setItem("refresh_token", data.refresh);   // read by nothing
original.headers!.Authorization = `Bearer ${data.access}`;
return apiClient(original);
```

`setTokens` is never called, so `useAuthStore.getState().accessToken` — which the *request* interceptor reads at `:12` — keeps the stale token; every subsequent request 401s and refreshes again.

Two further defects:
1. **Rotation race.** `settings/base.py:139-140` sets `ROTATE_REFRESH_TOKENS: True` and `BLACKLIST_AFTER_ROTATION: True`. With no deduplication, two concurrent 401s issue two refreshes; the second presents a token the first blacklisted → hard logout mid-session.
2. **Logout leak.** `src/lib/authStorage.ts:16-20` removes `localStorage["refresh_token"]` but **not** `localStorage["access_token"]`. A valid 30-minute bearer token survives logout in persistent storage — on a shared or lab machine. The function's own comment calls these "legacy keys" while `client.ts` actively writes them.

## Proposed State
`lib/authStorage.ts` is the only module touching storage; the Zustand store is the only holder of the live access token; the interceptor calls `setTokens(...)` and nothing else; one in-flight refresh promise is shared.

## Scope
- Remove both `localStorage` writes; call `store.setTokens(access, refresh)`
- Module-level in-flight promise so concurrent 401s await one refresh
- Use `authApi.refreshToken` rather than the inline `axios.post`
- Clear legacy `access_token` / `refresh_token` keys on application boot

## Out of Scope
Moving to httpOnly refresh cookies (post-MVP; needs CSRF design and an ADR). Session-inactivity expiry — that is `SEC-08`.

## Technical Approach
Standard shared-refresh-promise pattern; queue failed requests behind it and replay on resolve.

## Dependencies
None. **Blocks `FE-04`** — query retries increase concurrent 401s and would amplify the race.

## Risks
Low. Test the concurrent case explicitly; it is the one that currently fails.

## Security Impact
Direct. Removes a persistent post-logout bearer token and honours the application's own stated design (`authStorage.ts:1-4`: refresh in `sessionStorage`, access in memory only).

## Performance Impact
Removes a refresh-per-request loop after any token expiry.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] After a 401-triggered refresh, the **next** request carries the new token (assert the store value changed).
- [ ] Ten concurrent requests hitting 401 trigger exactly **one** refresh call.
- [ ] After `logout()`, `localStorage` contains no `access_token` and no `refresh_token`.
- [ ] `grep -rn "localStorage" src/api/client.ts` returns no matches.
- [ ] A user idle past access-token expiry can continue working without being logged out.

## Definition of Done
Merged with unit tests for the single-refresh and post-logout-clearing cases; manual verification in DevTools Application → Storage.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`frontend`, `security`, `auth`, `bug`, `mvp-required`

---

# FE-02 · Make lint, typecheck and tests runnable

## Objective
Turn on the three quality tools that are already installed and currently do nothing.

## Problem
ESLint 9 requires a flat config; there is none, so `npm run lint` cannot run and three installed plugins are inert. There is no `typecheck` script and no test runner, so types are only checked as a side effect of `npm run build`.

## Current State
`package.json` devDependencies include `eslint ^9.6.0`, `@typescript-eslint/eslint-plugin ^8`, `@typescript-eslint/parser ^8`, `eslint-plugin-react-hooks ^5`. `ls -a frontend | grep -i eslint` returns nothing — no `eslint.config.js`, no `.eslintrc*`, no `eslintConfig` key.

Scripts are `dev`, `build`, `preview`, `lint`. No `test`, no `typecheck`.

`tsconfig.json` is strict (`strict`, `noUnusedLocals`, `noUnusedParameters`) — which is why unused *symbols* are clean while roughly a dozen unused *files* survive: the compiler never sees a module nobody imports.

## Proposed State
`eslint.config.js` (flat) wired to both plugins; `"typecheck": "tsc --noEmit"`; Vitest configured with React Testing Library.

## Scope
- Flat ESLint config with `@typescript-eslint` and `react-hooks` rules
- `typecheck` script
- Vitest + `@testing-library/react` installed and a first test running
- All three wired into CI (`ARCH-01`)

## Out of Scope
Fixing every lint finding in one pass — record a follow-up if the count is large. Broad component test coverage.

## Technical Approach
Flat config with `languageOptions.parser` set to the TS parser and `plugins: { "react-hooks": ... }`. Vitest reuses the Vite config, so no separate transform pipeline is needed.

## Dependencies
Feeds `ARCH-01`.

## Risks
Low. First lint run will surface findings — including `PublishedRecordsPage.tsx:72`'s `exhaustive-deps` suppression, which `FE-04` removes properly.

## Security Impact
Indirect: `react-hooks` and unused-variable rules catch the class of mistake behind several findings here.

## Performance Impact
None on the application.

## Deployment Impact
None.

## Framework Impact
`+vitest`, `+@testing-library/react` (dev only). Activates three already-paid-for packages.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `npm run lint` exits without a configuration error.
- [ ] `npm run typecheck` exists and exits 0 on a clean tree.
- [ ] `npm test` runs and at least one test passes.
- [ ] A deliberate TypeScript error causes `npm run typecheck` to exit non-zero.
- [ ] All three commands run in CI.

## Definition of Done
Merged; three scripts green locally and in CI; any deferred lint findings ticketed.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`frontend`, `tooling`, `ci`, `testing`, `mvp-required`

---

# FE-03 · One module answers "what may this user do?"

## Objective
Collapse four non-equivalent definitions of "staff" into one hook, and remove a name collision that makes a wrong import silent.

## Problem
Four definitions disagree, and two of them are both exported as `useRole` from different modules with different return types.

## Current State

| Where | Definition | Differs when… |
|---|---|---|
| `hooks/useRole.ts:21` | role in `STAFF_ROLES` **or** Django staff | the canonical one |
| `store/auth.store.ts:100-102` | exported `useRole`, `useIsStaff`, `useIsReviewer` — **no Django-staff bypass** | a superuser with no role is not staff |
| `components/auth/ProtectedRoute.tsx:24` | private local `isDjangoStaff()` | router and page can disagree |
| `Sidebar.tsx`, `DocumentsPage.tsx:291` | re-derived inline | drifts on any change |

`store/auth.store.ts` exports a `useRole` returning `string | null`; `hooks/useRole.ts` exports a `useRole` returning an object of booleans. Both reachable via `@/`. An import from the wrong module type-checks in some uses and behaves differently.

Role strings are also compared as literals outside `lib/constants.ts` — `UserListPage` hardcodes the six names, `router/index.tsx:76` inlines an array identical to `REVIEWER_ROLES`.

## Proposed State
`hooks/useRole()` is the only way to ask. The colliding exports are deleted. Stage predicates (`canReview`, `canEdit`) live in the hook.

## Scope
- Delete `useRole`, `useIsStaff`, `useIsReviewer` from `store/auth.store.ts`
- Delete the private helpers in `ProtectedRoute` and `Sidebar`
- Replace inline role-literal comparisons with `lib/constants.ts` values
- Move `canReview()` from `RecordDetailPage` into the hook

## Out of Scope
A `<Can>` component (post-MVP). Server-side authorization — see `05-security-tasks.md`.

## Technical Approach
Delete the collisions first; TypeScript will surface every broken import immediately.

## Dependencies
None.

## Risks
Low. **Important framing:** this is a UX-consistency fix, **not** a security fix. `ProtectedRoute`'s own docstring is correct — *"client-side RBAC (UX only). Real enforcement is on the Django API (NFR-S4)."* Nothing here mitigates the server-side gaps in `05-security-tasks.md`.

## Security Impact
None directly. Prevents UI showing actions the API will reject, and vice versa.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required** (deleting the collision) · **MVP Recommended** (the rest)

## Acceptance Criteria
- [ ] `store/auth.store.ts` exports no hook named `useRole`.
- [ ] Exactly one `useRole` implementation exists in `src/`.
- [ ] `grep -rn '"Student"\|"Adviser"\|"KTTO"\|"RDCO"\|"ITSO"\|"IERC"' src/ --include=*.tsx` returns only `lib/constants.ts`.
- [ ] `npm run typecheck` passes.
- [ ] Sidebar, router and page agree on staff status for a Django superuser with no assigned role (test).

## Definition of Done
Merged; one hook; typecheck green; a unit test covering the superuser-without-role case.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`frontend`, `refactor`, `rbac`, `mvp-required`

---

# FE-04 · Adopt TanStack Query for server state

## Objective
Give "fetch a thing from the server" one owner, replacing hand-rolled state in 28 components.

## Problem
Caching, deduplication, retry, invalidation-after-mutation and error handling are re-decided in every page, mostly by omission — producing at least one user-visible defect where a network failure renders as an empty list.

## Current State
`@tanstack/react-query` is **not** installed (only `@tanstack/react-table`). 35 `.tsx` files use `useEffect`; twelve fetch directly inside one.

- `PendingRecordsPage.tsx:14` — `reviewsApi.pending().then(...).finally(...)` with **no `.catch`**. A network failure leaves `loading=false` and an empty list, rendering "No pending records are waiting for your review." A reviewer sees an empty queue instead of an error.
- `PublishedRecordsPage.tsx:69` — `.catch(() => {})`, error discarded.
- `PublishedRecordsPage.tsx:72` — `// eslint-disable-next-line react-hooks/exhaustive-deps` above a `JSON.stringify(filters)` dependency. That is a hand-rolled query key, complete with the suppression needed to make it work — and it is the only `eslint-disable` in the codebase.
- `notifications.store.ts:26` — `markAllRead: () => set({ unreadCount: 0 })` zeroes the count and leaves `items`; `markRead` filters client-side rather than refetching. Store and server diverge on the first interaction.
- The error-shape cast `(err as { response?: { data?: { detail?: string } } })?.response?.data?.detail` appears in **8 files**; Axios's own `AxiosError` type is imported nowhere outside `api/client.ts`.

## Proposed State
One typed query hook per resource in `api/`; pages consume hooks and own no fetch state; `notifications.store.ts` deleted.

## Scope
- Install `@tanstack/react-query`, add the provider
- One hook per resource: `useRecords(filters)`, `useRecord(id)`, `usePendingReviews()`, `useNotifications()`, etc.
- Migrate the 28 components incrementally
- Delete `notifications.store.ts`
- Centralise error extraction using `AxiosError`

## Out of Scope
Building shared list/table modules — that is `FE-05` and depends on this.

## Technical Approach
Both styles coexist during migration; convert page by page, highest-churn first (`features/records`, `features/review`).

## Dependencies
**`FE-01` must land first** — query retries amplify the refresh race. `FE-02` for tests.

## Risks
Low technically; medium on scope — 28 pages is real work. Team learning cost is 1–2 days.

**Documented alternative if time is short:** a hand-rolled `useApi<T>` hook (~40 lines) fixes the missing `.catch` and the ten duplicated loading divs for free, but not deduplication, caching or invalidation. See `FW-04` for the full three-way comparison. **Do that and stop** rather than doing neither. Do **not** adopt Query while keeping `notifications.store.ts` — two caches for one resource is worse than either alone.

## Security Impact
Minor positive — one error path means auth failures are handled consistently.

## Performance Impact
Positive: deduplication and caching remove redundant requests; supports `NFR-P2`.

## Deployment Impact
None.

## Framework Impact
`+@tanstack/react-query` (~13 KB gz). Removes `notifications.store.ts`. Lock-in low — hooks are swappable, server data untouched.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] No component in `src/features/` calls an API module directly inside `useEffect`.
- [ ] Every list page renders a distinct error state when its request fails (test with a mocked rejection) — specifically `PendingRecordsPage` no longer shows "No pending records" on a network error.
- [ ] `notifications.store.ts` is deleted.
- [ ] The `eslint-disable` in `PublishedRecordsPage.tsx` is gone.
- [ ] Marking a notification read refetches rather than mutating a local array.
- [ ] `grep -rc "response?: { data?: { detail" src/` shows the cast in at most 1 file.

## Definition of Done
Merged; all 28 components migrated or explicitly ticketed; hook tests in CI; `notifications.store.ts` deleted.

## Complexity
L

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`frontend`, `architecture`, `refactor`, `mvp-recommended`, `server-state`

---

# FE-05 · One list module instead of fourteen hand-rolled tables

## Objective
Replace duplicated table markup with the shared component that already exists, and add the sorting it is missing.

## Problem
`<table` appears in 14 feature files. The shared `DataTable` — which already wraps `@tanstack/react-table` and includes pagination — is imported by 2. A purpose-built pagination hook has 0 importers.

## Current State

| | Count |
|---|---|
| Files containing `<table` | **14** |
| Files importing `shared/DataTable` | **2** |
| Files importing `useDataTable` | **0** |

`components/shared/DataTable.tsx` is 124 lines with pagination at `:96-118` and a `TODO: add column sorting support` at `:3`. `hooks/useDataTable.ts` (30 lines) provides page/pageSize/search/ordering state and is used by nobody.

Two clusters: six near-identical review/record list pages with character-identical `<thead>` blocks; and two admin approval queues (`DownloadRequestsPage` 204 lines, `DeleteRequestsPage` 205 lines) sharing the same `STATUS_STYLES` map, filter tabs and refresh button verbatim.

**Relates to Jira `IR-39`**, which asks to *build* a data table component. It already exists — see `12-jira-ready-tasks.md` for the rewrite.

## Proposed State
`DataTable` gains sorting; a `RecordListPage` module replaces the six list pages; an `ApprovalQueuePage` module replaces the two admin queues; `useDataTable` is wired in or deleted.

## Scope
- Add column sorting to `DataTable` (closes its own TODO and `IR-39`'s sorting requirement)
- Add inline row actions so `IR-39`'s approve/reject requirement is met
- Build the two higher-level modules; migrate the eight pages
- Add an `overflow-x: auto` container (supports `FE-08` / `NFR-U3`)

## Out of Scope
The remaining six tables outside the two clusters — migrate opportunistically.

## Technical Approach
Both modules take a query hook (from `FE-04`) plus a column definition, so the page becomes a pure function of (hook, columns).

## Dependencies
**`FE-04` first** — otherwise the shared component needs loading/error props that `FE-04` then removes.

## Risks
Low; visual regressions only. Screenshot the eight pages before and after.

## Security Impact
None.

## Performance Impact
Neutral.

## Deployment Impact
None.

## Framework Impact
None — `@tanstack/react-table` is already installed.

## MVP Classification
**Post-MVP** (duplication, not defect) — except the sorting and row actions required by `IR-39`, which are **MVP Recommended**

## Acceptance Criteria
- [ ] `DataTable` supports column sorting, with sort state raised to the caller.
- [ ] `DataTable` supports inline row actions.
- [ ] Files containing a raw `<table` drop from 14 to at most 6.
- [ ] The six review/record list pages render through one shared module.
- [ ] `useDataTable` is either imported by the shared module or deleted.
- [ ] Every table scrolls horizontally within its container at a 360 px viewport.

## Definition of Done
Merged; eight pages migrated; before/after screenshots attached; `IR-39` closed against this.

## Complexity
L

## Suggested Jira Type
Story

## Suggested Priority
Medium

## Suggested Labels
`frontend`, `refactor`, `ui`, `post-mvp`

---

# FE-06 · Standardise on react-hook-form + Zod

## Objective
Ship one validation stack instead of two, and one set of rules instead of duplicates that disagree.

## Problem
Five validation packages ship. The same rules are written twice with different messages.

## Current State
Verified import counts:

| Package | Files importing |
|---|---|
| `react-hook-form` | 5 |
| `zod` | 3 |
| `formik` | 2 |
| `yup` | 1 |

Duplicated rules: password minimum 8 in `SignupPage.tsx:54` and `SettingsPage.tsx:27` with different message text; email validity as Yup `.email()` in `LoginForm.tsx` versus a hand-written regex in `SignupPage.tsx:49-50`; password confirmation twice. The input class string is duplicated verbatim between `LoginForm.tsx:20` and `SignupPage.tsx:37`.

## Proposed State
react-hook-form + Zod everywhere; shared rules in `lib/validation.ts`; `formik` and `yup` removed.

## Scope
- Migrate `LoginForm` off Formik
- Give `EvaluationPage` a Zod resolver
- Replace hand-rolled validation in `SignupPage` and `SettingsPage`
- `lib/validation.ts` for password, email and confirmation rules
- Remove `formik` and `yup` from `package.json`

## Out of Scope
Redesigning form UX. Splitting `SignupPage` (that is `FE-08`).

## Technical Approach
`recordFormSchema.ts` is the existing pattern — follow it. `SignupPage` is the largest migration; do it last.

## Dependencies
None. Overlaps `FE-08` on `SignupPage`.

## Risks
Low. Login and signup are critical paths — test both manually plus automated.

## Security Impact
Minor positive: one password rule rather than two that could drift below policy.

## Performance Impact
Smaller bundle (two packages removed).

## Deployment Impact
None.

## Framework Impact
**−2 dependencies.**

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `formik` and `yup` are absent from `package.json` and `package-lock.json`.
- [ ] `grep -rn "formik\|from \"yup\"" src/` returns no matches.
- [ ] Password and email rules are defined once in `lib/validation.ts`.
- [ ] Login, signup, settings and evaluation forms all validate and submit correctly (tests).
- [ ] Validation messages are identical for the same rule across forms.

## Definition of Done
Merged; two dependencies removed; schema unit tests in CI.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`frontend`, `forms`, `refactor`, `dependencies`

---

# FE-07 · Remove unreachable frontend code and unused dependencies

## Objective
Delete roughly 1,700 unreachable lines and six unused packages.

## Problem
Dead modules are invisible to the compiler (`noUnusedLocals` only sees imported files), and one duplicate has *different behaviour* from the module it shadows — the dangerous kind.

## Current State

| What | Lines | Why safe |
|---|---|---|
| `features/ai/RAGChatPage.tsx` + 7 components + `lib/chatStorage.ts` + `types/chat.ts` | ~840 | Not referenced by `router/index.tsx` or any component; `AIHubPage` is what is routed, and it calls no endpoints |
| `features/requests/AccessRequestsPage.tsx`, `features/storage/FolderBrowserPage.tsx` | ~350 | Unrouted |
| `router/PrivateRoute.tsx`, `router/RoleRoute.tsx`, `features/errors/ForbiddenPage.tsx` | ~120 | Superseded by `components/auth/ProtectedRoute.tsx`, the only guard the router uses |
| `components/layout/NotificationBell.tsx`, `components/records/DownloadRequestModal.tsx`, `contexts/DiscoverSearchContext.tsx`, `hooks/useDataTable.ts`, `features/discover/discoverUtils.ts`, `lib/signupData.ts` | ~250 | Zero importers each |
| `api/dashboard.ts`, `api/storage.ts` | ~100 | `dashboardApi.stats()` is bypassed by an inline `apiClient.get` in `Sidebar.tsx` |

**`features/discover/discoverUtils.ts` is a conflicting duplicate** of `lib/discoverUtils.ts` with different badge rules.

**Unused dependencies, verified at zero importers:** `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone`. With `formik` and `yup` from `FE-06`, that is **six** removable packages.

## Proposed State
Dead modules deleted; six dependencies removed; the `/storage` page decision applied.

## Scope
Delete the confirmed-dead modules and four dependencies. Fix the `Sidebar.tsx` inline call to use `dashboardApi` rather than keeping both.

## Out of Scope
`RAGChatPage` **if** `AI-08` (conversation UI) is in MVP scope — decide first; it may be the intended UI rather than dead code. Per-member API audit (`api/*.ts` individual exports) — a follow-up.

## Technical Approach
Grep for importers before each deletion; delete in one commit per cluster so revert is easy.

## Dependencies
`ARCH-03` decides `FolderBrowserPage` vs `ComingSoonPage`. `AI-08` decides the fate of the chat UI. Do after `FE-02` so typecheck catches mistakes.

## Risks
Medium on the chat UI specifically — 840 lines that may be wanted. **Confirm `AI-08` scope before deleting it**; everything else is low-risk.

## Security Impact
None.

## Performance Impact
Smaller bundle.

## Deployment Impact
None.

## Framework Impact
**−4 dependencies** here, −6 including `FE-06`.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] Every deletion has a documented zero-importer grep in the PR.
- [ ] `npm run build` and `npm run typecheck` pass.
- [ ] `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone` are absent from `package.json`.
- [ ] Exactly one `discoverUtils` module exists.
- [ ] `Sidebar.tsx` calls `dashboardApi.stats()` rather than an inline `apiClient.get`.
- [ ] A decision on the chat UI is recorded before it is deleted or kept.

## Definition of Done
Merged; grep evidence in the PR; bundle size before/after noted.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`frontend`, `cleanup`, `dependencies`, `technical-debt`

---

# FE-08 · Accessibility and responsive baseline at the primitive level

## Objective
Meet `NFR-U3` (360 px, no horizontal scroll) and fix the accessibility gaps that four small changes to shared primitives can cover.

## Problem
52 `aria-*` attributes across 128 files, concentrated in `ui/`. Generated markup has specific, fixable gaps — and wide tables have no horizontal-scroll container outside `DataTable`, which `NFR-U3` requires.

## Current State
- Icon-only buttons render `<i className="fa fa-chevron-left" />` inside `Button` with no `aria-label` — including `DataTable`'s pagination controls, so **every paginated table has two unlabelled buttons**
- `<th>` elements have no `scope="col"`; tables have no `<caption>`
- Loading states are plain text nodes with no `aria-live` or `role="status"` — the loading string `p-8 text-center text-gray-400 text-[13px]` appears in **10 files** while a `Spinner` component exists and is used in 5
- Decorative Font Awesome `<i>` elements carry no `aria-hidden="true"`
- Modal focus management unverified

## Proposed State
Fixes applied in `ui/` and `DataTable` so they propagate; a shared loading component with `role="status"`; every wide table in a horizontal-scroll container.

## Scope
- `aria-label` on `Button` when children are icon-only
- `aria-hidden="true"` on decorative icons
- Shared `LoadingState` component with `role="status"`, replacing the 10 duplicated divs
- `scope="col"` in `DataTable` headers
- `overflow-x: auto` containers on wide tables
- Verify modal focus trap and Escape handling

## Out of Scope
Full WCAG 2.1 AA audit (post-MVP, appropriate before institutional adoption).

## Technical Approach
Change the primitives, not the pages. Optionally add `eslint-plugin-jsx-a11y` to enforce it going forward.

## Dependencies
`FE-05` amplifies the benefit (one table module rather than 14). Validated by `VAL-14`.

## Risks
Low.

## Security Impact
None.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
Optional `+eslint-plugin-jsx-a11y` (dev only).

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] Every icon-only button has an accessible name (verified by `axe-core`).
- [ ] `axe-core` reports zero critical violations on login, submission, chat and workflow-status screens.
- [ ] All four `NFR-U3` core workflows complete at a 360 px viewport with no horizontal page scroll.
- [ ] Loading states announce via `role="status"`.
- [ ] The duplicated loading markup appears in at most 1 file.

## Definition of Done
Merged; `axe-core` check added to the frontend test suite; 360 px verification recorded for `VAL-14`.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`frontend`, `accessibility`, `responsive`, `nfr-u3`, `mvp-recommended`
