# 03 — Navigation

---

## 1 · What exists

`AppShell` composes Sidebar + Header + Breadcrumbs + main, with three responsive states.

| Breakpoint | Sidebar | Behaviour |
|---|---|---|
| < 768 px | Off-canvas drawer | Overlay with `aria-label="Close menu"` backdrop; toggled from Header |
| 768–1279 px | 60 px icon rail | Icons only, section titles hidden |
| ≥ 1280 px | 230 px full | Icons + labels + section titles |

`Sidebar` builds its sections from `navFor(role)` in [`lib/access.ts`](../../frontend/src/lib/access.ts), with badges attached per item. Active state is a brand-tinted background plus a left rail. There is no longer a "coming soon" pill — see §3.

**This is good and needs no structural change.** The work is reduction and correctness.

---

## 2 · Problems

| # | Problem | Evidence |
|---|---|---|
| 1 | **Too many destinations for the pilot** | ~37 page components; 16 serve the pilot workflow |
| 2 | **"Coming soon" items are navigational dead ends** | Sidebar renders a `comingSoon` pill; a user clicks and gets a stub |
| 3 | ~~**Inline role derivation**~~ | **Closed (`IR-160`).** `Sidebar` held four separate re-derivations of "staff" — one on `is_staff`, one on `is_superuser`, one on a role list — and disagreed with the router, so ITSO and IERC were shown Role Requests and Audit Log and then refused by it. Both now read one map |
| 4 | **`dashboardApi` bypassed** | `Sidebar` calls `apiClient.get` directly for stats instead of the API module (`FE-03`) |
| 5 | **Icon-only rail has no accessible names** | At 768–1279 px labels are visually hidden but not exposed to assistive tech ([12](12-accessibility.md)) |
| 6 | **Discover home is special-cased** | `AppShell` suppresses Header and padding for `/` — inconsistent with every other route |

---

## 3 · MVP sidebar

Five sections, each rendered only when the signed-in role has at least one item in it. Built from `frontend/src/lib/access.ts` — the same map the router gates on — so this listing describes code rather than intent.

```
RESEARCH EXPLORATION                                  (every role)
  Discover                /
  Ask IRIS                /ai
  My Library              /records/mine
  Calls & Conferences     /opportunities

IP MANAGEMENT
  Submit Disclosure       /records/add          (Student, Adviser)
  My Workspace            /workspace            (Student, Adviser)  · badge = pending
  Import Records          /records/import       (RDCO)

REVIEW QUEUE                                          (reviewers)
  Pending Records         /review/pending
  Approved                /review/approved
  Declined                /review/declined
  Approved Proposals      /review/approved-proposals  (RDCO)

TOOLS                                                 (every role)
  Notifications           /notifications        · badge = unread
  Settings & Profile      /settings

ADMINISTRATION                                        (RDCO)
  Role Requests           /admin/role-requests  · badge = pending
  Download Requests       /admin/download-requests
  Delete Requests         /admin/delete-requests
  Audit Log               /admin/audit
```

**Amended 2026-09-06.** This section described three sections, `Published Records` (deleted — Discover took the browse role) and `Notifications` in the header rather than the sidebar. It now matches what ships. **Manage Users and Active Sessions are gone from the app entirely**: account administration belongs to the Django admin site, and per-user session management is a separate screen tracked as `IR-124`.

### Rules

| Rule | Reason |
|---|---|
| **No "coming soon" items.** If it is not in the pilot, it is not in the nav | A dead end is worse than an absence, and it invites evaluation participants to comment on things that do not exist. The `comingSoon` flag has been **removed from `NavItem`** — nav entries now come from a map of screens that exist and are routed, so a dead end is no longer something to remember not to add |
| Sections appear only if they contain a permitted item | An empty "ADMINISTRATION" heading for a student is noise. Falls out of the map rather than being a second rule |
| Badge counts only where actionable | My Workspace, Review Queue, Notifications, Role Requests |
| Labels come from configuration post-MVP | "Review Queue" may be "Clearance Queue" elsewhere ([11](11-saas-admin.md)) |
| **One source of role truth — `lib/access.ts`** | Was `useRole()`, but `Sidebar` re-derived staff status inline anyway — four definitions of "staff" in one component. Now the router and the sidebar read one map, so a link cannot exist without a matching gate (`IR-160`) |

---

## 4 · Role-dependent navigation

| Section | Student | Adviser | RDCO | ITSO | IERC | KTTO |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Research Exploration | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit Disclosure | ✅ | ✅ | — | — | — | — |
| My Workspace | ✅ | ✅ | — | — | — | — |
| Import Records | — | — | ✅ | — | — | — |
| Review Queue | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| Approved Proposals | — | — | ✅ | — | — | — |
| Tools | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Administration | — | — | ✅ | — | — | — |

**The three offices are separate columns, deliberately.** Collapsing ITSO, IERC and KTTO into one "office reviewer" column would erase the distinction the thesis contribution rests on — parallel multi-office clearance, where one office requiring revision resets only its own clearance. They share a *screen*; they are not one role.

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

**Required data.** `user.role_name`, unread notification count, pending review count. **Not `user.is_staff`** — it is a Django admin-site flag, and using it for authorization was the defect `IR-165` closed.

**Permissions.** Items come from `navFor(role)` — one map, shared with the router, so a nav item cannot exist without a matching gate. Still **UX only**: the Django API enforces (`core/permissions.py`, `IR-165`).

**States.** Drawer open/closed (mobile) · rail/full (desktop) · item active · badge present/absent · section empty and therefore hidden.

**Errors.** Badge count fetch fails → render without a badge; **never block navigation on a count**. Currently `Sidebar` has no `.catch` on its stats call (`FE-03`).

**Empty states.** A role with no items in a section → the section is not rendered. A reviewer with an empty queue → nav item without a badge; the empty state lives on the queue screen.

**Loading states.** Nav renders immediately with no badges; badges appear when counts resolve. **Never block the shell on a data fetch** — the current implementation is correct here.

**Accessibility.** `<nav aria-label="Main">`; `aria-current="page"` on the active item; icon-rail items need `aria-label` or visually-hidden text since labels are hidden at 768–1279 px; drawer toggle needs `aria-expanded` and `aria-controls`; focus moves into the drawer on open and returns to the toggle on close. See [12](12-accessibility.md).

**Responsive.** Three states as above. At 360 px the drawer is full-width and dismissible by backdrop, Escape, or the close control ([13](13-responsive.md)).

**MVP/Post-MVP.** MVP: the three sections above. Post-MVP: institution switcher (not needed under instance-per-tenant, [ADR-005](../adr/005-instance-per-tenant.md)) · configurable nav labels · saved views · global search.

**Backend/API dependencies.** `dashboardApi.stats()` for counts (`FE-03` — stop bypassing it) · `notificationsApi` unread count · `reviewsApi.pending()` for the queue badge.
