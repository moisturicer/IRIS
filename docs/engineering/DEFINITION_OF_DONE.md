# Definition of Done

**Purpose.** Defines the three gates a work item must pass — Ready, Review, Done — and what must be true to cross each one.
**Owns.** The Definition of Ready, the conditions for entering review, the reviewer's verification duty, and the Definition of Done.
**Does not own.** How work moves across the board (`SDLC.md`) · branch and PR mechanics (`SDLC.md`) · Jira states and labels (`../agents/issue-tracker.md`) · requirements, design and decisions (`../adr/`).
**Authority.** This document is the single Definition of Done for IRIS. **Jira and GitHub must not disagree with it.** If they do, this document wins and the other is corrected.
**Update when.** A gate proves to be wrong in practice.

> Replaces `WORK_ITEM_LIFECYCLE.md`, which held these gates alongside the board flow and the Jira label taxonomy. The flow moved to [`SDLC.md`](SDLC.md) §11; the states and labels moved to [`../agents/issue-tracker.md`](../agents/issue-tracker.md).

---

## 1 · Definition of Ready

An item may enter **To Do / Ready to Pull** only when all of the following hold:

- [ ] **Objective is stated** — what changes, in one or two sentences
- [ ] **Scope and out-of-scope are written**, so the boundary is not a judgement call at pull time
- [ ] **Acceptance criteria exist** and are checkable — each one either passes or fails
- [ ] **Dependencies are identified**, and any blocking item is named
- [ ] **Requirement or design reference exists** where applicable — an ADR, a `docs/ui-ux/` section, or an `FR-`/`NFR-` id used as a label
- [ ] **Known blockers are recorded**; if an external decision is pending, the item is not Ready
- [ ] **It is actionable** — a developer can begin without first discovering what the task means

> **The test:** if the person pulling it has to go and find out what the item actually means before they can start, it was not Ready.

An item that fails any of these keeps the `not-ready` label and stays out of the pullable queue. Making it Ready is itself work, and it is done by whoever raised it.

---

## 2 · Entering review

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

## 3 · Review → Done gate

The reviewer performs **independent verification**. Reading the diff is not enough; the reviewer must decide whether the acceptance criteria are actually met.

The reviewer considers:

| Dimension | Question |
|---|---|
| Correctness | Does it do what the item said, for the cases that matter? |
| Acceptance criteria | Is each one genuinely satisfied, or only plausibly? |
| Regression risk | What else touches this? Is it covered? |
| Architecture alignment | Does it match the ADRs, or quietly diverge? |
| Security | Auth, permissions, file access, secrets, external transmission |
| Testing | Do the tests test the behaviour, or only that the code runs? |
| CI | Green, or explained? |
| Documentation | Updated where it needed to be? |
| Traceability | Requirement mapping current? |
| Deployment | Migrations, configuration, environment — any manual step? |

**Human review is the approval gate.** AI-assisted review may be used to find candidate issues, and is often good at it — but **an AI review is not an approval**. A human names themselves as the approver and is accountable for the judgement.

**Reviewer and author must be different people.** On a four-person team this is always possible.

---

## 4 · Definition of Done

An item is **Done** only when the following hold. This is the same list the repository uses; there is no second definition.

### Required for every work item

- [ ] All acceptance criteria satisfied
- [ ] Implementation complete
- [ ] CI passing on the merged result
- [ ] Code review completed by someone other than the author
- [ ] **Explicit reviewer approval recorded**
- [ ] No known blocking defect remains
- [ ] Merged to the current baseline branch (**`feat/rag-service`**)

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

## 5 · Reopening

If review finds the item does not satisfy its requirements:

1. Move it **In Review → In Progress**
2. Comment with **what specifically is unmet** — the criterion, not a general impression
3. It stays assigned to the same person unless they hand it over

Reopening is normal and carries no stigma. It is much cheaper than a false Done, which surfaces later as a defect against a requirement everyone believed was met.

**Do not** open a new item for work that belongs to an existing one — the original item's history is the record of what it took.
