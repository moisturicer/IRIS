# 06 — Record Detail

**Verdict: KEEP, with the Clearance Track added.** The workflow's home, and the screen where the thesis contribution becomes visible or does not.

---

## 1 · What exists

`RecordDetailPage` — 402 lines. Renders identity, abstract, metadata, `reviews` history, a resubmit button for declined records, a rejection notice, and role-gated reviewer actions.

`RecordDetailSerializer` exposes `owners`, `authors`, `reviews`, classification, type, adviser, IP flags, dates.

**It does not expose `clearances`.** So the screen shows a review *history* but no per-office *state* — a user can read that IERC declined on 18 Sep, but cannot see that ITSO and KTTO are cleared, nor that their clearance survived.

---

## 2 · Layout

Ordered by what users look for first — **state before identity**. A reviewer opening a record already knows what it is.

```
┌────────────────────────────────────────────────────────────┐
│ ← My Submissions                                           │
│                                                            │
│ Machine learning for crop disease detection                │
│ Thesis/Research · Submitted 12 Sep      [Revision requested]│
├────────────────────────────────────────────────────────────┤
│ ↩ IERC has requested revisions                     18 Sep  │  ← 1
│   "Consent form is missing section 4."                     │
│   — A. Reyes, IERC                                         │
│   ITSO and KTTO have already cleared this record. Their    │
│   approval is preserved — they won't review it again.      │
├──────────────────────────────┬─────────────────────────────┤
│ WORKFLOW                     │ RESUBMIT                    │  ← 2, 3
│  ✓ Submitted          12 Sep │  Before resubmitting:       │
│  ✓ RDCO Intake        14 Sep │   ✓ Upload revised document │
│  ● Office Clearance    2 of 3│   ○ Address IERC's comments │
│    ✓🛡 ITSO   preserved 14 Sep│                             │
│    ✓  KTTO   cleared   16 Sep│  When you resubmit:         │
│    ↩  IERC   revision  18 Sep│   → IERC reviews again      │
│  ○ RDCO Final        Not yet │   ✓ ITSO, KTTO keep         │
│  ○ Published         Not yet │        their clearance      │
│                              │  [ Resubmit for review ]    │
├──────────────────────────────┴─────────────────────────────┤
│ ABSTRACT                                                   │  ← 4
│ DOCUMENTS                              Manage documents →  │  ← 5
│ HISTORY                                                    │  ← 6
│ DETAILS  classification · IP type · authors · dates        │  ← 8
└────────────────────────────────────────────────────────────┘
```

| # | Block | Shown when |
|---|---|---|
| 1 | Decline banner | `pipeline_status = declined` |
| 2 | **Clearance Track** | Always |
| 3 | Resubmission panel | Declined **and** viewer is the owner |
| 4 | Abstract | Always |
| 5 | Documents | Always; management link if permitted |
| 6 | History | Always |
| 7 | Reviewer actions | Viewer may act at the current stage |
| 8 | Details | Always, collapsed by default at 360 px |

Blocks 2 and 3 sit side by side at ≥ 1024 px and stack below it.

---

## 3 · What each viewer needs

| Viewer | Primary question | Emphasis |
|---|---|---|
| **Owner, declined** | *"What do I have to do?"* | Decline banner + resubmission panel |
| **Owner, in progress** | *"Where is it?"* | Clearance Track |
| **Reviewer, actionable** | *"What am I deciding, and what have others said?"* | Track + documents + other offices' comments |
| **Reviewer, not their stage** | *"What is the status?"* | Track, read-only, no action controls |
| **RDCO at final review** | *"Have all offices cleared?"* | Track — the whole point of their stage |
| **Any viewer, published** | *"What is this research?"* | Abstract, documents, authors |

**One layout, emphasis by state.** Not four screens.

---

## 4 · The reviewer's need for peer comments

A reviewer at `parallel_review` benefits from seeing what other offices said — KTTO's IP classification informs IERC's ethics view. The Clearance Track already carries comment excerpts, which serves this.

**Design constraint.** Do not hide other offices' comments behind a click. But do **not** show them before the reviewer has formed a view — anchoring is a real risk in a small population, and it would contaminate the evaluation's independence assumption. Excerpts in the track are sufficient; full comments are one interaction away in History.

---

## 5 · Specification

**User.** Record owner (student), adviser, all four office roles, RDCO.

**Goal.** Understand where the record stands, what has been decided, and what to do next.

**Primary action.** Varies by viewer and state: resubmit (owner, declined) · record a decision (eligible reviewer) · none (read-only viewer).

**Secondary actions.** Manage documents · view history · download current document · view a reviewer's full comment.

**Required data.** Record identity and metadata · `reviews[]` · **`clearances[]`** *(new, `W-07`)* · **`route[]`** *(new)* · **`resubmission{}`** *(new)* · uploads for the documents block.

**Permissions.**

| Rule | Enforcement |
|---|---|
| Visible only to permitted viewers | `S-02` — `visible_to(user)` on **all** actions, not only `list` |
| Resubmit — owner or staff only | `reviews/views.py` resubmit check |
| Decision controls — only if eligible at the current stage | `W-05` `ReviewPolicy` |
| Documents — owner or staff | `S-03` |

> **Today `GET /records/:id/` returns any record to any authenticated user** (`S-02`). Until that is fixed, this screen is the primary vehicle for the disclosure. It is a blocker for the pilot, not a refinement.

**States.**

| State | Rendering |
|---|---|
| Draft | Track shows the future route, all `not_started`. Edit and Submit actions |
| In sequential stage | Track with the active stage marked; no office group |
| In clearance stage | Track with office rows; partial clearance visible |
| Declined | Decline banner + resubmission panel (owner) |
| Rejected | Frozen track, terminal notice, **no resubmit control** |
| Published / Completed | Full track complete; read-only; document download |
| Pending deletion | Notice; actions suppressed |

**Errors.**

| Error | Handling |
|---|---|
| 404 | *"This record doesn't exist, or you don't have access to it."* — **one message for both**, so the response does not confirm existence |
| 403 on an action | Explain which role may act; do not blame the user |
| `clearances` missing from the payload | Render the sequential track plus *"Office status unavailable"*. **Never fabricate a state** |
| Resubmit rejected | Surface the unmet requirement specifically — *"Upload a revised document before resubmitting"* — not a generic failure |

**Empty states.** No documents → *"No documents uploaded yet"* + upload action if permitted. No history → *"No decisions recorded yet."* Proposal → no office group, no empty container.

**Loading states.** Skeleton matching the final block layout — identity, track, then body. Blocks resolve independently so the track is not blocked by the document list.

**Accessibility.**
- `<h1>` is the record title
- Each block a `<section>` with an `<h2>` and `aria-labelledby`
- Decline banner `role="status"`, announced once on load
- Track as `<ol>`; office group a nested `<ul>`; `aria-current="step"` on the active stage
- Status conveyed by **icon + text**, never colour alone (WCAG 1.4.1)
- Resubmission checklist uses real list semantics with state in text, not only an icon
- Focus lands on `<h1>` on navigation
- Details collapsible uses a `<button aria-expanded>`, not a click-handled div

**Responsive.**

| Width | Layout |
|---|---|
| ≥ 1024 px | Two columns — track left, resubmission right; body full-width below |
| 768–1023 px | Single column, track then resubmission |
| < 768 px | Single column; Details collapsed by default; office rows stack label/status then comment |
| 360 px | No horizontal scroll; long titles wrap, never truncate to a tooltip only |

**MVP/Post-MVP.** **MVP** — all eight blocks including the Clearance Track. **Post-MVP** — inline document preview, comment threads, per-office SLA timers, related-records links, export to PDF.

**Backend/API dependencies.**

| Dependency | Task | Status |
|---|---|---|
| `clearances[]`, `route[]`, `resubmission{}` | **`W-07`** | **Not built — blocks the contribution's visibility** |
| Visibility on `retrieve` | `S-02` | **Not built — security blocker** |
| Audit-backed history incl. resubmission markers | `W-04` | Not built |
| Stage and office labels as data | `W-01` | Not built |
| `reviews[]`, identity, metadata | — | **Exists** |
