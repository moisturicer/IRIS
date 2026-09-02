# 07 — Review & Clearance

**Verdict: KEEP the queue and the decision screen. MERGE four list pages into one. Make the decision screen self-sufficient.**

This is where the reviewer side of the contribution lives. A reviewer who cannot see what the other offices have done is being asked to make a parallel decision with sequential information.

---

## 1 · What exists

| Screen | Lines | State |
|---|---|---|
| `PendingRecordsPage` | 63 | Raw `<table>`; columns Title / Type / Submitted / Action |
| `EvaluationPage` | 238 | Three-option decision, comment gating, rejection warning |
| `ApprovedRecordsPage` | 51 | Near-duplicate list |
| `DeclinedRecordsPage` | 59 | Near-duplicate list |
| `ApprovedProposalsPage` | 116 | Near-duplicate list |
| `ReviewAnalyticsPage` | 13 | Stub — backend returns 501 |

`EvaluationPage`'s `DECISION_OPTIONS` is **the best copy in the codebase** and should be preserved verbatim:

> **Request Revision** — *"Send back to the owner for changes. They may resubmit after revising."*

It refuses to surface the database word `declined`, and it tells the reviewer the action is not terminal. Keep it.

---

## 2 · Problems

| # | Problem | Consequence |
|---|---|---|
| 1 | **The queue does not show the stage or the office** | A KTTO reviewer and an IERC reviewer see byte-identical rows. Neither can tell what is being asked of them |
| 2 | **The decision screen shows no clearance state** | At `parallel_review` the reviewer cannot see whether the other two offices have cleared, declined, or not started |
| 3 | **Documents are a navigation away** | `View & Attach Documents` is a `<Link>` to `/records/:id/documents`. **The typed comment is lost.** A reviewer who opens the PDF to check a detail loses their work |
| 4 | **Rejection is one click** | The red warning panel is good, but `Submit Decision` fires a permanent, non-resubmittable action with no confirmation. `ConfirmDialog` exists and is not used here |
| 5 | **The decision's meaning is never stated** | At `parallel_review`, approving records *one office's* clearance, not the record's approval. The form never says which |
| 6 | **Three list pages are filters** | Approved / Declined / ApprovedProposals differ only by a query parameter |
| 7 | **No concurrency handling** | If IERC declines while KTTO is mid-form, KTTO's submit fails with a generic `detail` string |
| 8 | **Decision colour is the only signal** | `text-green-700` / `text-amber-700` / `text-red-700` carry the meaning. WCAG 1.4.1 |
| 9 | **`reviewsApi.pending()` returns a bare array** | No pagination. Adequate at pilot scale, not beyond (`FE-09`) |

---

## 3 · The queue

One screen. Filters, not sibling pages.

```
Review Queue                                          4 waiting

  [ Waiting ▾ ]  [ All types ▾ ]              ○ Waiting  ○ Decided

  ┌──────────────────────────────────────────────────────────┐
  │ Machine learning for crop disease detection              │
  │ Thesis/Research · Your stage: IERC clearance             │
  │ Waiting 3 days · ITSO ✓  KTTO ⏱  IERC ← you       Review │
  ├──────────────────────────────────────────────────────────┤
  │ Blockchain credential verification            RESUBMITTED│
  │ Thesis/Research · Your stage: IERC clearance             │
  │ Waiting 4 hours · ITSO ✓🛡  KTTO ✓🛡  IERC ← you   Review │
  └──────────────────────────────────────────────────────────┘
```

Three additions to every row, all load-bearing:

| Addition | Why |
|---|---|
| **Your stage** | Names what the reviewer is being asked for |
| **Waiting time** | The only prioritisation signal a queue needs. Also the raw material for the turnaround metric (`W-04`) |
| **Peer clearance strip** | The reviewer sees the parallel state *before* opening the record |
| **`RESUBMITTED` marker** | The one row type where preserved clearances matter, flagged in the list |

A resubmitted record whose peers are marked preserved (`✓🛡`) tells the reviewer, without opening anything: *the others are done; this is waiting only on me.* That is the contribution, visible in a list row.

---

## 4 · The decision screen

**Make it self-sufficient.** The reviewer must never navigate away mid-decision.

```
┌─────────────────────────────────┬──────────────────────────────┐
│ Machine learning for crop…      │ YOUR DECISION                │
│ Thesis/Research · Submitted 12 Sep                             │
│                                 │ You are recording            │
│ CLEARANCE                       │ IERC clearance.              │
│  ✓🛡 ITSO  preserved     14 Sep  │                              │
│  ✓  KTTO  cleared       16 Sep  │  ○ ✓ Approve                 │
│  ●  IERC  ← your decision       │  ○ ↩ Request Revision        │
│                                 │  ○ ⊘ Reject                  │
│ ITSO and KTTO cleared this      │                              │
│ record before it was revised.   │  Comment (required)          │
│ Their clearance is preserved.   │  ┌────────────────────────┐  │
│                                 │  └────────────────────────┘  │
│ ABSTRACT                        │                              │
│ ▸ Consent form.pdf      2.1 MB  │  [ Cancel ] [ Submit ]       │
│ ▸ Manuscript.pdf        8.4 MB  │                              │
│ PEER COMMENTS                   │                              │
│  KTTO, 16 Sep — "No IP conflict"│                              │
└─────────────────────────────────┴──────────────────────────────┘
```

### Rules

| Rule | Reason |
|---|---|
| **Documents open in place** — a viewer panel or a new tab, never an in-app navigation | Problem 3. The comment survives |
| **State which office the decision records** | Problem 5. *"You are recording IERC clearance."* — text supplied by `W-07`'s `office_label` |
| **Reject requires confirmation** | Problem 4. `ConfirmDialog`; a second deliberate action, not a typed acknowledgement |
| **Every option carries an icon** | Problem 8 |
| **Peer comments visible, below the fold** | The reviewer forms a view first ([06](06-record-detail.md) §4) |
| **Preserved clearances explained in one sentence** | The same sentence used everywhere else ([08](08-workflow-resubmission.md)) |
| Comment required for Revision and Reject | Already correct. Keep |

### Stale state

If the record moved while the form was open:

> **This record has moved.** IERC requested revisions while you were reviewing.
> Your comment has been kept below. Nothing was submitted.

Never discard the reviewer's typed text. Never submit into a changed state. This depends on `W-03` making the transition atomic — without it the failure is a 500, not a message.

---

## 5 · Specification — Review Queue

**User.** Adviser, RDCO, ITSO, IERC, KTTO.

**Goal.** See what is waiting for me, in priority order, and open one.

**Primary action.** Open a record for decision.

**Secondary actions.** Filter by state or type · switch to decided records · open the record detail read-only.

**Required data.** `reviewsApi.pending()` — per row: id, title, type, `created_at`, **stage**, **the viewer's office**, **waiting time**, **peer clearance summary**, **resubmission flag**.

**Permissions.** Rows are only those the viewer may act on — `W-05`'s `ReviewPolicy.stages_for(role)`, server-side. The queue is a permission surface, not a convenience filter: a row here asserts the viewer may act.

**States.** Has items · empty · loading · filtered-to-empty · single item.

**Errors.** Fetch fails → inline error with retry, queue shape retained. A 403 means the role state changed — send the user to the home screen with an explanation; do not render an empty queue that implies *nothing waiting*.

**Empty states.** *"Your review queue is clear."* Filtered to empty → *"No records match this filter"* plus a clear-filters action. These are different messages; conflating them makes a filter look like a bug.

**Loading states.** Skeleton rows at final height. Never a bare `Loading…` — the current `text-gray-400 text-[13px]` string is both a contrast failure and one of ten duplicates ([01](01-design-system.md)).

**Accessibility.** `<h1>` "Review Queue". Rows are a list of links, not click-handled `<tr>`s. Waiting time carries `<time datetime>` with a full date in `title`. The peer clearance strip is not decorative — each icon needs text, e.g. `aria-label="ITSO cleared"`. The count is announced via `aria-live="polite"` on change only.

**Responsive.** ≥ 1024 px rows with inline metadata. < 768 px cards: title, stage, waiting time, then the clearance strip wrapping; the action becomes a full-width button. No horizontal scroll at 360 px ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP** — one queue, stage, waiting time, peer strip, resubmission marker. **Post-MVP** — bulk actions, sorting, saved filters, SLA colouring, per-office workload view.

**Backend/API dependencies.** `reviewsApi.pending()` extended with stage, office, waiting time and peer summary (**`W-07`**) · `W-05` for the eligibility rule · pagination (`FE-09`).

---

## 6 · Specification — Decision Screen

**User.** Adviser, RDCO, ITSO, IERC, KTTO.

**Goal.** Record a defensible decision without leaving the screen.

**Primary action.** Submit decision.

**Secondary actions.** Open a document · read peer comments · view full history · cancel.

**Required data.** Record identity, abstract, authors · **`clearances[]`** *(`W-07`)* · uploads with URLs · peer `reviews[]` · the viewer's office and stage · `resubmission{}` when applicable.

**Permissions.** The server verifies eligibility at submit — `W-05`. Client gating is UX only ([03](03-navigation.md)). **A reviewer who is not eligible must not see the form**, because a rendered form is a promise.

**States.**

| State | Rendering |
|---|---|
| Eligible, first review | Full form, clearance panel, no preservation sentence |
| Eligible, after resubmission | Form + preserved clearances + the previous decline reason |
| Not eligible | Read-only record view + *"You are not the reviewer for this stage."* |
| Submitting | Button `loading`; form disabled; **navigation blocked** |
| Submitted | Redirect to the queue with a confirmation naming the office and the decision |
| Stale | The stale-state notice above; comment preserved |
| Reject selected | Warning panel + confirmation on submit |

**Errors.**

| Error | Handling |
|---|---|
| Comment empty on Revision/Reject | Inline at the field; focus moves there. Already handled — move it from a form-level string to a field error |
| 403 at submit | *"You are no longer the reviewer for this stage."* Preserve the comment |
| 409 / stale | The stale notice. Preserve the comment |
| Network failure | Retry in place. **Never** clear the form |
| Record fetch fails | Full-screen error with retry; do not render a form against no record |

**Empty states.** No documents → *"No documents were attached to this submission"* — an explicit statement, because deciding without documents is a decision the reviewer should make knowingly. No peer comments → the section is not rendered.

**Loading states.** Skeleton in the final two-column shape. The form stays disabled until the record resolves, so a decision cannot be typed against nothing.

**Accessibility.**
- Decision options are a genuine `<fieldset>` + `<legend>` radio group, arrow-key navigable
- Each option carries an icon **and** a label **and** a description — never colour alone (WCAG 1.4.1)
- The office statement sits in the `<legend>`, so screen-reader users hear *what* they are deciding before the options
- The comment `<textarea>` is labelled, with `aria-describedby` for the required-state hint and `aria-invalid` on error
- The reject warning is `role="alert"` when reject is selected
- The confirmation dialog traps focus and restores it on close — **`Modal` has no focus trap today** ([01](01-design-system.md), [12](12-accessibility.md))
- The clearance panel is an `<ol>` with a text status per office

**Responsive.** ≥ 1024 px two columns as drawn. 768–1023 px single column, context above the form. < 768 px single column; the clearance panel collapses to a summary line — *"2 of 3 offices cleared"* — expandable; actions full-width and stacked. The document viewer becomes a new tab rather than a side panel.

**MVP/Post-MVP.** **MVP** — self-sufficient decision screen, clearance context, office statement, reject confirmation, stale handling. **Post-MVP** — inline PDF annotation, decision templates, delegation, request-more-information as a fourth option.

**Backend/API dependencies.**

| Dependency | Task | Status |
|---|---|---|
| `clearances[]` on the record payload | **`W-07`** | **Not built — the reviewer cannot see parallel state** |
| `ReviewPolicy` eligibility | `W-05` | Not built |
| Atomic transition + audit inside the transaction | `W-03`, `W-04` | Not built |
| Office and stage labels as data | `W-01` | Not built |
| `POST /reviews/` decision submit | — | **Exists** |
| Document access with ownership checks | `S-03` | **Exists, unchecked** |

---

## 7 · The four list pages

| Page | Disposition |
|---|---|
| `PendingRecordsPage` | **Becomes the queue.** Keep the route `/review/pending` |
| `ApprovedRecordsPage` | **Merge** — a `Decided` filter |
| `DeclinedRecordsPage` | **Merge** — a `Decided` filter |
| `ApprovedProposalsPage` | **Merge** — type filter plus decided |
| `ReviewAnalyticsPage` | **Remove from the router.** Backend returns 501; Module 7 is Phase 2 ([15](15-mvp-ui-scope.md)) |

Four routes become one screen with two filters. That removes three screens' worth of states, errors, empty states and loading states — roughly a day of work not spent, and three fewer places for an evaluation participant to get lost.
