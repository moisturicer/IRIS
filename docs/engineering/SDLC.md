# SDLC — How work moves from intent to production

**Purpose.** The mechanics of getting a change from an idea into a deployed system.
**Owns.** Branching, pull requests, CI, review, merge, release, deployment, maintenance, emergency changes.
**Does not own.** What each Jira state means (`WORK_ITEM_LIFECYCLE.md`) · requirements (SRS) · design (SDD) · local setup (`DEVELOPMENT.md`).
**Authority.** Process authority. If a PR conflicts with this, the PR is wrong.
**Update when.** The branch model, CI, or release process changes.

---

## 1 · The pipeline

```
Intent / Issue
   → Requirements      (SRS reference, or an SRS amendment)
   → Design            (SDD / ADR, only where a decision is needed)
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

**Baseline: `refactor/docker-service`.** This is the current development baseline, not `main`.

| Prefix | For |
|---|---|
| `feat/` | New capability |
| `fix/` | Defect fix |
| `docs/` | Documentation only |
| `refactor/` | Behaviour-preserving change |
| `test/` | Tests only |
| `chore/` | Tooling, dependencies, CI |

Name after the work, and reference the Jira key: `feat/IR-69-transition-table`.

**Rules**
- Branch from the current baseline; do not branch from another feature branch unless it is a genuine dependency
- Rebase or merge the baseline in before requesting review, so the reviewer sees the real result
- One work item per branch — a branch that closes three items cannot be reverted cleanly
- **Never force-push a branch someone else is reviewing**
- Delete the branch after merge

---

## 3 · Commits

Present tense, explaining **why** where the reason is not obvious from the diff.

```
fix: enforce record visibility on retrieve

get_queryset filtered only on `list`, so GET /records/<id>/
returned any record to any authenticated user. One visible_to()
predicate now applies to every action.

IR-60
```

**No AI attribution in commit messages.** No `Co-Authored-By`, no generated-with trailer. The commit history is assessed.

---

## 4 · Pull requests

A PR is a request for **independent verification**, not a notification that work happened.

**Every PR states:**
- What changed and why
- The Jira key
- How each acceptance criterion was verified
- Test evidence — what was run, and the result
- Anything the reviewer should look at particularly hard
- Migrations, configuration, or deployment steps required

**Do not open a PR** that is a draft of an idea. Use a draft PR explicitly if you want early feedback, and say what kind of feedback you want.

**Size.** Small enough to review properly. A 2,000-line PR gets a worse review than four 500-line ones, and the reviewer's approval means less.

---

## 5 · CI

CI is **evidence**, not a formality. See `.github/workflows/ci.yml`.

| Gate | What it proves |
|---|---|
| Backend import smoke | The URLconf loads — this alone catches three of the five current blockers |
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

Covered in full by `WORK_ITEM_LIFECYCLE.md` §7-8. In brief:

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
- Documentation drift is a defect: if code and SDD disagree, one of them is wrong and it is fixed

---

## 10 · Documentation changes

Documentation follows the same path: branch, PR, review, merge. It is not exempt.

| Change | Also update |
|---|---|
| Requirement changes | SRS, with an amendment entry, plus `docs/testing/TRACEABILITY.md` |
| Design changes | SDD |
| An architectural decision | A new ADR — never edit an accepted one; supersede it |
| Behaviour changes | `DEVELOPMENT.md` if a command or workflow changed |
| Process changes | This file or `WORK_ITEM_LIFECYCLE.md` |

**Never let two documents define the same thing.** If a fact needs to appear in two places, one states it and the other links.
