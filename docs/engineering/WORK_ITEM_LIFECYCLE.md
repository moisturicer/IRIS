# Work Item Lifecycle

**Purpose.** Defines what each Jira state means and what must be true to leave it.
**Owns.** The definition of Ready, In Progress, Blocked, Review, Done, and the pull model.
**Does not own.** Requirements (SRS) · design (SDD) · architectural decisions (`docs/adr/`) · the branch and PR mechanics (`SDLC.md`).
**Authority.** This document is the single definition of Done for IRIS. **Jira and GitHub must not disagree with it.** If they do, this document wins and the other is corrected.
**Depends on.** `SDLC.md` for the mechanics it references.
**Update when.** The Jira workflow changes, or a gate proves to be wrong in practice.

---

## 1 · The model

IRIS runs a **pull-based Kanban**. There is no sprint, no commitment ceremony, and no planning dependency.

```
   ┌──────────────────┐
   │  Not Ready       │  ← does not appear as pullable
   └────────┬─────────┘
            │ Definition of Ready met
            ▼
   ┌──────────────────┐
   │  TO DO           │  ← ready-to-pull, unassigned
   │  Ready to Pull   │
   └────────┬─────────┘
            │ a person pulls it and assigns themselves
            ▼
   ┌──────────────────┐        ┌──────────────────┐
   │  IN PROGRESS     │ ◄────► │  + blocked label │
   └────────┬─────────┘        └──────────────────┘
            │ ready for independent verification
            ▼
   ┌──────────────────┐
   │  IN REVIEW       │ ──── reopened ───► IN PROGRESS
   └────────┬─────────┘
            │ Definition of Done met + human approval
            ▼
   ┌──────────────────┐
   │  DONE            │
   └──────────────────┘
```

**Blocked is a label, not a column.** A blocked item stays in its current column and gains the `blocked` label. This keeps the board honest: work in progress that cannot proceed is still work in progress, and it still counts against WIP.

---

## 2 · Pull-based assignment

| Rule | Reason |
|---|---|
| Work stays **unassigned** while it waits | An assignee on unstarted work is a guess, and it discourages anyone else from picking it up |
| The person who pulls the item **assigns themselves** | Ownership is established by starting, not by allocation |
| **No bulk assignment.** No assignment by historical role | The four team members are interchangeable on most cards |
| Nobody is assigned to make an item visible on the board | Visibility is a board-filter concern, never an assignment concern |
| An item may be handed over by reassigning, with a comment saying where it stands | Silent reassignment loses context |

**Do not assign an issue to make it appear.** If it is not appearing, the board filter is wrong — fix the filter.

---

## 3 · Definition of Ready

An item may enter **To Do / Ready to Pull** only when all of the following hold:

- [ ] **Objective is stated** — what changes, in one or two sentences
- [ ] **Scope and out-of-scope are written**, so the boundary is not a judgement call at pull time
- [ ] **Acceptance criteria exist** and are checkable — each one either passes or fails
- [ ] **Dependencies are identified**, and any blocking item is named
- [ ] **Requirement or design reference exists** where applicable — an SRS `FR-`/`NFR-` id, an ADR, or a `docs/ui-ux/` section
- [ ] **Known blockers are recorded**; if an external decision is pending, the item is not Ready
- [ ] **It is actionable** — a developer can begin without first discovering what the task means

> **The test:** if the person pulling it has to go and find out what the item actually means before they can start, it was not Ready.

An item that fails any of these keeps the `not-ready` label and stays out of the pullable queue. Making it Ready is itself work, and it is done by whoever raised it.

---

## 4 · To Do / Ready to Pull

**Means.** Fully specified, unblocked, unassigned, and available for anyone to take.

**Entry.** Definition of Ready met.
**Exit.** Someone pulls it.

Order within the column is a priority signal (`Highest` = P0), not an instruction. A developer may pull a lower-priority item when a higher one is blocked or outside their current context — but **P0 blockers should not sit while P2 work is pulled**, and the board makes that visible.

---

## 5 · In Progress

**Means.** A person has deliberately pulled this item and is actively implementing or investigating it.

**On pulling:**
- [ ] Assign yourself
- [ ] Move to **In Progress**
- [ ] Create a branch per `SDLC.md`

**While in progress:**
- Keep it to a small number of concurrent items per person — In Progress is the constraint that makes a pull system work
- If you stop working on it for more than a day or two, either say why in a comment or move it back to To Do and unassign
- If it turns out not to be Ready after all, move it back and say what was missing

**In Progress is not a parking space.** An item nobody is actively working is either blocked (label it) or not started (return it).

---

## 6 · Blocked

**Means.** Work cannot reasonably proceed because of a genuine impediment.

Legitimate blockers: an unmet dependency on another item · an external decision (adviser, RDCO, data governance) · an unavailable resource or access · a technical blocker with no reasonable workaround.

**Not blockers:** the work is hard · the developer is busy elsewhere · the item is half-finished and awkward to pick up.

**When blocking an item, add the `blocked` label and a comment recording:**

| Field | Example |
|---|---|
| Blocking reason | External data-governance decision outstanding |
| The dependency or blocker | Permission for external AI data transmission |
| What is needed to unblock | Written confirmation from the adviser |
| Owner, if there is one | Adviser — request sent |
| Date identified | 2026-09-01 |

**Unblocking** removes the label and adds a comment saying what changed. A blocked item that has not moved in a week should be raised — a stale blocker usually means nobody owns the unblocking.

**Currently blocked (`blocked` label):** IR-63, IR-66, IR-67, IR-68.

---

## 7 · Review

**Review does not mean "I think I'm finished."**
**Review means "the implementation is complete enough for someone else to verify independently."**

An item moves **In Progress → In Review** only when all applicable conditions hold:

**Always required**
- [ ] Implementation is complete — not partial, not "the rest is easy"
- [ ] The author has **self-checked every acceptance criterion** and can say how each was verified
- [ ] A pull request exists and describes what changed and why
- [ ] CI has run, and is either **passing** or the failure is understood and explained in the PR

**Required when applicable**
- [ ] Tests added or updated for the behaviour changed
- [ ] Those tests have actually been executed, and the output is available
- [ ] Documentation updated where behaviour or interfaces changed
- [ ] Requirements traceability updated for a requirement-bearing change
- [ ] Security implications addressed for anything touching auth, permissions, file access, secrets or external calls
- [ ] Migrations included and applied against a copy of a realistic database

**Putting an item in Review with a red CI and no explanation is not a review request** — it moves the debugging onto the reviewer.

---

## 8 · Review → Done gate

The reviewer performs **independent verification**. Reading the diff is not enough; the reviewer must decide whether the acceptance criteria are actually met.

The reviewer considers:

| Dimension | Question |
|---|---|
| Correctness | Does it do what the item said, for the cases that matter? |
| Acceptance criteria | Is each one genuinely satisfied, or only plausibly? |
| Regression risk | What else touches this? Is it covered? |
| Architecture alignment | Does it match the SDD and the ADRs, or quietly diverge? |
| Security | Auth, permissions, file access, secrets, external transmission |
| Testing | Do the tests test the behaviour, or only that the code runs? |
| CI | Green, or explained? |
| Documentation | Updated where it needed to be? |
| Traceability | Requirement mapping current? |
| Deployment | Migrations, configuration, environment — any manual step? |

**Human review is the approval gate.** AI-assisted review may be used to find candidate issues, and is often good at it — but **an AI review is not an approval**. A human names themselves as the approver and is accountable for the judgement.

**Reviewer and author must be different people.** On a four-person team this is always possible.

---

## 9 · Definition of Done

An item is **Done** only when the following hold. This is the same list the repository uses; there is no second definition.

### Required for every work item

- [ ] All acceptance criteria satisfied
- [ ] Implementation complete
- [ ] CI passing on the merged result
- [ ] Code review completed by someone other than the author
- [ ] **Explicit reviewer approval recorded**
- [ ] No known blocking defect remains
- [ ] Merged to `refactor/docker-service` (or the current baseline branch)

### Required when applicable

- [ ] Tests added or updated, **and executed, with evidence** (CI run, or recorded output)
- [ ] Requirements traceability updated — `docs/testing/TRACEABILITY.md`
- [ ] Documentation updated
- [ ] Security implications addressed and stated
- [ ] Database migrations included and tested on a realistic copy
- [ ] Deployment or configuration changes applied and recorded
- [ ] Evidence recorded for anything claimed as verified

### Never sufficient on its own

Writing code · the author saying it works · opening a PR · one local test passing · CI being green without review.

> **A requirement is not complete because source code exists for it.** It is complete when a test demonstrates it and the evidence is recorded.

---

## 10 · Reopening

If review finds the item does not satisfy its requirements:

1. Move it **In Review → In Progress**
2. Comment with **what specifically is unmet** — the criterion, not a general impression
3. It stays assigned to the same person unless they hand it over

Reopening is normal and carries no stigma. It is much cheaper than a false Done, which surfaces later as a defect against a requirement everyone believed was met.

**Do not** open a new item for work that belongs to an existing one — the original item's history is the record of what it took.

---

## 11 · Alignment with Jira

| Lifecycle state | Jira status | Board column | Marker |
|---|---|---|---|
| Not Ready | To Do | To Do | `not-ready` label |
| Ready to Pull | To Do | To Do | `ready-to-pull` label, no assignee |
| In Progress | In Progress | In Progress | assignee set |
| Blocked | *unchanged* | *unchanged* | `blocked` label + comment |
| Review | In Review | Review | PR linked |
| Done | Done | Done | reviewer approval recorded |

Statuses already exist in project IR; **no new status is required**.

**Board filter must include `s2-active`** so the Semester 2 queue is continuously visible, and must not depend on sprint membership. Semester 1 issues carry `legacy-s1` and are excluded from the active board.

---

## 12 · Labels

| Group | Values |
|---|---|
| Lifecycle | `s2-active` `legacy-s1` |
| Legacy class | `superseded` `duplicate` `merged` `deferred` `historical` `delivered` |
| MVP | `mvp-blocker` `mvp-required` `mvp-recommended` `post-mvp` `do-not-build` |
| Phase | `phase-w1-w2` `phase-w3` `phase-w4-w7` `phase-w8-w10` `phase-w11-w12` `phase-w13-w15` `post-semester` |
| Area | `area-backend` `area-frontend` `area-workflow` `area-security` `area-rag` `area-saas` `area-deployment` `area-testing` `area-mvp-validation` `area-uiux` `area-research` `area-documentation` `area-commercialization` `area-architecture` |
| Thesis | `thesis-critical` |
| Flow | `ready-to-pull` `blocked` `not-ready` |

Priority maps to the Jira field: P0 → `Highest`, P1 → `High`, P2 → `Medium`, P3 → `Low`.

**`thesis-critical` items are protected from scope cuts.** If capacity slips, cut from RAG and supporting frontend work first — never from the workflow contribution or its measurement.
