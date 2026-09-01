# 03 — Navigation

---

## 1 · What exists

`AppShell` composes Sidebar + Header + Breadcrumbs + main, with three responsive states.

| Breakpoint | Sidebar | Behaviour |
|---|---|---|
| < 768 px | Off-canvas drawer | Overlay with `aria-label="Close menu"` backdrop; toggled from Header |
| 768–1279 px | 60 px icon rail | Icons only, section titles hidden |
| ≥ 1280 px | 230 px full | Icons + labels + section titles |

`Sidebar` builds `NavItem[]` per section, gated by `useRole()`, with an unread-notification badge and a "coming soon" pill for stubs. Active state is a brand-tinted background plus a left rail.

**This is good and needs no structural change.** The work is reduction and correctness.

---

## 2 · Problems

| # | Problem | Evidence |
|---|---|---|
| 1 | **Too many destinations for the pilot** | ~37 page components; 16 serve the pilot workflow |
| 2 | **"Coming soon" items are navigational dead ends** | Sidebar renders a `comingSoon` pill; a user clicks and gets a stub |
| 3 | **Inline role derivation** | `Sidebar` calls `useRole()` then re-derives staff status inline — a fourth definition of "staff" (`FE-05`) |
| 4 | **`dashboardApi` bypassed** | `Sidebar` calls `apiClient.get` directly for stats instead of the API module (`FE-03`) |
| 5 | **Icon-only rail has no accessible names** | At 768–1279 px labels are visually hidden but not exposed to assistive tech ([12](12-accessibility.md)) |
| 6 | **Discover home is special-cased** | `AppShell` suppresses Header and padding for `/` — inconsistent with every other route |

---

## 3 · MVP sidebar

Three sections. Everything else removed from the router (`FE-02`).

```
WORK
  Home                    /
  My Submissions          /records/mine
  New Submission          /records/add          (Student, Adviser, RDCO)
  Review Queue            /review/pending       (reviewers)  ·  badge = pending count

DISCOVER
  Published Records       /records
  Search                  /ai

ADMIN                                            (RDCO only)
  Role Approvals          /users/role-requests
  Audit Log               /audit
```

Plus **Notifications** in the Header, not the sidebar — it is a transient index, not a place.

### Rules

| Rule | Reason |
|---|---|
| **No "coming soon" items.** If it is not in the pilot, it is not in the nav | A dead end is worse than an absence. It also invites evaluation participants to comment on things that do not exist |
| Sections appear only if they contain a permitted item | An empty "ADMIN" heading for a student is noise |
| Badge counts only where actionable | Review Queue and Notifications. Not on "Published Records" |
| Labels come from configuration post-MVP | "Review Queue" may be "Clearance Queue" elsewhere ([11](11-saas-admin.md)) |
| One source of role truth — `useRole()` | `FE-05`; no inline re-derivation |

---

## 4 · Role-dependent navigation

| Section | Student | Adviser | RDCO | ITSO / IERC / KTTO |
|---|---|---|---|---|
| Home | ✅ | ✅ | ✅ | ✅ |
| My Submissions | ✅ | ✅ | ✅ | ✅ |
| New Submission | ✅ | ✅ | ✅ | — |
| Review Queue | — | ✅ | ✅ | ✅ |
| Published Records | ✅ | ✅ | ✅ | ✅ |
| Search | ✅ | ✅ | ✅ | ✅ |
| Role Approvals | — | — | ✅ | — |
| Audit Log | — | — | ✅ | — |

**Client-side gating is UX only.** `ProtectedRoute`'s docstring is already correct: *"client-side RBAC (UX only). Real enforcement is on the Django API (NFR-S4)."* Hiding a nav item is a courtesy; `S-02`…`S-05` are the control.

**Design consequence:** never rely on nav hiding for confidentiality. If a user reaches a forbidden route by URL, the server returns 403/404 and the UI shows the forbidden state — it does not pretend the route is absent.

---

## 5 · Breadcrumbs

Driven by route `handle.crumb` metadata — a good pattern already in place.

**Rules.** Never more than three levels. The record title is the last crumb on a detail screen, truncated with a `title` attribute. Breadcrumbs are supplementary — they never carry the only path to a destination. Marked up as `<nav aria-label="Breadcrumb">` with an ordered list and `aria-current="page"` on the last item.

```
Home / My Submissions / Machine learning for crop disease…
```

---

## 6 · Header

| Element | Behaviour |
|---|---|
| Menu toggle | < 768 px only; `aria-expanded`, `aria-controls` |
| Page title | Optional; usually redundant with `PageHeader` |
| Notification bell | Unread count; `aria-label="Notifications, 3 unread"` |
| User menu | Name, role, sign out |

**Do not add a global search box to the Header for the MVP.** Search is a destination with its own state, sources and degraded mode ([09](09-search-rag.md)); a header input implies instant results the architecture does not provide.

---

## 7 · Entry points to the record detail

Reachable from six places. Every one must carry enough context that the destination is not a surprise.

| From | Carries |
|---|---|
| My Submissions | Title, type, **stage** |
| Review Queue | Title, type, **stage, waiting time** |
| Published Records | Title, authors, year |
| Search results | Title, snippet, relevance |
| Notifications | The event that fired |
| Audit log | The event and actor |

**Every list row shows the stage.** A user should never open a record to find out where it is — that is what the list is for. Currently `RecordListSerializer` includes `pipeline_status`, so this is achievable without API work.

---

## 8 · Specification

**User.** All authenticated roles.

**Goal.** Reach the right destination in two clicks or fewer, and always know where they are.

**Primary action.** Navigate.

**Secondary actions.** Toggle sidebar (mobile) · open notifications · sign out.

**Required data.** `user.role_name`, `user.is_staff`, unread notification count, pending review count.

**Permissions.** Items filtered by `useRole()`. **UX only** — server enforces.

**States.** Drawer open/closed (mobile) · rail/full (desktop) · item active · badge present/absent · section empty and therefore hidden.

**Errors.** Badge count fetch fails → render without a badge; **never block navigation on a count**. Currently `Sidebar` has no `.catch` on its stats call (`FE-03`).

**Empty states.** A role with no items in a section → the section is not rendered. A reviewer with an empty queue → nav item without a badge; the empty state lives on the queue screen.

**Loading states.** Nav renders immediately with no badges; badges appear when counts resolve. **Never block the shell on a data fetch** — the current implementation is correct here.

**Accessibility.** `<nav aria-label="Main">`; `aria-current="page"` on the active item; icon-rail items need `aria-label` or visually-hidden text since labels are hidden at 768–1279 px; drawer toggle needs `aria-expanded` and `aria-controls`; focus moves into the drawer on open and returns to the toggle on close. See [12](12-accessibility.md).

**Responsive.** Three states as above. At 360 px the drawer is full-width and dismissible by backdrop, Escape, or the close control ([13](13-responsive.md)).

**MVP/Post-MVP.** MVP: the three sections above. Post-MVP: institution switcher (not needed under instance-per-tenant, [ADR-005](../adr/005-instance-per-tenant.md)) · configurable nav labels · saved views · global search.

**Backend/API dependencies.** `dashboardApi.stats()` for counts (`FE-03` — stop bypassing it) · `notificationsApi` unread count · `reviewsApi.pending()` for the queue badge.
