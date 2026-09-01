# 14 — Component Inventory

**Verdict: the primitives are good. Almost nothing uses them.**

---

## 1 · Census

| Location | Files | Lines |
|---|---|---|
| `components/` | 31 | 1,981 |
| `features/` | 48 | — |
| **Total** | **79** | |

---

## 2 · The adoption gap

This is the finding that explains most of [01](01-design-system.md)'s drift numbers.

| Primitive | Importers | Bypass |
|---|---|---|
| `Button` | **8** | **134** uses of `bg-[#6B0F12]` on hand-rolled `<button>` elements |
| `Spinner` | ~8 | **10** files hand-roll `<div className="p-8 text-gray-400 text-[13px]">Loading...</div>` |
| `DataTable` | **2** | **14** files build raw `<table>` |
| `EmptyState` | 12 | The healthiest adoption in the set |
| `text-sm` token | 7 | **182** uses of `text-[13px]` |
| `brand` token | 61 | **134** uses of `[#6B0F12]` |

A component library exists. Roughly a tenth of the product uses it.

**The `text-[13px]` case is the clearest.** `tailwind.config.js` defines `sm: ["13px", { lineHeight: "20px" }]`. So `text-sm` and `text-[13px]` compile to **the same declaration**. 182 occurrences of an arbitrary value that is byte-identical to the token it bypasses — a pure find-and-replace with zero visual risk.

**Why this matters beyond tidiness.** Every accessibility fix in [12](12-accessibility.md) is costed on the assumption that fixing a primitive fixes its consumers. `Input` gaining `aria-describedby` corrects four screens *only if those screens use `Input`*. A hand-rolled `<textarea>` on the decision screen — which is what `EvaluationPage` has — inherits nothing. **Adoption is the multiplier on every other number in this document set.**

---

## 3 · `components/ui/` — the primitives

| Component | Lines | Verdict | Work |
|---|---|---|---|
| `Button` | 48 | **FIX** | Replace `bg-[#6B0F12]` with `bg-brand`. 5 variants × 3 sizes is right; keep the API |
| `Input` | 49 | **FIX** | **Add `aria-invalid` and `aria-describedby`.** Highest-leverage fix in the product ([12](12-accessibility.md) §2E) |
| `Modal` | 56 | **FIX** | **Add focus trap and focus restore.** Has `role`, `aria-modal`, `aria-labelledby`, Escape, `aria-hidden` backdrop already |
| `Badge` | 27 | **KEEP** | Sound |
| `Card` | 24 | **KEEP** | Sound |
| `Spinner` | 23 | **KEEP** | Sound — it is bypassed, not wrong |
| `Toast` | 39 | **KEEP** | Needs `role="status"` on its region |

**No new primitive is needed.** The set is complete for this product.

---

## 4 · `components/shared/`

| Component | Lines | Verdict | Work |
|---|---|---|---|
| `DataTable` | 124 | **FIX** | `<caption>`, `<th scope>`, `overflow-x-auto`, cards below 768 px ([13](13-responsive.md)). Fix once — the two consumers and every future one inherit it |
| `StatusBadge` | 26 | **FIX** | Remove the stale `ktto_review` key; take labels from the API, not a literal map ([11](11-saas-admin.md)) |
| `EmptyState` | 15 | **FIX** | `text-gray-400` → `text-gray-500`. Add an optional action slot — most empty states in these docs prescribe a next step |
| `ConfirmDialog` | 49 | **KEEP** | Correct. **Use it on the reject action** ([07](07-review-clearance.md)) |
| `FileUploadZone` | 74 | **FIX** | Must expose a real keyboard-operable `<input type="file">`, not drag-only ([05](05-submission.md)) |
| `RoleBadge` | 20 | **FIX** | Same hardcoded-vocabulary issue as `StatusBadge` |
| `ComingSoonPage` | 39 | **REMOVE** | No "coming soon" destinations in the pilot ([03](03-navigation.md)). Deleting the component is what enforces the rule |

---

## 5 · `components/layout/`

| Component | Lines | Verdict | Work |
|---|---|---|---|
| `Sidebar` | 231 | **FIX** | Three sections only ([03](03-navigation.md)); stop bypassing `dashboardApi` (`FE-03`); one source of role truth (`FE-05`); **label the icon rail** ([12](12-accessibility.md)); `.catch` on the stats call |
| `AppShell` | 55 | **FIX** | Drop the `/` full-bleed special case; add a skip link; move focus to `<h1>` on route change |
| `NotificationBell` | 104 | **FIX** | `w-[320px]` dropdown needs `max-w-[calc(100vw-2rem)]` ([13](13-responsive.md)) |
| `Header` | 50 | **FIX** | `w-[34px]` toggle is below the 44 px touch target; **no global search box** ([03](03-navigation.md) §6) |
| `Breadcrumbs` | 46 | **KEEP** | `handle.crumb` metadata is a good pattern |
| `PageHeader` | 17 | **KEEP** | Sound |

---

## 6 · `components/auth/`, `compliance/`, `records/`

| Component | Lines | Verdict | Note |
|---|---|---|---|
| `ProtectedRoute` | 70 | **KEEP** | Its docstring is already correct: *"client-side RBAC (UX only)"* |
| `AuthBrandPanel` | 200 | **KEEP** | Largest presentational component; login only. Not on the workflow spine, so leave it alone |
| `LoginForm` | 127 | **FIX** | Errors must associate with fields |
| `AccountLockedModal` | 76 | **KEEP** | |
| `ForbiddenScreen` | 52 | **KEEP** | Needed by the *"reached a forbidden route by URL"* rule ([03](03-navigation.md) §4) |
| `AuthAlert` | 51 | **KEEP** | |
| `AuthLayout`, `AuthBootstrap` | 55 | **KEEP** | |
| `DpaConsentModal` / `DpaConsentGate` | 153 | **KEEP** | FR-M6-02. Consent text must be readable, not click-through ([05](05-submission.md)) |
| `DownloadRequestModal` | 81 | **DEFER** | The download-token flow is broken at import (`records/views.py:535–579`) |

---

## 7 · Components to build

Six. Two matter.

| # | Component | Effort | Why |
|---|---|---|---|
| 1 | **`ClearanceTrack`** | **~1 day** | The thesis contribution's only visual representation. Vertical stage list, per-office rows, 7 states, `<ol>` semantics, 360 px-safe ([08](08-workflow-resubmission.md)) |
| 2 | **`ClearanceStatus`** | *(within 1)* | One office's state as **icon + label + colour**. The unit that makes `preserved` distinguishable without colour ([12](12-accessibility.md) §2C) |
| 3 | **`PreservationNotice`** | ~1 hr | The one sentence — *"ITSO and KTTO have already cleared this record. Their approval is preserved."* — rendered in **four** places: record detail, decision screen, home attention card, history entry. **One component guarantees the wording is identical in all four**, and guarantees it disappears under `RESTART_ALL` because the array is empty, with no policy branch anywhere in the frontend |
| 4 | **`Skeleton`** | ~1 hr | Replaces 10 duplicated `Loading...` strings. `role="status"`, `aria-live="polite"`, sized to final content ([12](12-accessibility.md) §2G) |
| 5 | **`RecordCard`** | ~2 hrs | Used by home, my submissions, published records and the review queue. Consolidates four near-identical row treatments and carries the stage on every row ([03](03-navigation.md) §7) |
| 6 | **`HistoryTimeline`** | ~2 hrs | Merged decision + workflow timeline, reverse-chronological `<ol>` ([10](10-audit-history.md)) |

Plus one CSS utility, not a component: **`sr-only`**. Zero visually-hidden text exists in the product today ([12](12-accessibility.md) §1).

---

## 8 · Effort

| Group | Effort |
|---|---|
| Primitive fixes — `Button`, `Input`, `Modal`, `Toast` | ~1.5 hrs |
| Shared fixes — `DataTable`, `StatusBadge`, `EmptyState`, `FileUploadZone`, `RoleBadge` | ~3 hrs |
| Layout fixes — `Sidebar`, `AppShell`, `Header`, `NotificationBell` | ~3 hrs |
| Token retrofit — `text-[13px]` → `text-sm`, `[#6B0F12]` → `brand` | ~1 hr *(mechanical)* |
| `text-gray-400` → `text-gray-500`, `aria-hidden` on icons | ~1.75 hrs |
| **New components 3–6** | ~6 hrs |
| **`ClearanceTrack` (1–2)** | **~1 day** |
| **Total** | **≈ 3 dev-days** |

Against ~27 dev-days for the semester, of which ~12 are committed to making the system boot and closing authorization defects.

**Sequencing matters more than the total.** Do the primitive fixes *first* — they are 1.5 hours and they mean `ClearanceTrack` is built on an `Input` and `Modal` that are already correct, instead of being retrofitted afterwards.

---

## 9 · Adoption rules

The inventory is worth nothing without these.

| Rule | Enforcement |
|---|---|
| **No hand-rolled `<button>`.** Use `Button` | Lint rule or review |
| **No arbitrary colour values.** Use `brand`, `gold`, `cream` | The 134 occurrences are the debt |
| **No arbitrary font sizes.** `text-[13px]` **is** `text-sm` | Mechanical replacement |
| **No hand-rolled loading text.** Use `Skeleton` | 10 sites |
| **No raw `<table>`.** Use `DataTable`, or cards below 768 px | 14 files, most of which are being cut anyway |
| **No `<div onClick>`** for navigation | Only 1 today — hold the line |
| **No English mapped from a key in the frontend.** Labels come from the API | [11](11-saas-admin.md) |

**Where this can be dropped.** The full token retrofit across 316 occurrences is post-MVP — it is cosmetic debt with no user-visible consequence, and [01](01-design-system.md) already classifies it that way. What cannot be dropped is the primitive fixes, because every accessibility guarantee in [12](12-accessibility.md) depends on them, and `ClearanceTrack`, because without it the contribution has no interface.

---

## 10 · Removals

| Component(s) | Files | Reason |
|---|---|---|
| `RAGChatPage` + 7 chat components | 8 | Routed to nothing; conversational memory excluded ([ADR-006](../adr/006-minimum-rag-pipeline.md)); backend models are field-less stubs ([09](09-search-rag.md)) |
| `ComingSoonPage` | 1 | Removing the component enforces the no-dead-ends rule |
| `AccessRequestsPage` | 1 | Two request systems for one concept ([11](11-saas-admin.md)) |
| Storage / folder-browser components | — | Not on the workflow spine ([02](02-information-architecture.md)) |

**Removed means unrouted, not deleted from the repository.** No component in this document set needs to be destroyed — the router is the scope boundary, and it can be changed back in an afternoon if the pilot proves a need. Full disposition in [15](15-mvp-ui-scope.md).
