# 15 — MVP UI Scope

**The pilot surface is defined per role, not as a single number — see [§10](#10--the-surface-by-role).**

The scope boundary in [ADR-001](../adr/001-mvp-scope-boundary.md), applied to the interface.

> **The "16 screens" target is retired.** It was set before Discover, My Library, My Workspace
> and Calls & Conferences existed, and a single global cap cannot survive a four-role system —
> every argument about it turns into an argument about whether an administration screen counts.
> §2's four dispositions still bind, and §1's spine test is still the test. What changed is the
> unit: **each role has a named surface**, and a screen is in scope when it appears on one of
> them. §10 is that list, and it is the answer to "what does this role see?" — the question
> this document previously could not answer.

---

## 1 · The test

A screen is in the MVP if it sits on the workflow spine ([02](02-information-architecture.md)):

```
SUBMIT → REVIEW → ROUTE → PARALLEL CLEARANCE → DECLINE/APPROVE
   → CLEARANCE-AWARE RESUBMISSION → COMPLETE/PUBLISH → AUDIT
```

…or is required to reach it (authentication), or is required to evaluate it (audit).

**Everything else is out**, regardless of how finished it looks. A completed screen that is not on the spine still costs states, errors, empty states, loading states, accessibility, responsive behaviour, test coverage, and — during the pilot — a participant's attention.

Four dispositions:

| | Meaning |
|---|---|
| **KEEP** | On the spine. Build or fix it |
| **REDUCE** | On the spine, but smaller than it currently is |
| **DEFER** | Route removed, **component retained**. Re-routable in an afternoon |
| **REMOVE** | Unrouted, and not intended to return in this form |

**No component is deleted from the repository.** The router is the scope boundary. That makes every cut here reversible, which is the only reason cuts this deep are safe to make before a pilot.

---

## 2 · Disposition — all 37

### Authentication — 4 screens, all KEEP

| Page | Disposition | Note |
|---|---|---|
| `LoginPage` | **KEEP** | Field-associated errors ([12](12-accessibility.md)) |
| `SignupPage` | **KEEP** | |
| `EmailVerifyPage` | **KEEP** | |
| `PendingApprovalPage` | **KEEP** | `AppShell` renders it before the app ([04](04-dashboard.md)) |

### The spine — 9 screens

| Page | Disposition | Doc |
|---|---|---|
| `HomePage` | **REDUCE** | [04](04-dashboard.md) — work list, no charts |
| `AddRecordPage` | **REDUCE** | [05](05-submission.md) — type-first, route preview, explicit submit |
| `EditRecordPage` | **KEEP** | Resubmission path ([08](08-workflow-resubmission.md)) |
| `MyRecordsPage` | **KEEP** | Stage on every row |
| `RecordDetailPage` | **KEEP** | [06](06-record-detail.md) — **+ Clearance Track** |
| `DocumentsPage` | **KEEP** | Genuinely a separate task |
| `PendingRecordsPage` | **REDUCE** | [07](07-review-clearance.md) — becomes the one queue |
| `EvaluationPage` | **KEEP** | [07](07-review-clearance.md) — made self-sufficient |
| ~~`PublishedRecordsPage`~~ | **REMOVED** | Was **KEEP** (*"public value of the corpus"*). `DiscoverPage` took the browse role and the component was deleted — the corpus is still public, through Discover. See the reversal note under `DiscoverPage` in DEFER below |

### Supporting — 3 screens

| Page | Disposition | Doc |
|---|---|---|
| `AIHubPage` | **REDUCE** | [09](09-search-rag.md) — rebuilt as "Search" |
| `NotificationsPage` | **KEEP** | Index into the workflow ([02](02-information-architecture.md) §7) |
| `ForbiddenPage` | **KEEP** | Required by the URL-access rule ([03](03-navigation.md) §4) |

### RDCO — 2 screens

| Page | Disposition | Doc |
|---|---|---|
| `AuditLogPage` | **KEEP** | [10](10-audit-history.md) — needs `W-04`'s events |
| `RoleRequestsPage` | **KEEP** | [11](11-saas-admin.md) — the only administration in the pilot |

**That is 18 components producing 16 destinations** — `ForbiddenPage` and `PendingApprovalPage` are
states rather than destinations. This was the original sixteen; [§10](#10--the-surface-by-role)
supersedes it as the definition of scope, and the two differ — §10 is what is actually built.

### DEFER — 11

| Page | Reason |
|---|---|
| `DashboardPage` | Unrouted already. `HomePage` is the landing |
| `DiscoverPage` | **Reversed — now KEEP, and it is the landing route.** The reasoning stands ("two browse surfaces, one corpus") but resolved the other way: Discover won and `PublishedRecordsPage` was deleted. Recorded here rather than edited away, because the original call was reversed by a decision, not by a mistake |
| `ApprovedRecordsPage` | A filter on the queue ([07](07-review-clearance.md)) |
| `DeclinedRecordsPage` | A filter on the queue |
| `ApprovedProposalsPage` | A filter on the queue |
| `UserListPage` | Django admin covers it at pilot scale |
| `SettingsPage` | Nothing in it is per-user configurable in the MVP |
| `SessionsPage` | Real, but an operator task at this scale |
| `DownloadRequestsPage` | The download-token flow **fails at import** (`records/views.py:535–579`) |
| `DownloadTokenPage` | Same broken flow |
| `DeleteRequestsPage` | Not on the spine |
| `HelpPage` | Content, not a feature. Revisit after NFR-U2 testing shows where users get stuck |
| `ImportRecordsPage` | Imported records distort turnaround metrics (`W-04`) |
| `DocumentReviewsPage` | 13-line stub |
| `ReviewAnalyticsPage` | 13-line stub; backend returns **501**; Module 7 is Phase 2 |

### REMOVE — 4

| Page | Reason |
|---|---|
| `RAGChatPage` + 7 components | Routed to nothing; `Conversation`/`ChatMessage` are field-less stubs; conversational memory excluded by [ADR-006](../adr/006-minimum-rag-pipeline.md) |
| `StoragePage` | Not on the spine; overlaps `DocumentsPage` |
| `FolderBrowserPage` | Same |
| `AccessRequestsPage` | Superseded by role requests — two request systems for one concept |

---

## 3 · What the cuts buy

| | Before | After |
|---|---|---|
| Routes | 32 | **16** |
| Page components in scope | 37 | **18** |
| Screens needing full spec | 37 | **16** |
| Screens with a "coming soon" dead end | 3+ | **0** |

Every removed screen is a screen that does not need seven states, an error path, an empty state, a loading state, an accessibility pass, three responsive layouts and a test.

**The pilot consequence is larger than the engineering one.** In Weeks 11–12, participants performing timed tasks against NFR-U2 will explore whatever is in the navigation. A "coming soon" panel or a stub returning 501 produces a usability finding about a feature that does not exist — noise in the only dataset the evaluation gets.

---

## 4 · Effort

| Work | Effort | Source |
|---|---|---|
| Design-system and primitive fixes | ~0.5 day | [01](01-design-system.md), [14](14-component-inventory.md) |
| Accessibility fixes | ~0.75 day | [12](12-accessibility.md) |
| **`ClearanceTrack` + `ClearanceStatus`** | **~1 day** | [08](08-workflow-resubmission.md) |
| `PreservationNotice`, `Skeleton`, `RecordCard`, `HistoryTimeline` | ~0.75 day | [14](14-component-inventory.md) |
| Home reduction | ~0.5 day | [04](04-dashboard.md) |
| Submission — type-first + submit boundary | ~1 day | [05](05-submission.md) |
| Record detail — track integration, 8 blocks | ~1 day | [06](06-record-detail.md) |
| Queue merge + self-sufficient decision screen | ~1.5 days | [07](07-review-clearance.md) |
| Search rebuild + degraded mode | ~1 day | [09](09-search-rag.md) |
| Audit + history corrections | ~0.5 day | [10](10-audit-history.md) |
| Navigation reduction, route removal | ~0.25 day | [03](03-navigation.md) |
| Responsive pass, 360 px verification | ~0.5 day | [13](13-responsive.md) |
| **Total frontend** | **≈ 9 dev-days** | |

Against ~27 dev-days for the semester, of which ~12 are committed to making the system boot and closing twelve authorization defects. Frontend at 9 leaves ~6 for backend workflow, RAG, deployment and testing.

**That is tight, and the estimate should be read as a lower bound.** The cut order below exists because it will be needed.

---

## 5 · Cut order

If capacity slips, cut in this order. Decided now, not under pressure in Week 7.

| Order | Cut | Cost of cutting |
|---|---|---|
| 1 | **The AI answer block** | [ADR-006](../adr/006-minimum-rag-pipeline.md) already pre-commits to this at end of Week 6. Search still works on FTS — the screen is designed to lose this block cleanly ([09](09-search-rag.md)) |
| 2 | **Token retrofit** (316 occurrences) | Cosmetic only. No user-visible consequence |
| 3 | **Search screen entirely** | Falls back to `PublishedRecordsPage` keyword filtering. FR-M4-01 becomes Phase 2 |
| 4 | **History timeline merge** | `reviews[]` alone still renders. **But `W-04`'s events must still be written** — the UI can wait, the data cannot |
| 5 | **Home reduction** | Keep the existing `HomePage`. Ugly, not broken |
| 6 | **Responsive polish below 768 px** | **Only down to "no horizontal scroll".** NFR-U3 is a requirement, not polish |

### Never cut

| | Why |
|---|---|
| **`ClearanceTrack`** | Without it the thesis contribution has no interface. Five of the eight required communications are absent today ([00](00-design-direction.md)) |
| **`PreservationNotice`** | The one sentence that makes preserved clearance legible |
| **`W-04` workflow events** | Not a UI item, but the constraint that governs UI sequencing. Events not written during the Weeks 11–12 pilot **cannot be reconstructed**, and there is no second pilot ([10](10-audit-history.md)) |
| **`Input` and `Modal` fixes** | 1.25 hours; every accessibility guarantee depends on them |
| **NFR-U3 at 360 px** | A stated requirement |
| **`S-02` visibility on `retrieve`** | Not a UI item. Until it lands, record detail is the vehicle for an unauthorised disclosure ([06](06-record-detail.md)) |

---

## 6 · Sequencing

Order within the ~9 days. The dependencies are real, not preferences.

| Phase | Work | Why here |
|---|---|---|
| **1** | Primitive fixes — `Input`, `Modal`, `Button`, `Skeleton`, `sr-only` | **1.5 hours.** Everything built afterwards inherits correct behaviour instead of being retrofitted |
| **2** | Route removal, navigation reduction | Shrinks the surface before it is worked on. Cheapest day in the plan |
| **3** | **`W-07` API contract** *(backend)* | `ClearanceTrack` cannot be built against a payload that does not exist |
| **4** | **`ClearanceTrack`, `ClearanceStatus`, `PreservationNotice`** | The contribution. Do it while capacity is certain |
| **5** | Record detail, then decision screen | The two screens the track lands in |
| **6** | Home, submission, queue merge | Highest NFR-U2 impact |
| **7** | Search, audit, history | Supporting, and the first candidates for the cut list |
| **8** | Responsive and accessibility verification | Against finished screens |

**Phases 3 and 4 are the ones to protect.** They are the difference between a system that implements clearance-aware resubmission and a system that can be *observed* implementing it — and the evaluation measures the second.

---

## 7 · Post-MVP

Recorded so the exclusions are decisions rather than omissions.

| Item | Why not now |
|---|---|
| KPI dashboard, charts | Module 7 is Phase 2 in the SRS; `recharts` has zero importers |
| Conversational AI, summarization, chunk-level citation | [ADR-006](../adr/006-minimum-rag-pipeline.md) |
| Pooled multi-tenancy UI | [ADR-005](../adr/005-instance-per-tenant.md) — designed on paper only ([11](11-saas-admin.md)) |
| Billing, subscriptions, payment | Explicitly excluded from the MVP |
| Bulk review actions, delegation, SLA timers | Volume features; the pilot has no volume |
| Autosave drafts, document templates, bulk author import | Convenience |
| Inline PDF annotation | Large, and no requirement asks for it |
| Full token retrofit | Cosmetic debt |
| Storage browser, deletion requests, download tokens | Off-spine; the download flow is broken at import |
| Formal third-party accessibility audit | No conformance claim is made beyond [12](12-accessibility.md)'s stated scope |

---

## 8 · The boundary in one line

> **Build the sixteen screens that carry a submission from a student's draft to a published record, make the clearance state visible at every step, and instrument it well enough to measure. Everything else waits.**

---

## 9 · Recorded deviations

Screens built outside the sixteen. Listed here so the boundary above stays true
rather than quietly wrong — each one is either brought into scope by a decision,
or unrouted before the pilot.

| Screen | Route | Status | Note |
|---|---|---|---|
| `DiscoverPage` | `/` | Built, routed | Listed as **DEFER** in §2 ("overlaps `PublishedRecordsPage`"). It is now the landing surface, so the overlap resolves the other way — `PublishedRecordsPage` was deleted |
| `PaperViewPage` | `/records/:id` | Built, routed | Replaces `RecordDetailPage` (**KEEP**), carrying the Clearance Track required by [06](06-record-detail.md). In scope; the component changed, not the disposition |
| `MyLibraryPage` | `/records/mine` | Built, routed | **Not in the sixteen.** A reader-side saved-research surface: folders, likes, reading history. Took over the `My Library` route from `MyRecordsPage mode="library"`, which duplicated My Workspace behind a status filter |
| `CallsAndConferencesPage` | `/opportunities` | Built, routed | **Not in the sixteen, and not in any requirement.** A deadline board for internal calls, conference deadlines, funding windows and institutional grants, backed by a new `apps.opportunities`. Requested directly by the team; see [IR-121](https://citiris.atlassian.net/browse/IR-121) |

**`MyLibraryPage` carries no server state.** There is no bookmark, folder, like or
reading-history model in `backend/apps/` — `apps.storage` stores uploaded files and is
removed server-side by `P0-06`. Everything the page saves lives in the viewer's
`localStorage` (`lib/recordLibrary`), and every surface on it says so. Saved ids resolve
through the **list** endpoint (`?id=`), never `retrieve`, because `RecordViewSet.get_queryset`
applies `publicly_visible()` only on `list`.

**`CallsAndConferencesPage` has no SRS backing at all**, and that is worth stating
plainly rather than leaving for a reader to discover. `docs/SRS.md` contains no
requirement for announcements, calls for proposals, funding windows or institutional
grants; there is no ADR and there was no prior Jira card. It is a product addition the
team asked for, not a requirement being implemented, so **nothing in `TRACEABILITY.md`
changes** — there is no requirement for it to trace to. Two limits were chosen
deliberately and are recorded in IR-121: nothing scrapes external sources (a staff
member types every entry, with a `source` field attributing external ones), and the
calendar action emits an `.ics` file rather than scheduling an in-app reminder, because
Celery does not currently consume its own queue ([IR-83](https://citiris.atlassian.net/browse/IR-83))
and a scheduled reminder would silently never fire. Bookmarks are `localStorage`, with
the same no-server-state caveat as My Library.

**Resolved.** This was open against IR-86 (now **[IR-160](https://citiris.atlassian.net/browse/IR-160)** —
*Reduce the pilot surface to 16 screens*), whose acceptance criteria were *"16 routes remain"* and
*"Every remaining nav item leads somewhere real"*.

The second is **met**: no nav item is a placeholder. The last two `comingSoon` entries — Review
Analytics and Document Reviews, both already **DEFER** in §2 as 13-line stubs, one of them backed by
an endpoint that returns 501 — were removed from the nav and the router, along with the Storage
entry before them. A badge promising a screen that is not coming is worse than the screen's absence.

The first is **deliberately not met, and is withdrawn as a criterion.** The count is not 16 and will
not be; see the note at the top of this document and [§10](#10--the-surface-by-role). The reader-side
section IR-160 anticipated ("either §2 gains a reader-side section... or these routes come out") is
what §10 became — it covers Discover, My Library and Calls & Conferences by naming the role that
sees them, rather than by arguing them past a number.

---

## 10 · The surface, by role

Read off `frontend/src/router/index.tsx` and `components/layout/Sidebar.tsx` as built, not aspirational.
**This section is the scope boundary.** A screen is in the MVP when it appears below.

Roles come from `backend/core/permissions.py`: `REVIEWER_ROLES` = Adviser, KTTO, RDCO, ITSO, IERC ·
`STAFF_ROLES` = KTTO, RDCO, ITSO, IERC · Django admin is `is_staff`/`is_superuser`.

### Every signed-in user — 8

| Screen | Route | Group |
|---|---|---|
| Discover | `/` | Research Exploration |
| Ask IRIS | `/ai` | Research Exploration |
| My Library | `/records/mine` | Research Exploration |
| Calls & Conferences | `/opportunities` | Research Exploration |
| Submit Disclosure | `/records/add` | IP Management |
| My Workspace | `/workspace` | IP Management |
| Notifications | `/notifications` | Tools |
| Settings & Profile | `/settings` | Tools |

**This is the student surface** — a student sees these eight and nothing else. Every other role sees
these eight *plus* the sections below, because every role also submits and browses.

### + Reviewer — 3, or 4 for RDCO

`REVIEWER_ROLES`. Rendered behind `isReviewer`.

| Screen | Route |
|---|---|
| Pending Records | `/review/pending` |
| Approved | `/review/approved` |
| Declined | `/review/declined` |
| Approved Proposals *(RDCO only)* | `/review/approved-proposals` |

### + Staff — 4, or 6 for a Django admin

`STAFF_ROLES`. Rendered behind `isStaff`.

| Screen | Route | Gate |
|---|---|---|
| Manage Users | `/admin/users` | `isStaff` |
| Download Requests | `/admin/download-requests` | `isStaff` |
| Delete Requests | `/admin/delete-requests` | `isStaff` |
| Active Sessions | `/admin/sessions` | `isStaff` |
| Role Requests | `/admin/role-requests` | Django admin |
| Audit Log | `/admin/audit` | Django admin |

### Reached from a screen, not from nav

Not counted above, because nobody navigates to them directly: `/records/:id` (paper view),
`/records/:id/edit`, `/records/:id/documents`, `/review/:id/evaluate`, `/records/import`, `/help`,
and the entry screens (`/login`, `/signup`, `/activate/...`, `/download`).

### What this replaces

The per-role lists answer the question the global count could not: **what does this role see?**
The count was a proxy for "is the pilot small enough". The lists are the thing itself — and they make
the next gap obvious, which is that the reviewer surface is three queue screens and a decision screen
while the student surface is eight built-out ones. That asymmetry is the work
[IR-143](https://citiris.atlassian.net/browse/IR-143) covers, not a scope question.
