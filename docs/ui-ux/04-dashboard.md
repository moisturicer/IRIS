# 04 — Home / Dashboard

**Verdict: REDUCE.** Replace the current landing with a role-aware "what needs me" screen. No analytics, no charts.

---

## 1 · What exists

Two competing landings: `HomePage` (routed at `/`) and `DashboardPage` (unrouted). `AppShell` special-cases `/` as full-bleed with no Header, so the home screen is structurally inconsistent with every other route.

`Sidebar` fetches dashboard stats via an inline `apiClient.get`, bypassing `api/dashboard.ts` — which is itself dead code (`FE-03`).

`recharts` is installed with **zero importers**. Someone intended charts; nobody built them.

---

## 2 · Direction

**A dashboard is not the point.** IRIS's users arrive with a specific intent — check my submission, review what is waiting for me. A KPI screen answers a question they did not ask, and Module 7 (KPI Dashboard) is already Phase 2 in the SRS.

**Replace with a work list.** One question: *what needs my attention?*

```
Good afternoon, Jasmin

  NEEDS YOUR ATTENTION
  ┌──────────────────────────────────────────────────────┐
  │ ↩ IERC requested revisions                           │
  │   Machine learning for crop disease detection        │
  │   18 Sep · ITSO and KTTO clearance preserved      →  │
  └──────────────────────────────────────────────────────┘

  YOUR SUBMISSIONS                              View all →
  ┌──────────────────────────────────────────────────────┐
  │ Blockchain credential verification                   │
  │ Thesis/Research · With IERC and KTTO for review   →  │
  ├──────────────────────────────────────────────────────┤
  │ Solar panel efficiency study                         │
  │ Project · Published · 2 Sep                       →  │
  └──────────────────────────────────────────────────────┘
```

Reviewers get the same shape with their queue first:

```
  AWAITING YOUR REVIEW                                (4)
  ┌──────────────────────────────────────────────────────┐
  │ Machine learning for crop disease detection          │
  │ Thesis/Research · Waiting 3 days                  →  │
  └──────────────────────────────────────────────────────┘
```

**"Needs your attention" is the whole design.** For a student that is declined records. For a reviewer it is their pending queue. It is the only block that earns the top of the screen, and it is the block that makes the workflow feel responsive rather than opaque.

---

## 3 · Composition by role

| Role | Block 1 | Block 2 | Block 3 |
|---|---|---|---|
| **Student** | Needs attention — declined records | My submissions (5 recent) | Recently published (browse) |
| **Adviser** | Awaiting your review | My submissions | Recently published |
| **RDCO** | Awaiting your review | Pending role approvals | Recently published |
| **ITSO / IERC / KTTO** | Awaiting your review | — | Recently published |

**Blocks are hidden when empty**, except "needs your attention", which shows a positive empty state — the reassurance is the point.

---

## 4 · What is deliberately excluded

| Excluded | Reason |
|---|---|
| Charts and KPI tiles | Module 7 is Phase 2 in the SRS. `recharts` has zero importers; do not start now |
| Counts as headline numbers | "12 submissions" is not actionable. The list is |
| Activity feed | Duplicates notifications ([02](02-information-architecture.md) §7) |
| System health, storage usage | Operator concerns, not user concerns |
| Analytics for the pilot | Usage evidence comes from `W-04`'s audit export, not a dashboard ([`docs/mvp-validation/03-final-evaluation-plan.md`](../mvp-validation/03-final-evaluation-plan.md)) |

---

## 5 · Specification

**User.** All authenticated roles.

**Goal.** See what needs attention and reach it in one click.

**Primary action.** Open the record that needs action.

**Secondary actions.** View all submissions · view all pending reviews · browse published records.

**Required data.**
- Student: records owned with `pipeline_status = declined`; 5 most recent owned records
- Reviewer: `reviewsApi.pending()` — records at their stage with a pending clearance
- RDCO: pending role requests count
- All: 3–5 recently published records

**Permissions.** Each block filtered by role; all data server-filtered (`B-05`). **The home screen must never surface a record the viewer cannot open** — a title alone is a disclosure.

**States.**

| State | Rendering |
|---|---|
| Has attention items | Attention block first, amber-accented |
| Nothing needs attention | Positive empty state: *"Nothing needs your attention right now."* |
| New user, no submissions | Onboarding: *"You haven't submitted anything yet."* + primary "New Submission" |
| Reviewer with empty queue | *"Your review queue is clear."* |
| Pending role approval | Never reaches here — `AppShell` renders `PendingApprovalPage` |

**Errors.** Any block's fetch fails → that block shows an inline error with retry; **other blocks still render**. A dashboard that fails wholesale because one count failed is worse than a partial one.

**Empty states.** As above. Every empty state is written as reassurance or as a next step, never as an absence.

**Loading states.** Skeleton cards matching final dimensions — the block shapes are known, so skeletons avoid layout shift. Blocks resolve independently; the screen does not wait for the slowest.

**Accessibility.** `<h1>` greeting; each block an `<h2>` with a `<section aria-labelledby>`. Cards are links, not click-handled divs — real `<a>` elements so keyboard and middle-click work. Attention items get `role="status"` only on first render, not on every poll, to avoid repeated announcement.

**Responsive.** Single column throughout. At ≥ 1024 px blocks may sit two-up, but single-column is acceptable and simpler. Cards are full-width at 360 px with stage and date stacking below the title ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP** — attention block, submissions list, published list. **Post-MVP** — KPI tiles, per-stage throughput, SLA warnings, saved filters.

**Backend/API dependencies.** `recordsApi.mine()` (currently returns a bare array — `FE-09` should paginate) · `reviewsApi.pending()` · `recordsApi.list()` for published · role-requests count for RDCO. **`W-07`'s `offices_preserved`** for the "clearance preserved" line on attention cards.
