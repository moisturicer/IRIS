# Test Plan

**Purpose.** How IRIS is tested, and what counts as evidence.
**Owns.** Test strategy, levels, execution, evidence rules.
**Does not own.** Requirement→test mapping ([`TRACEABILITY.md`](TRACEABILITY.md)) · research evaluation ([`../mvp-validation/`](../mvp-validation/)) · Definition of Done ([`../engineering/WORK_ITEM_LIFECYCLE.md`](../engineering/WORK_ITEM_LIFECYCLE.md)).
**Authority.** Authoritative for engineering testing.
**Update when.** Test tooling, levels or evidence rules change.

---

## 1 · Current state — stated plainly

**There are zero automated tests in this repository.** No test files, no pytest configuration, no frontend test runner.

Every claim of "working" in IRIS today rests on manual observation. That is the starting position this plan addresses, and it is why the first test written is worth more than the next twenty.

---

## 2 · Engineering testing vs research validation

Two different activities. Do not merge them.

| | Engineering testing | Research validation |
|---|---|---|
| Question | Does the code do what the requirement says? | Does the workflow model improve on the manual process? |
| Owner | This document | [`../mvp-validation/`](../mvp-validation/) |
| Method | Automated tests, CI | ISO 9241-11, GQM, SUS, controlled comparison |
| Evidence | Test output, CI runs | Task metrics, effect sizes, SUS scores, interviews |
| Fails when | A test fails | The hypothesis is not supported — **a legitimate result** |

A passing test suite says nothing about whether the contribution is better than the alternative. Only the controlled comparison can say that, and it must be free to return a negative result.

---

## 3 · Levels

| Level | Scope | Where |
|---|---|---|
| **Import smoke** | The application imports and the URLconf resolves | `backend/` |
| **Unit** | One function or class, no database where avoidable | `backend/apps/*/tests/` |
| **Integration** | Service functions against a real database — workflow transitions, clearance state | `backend/apps/*/tests/` |
| **API / authorization** | Endpoint behaviour per role, per ownership | `backend/apps/*/tests/` |
| **Frontend build** | Types compile, lint passes | `frontend/` |
| **Deployment smoke** | Post-deploy checks against a running instance | manual, scripted later |

**Deliberately excluded:** end-to-end browser automation, load-testing infrastructure, mutation testing, a frontend test harness (P3). Each is defensible on its own and unaffordable together against the semester budget.

---

## 4 · Priority — what to test first

Not everything is worth testing equally. In order:

1. **Import smoke.** One test. Catches three of the five current blockers.
2. **Authorization matrix.** Role × action × ownership. This is where twelve live defects are, and where a regression is a confidentiality breach rather than a bug.
3. **Workflow transitions across both resubmission policies.** The thesis contribution. Must be correct under `PRESERVE` **and** `RESTART_ALL`, or the comparison is invalid.
4. **Clearance state serialization.** That `preserved` is true only after a genuine resubmission.
5. **Transaction boundaries.** A forced mid-transition failure leaves no partial write.
6. Everything else.

---

## 5 · Evidence rules

**Evidence is an artefact, not an assertion.**

| Acceptable | Not acceptable |
|---|---|
| A CI run URL with the result | "Tests pass" |
| Pasted test output showing what ran | "I tested it locally" |
| A screenshot for a visual or manual check | "It works" |
| A recorded command and its exit status | A checkbox with nothing behind it |

**Rules**
- **Do not mark a test as passed without execution evidence.**
- **Do not modify a test to make it pass.** If the test is wrong, fix it deliberately and say so in the PR.
- A skipped test is a failing test in disguise. If it is skipped, record why and when it returns.
- CI output is the default evidence. Manual evidence is for things CI cannot do.

**There is no `TEST_EVIDENCE.md`, and there should not be.** A document asserting that evidence exists is not evidence. Evidence lives in CI runs, recorded outputs and artefacts, and is linked from [`TRACEABILITY.md`](TRACEABILITY.md).

---

## 6 · Execution

```bash
# backend — once the harness lands
cd backend && pytest
cd backend && pytest apps/reviews -v

# frontend
cd frontend && npm run lint
cd frontend && npm run build
```

CI runs on every push and pull request to `refactor/docker-service` — see [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). It currently reports the absence of a backend test harness as a warning on every run, deliberately, so the gap stays visible.

---

## 7 · Entry and exit

**A change may enter Review when** implementation is complete, acceptance criteria are self-verified, applicable tests are added and executed, and CI is green or the failure is explained.

**A change may exit to Done when** the Definition of Done in [`../engineering/WORK_ITEM_LIFECYCLE.md`](../engineering/WORK_ITEM_LIFECYCLE.md) §9 is met. There is no separate testing sign-off — that document is the single gate.

---

## 8 · NFR verification

Non-functional requirements are verified as part of the Weeks 8-15 evidence work, not by unit tests.

| Group | NFRs | How |
|---|---|---|
| Security | NFR-S1…S6 | Authorization matrix tests + manual verification of session expiry and audit immutability |
| Performance | NFR-P1…P5 | Measured against the deployed instance, including the 100-concurrent-session target |
| Usability | NFR-U1, **NFR-U2** | Task-based testing. **NFR-U2 requires 5 of 5 participants to complete a submission in under 10 minutes** |
| Accessibility | NFR-U3 | axe-core in CI, keyboard walkthrough, screen reader pass, **no horizontal scroll at 360 px** |
| Reliability | NFR-R2…R4 | Failure injection and a rehearsed restore |

Each records its evidence in [`TRACEABILITY.md`](TRACEABILITY.md). **An NFR with no evidence is reported as unverified, not as met.**
