# 08 — Workflow & Resubmission UX

**The core of this document set.** The patterns here are the interface to the thesis contribution, and without them the contribution cannot be observed, used or evaluated.

---

## 1 · What must be communicated

From the brief, mapped to current state:

| Requirement | Today | Needed |
|---|---|---|
| Current workflow state | ✅ `StatusBadge` | Keep |
| Office clearance status | ❌ | **Clearance Track** |
| Pending offices | ❌ | **Clearance Track** |
| Approved offices | ❌ | **Clearance Track** |
| Declining office | ❌ | **Decline banner** |
| Preserved clearances | ❌ | **Preservation notice** |
| Resubmission requirements | ⚠️ | **Resubmission panel** |
| Final completion | ✅ | Keep |

Four new patterns. All live on the record detail screen ([06](06-record-detail.md)); two also appear in the reviewer queue ([07](07-review-clearance.md)).

---

## 2 · The modelling problem

IRIS's workflow is **not linear**, so a linear stepper cannot express it.

```
Proposal          draft → adviser_review → approved → completed

Thesis/Research   draft → rdco_intake → ┌─ IERC ─┐ → rdco_review → published
                                        └─ KTTO ─┘   (both must clear)

Project           draft → rdco_intake → ITSO ──┬─ IERC ─┐ → rdco_review → published
                                        └ KTTO ─────────┘
                                        (KTTO starts at ITSO stage, runs alongside)
```

Three properties any pattern must handle:

1. **Sequential stages** with a defined order
2. **Parallel offices within a stage**, each with independent state
3. **Overlap** — KTTO begins during `itso_review` and continues into `parallel_review`, so "current stage" does not determine which offices are active

Plus the resubmission property that is the contribution: **after a decline, some offices' completed work persists and some does not.**

---

## 3 · Pattern evaluation

| Pattern | Parallelism | 360 px | Preservation | Verdict |
|---|---|---|---|---|
| Horizontal stepper | Poor — branches don't fit | **Fails** — 6 stages scroll horizontally, violating NFR-U3 | Poor | ❌ |
| Progress bar + % | None | Fine | None | ❌ Hides everything that matters |
| Kanban board | Good | Fails | Poor | ❌ Wrong altitude — this is one record, not a portfolio |
| Timeline (events) | Implicit only | Good | Poor — shows history, not current state | ⚠️ Complementary, not primary |
| **Vertical stage list with per-office rows** | **Explicit** | **Good** | **Explicit** | ✅ **Recommended** |

### Why vertical

**NFR-U3 requires all core workflows usable at 360 px with no horizontal scrolling.** A horizontal stepper with six stages cannot meet that without scroll or unreadable compression. A vertical list is naturally single-column, degrades to mobile without a separate layout, and gives each office a full-width row for status, actor, date and comment.

It also matches the reading task: users scan *down* a status list, they do not trace a path.

---

## 4 · The Clearance Track

The primary new component. One instance per record.

### Structure

```
WORKFLOW

 ✓  Submitted                                    12 Sep
 │
 ✓  RDCO Intake Review                           14 Sep
 │   Approved by M. Santos
 │
 ●  Office Clearance                    2 of 3 cleared
 │
 │   ┌─────────────────────────────────────────────┐
 │   │ ✓🛡 ITSO          Cleared — preserved  14 Sep│
 │   │    "No technical concerns."                  │
 │   ├─────────────────────────────────────────────┤
 │   │ ✓  KTTO          Cleared              16 Sep │
 │   │    "IP classification: copyright."           │
 │   ├─────────────────────────────────────────────┤
 │   │ ↩  IERC          Revision requested   18 Sep │
 │   │    "Consent form is missing section 4."      │
 │   └─────────────────────────────────────────────┘
 │
 ○  RDCO Final Review                        Not yet
 │
 ○  Published                                Not yet
```

### Rules

| Rule | Reason |
|---|---|
| Every stage of the record's route is shown, including future ones | "What happens next" is the second question every user asks |
| Completed stages collapse to one line with actor and date | Density; the detail is in history |
| The active stage expands to show per-office rows | This is where the information is |
| Office rows carry **status, actor, date and the comment excerpt** | A reviewer's comment is the actionable content, not a footnote |
| Never colour alone | WCAG 1.4.1 — icon + label + colour, always |
| `preserved` is visually distinct from `cleared` | **This is the contribution.** Same green, added border and shield glyph, plus the word "preserved" |
| Order offices consistently | By stage entry, then alphabetically. Never reorder on state change — it destroys scan memory |
| Stage and office labels come from the API | Per-institution configuration ([11](11-saas-admin.md)); never hardcode "IERC" |

### States

| State | Icon | Label | Note |
|---|---|---|---|
| `not_started` | ○ dot | "Not yet required" | Dashed, muted |
| `pending` | ⏱ clock | "Awaiting review" | |
| `in_review` | 👁 eye | "In review" | Only if the API can distinguish it — otherwise omit |
| `cleared` | ✓ check | "Cleared" | Green |
| **`preserved`** | **✓🛡 check + shield** | **"Cleared — preserved"** | **Green + border. Tooltip and inline text explain it** |
| `declined` | ↩ return arrow | "Revision requested" | Amber. Recoverable |
| `rejected` | ⊘ stop | "Rejected" | Red. Terminal |

### Empty and edge cases

- **Proposal route** — no clearance stage exists. Render the sequential track only, with no empty office group. Do not show an empty container.
- **Draft** — show the route the record *will* take once submitted, all stages `not_started`. This is genuinely useful: it tells a student what they are entering.
- **Rejected** — freeze the track, mark the rejecting stage, grey subsequent stages, and state plainly that it cannot be resubmitted.

---

## 5 · The decline banner

When `pipeline_status = declined`, the owner needs three facts immediately: **who declined, why, and what to do**.

```
┌────────────────────────────────────────────────────────┐
│ ↩  IERC has requested revisions              18 Sep    │
│                                                        │
│    "The consent form is missing section 4. Please      │
│     attach the completed form and resubmit."           │
│                                                        │
│    — A. Reyes, IERC                                    │
│                                                        │
│    ITSO and KTTO have already cleared this record.     │
│    Their approval is preserved — they will not need    │
│    to review it again.                                 │
│                                                        │
│    [ Upload revised document ]  [ View full history ]  │
└────────────────────────────────────────────────────────┘
```

**The third paragraph is the contribution, in plain language.** It is what a student would otherwise never learn, and it is the sentence the evaluation's comprehension check (`M17`) tests.

**Copy must derive from data, not assumption.** Under the `RESTART_ALL` evaluation policy ([ADR-004](../adr/004-restart-all-comparison-mode.md)) no clearances are preserved, so the paragraph must not appear. Render it only when `preserved_offices` is non-empty. **Never hardcode preservation language.**

---

## 6 · The resubmission panel

Replaces the current bare "Resubmit for Review" button, which states no requirements.

```
RESUBMIT

Before resubmitting, you need to:
  ✓  Upload at least one revised document        (1 uploaded)
  ○  Address IERC's comments

When you resubmit:
  →  IERC will review again
  ✓  ITSO and KTTO keep their clearance

                              [ Resubmit for review ]
```

**Why a checklist.** `resubmit_record` (`reviews/services.py:352-365`) refuses resubmission unless a document was uploaded after the last decline — and the current UI does not say so. Users hit a server error for a rule they were never told. Show the gate before it fires.

**Why "when you resubmit".** It sets expectation and, again, makes preservation visible at the moment it matters most.

**Under `RESTART_ALL`** the second block reads *"IERC, ITSO and KTTO will all review again"* — driven by the same API field, no special-casing.

---

## 7 · Restart-all must not confuse ordinary users

[ADR-004](../adr/004-restart-all-comparison-mode.md) makes resubmission policy instance-level configuration, default `CLEARANCE_AWARE`, with `RESTART_ALL` used on a **separate evaluation instance**.

**UI rules:**

1. **No policy indicator in the ordinary interface.** No badge, no setting, no mention. A user should never see the word "policy".
2. **All copy derives from data.** The API returns which offices were reset and which preserved; the UI renders what it is given. Under `RESTART_ALL` the preservation sentence simply does not appear, because the array is empty.
3. **No conditional branches on policy anywhere in the frontend.** If a component needs to know the policy, the API contract is wrong.
4. **Evaluation sessions run on a separate instance**, so participants never encounter a mid-session change.

Consequence: the same components serve both arms of the experiment with no special-casing, and ordinary users cannot tell a policy exists.

---

## 8 · History and auditability

The Clearance Track shows **current state**. History shows **what happened**. Both are needed; they answer different questions.

Current: `RecordDetailSerializer` exposes `reviews` (the `Review` history) — good, and already rendered.

**Add:** a resubmission marker in the history, showing the boundary and what carried across.

```
18 Sep   IERC requested revisions
19 Sep   ── Resubmitted by J. Cruz ──────────────
         ITSO, KTTO clearance preserved
         IERC review required again
20 Sep   IERC cleared
```

**Important limitation to design around:** `resubmit_record` **deletes clearance rows** on a sequential-stage decline (`reviews/services.py:381`). The clearance table therefore cannot serve as the audit trail. History must be built from `AuditEvent` (`W-04`), which is why `W-04` records `offices_reset` and `offices_preserved` at resubmission time.

---

## 9 · API dependencies

**None of this is renderable today.** `RecordClearance` is never serialized.

**`W-07` — required additions to `RecordDetailSerializer`:**

```
clearances: [
  { office_code, office_label, status, reviewed_by_name,
    reviewed_at, comment, preserved: bool }
]
route: [
  { stage_code, stage_label, status, entered_at,
    completed_at, actor_name, parallel: bool }
]
resubmission: {
  can_resubmit: bool,
  requirements: [{ code, label, satisfied: bool }],
  offices_to_rereview: [office_label],
  offices_preserved: [office_label]
}
```

**Design notes on the contract:**

- **`office_label` and `stage_label` are institution-supplied**, not derived from a frontend enum. This is what makes per-institution terminology possible ([11](11-saas-admin.md)) without a frontend change.
- **`preserved` is a server-computed boolean**, not inferred by the client. The client cannot know it — the information is destroyed when clearance rows are reset.
- **`resubmission.requirements`** exposes the server-side gate so the UI can show it before it fires.
- **`offices_preserved`** empty ⇒ no preservation copy. That single rule is what makes the restart-all policy invisible.

Estimated: **~1 dev-day** including the serializer, the `ClearanceTrack` component, the decline banner and the resubmission panel. Tracked as `W-07`.

---

## 10 · Specification

**User.** Record owner (student), reviewing office staff, adviser, RDCO.

**Goal.** Understand where a record is, which offices have acted, what happens next, and — after a decline — exactly what is required.

**Primary action.** Owner: upload a revised document and resubmit. Reviewer: record a decision.

**Secondary actions.** View full history · view a reviewer's comment in full · download the current document.

**Required data.** `clearances[]`, `route[]`, `resubmission{}`, `reviews[]`, `pipeline_status`, `record_type`.

**Permissions.** Owner sees their own record's track. Reviewers see records at their stage. Others see the track only for records visible to them (`S-02`, `B-05`). **The track must not leak the existence of records the viewer cannot see.**

**States.** Draft (all `not_started`) · in sequential stage · in clearance stage (partial) · declined · rejected (frozen) · published · completed.

**Errors.** Clearance data missing from the response → render the sequential track and a neutral "Office status unavailable" row; **never fabricate a state**. Resubmission rejected by the server → surface the specific unmet requirement, not a generic failure.

**Empty states.** Proposal route → no office group, no empty container. No history yet → "No decisions recorded yet."

**Loading states.** Skeleton rows matching the final track shape, not a centred spinner — the track has known structure, so a skeleton avoids layout shift.

**Accessibility.** The track is an ordered list (`<ol>`), each stage a list item; office group a nested list. Status conveyed by icon + text, never colour alone. `aria-current="step"` on the active stage. The decline banner is `role="status"` so it is announced. See [12](12-accessibility.md).

**Responsive.** Single column at every breakpoint. At 360 px, office rows stack label/status on the first line and comment beneath. No horizontal scroll ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP — this is the thesis contribution's interface.** Post-MVP: per-office SLA timers, estimated completion, stage-duration display.

**Backend/API dependencies.** `W-07` (serializer), `W-04` (audit events for history), `B-05` (visibility scope), `W-01`/`W-02` (route and policy as data).
