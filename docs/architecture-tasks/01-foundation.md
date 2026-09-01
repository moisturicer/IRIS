# 01 — Foundation

Cross-cutting tasks that unblock or constrain everything else.

---

# F-01 · CI pipeline

## Objective
A GitHub Actions workflow that fails the build on import errors, missing migrations, broken Compose config, lint and type errors.

## Problem
No CI exists. Every one of the five current blockers is machine-detectable and none was detected. This is the root cause of the review, not a side finding.

## Evidence
No `.github/` directory. `package.json` scripts: `dev`, `build`, `preview`, `lint` — no `test`, no `typecheck`. `requirements/development.txt:4`: `# TODO: add pytest-django and factory-boy when writing tests`.

## Current State
Nothing runs on push. Broken code merges silently.

## Proposed State
`.github/workflows/ci.yml`, two jobs, six checks, under five minutes.

## Scope
Backend job (Postgres service container): install deps → `makemigrations --check --dry-run` → `manage.py check` → `pytest`. Frontend job: `npm ci` → `typecheck` → `lint` → `build`. Plus `docker compose config` on both files.

## Out of Scope
Deployment automation, container publishing, coverage gates, multi-version matrices.

**Dependency and secret scanning is in scope but specified separately** as `T-05` — it plugs into this workflow rather than duplicating it. SAST, container image scanning and licence scanning remain out of scope.

## Technical Approach
Pin action versions; cache pip and npm. Land the workflow early with `pytest` and `lint` steps commented, enabling each as `T-01` and `FE-04` arrive.

## Dependencies
`T-01` (pytest), `FE-04` (eslint config, typecheck script). Can land before both.

## Risks
Low. A red first build is expected and is the point — budget time for what it surfaces.

## Security Impact
Indirect and large: prevents silent reintroduction of the `05-security.md` defects once fixed.

## Performance Impact
None on the application.

## SaaS Impact
Becomes the gate for per-instance releases under [ADR-005](../adr/005-instance-per-tenant.md).

## Research/Thesis Impact
None directly; protects the thesis-critical work from regression.

## MVP Classification
MVP BLOCKER

## Priority
P1

## Complexity
S

## Acceptance Criteria
- [ ] Workflow triggers on push and pull request.
- [ ] An undefined name in any Django module fails at `manage.py check` (demonstrated, then reverted).
- [ ] A model field without a migration fails at `makemigrations --check` (demonstrated).
- [ ] A Compose build context that does not exist fails at `docker compose config`.
- [ ] A TypeScript error fails `npm run typecheck`.
- [ ] Total runtime under 5 minutes.

## Testing Requirements
The workflow is itself the test harness. Verify each check fails on a deliberately broken commit.

## Documentation Requirements
Required-checks list recorded in `docs/SDLC_PROCESS.md` (or `DOC-04` if that document does not yet exist).

## Definition of Done
Merged and green on `refactor/docker-service`; branch protection enabled by the repo owner; both demonstrations recorded in the PR.

---

# F-02 · `core/enums.py` — one `TextChoices` per concept

## Objective
Replace five independent encodings of the clearance offices, and scattered status literals, with one source of truth per concept.

## Problem
Adding a fifth reviewing office requires finding and editing four of five dictionaries across three modules. Missing one fails **silently**, because every notification path swallows exceptions.

## Evidence
`{ITSO, IERC, KTTO}` encoded five times: `RecordClearance.OFFICE_CHOICES` (`reviews/models.py:56`) · `ROLE_TO_OFFICE` (`reviews/services.py:68`) · `CLEARANCE_OFFICES` (`reviews/services.py:381`) · `_OFFICE_TO_ROLE` (`notifications/services.py:416`) · `_OFFICE_LABELS` (`notifications/services.py:264`). Also: `Record.IP_TYPE_CHOICES` restated as `VALID_IP_TYPES` (`records/views.py:180`); the queued/running/done/failed quartet duplicated on `PdfExtraction` and `EmbeddingJob`.

## Current State
Office identity is code, in five places.

## Proposed State
`core/enums.py` with `PipelineStatus`, `ClearanceOffice`, `ReviewStage`, `IPType`, `JobStatus`, `WorkflowEvent` as `models.TextChoices`. `ClearanceOffice` carries a `role_name` property so the role↔office mapping is a member attribute, not a fourth dict.

## Scope
Create the enums; replace all five office encodings, the IP-type duplication and the job-status duplication; replace status literals in `reviews/services.py` and `records/views.py`.

## Out of Scope
The transition table itself (`W-01`) — this is its prerequisite.

## Technical Approach
Member **values must match existing database strings exactly** so no data migration is required. Verify with a `makemigrations --check` showing no schema change.

## Dependencies
None. **Prerequisite for `W-01`.**

## Risks
Low if values match exactly. A mismatch is a silent data bug — assert equality in a test.

## Security Impact
Indirect: removes a class of silent authorization mis-mapping.

## Performance Impact
None.

## SaaS Impact
First step toward institution-configurable offices ([ADR-005](../adr/005-instance-per-tenant.md)). The enum becomes the default set an institution overrides.

## Research/Thesis Impact
Supporting — `W-01` depends on it.

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
S

## Acceptance Criteria
- [ ] `core/enums.py` defines the six enums.
- [ ] `grep -rn '"itso"\|"ierc"\|"ktto"' backend/apps/` returns matches only in `core/enums.py`.
- [ ] `makemigrations --check` reports no schema change.
- [ ] A test asserts every enum value equals the string previously stored in the database.
- [ ] `VALID_IP_TYPES` is gone.

## Testing Requirements
Value-equality test against the pre-change database strings; runs in CI.

## Documentation Requirements
None beyond docstrings.

## Definition of Done
Merged; all call sites migrated; equality test in CI.

---

# F-03 · Week 3 requirements and design refactor

## Objective
Formalise every scope cut, contradiction and amendment in the SRS, SDD and traceability matrix, so the delivered system and the governing documents agree.

## Problem
Cuts that are not recorded in the SRS become undocumented deviations — worse than the original scope, and indefensible at a technical defence.

## Evidence
Contradictions found in the current documents: **Qdrant residue** — SRS §384 lists "Qdrant snapshot exports" while §456 and §624 state there is no separate vector database. **Two extraction hierarchies** — §31 says OpenDataLoader → PyMuPDF → Tesseract; §481-489 and §361 say Docling-serve primary with PyMuPDF fallback. **NFR-P3** demands a 3-second p95 complete chatbot response against a 3–10 s LLM round-trip. **Embedding provider** is "TBD" (§632) while §197 already commits to a data-handling guarantee. The **SDD** contains a Cohere reference the SRS does not support.

## Current State
Documents describe a system that differs from what is built and from what will be built.

## Proposed State
SRS and SDD amended; traceability matrix created; every deferral marked Phase 2 with rationale.

## Scope
Remove Qdrant residue · collapse the extraction hierarchy to one · amend NFR-P3 per [ADR-011](../adr/011-evaluation-framework.md) · record the [ADR-001](../adr/001-mvp-scope-boundary.md) cuts as Phase 2 · record the SaaS and tenancy position ([ADR-005](../adr/005-instance-per-tenant.md)) · remove the SDD's Cohere reference · update the change-history table with reasons and ADR references.

## Out of Scope
Rewriting requirements wholesale. Changing the contribution.

## Technical Approach
Dated change-history rows citing the ADR that drove each amendment, so SRS and ADR register agree.

## Dependencies
**Blocked on the SRS amendment procedure** (open external blocker #4). All eleven ADRs feed it.

## Risks
The SRS is an assessed artefact; amendments may need supervisor or panel sign-off. Confirm the process before editing.

## Security Impact
§197's "anonymized chunks only" claim must match what `R-02` implements, or the SRS asserts a guarantee the code does not provide.

## Performance Impact
NFR-P3's amended value determines whether `V-10` can pass.

## SaaS Impact
Records the SaaS intent, which the current SRS (single CIT-U deployment) does not.

## Research/Thesis Impact
High. The panel assesses these documents; internal consistency is part of the mark.

## MVP Classification
MVP REQUIRED

## Priority
P0 — Week 3

## Complexity
M

## Acceptance Criteria
- [ ] No Qdrant reference remains outside the historical change log.
- [ ] Exactly one extraction hierarchy is specified.
- [ ] NFR-P3 states an achievable, measurable target.
- [ ] Every ADR-001 deferral appears as Phase 2 with rationale.
- [ ] §197's data-handling claim matches implemented behaviour.
- [ ] The SDD contains no technology the SRS does not support.
- [ ] Change history updated with dated rows citing ADRs.

## Testing Requirements
None (documentation). A CI link-checker over `docs/` prevents dead references.

## Documentation Requirements
This task *is* documentation. Output: amended SRS, amended SDD, `DOC-06` traceability matrix.

## Definition of Done
Amendments merged and reviewed per the confirmed process; SRS, SDD, ADRs and code agree.
