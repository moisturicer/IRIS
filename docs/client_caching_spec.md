# Pages keep what they have read across navigation: client-side caching — specification

**Status: PROPOSED (19 Nov 2026).** Nothing here is approved. Drafted by an AI agent (Claude Code) at Lee Jasmin Adolfo's request, from reading `main` at `13b37b1e` (after IR-1213 merged); nothing was measured in a running app. AI does not make architecture decisions (CLAUDE.md), so §4 is a recommendation for the decision ticket [IR-1032](https://citiris.atlassian.net/browse/IR-1032), whose named approver is Ashlee Sean.

**This spec is the input to IR-1032, not its deliverable.** IR-1032 is done when ADR-061 is amended or superseded and accepted. Most tickets in Appendix A have no keys on purpose: IR-1032 says the migration ticket is created only after its ADR is accepted, and CLAUDE.md forbids inventing keys. The one defect found here, T1, is already a card ([IR-1241](https://citiris.atlassian.net/browse/IR-1241)).

**How it relates to other documents.**
- **[ADR-061](adr/061-request-timeout-cancellation-and-retry.md)** (timeouts, cancellation, no automatic retry) binds every ticket here. It explicitly deferred "a data-fetching library (e.g. TanStack Query)" to a later team decision. That decision is IR-1032.
- **[ADR-073](adr/073-live-updates-by-server-sent-hints.md)** (live updates by server hints, accepted 2026-11-19, **merged** in [IR-1213](https://citiris.atlassian.net/browse/IR-1213), `fc556c1a`) decides *when* a page re-reads. This spec decides *what a page shows while it re-reads, and whether it needs to*. The two share one set of topic names, and the names IR-1213 shipped are the ones §4.4 uses.
- **[`architecture-review/03-frontend-architecture.md`](architecture-review/03-frontend-architecture.md)** compared hand-rolled reads, one `useApi` hook and TanStack Query, and recommended TanStack Query after the P0/P1 work. `architecture-tasks/03-frontend.md` then deferred it under ADR-001. This spec revisits it because the problem it predicted is now the one people report.

---

## 1. Problem statement

**What people see.** Open Discover: the papers load. Open another page, for example My Reviews as RDCO: its list loads. Go back to Discover: the papers load *again*, from a blank skeleton, as if the page had never been opened.

**Why.** IRIS has no client-side cache.
- Every screen reads in its own `useEffect`, or through `useApiRead` (IR-914), and keeps the answer in component state. When the route changes, the component unmounts and the answer is thrown away.
- `useApiRead` and `usePagedRead` are used by 8 screens; about 60 components still fetch by hand.
- IR-1213 gave `useApiRead` a quiet `refresh` that keeps the old answer on screen until the new one arrives. That helps only while the page stays open: it is still component state, so navigating away still throws it away.
- The browser cannot help either: every `/api/` response is `Cache-Control: no-store` (`core/middleware.py`, IR-821, ASVS 8.2.1), deliberately, so records never sit in a shared lab computer's disk cache. That middleware's own comment says *"the app's own data layer does the caching it needs in memory"*. **That data layer does not exist yet.**

The one exception proves the pattern works here: `store/library.store.ts` loads saved papers once per session, de-duplicates in-flight reads, and is cleared on every session change (`sessionEpoch`). Discover, the Record page and My Library never disagree about what is saved, and none of them re-reads it.

### 1.1 What one round trip costs today (Discover → My Reviews → Discover)

Read from the code, not measured.

| Step | Requests | Notes |
|---|---|---|
| Open Discover | **8 JSON reads**: `classifications` (**twice**), `colleges`, `record-types`, `facets`, `interests`, `psced`, then the list or For you | `DiscoverPage.tsx:231` and `:276` each read classifications |
| | **up to 12 whole manuscript PDFs** in the one-column list view | `PaperThumbnail.tsx` downloads the full paper to draw page 1 (§1.2) |
| | **2 sidebar reads**: `dashboard/stats`, and `queue-counts` for RDCO | `Sidebar.tsx`: both effects depend on `pathname` and `search`, so they re-read on every address change; since IR-1213 also on every matching hint and on tab focus |
| Open My Reviews | 1 read (`reviews/mine`) + 2 sidebar reads | |
| Back to Discover | **all of the first row again**, from a blank page | scroll position is restored (sessionStorage), the data is not |
| Type in Discover's search | 2 sidebar reads **per debounced keystroke** | the query string changes, and the sidebar effects depend on `search` |

### 1.2 Two findings that are bugs, not only slowness

1. **Discover thumbnails download whole papers again.** [IR-1130](https://citiris.atlassian.net/browse/IR-1130) ("covers load a small first-page image instead of the whole manuscript") was **closed as obsolete on 2026-11-15** because IR-1082 had deleted `ManuscriptCover`. The same day, **IR-1141 (`820b77da`) added `PaperThumbnail`, which calls `recordsApi.manuscriptBlob` per row again**. The cost IR-1130 described is back: a page of 12 rows downloads 12 papers, and every return to Discover downloads them again.
2. **Each of those thumbnails writes a `DOWNLOAD` audit event.** `RecordViewSet.manuscript` (`apps/records/views.py:579`) calls `create_audit_event("DOWNLOAD", …, metadata={"source": "manuscript", "inline": True})` on every call. Scrolling Discover therefore records "downloads" of papers nobody opened, once per visit. The audit export is evaluation evidence (`docs/evaluation/AUDIT_EXPORT.md`), so this inflates a number the thesis may report. **Caching alone does not fix this**: the first visit still writes them. Both are tracked as [IR-1241](https://citiris.atlassian.net/browse/IR-1241).

---

## 2. Goals

- **G1.** Returning to a page shows what it showed before **at once**, then refreshes it quietly if it may have changed. No blank skeleton on Back.
- **G2.** The same data is read once, not once per component (classifications, the sidebar counts, the record's detail).
- **G3.** What a person sees is never *wrong*, only at most briefly *old*, and work queues are re-checked every time they are opened.
- **G4.** Nothing cached outlives the session or crosses accounts on a shared PC.
- **G5.** A Discover thumbnail never downloads a whole paper and never records a download.

## 3. Non-goals

- HTTP caching of API responses. `no-store` stays (IR-821).
- Offline use, or persisting any cache to `localStorage`, `sessionStorage` or IndexedDB (ADR-044 §7, ASVS 8.2.1).
- Caching AI runtime streams, reader grants, auth endpoints, downloads, watermarked copies or the audit export.
- Changing what the server returns or who may read it. `visible_to` stays the one predicate.
- Live updates themselves (ADR-073, IR-1213).

---

## 4. Proposed approach

### 4.1 The decision IR-1032 has to make

IR-1032 already lists three options. Restated against this problem:

**A. Finish migrating to `useApiRead`.**
- *Gains:* no new dependency; ADR-061 unchanged; screens become consistent.
- *Costs:* **does not fix the reported problem.** `useApiRead` keeps its answer in component state, so Back still starts blank. Adding a cache to it means writing keys, de-duplication, invalidation, garbage collection and session clearing by hand — the "small, worse TanStack Query" the architecture review warned about.

**B. Adopt TanStack Query (`@tanstack/react-query` v5), configured to IRIS's rules.** *Recommended.*
- *Gains:* an in-memory cache keyed by what was asked; stale-while-revalidate (G1); de-duplication of identical reads (G2); `invalidateQueries` after a write and on an ADR-073 hint; infinite queries for Load more; it passes an `AbortSignal` to every read, so ADR-061's cancellation carries over.
- *Costs:* about 13 KB gzipped; one more concept for four people to learn; its defaults contradict ADR-061 (it retries three times) and must be overridden (§4.2); two styles coexist until the migration ends; tests need a `QueryClient` wrapper.

**C. Per-page Zustand stores, like `library.store.ts`.**
- *Gains:* no dependency; a pattern the team already knows and trusts.
- *Costs:* every page writes its own loading, fencing, staleness and invalidation. library.store.ts is ~420 lines for one resource; IRIS has about twenty.

**D. Keep pages mounted (hide instead of unmount on route change).**
- *Gains:* zero data code; Back is instant.
- *Costs:* react-router v6 has no keep-alive; every visited page keeps running effects and memory; a kept page never re-checks, so work queues go stale (fails G3).

### 4.2 IRIS defaults for the cache (if B is chosen)

One `QueryClient`, created in `App.tsx`. Every number below is **proposed, not approved**, and lives in one file so changing it is one line, as ADR-061 did for timeouts.

| Setting | Value | Why |
|---|---|---|
| `retry` | `false` | ADR-061: nothing repeats a read on its own. A timeout shows the *interrupted* state and the reader's Retry. |
| `refetchOnWindowFocus` | `true` | ADR-073 decision 6 already requires a refetch on focus. |
| `refetchOnReconnect` | `true` | Same rule, for a dropped campus connection. |
| `gcTime` | 10 minutes | An unvisited page's data is dropped after this. |
| `staleTime` | per class, §4.3 | |
| persister | **none** | In memory only (§3). |
| on session change | `queryClient.clear()` | Subscribed to the same `sessionEpoch` `library.store` uses, so the next person on a shared PC starts empty, and a response that lands after sign-out is discarded. |

`useApiRead` keeps its public shape (`status`, `data`, `error`, `retry`, IR-1213's quiet `refresh`, with `interrupted` from `isRequestTimeout`) and is re-implemented over `useQuery` with an added `key`. `refresh` becomes a background refetch, which is what it already promises. A screen already on `useApiRead` migrates by adding one argument.

### 4.3 What is cached, and how fresh it must be

| Class | Examples | `staleTime` | On return |
|---|---|---|---|
| **Reference lists** | classifications, colleges, record types, PSCED, Discover's facet years, advisers | 30 min | shown, not re-read |
| **Catalogue** | Discover list and For you, people search, similar / related works, a person's profile | 60 s | shown at once; re-read in the background if older |
| **Work queues** | My Reviews (per tab and filter), Office console, RDCO's request queues, the sidebar counts, the bell, Notifications | **0** | shown at once **and always re-read**, with a quiet "Updating" hint; ADR-073 hints invalidate them |
| **A record** | the record detail, AI overview, comments, review threads, documents, response letters | 0–30 s | shown at once, re-read; invalidated by the page's own writes and by `record:<id>` hints |
| **Manuscript bytes** | the Paper View reader's PDF | session, max 3 papers | §4.5 |
| **Never cached** | auth, grants, runtime streams, downloads, audit export, `incrementAccess` and every other write | — | — |

`incrementAccess` is a write, so caching the record never suppresses the per-visit count.

**The work-queue rule matters for the workflow.** A cached My Reviews list may show a seat someone else claimed a minute ago. The server already refuses a stale act (seat claim, routing), and the row error already says so; the cache only changes what is shown for the second before the re-read lands.

### 4.4 Query keys are ADR-073's topics

ADR-073 sends hints such as `{"topics": ["reviews", "record:42"]}`. On `main`, pages subscribe with `useLiveRefresh(topics, reload)` (`hooks/useLiveRefresh.ts`), using exactly five topics:

| Topic | Subscribed by today |
|---|---|
| `queues` | the sidebar's RDCO counts; Role, Download, Delete and Call requests |
| `reviews` | My Reviews, the Office console, the sidebar's My Reviews count |
| `library` | My Library, the sidebar's My Library dot |
| `notifications` | `useNotifications` (the bell) |
| `record:<id>` | Paper View |

If every query key starts with the matching topic, a hint becomes one call:

```ts
// api/queryKeys.ts — one place names every key
export const keys = {
  reviews:       (view: MyReviewsView) => ["reviews", "mine", view] as const,
  officeConsole: ()                    => ["reviews", "office"] as const,
  queues:        ()                    => ["queues"] as const,
  notifications: ()                    => ["notifications"] as const,
  library:       ()                    => ["library", "mine"] as const,
  record:        (id: number)          => ["record", id] as const,
  catalogue:     (q: DiscoverQuery)    => ["catalogue", q] as const,
  reference:     (name: string)        => ["reference", name] as const,
};

// on a hint: "record:42" → ["record", 42]; "reviews" → ["reviews"]
queryClient.invalidateQueries({ queryKey: topicToKey(topic) });
```

`queueCountsChanged()` (IR-1138) becomes `invalidateQueries({ queryKey: ["queues"] })`.

`useLiveRefresh` itself can stay: its coalescing, reconnect and focus handling are already right. Only the `reload` passed to it changes, from a hand-written re-read to an invalidation. Once a page's reads are queries, `refetchOnWindowFocus` and `useLiveRefresh`'s own focus handler overlap; T12 keeps one.

### 4.5 Discover thumbnails and the reader's PDF

**Thumbnails (G5): a small image from the server**, as IR-1130's acceptance criteria already said:
- `GET /records/<id>/first-page/` returns a small image, behind `get_object()` / `visible_to` (404 for a reader who cannot see it), by record id, never a path.
- `Cache-Control: private, max-age=…`, with the served revision in the URL or an `ETag`, so a new version changes the image. The profile photo already opts out of `no-store` this way (`apps/accounts/views.py:573`).
- **It writes no `DOWNLOAD` event**, or a distinct event kind if the team wants views counted. That is a team decision (§6).
- Rendered once per revision on the server (Celery) or on first request. This is backend work.

*Gains:* tens of kilobytes instead of a paper per row; no PDF parsing in the browser; the browser's private cache then makes Back free; no audit noise.
*Costs:* an endpoint, a render step and its storage; a backend owner.

*Interim, frontend only:* keep each drawn thumbnail as an image in an in-memory map keyed by record id, so a return to Discover does not download again. This halves the repeated cost but leaves the first visit's downloads and audit events, so it does not close G5.

**The reader's PDF:** keep the last 3 papers' bytes in memory, keyed by record id **and** served revision (`served_manuscript_identity`, IR-583), cleared with the rest on session change. Reopening a paper from Discover then skips the download. IR-1128 (In Review) draws the reader's name over the page in the browser, so the bytes are the same for every reader and caching them changes no watermark. If IR-1129's pre-built per-reader copy is ever adopted, the key must include the reader too.

---

## 5. Constraints every ticket keeps

- **Session isolation.** Every cache, including the thumbnail and PDF maps, is cleared on `sessionEpoch`. A test proves account B never sees account A's cached rows after sign-out and sign-in on the same tab.
- **ADR-061.** No automatic retry; reads cancel on unmount and key change; a stale response never replaces a newer one.
- **Accessible states.** Loading, interrupted and failed stay distinguishable (IR-914). A background re-read never moves focus or re-announces a list; only a change the reader caused is announced.
- **One cache per resource.** Never keep a Zustand store *and* a query for the same data (architecture review §03). `library.store` keeps saved papers and folders; `records.mine` (My Library's own list) is a separate resource and may become a query.
- **Bundle.** `npm run build` and `scan:bundle` pass; devtools are not shipped.

---

## 6. Open questions for the team

1. **IR-1032: is option B accepted?** Approver Ashlee Sean. Everything in Appendix A except T1 waits on it.
2. **The `staleTime` numbers in §4.3.** Proposed only.
3. **Should a thumbnail count as a download in the audit log?** Recommended: no. Today it does, once per row per visit.
4. **Who builds the first-page endpoint?** It is backend; this spec's author owns frontend.
5. ~~**Order against IR-1213.**~~ Settled: IR-1213 merged first (2026-11-19), with the topic names §4.4 uses. T12 replaces each `reload` with an invalidation.
6. **PDF memory ceiling** on lab PCs: is 3 papers right?

---

## Appendix A. Proposed tickets

All under the frontend epic [IR-518](https://citiris.atlassian.net/browse/IR-518) unless noted. Keys are assigned when the cards are created. Priority reflects what people reported and what is a defect.

| # | Ticket | Area | Depends on | Size |
|---|---|---|---|---|
| T0 | **(exists) [IR-1032](https://citiris.atlassian.net/browse/IR-1032)**: decide the server-state approach; amend ADR-061 with §4.1–4.4 if B is chosen | architecture | — | S |
| T1 | **(created) [IR-1241](https://citiris.atlassian.net/browse/IR-1241)**: Discover thumbnails download each whole paper and record a download for every row. First-page image endpoint (backend) and `PaperThumbnail` switched to it (frontend); an interim in-memory thumbnail map may ship first | backend + frontend | — | M |
| T2 | **Foundation**: add TanStack Query; IRIS defaults (§4.2); `api/queryKeys.ts` (§4.4); clear on session change; `useApiRead` over `useQuery`; test wrapper; tests for no-retry, cancellation and no cross-account leak | frontend | T0 | M |
| T3 | **Reference lists read once per session**: classifications, colleges, record types, PSCED, facets, advisers, used by Discover, interests, Edit details and Publish | frontend | T2 | S |
| T4 | **Discover keeps its results on Back**: list and For you as infinite queries; scroll restore from the cache instead of re-reading N pages; Not interested via `setQueryData`; stale-cursor handling kept; people results too | frontend | T2, T3 | M |
| T5 | **Sidebar counts, bell and Notifications from one cache**: no re-read on every address change; `queueCountsChanged` → invalidation; replace `notifications.store` (absorbs [IR-1033](https://citiris.atlassian.net/browse/IR-1033)'s refetch on focus) | frontend | T2 | M |
| T6 | **My Reviews and Office console show the last list at once and re-check it**: keyed per tab and filter; seat claim and decisions invalidate `["reviews"]` | frontend | T2 | M |
| T7 | **My Library's own list cached** (`records.mine`), `library.store` unchanged | frontend | T2 | S |
| T8 | **Paper View sections cached per record**: detail, AI overview, comments, threads, documents, related works; writes invalidate `["record", id]` | frontend | T2 | L (split by section if needed) |
| T9 | **Reader PDF kept for the last 3 papers** by record and revision (§4.5) | frontend | T2 | S |
| T10 | **RDCO request queues and admin pages on the cache**: Role, Download, Delete, Call requests; reported comments; users; audit log; sessions; notices; retention | frontend | T2 | M |
| T11 | **Remaining reads**: Calls & Conferences, My Calls, person profile, Ask IRIS's earlier conversations | frontend | T2 | S |
| T12 | **ADR-073 hints invalidate queries by topic**: the eleven `useLiveRefresh` call sites in §4.4 pass an invalidation instead of a hand-written re-read; one focus handler, not two | frontend | T2 (IR-1213 merged) | S |

**Suggested order.** T1 now (a defect, independent of T0). Then T0 → T2 → T3 → T4 and T5 (the two the report names) → T6 → T8/T9 → T7, T10, T11. T12 is done page by page as each page moves onto the cache; until then IR-1213's `reload` callbacks keep working unchanged.

**Each implementation ticket's acceptance criteria include:** the Back scenario of §1.1 for its pages shows the previous content with no skeleton; its writes invalidate what they change; its tests run under the `QueryClient` wrapper with no retry; and `docs/testing/traceability/IR-XXX.md` is added (ADR-055).
