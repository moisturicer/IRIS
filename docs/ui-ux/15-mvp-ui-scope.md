# 15 — MVP UI Scope

**37 page components. 32 routes. 16 MVP screens.**

The scope boundary in [ADR-001](../adr/001-mvp-scope-boundary.md), applied to the interface.

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
| `PublishedRecordsPage` | **KEEP** | Public value of the corpus |

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

**That is 18 components producing 16 MVP screens** — `ForbiddenPage` and `PendingApprovalPage` are states rather than destinations.

### DEFER — 11

| Page | Reason |
|---|---|
| `DashboardPage` | Unrouted already. `HomePage` is the landing |
| `DiscoverPage` | Overlaps `PublishedRecordsPage`. Two browse surfaces, one corpus |
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

**`MyLibraryPage` carries no server state.** There is no bookmark, folder, like or
reading-history model in `backend/apps/` — `apps.storage` stores uploaded files and is
removed server-side by `P0-06`. Everything the page saves lives in the viewer's
`localStorage` (`lib/recordLibrary`), and every surface on it says so. Saved ids resolve
through the **list** endpoint (`?id=`), never `retrieve`, because `RecordViewSet.get_queryset`
applies `publicly_visible()` only on `list`.

**Open against [IR-86](https://citiris.atlassian.net/browse/IR-86)** (P1-18, *Reduce the pilot
surface to 16 screens*). Its acceptance criteria include *"16 routes remain"* and *"Every
remaining nav item leads somewhere real"*. The second is satisfied — no view here is a
placeholder, and Reading History is written by `PaperViewPage` rather than mocked. The
first is not, and **that is a team decision, not an implementation one**: either §2 gains a
reader-side section covering Discover and My Library, or these routes come out before the
pilot. Until it is decided, the count in §3 is understated by the rows above.
