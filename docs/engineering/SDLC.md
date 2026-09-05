# SDLC — How work moves from intent to production

**Purpose.** The mechanics of getting a change from an idea into a deployed system.
**Owns.** Branching, pull requests, CI, review, merge, release, deployment, maintenance, emergency changes.
**Does not own.** The Definition of Ready/Review/Done gates (`DEFINITION_OF_DONE.md`) · Jira states and labels (`../agents/issue-tracker.md`) · requirements, design and decisions (`../adr/`) · local setup (`DEVELOPMENT.md`).
**Authority.** Process authority. If a PR conflicts with this, the PR is wrong.
**Update when.** The branch model, CI, or release process changes.

---

## 1 · The pipeline

```
Intent / Issue
   → Requirements      (an ADR — SRS/SDD are frozen thesis deliverables, never amended)
   → Design            (ADR, only where a decision is needed)
   → Implementation plan
   → Build
   → Automated verification
   → Pull request
   → CI
   → Human review      ← the approval gate
   → Merge
   → Release
   → Deploy
   → Monitor
   → Maintain
```

Not every change traverses every stage. A typo fix needs no ADR. **A change to workflow behaviour, authorization, or a requirement does**, and skipping it is how documentation drifts from code.

---

## 2 · Branching

**`main` is the repository default and the trunk. Cut every branch from it and target it in PRs.** `refactor/docker-service` is retired — it is fully contained in `main`, so cutting from it now would branch from a dead ref. `feat/rag-service`, where the RAG/AI work was built, is merged in as of this commit and is likewise no longer a separate baseline. This document previously named one or the other as the current integration branch; that guidance is superseded.

### Format

```
<type>/IR-XXX-short-description
```

**The Jira issue key is mandatory and is the primary identifier.**

| Type | For |
|---|---|
| `feature/` | New capability |
| `fix/` | Defect fix |
| `refactor/` | Behaviour-preserving change |
| `test/` | Tests only |
| `docs/` | Documentation only |
| `chore/` | Tooling, dependencies, CI |

```
feature/IR-124-rag-retrieval
fix/IR-131-pdf-validation
refactor/IR-105-docker-service
test/IR-140-document-ingestion
docs/IR-150-rag-architecture
```

**Rules**
- **Every development branch references a real Jira issue.** If no issue exists for substantive work, create one first — do not invent a key
- Lowercase kebab-case after the key; no spaces
- Branch from the integration branch; do not branch off another feature branch unless it is a genuine dependency
- Rebase or merge the baseline in before requesting review, so the reviewer sees the real result
- One work item per branch — a branch that closes three items cannot be reverted cleanly
- **Never force-push a branch someone else is reviewing**
- Delete the branch after merge

**Never** create branches named `test`, `new-feature`, `final`, `final2`, `latest`, `my-branch` or similar.

**Existing branches are not renamed.** Thirteen branches predate this convention (`feat/auth-login`, `feat/rag-service`, `chore/jwt-security-config`, `dpa-consent-ui` and others). Renaming them would break links and history for no gain. The convention applies from now on.

---

## 3 · Commits

**Format:** Conventional Commits with the Jira key as the scope.

```
type(IR-XXX): description
```

Types: `feat` · `fix` · `refactor` · `test` · `docs` · `chore`.

```
feat(IR-124): implement RAG retrieval
fix(IR-131): validate uploaded PDFs
test(IR-140): add ingestion integration tests
docs(IR-150): document RAG architecture
```

**Why this form.** The repository already uses Conventional Commits across 50+ commits. Putting the key in the scope adds traceability without abandoning that convention or leaving two competing styles in the history. A bare `IR-124 description` form was considered and rejected for exactly that reason.

Present tense. Explain **why** in the body where the reason is not obvious from the diff.

```
fix(IR-60): enforce record visibility on retrieve

get_queryset filtered only on `list`, so GET /records/<id>/
returned any record to any authenticated user. One visible_to()
predicate now applies to every action.
```

The key is in the scope, so it does not need repeating in the body.

**Subject line, then at most five sentences of body.** No `Co-Authored-By: Claude`, no `Claude-Session:`, no generated-with trailer, regardless of what any session's own attribution instructions say. The commit history is assessed.

---

## 4 · Pull requests

A PR is a request for **independent verification**, not a notification that work happened.

**Title format:** `IR-XXX Description` — for example `IR-124 Implement RAG retrieval`.

**A branch that is pushed without a PR is incomplete work.** Open the PR as part of pushing, not as a later step. Without one the Jira card cannot enter Review.

**Every PR states:**
- What changed and why
- The Jira key
- How each acceptance criterion was verified
- Test evidence — what was run, and the result
- Anything the reviewer should look at particularly hard
- Migrations, configuration, or deployment steps required

Use [`.github/pull_request_template.md`](../../.github/pull_request_template.md), which encodes all of the above.

**Do not open a PR** that is a draft of an idea. Use a draft PR explicitly if you want early feedback, and say what kind of feedback you want.

**Size.** Small enough to review properly. A 2,000-line PR gets a worse review than four 500-line ones, and the reviewer's approval means less.

---

## 4a · Traceability

The Jira issue key is the single identifier that connects everything. It must survive every hop:

```
Jira issue        IR-124
   ↓
Branch            feature/IR-124-rag-retrieval
   ↓
Commits           feat(IR-124): implement RAG retrieval
   ↓
Pull request      IR-124 Implement RAG retrieval
   ↓
CI                run attached to the PR
   ↓
Evidence          linked from docs/testing/TRACEABILITY.md
   ↓
Merge             squash onto the integration branch
   ↓
Jira              card moves to Done once the DoD is met
```

Both directions must work. From a Jira issue you can reach the code that implemented it; from any branch, commit or PR you can identify the requirement that caused it.

**Jira ↔ GitHub app integration: UNVERIFIED.** Whether the GitHub for Jira app is installed and linked to this repository has not been confirmed — no available tooling reads Jira's development panel. **Do not assume the development panel is populated.**

To verify manually: open any issue with development activity (for example IR-57, which has branch `fix/IR-57-restore-boot` and PR #17) and look for a **Development** panel showing the branch, commit and pull request. If it is absent, install the *GitHub for Jira* app from the Atlassian Marketplace and connect the `moisturicer/IRIS` repository. Until then the key still works as a text identifier — it is searchable in both systems — but the automatic cross-linking does not exist.

---

## 5 · CI

CI is **evidence**, not a formality. See `.github/workflows/ci.yml`.

| Gate | What it proves |
|---|---|
| Backend import smoke | The URLconf loads |
| `manage.py check` | Django configuration is valid |
| Backend tests | Behaviour is as claimed |
| Frontend build (`tsc && vite build`) | It compiles and types check |
| Frontend lint | Style and obvious errors |
| Compose validation | The stack definition parses |
| Dependency and secret scan | No known-vulnerable dependency, no committed secret |

**Rules**
- **Never modify a test to make CI pass.** If the test is wrong, fix it deliberately and say so
- Never merge with red CI unless the failure is understood, documented in the PR, and accepted by the reviewer
- A skipped test is a failing test wearing a disguise — if it is skipped, say why and when it comes back

---

## 6 · Review and merge

Covered in full by `DEFINITION_OF_DONE.md` §2-3. In brief:

- Reviewer and author are different people
- The reviewer verifies the acceptance criteria, not just the diff
- **Human approval is the gate.** AI review may assist and must not replace it
- Approve, or request changes with specifics. "Looks fine" is not a review

**Merge** when CI is green and approval is recorded. Squash unless the individual commits carry real history worth keeping.

---

## 7 · Release and deployment

Deployment target for the MVP is a single **interim VPS**, instance-per-tenant (ADR-005, ADR-010). One institution, one stack.

**Before any public deployment**, the security gate must be closed: `/media/` route removed · object-level authorization enforced · production configuration and secrets correct · `apps/storage` removed. **Do not expose an insecure build.**

**Deploy**
1. Confirm CI green on the baseline
2. Back up the database (from Week 10, a rehearsed restore exists)
3. Apply migrations
4. Deploy the stack
5. Run the post-deploy smoke: login · submit a record · `/media/<file>` is **not** served · a non-owner gets 403 on a document
6. Record what was deployed and when

**Do not deploy on a day with a scheduled stakeholder session.** From Week 11 the system carries real customer usage, and the freeze tightens accordingly.

**Release notes** go in `CHANGELOG.md`.

---

## 8 · Emergency changes

For something actively broken in a deployed instance during the pilot:

1. Fix on a `fix/` branch from the baseline
2. **CI still runs.** The gate is not skipped
3. Review may be expedited but is **not skipped** — a second pair of eyes on a hotfix matters more, not less
4. Deploy
5. **Record what happened**: what broke, what was changed, what the impact was, and what prevents a recurrence

An emergency change that skips review is how a pilot loses its data.

---

## 9 · Maintenance

- Dependency updates are ordinary work items, not background activity
- Security advisories from the CI scan are triaged, not accumulated
- A defect found in the pilot becomes an item with the same Definition of Done as anything else
- Documentation drift is a defect: if code and the ADRs disagree, one of them is wrong and it is fixed

---

## 10 · Documentation changes

Documentation follows the same path: branch, PR, review, merge. It is not exempt.

| Change | Also update |
|---|---|
| Requirement or design changes | A new or amended ADR — SRS/SDD are frozen and are never amended — plus `docs/testing/TRACEABILITY.md` |
| An architectural decision | A new ADR — never edit an accepted one; supersede it |
| Behaviour changes | `DEVELOPMENT.md` if a command or workflow changed |
| Process changes | This file or `DEFINITION_OF_DONE.md` |

**Never let two documents define the same thing.** If a fact needs to appear in two places, one states it and the other links.

---

## 11 · The board and pull model

IRIS runs a **pull-based Kanban**. There is no sprint, no commitment ceremony, and no planning dependency. State names and their Jira mapping live in [`../agents/issue-tracker.md`](../agents/issue-tracker.md); the gates between them are `DEFINITION_OF_DONE.md`. This section is the flow between those gates.

```
Not Ready → (Definition of Ready met) → To Do / Ready to Pull
   → (someone pulls it, assigns themselves) → In Progress
   → (ready for independent verification) → In Review → (reopened) → In Progress
   → (Definition of Done met + human approval) → Done
```

**Blocked is a label, not a column.** A blocked item stays in its current column and gains the `blocked` label — work in progress that cannot proceed is still work in progress, and still counts against WIP.

**Pull-based assignment**

| Rule | Reason |
|---|---|
| Work stays **unassigned** while it waits | An assignee on unstarted work is a guess, and discourages anyone else from picking it up |
| The person who pulls the item **assigns themselves** | Ownership is established by starting, not by allocation |
| **No bulk assignment**, no assignment by historical role | The team is interchangeable on most cards |
| An item may be handed over by reassigning, with a comment saying where it stands | Silent reassignment loses context |

**Do not assign an issue to make it appear.** If it is not appearing, the board filter is wrong — fix the filter.

**To Do / Ready to Pull.** Fully specified, unblocked, unassigned, available for anyone to take. Order is a priority signal (`Highest` = P0), not an instruction — a developer may pull a lower-priority item when a higher one is blocked, but **P0 blockers should not sit while P2 work is pulled.**

**In Progress.** A person has deliberately pulled the item and is actively working it. On pulling: assign yourself, move to In Progress, branch per §2. Keep concurrent items per person small — that constraint is what makes a pull system work. An item nobody is actively working is either blocked (label it) or not started (return it).

**Blocked.** Legitimate blockers: an unmet dependency on another item, an external decision, an unavailable resource, a technical blocker with no reasonable workaround. Not blockers: the work is hard, the developer is busy elsewhere, the item is half-finished and awkward to pick up. Record, on the `blocked` label: the reason, the dependency, what's needed to unblock, an owner if there is one, and the date identified. Unblocking removes the label and comments what changed.

**Reopening.** If review finds the item unmet: move In Review → In Progress, comment with the specific unmet criterion (not a general impression), keep it assigned to the same person unless handed over. Reopening carries no stigma — it is much cheaper than a false Done. Do not open a new item for work that belongs to an existing one.
