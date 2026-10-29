# Test Plan

**Purpose.** How IRIS is tested, and what counts as evidence.
**Owns.** Test strategy, levels, execution, evidence rules.
**Does not own.** Requirement→test mapping ([`TRACEABILITY.md`](TRACEABILITY.md)) · research evaluation ([`../mvp-validation/`](../mvp-validation/)) · Definition of Done ([`../engineering/DEFINITION_OF_DONE.md`](../engineering/DEFINITION_OF_DONE.md)).
**Authority.** Authoritative for engineering testing.
**Update when.** Test tooling, levels or evidence rules change.

---

## 1 · Current state — stated plainly

**The backend harness exists (IR-82):** `pytest.ini` + `conftest.py`, with DB-required tests skipping cleanly when no Postgres is reachable — **except where `IRIS_REQUIRE_DB` is set, which CI does, and where that same condition fails the run instead (IR-163).** Skipping is a convenience for a laptop with no database running; in CI it is how a suite reports success having executed nothing, which is what happened to the authorization suite until IR-165. The decision lives in `backend/testing/harness.py` and is covered by `apps/tests/test_harness.py`. Coverage is concentrated where the RAG pipeline was built out — `apps/ai` (chunking, extraction, ingestion, repositories) and `apps/documents` — plus an import smoke test (`apps/tests/test_boot.py`) and targeted authorization tests in `apps/records`.

**The frontend still has zero automated tests.** No test runner is installed; `npm run lint` and `npm run build` are the only automated frontend checks.

Backend and frontend workflow-layer coverage (clearance transitions, resubmission policy, remaining authorization gaps) is thinner than the RAG-side coverage — see `docs/testing/TRACEABILITY.md` for what is and isn't demonstrated per requirement. **A requirement is not satisfied because code exists for it; it is satisfied when a test demonstrates it and the evidence is recorded.**

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

1. **Import smoke.** One test (`apps/tests/test_boot.py`), already in place.
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
- A skipped test is a failing test in disguise. If it is skipped, record why and when it returns. **In CI this is enforced, not asked for:** `IRIS_REQUIRE_DB=1` turns a wholesale environment skip into a failed run, so the only skips that can reach a green build are individual tests opting out for a stated reason.
- **Judge a run by what it executed, not by its colour.** Two green suites in this repo had run nothing — one via a namespace-package discovery failure (`Found 0 test(s)`, exit 0), one via environment skipping. Both looked identical to a passing build.
- CI output is the default evidence. Manual evidence is for things CI cannot do.

**There is no `TEST_EVIDENCE.md`, and there should not be.** A document asserting that evidence exists is not evidence. Evidence lives in CI runs, recorded outputs and artefacts, and is linked from [`TRACEABILITY.md`](TRACEABILITY.md).

---

## 6 · Execution

```bash
# backend
cd backend && python -m pytest -q
cd backend && python -m pytest apps/reviews -v
cd backend && python -m pytest apps/ai apps/documents   # RAG pipeline suites

# Reproduce CI's contract locally: a missing database fails the run instead of
# skipping it. Use this before claiming a suite passed.
cd backend && IRIS_REQUIRE_DB=1 python -m pytest -ra

# frontend
cd frontend && npm run lint
cd frontend && npm run build
```

CI runs on every push and pull request to `feat/rag-service` and `main` — see [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). `ci.yml`'s own comment records that it is expected to stay red until IR-57 (application boot) and IR-58 (Docker stack) land — do not weaken a gate to make it green.

### Security gate — dependency audits (IR-613)

The CI `security` job fails on any **high or critical** advisory in the backend's production dependencies (`pip-audit -r backend/requirements/production.txt`, which includes `base.txt`) or the frontend lockfile (`npm audit`), unless the advisory is accepted in [`security/allowlist.yml`](../../security/allowlist.yml). Moderate and low findings are printed and kept as the `dependency-audit` artifact, but do not fail the job.

Three things also fail it (IR-633): a backend dependency `pip-audit` **could not audit** (it reports a `skip_reason`), which counts as a high finding named `skipped:<package>`; a gate run given **no report at all**; and an allowlist with a **duplicate id**. npm reports only an advisory's GHSA id, so the gate looks up its aliases on OSV, and a CVE entry matches an npm finding too. A failed OSV lookup leaves a finding high and without aliases, so an outage can fail the gate but never pass it.

`security/audit_gate.py` makes the decision, not the tools' own flags: `npm audit` has no allowlist, and `pip-audit` reports no severity. Python severities are the GitHub-reviewed ones from OSV. A finding whose severity cannot be found counts as high, so an OSV outage fails the gate rather than passing it. The gate's own tests run first in the same job (`python -m pytest security/tests`).

**Accepting a finding.** Fix by upgrading wherever an upgrade exists. When one does not, or the advisory does not apply (for example a dev-server-only bug in a tool that never ships), add an entry:

```yaml
entries:
  - id: GHSA-xxxx-xxxx-xxxx    # any alias matches: GHSA, CVE or PYSEC, any case
    reason: Why it does not apply, or what blocks the upgrade.
    owner: Who revisits it
    expires: 2026-12-31        # at most 90 days out
```

All four fields are required. **An expired entry fails CI** even if the finding is gone. The entry goes through normal PR review like any other change. When the gate reports an entry as `unused`, the finding is gone and the entry should be deleted.

Reproduce locally from the repo root:

```bash
pip install pip-audit==2.10.1 pyyaml==6.0.2
pip-audit -r backend/requirements/production.txt -f json -o pip-audit.json
(cd frontend && npm audit --json > ../npm-audit.json)
python -m security.audit_gate --allowlist security/allowlist.yml --pip-audit pip-audit.json --npm-audit npm-audit.json
```

### Security gate — static analysis (IR-614)

The same job runs **bandit** (1.9.4) over `backend/` and `ai/`, and **semgrep** (1.180.0) over the whole repository with the `p/django`, `p/python`, `p/typescript`, `p/react` and `p/secrets` rulesets plus [`security/semgrep.yml`](../../security/semgrep.yml). Both reports go to the same gate and the same allowlist, so there is one exception process. A bandit `HIGH` or semgrep `ERROR` finding fails the job; medium and low are printed and kept as the `sast` artifact. A file bandit could not parse, or a semgrep error at `error` level, also fails it: unscanned is not clean. A semgrep `warn` (a rule timing out on one file) is reported only.

**Naming a finding.** A SAST finding's id is `<tool>:<rule>:<path>`, for example `bandit:B602:backend/core/utils.py` or `semgrep:security.iris-request-data-in-raw-sql:backend/apps/records/views.py`. An allowlist entry therefore accepts **one rule in one file**: it survives the code above it moving, and the same rule in another file still fails. There is no way to allowlist a rule everywhere, by design.

**What the local rule is for.** The registry rates request data reaching raw SQL as `WARNING` (semgrep) and `MEDIUM` (bandit `B608`), so `cursor.execute(f"... {request.GET['q']}")` would only be reported. `security/semgrep.yml` raises exactly that case to `ERROR`. It is a taint rule, so SQL built from constants is not a finding. Verified 2026-10-29 with a probe file outside the repo: `subprocess.call(..., shell=True)` with a non-literal command and the f-string `cursor.execute` both blocked, a parameterised `cursor.execute(sql, [value])` did not.

**What still passes.** The rule is narrower than "any f-string in `cursor.execute`", on purpose. It fires only when the source (`request.*`) and the sink are in the **same function**: open-source semgrep does not follow taint through a call, so request data handed to a helper that builds the SQL is reported at `WARNING`, not blocked. A bare `cursor.execute(f"... {x}")` with no request source is also only reported. Bandit's `B602` (`shell=True`) is `HIGH` only when the command is not a literal; `shell=True` with a fixed string is `LOW`.

**Exclusions.** Two, each commented in its file:

- bandit's `B101` (`assert`) is skipped in test files ([`security/bandit.yml`](../../security/bandit.yml)), where pytest's assertions made it fire 5,759 times. It stays on for application code.
- [`.semgrepignore`](../../.semgrepignore) leaves out installed, built and vendored code (`node_modules/`, `dist/`, `build/`, `vendor/`, virtualenvs, `*.min.js`) plus `.gitignore`. It exists to *replace* semgrep's built-in list, which also skips every `tests/` directory: without it, all 277 tracked files under `tests/` went unscanned. Tests are scanned now.

Migrations are not excluded by either tool; nothing in them is a finding today.

**Baseline when this landed (2026-10-29, the commands below run locally on Windows: bandit 1.9.4 over `backend/` and `ai/`, semgrep 1.180.0 over 1,405 files):** no high finding in either tool, so the allowlist stays empty. Reported below the gate: bandit `B608` twice in `backend/apps/ai/keyword_index.py` (table names from module constants, not input) and semgrep `react-dangerouslysetinnerhtml` in `frontend/src/features/ai/components/PassageQuote.tsx` (KaTeX output with `trust` off), plus low findings.

```bash
pip install bandit==1.9.4 semgrep==1.180.0 pyyaml==6.0.2
bandit -c security/bandit.yml -r backend ai -f json -o bandit.json -q --exit-zero
semgrep scan --metrics=off --json -o semgrep.json --config p/django --config p/python \
  --config p/typescript --config p/react --config p/secrets --config security/semgrep.yml .
python -m security.audit_gate --allowlist security/allowlist.yml --bandit bandit.json --semgrep semgrep.json
```

The registry rulesets are fetched at run time and are not versioned: pinning semgrep pins the engine, not the rules, so a registry update can add a finding without a change here.

---

## 7 · Entry and exit

**A change may enter Review when** implementation is complete, acceptance criteria are self-verified, applicable tests are added and executed, and CI is green or the failure is explained.

**A change may exit to Done when** the Review → Done gate in [`../engineering/DEFINITION_OF_DONE.md`](../engineering/DEFINITION_OF_DONE.md) §3 is met. There is no separate testing sign-off — that document is the single gate.

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
