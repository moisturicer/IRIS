# 11 — Documentation Tasks

Six tasks. For a thesis, documentation is an **assessed artefact**, not overhead — and `docs/` currently overstates what was built.

---

# DOC-01 · Fix the seven dead links in `docs/README.md`

## Objective
Make the engineering documentation hub honest about what exists.

## Problem
`docs/README.md` presents itself as the central index and links nine documents. Seven do not exist.

## Current State
Verified by direct check:

| Linked document | Exists? |
|---|---|
| `SOFTWARE_ENGINEERING_PLAN.md` | **No** |
| `SDLC_PROCESS.md` | **No** |
| `SECURITY.md` | **No** |
| `SECURITY_RISK_REGISTER.md` | **No** |
| `TEST_PLAN.md` | **No** |
| `TRACEABILITY_MATRIX.md` | **No** |
| `DEVELOPMENT_GUIDE.md` | **No** |
| `../frontend/docs/FRONTEND_IMPLEMENTATION.md` | Yes |
| `../CHANGELOG.md` | Yes |

`docs/backend_frontend_architecture_review.md` also cites a companion `architecture_review_and_aws_roadmap.md` that is absent.

The README's "Quick start for new contributors" instructs readers to read three documents, two of which do not exist.

## Proposed State
Every link resolves, or is explicitly marked as planned with an owner.

## Scope
Audit every link in `docs/README.md`; remove, mark as planned, or point to the real location. Add links to `docs/architecture-review/` and `docs/architecture-tasks/`, which exist and are unlisted.

## Out of Scope
Writing the missing documents (`DOC-04`, `DOC-05`, `DOC-06`).

## Technical Approach
Ten minutes of editing. Add a CI link-checker over `docs/` to prevent recurrence (`ARCH-01`).

## Dependencies
None.

## Risks
None.

## Security Impact
`SECURITY.md` and `SECURITY_RISK_REGISTER.md` are referenced by the README's own guidance — *"Before auth/RBAC changes, read SECURITY.md"* — which currently points at nothing. That is a process gap, not just a broken link.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] Every link in `docs/README.md` resolves to an existing file.
- [ ] Documents that are planned rather than written are marked "planned" with an owner and a ticket.
- [ ] `docs/architecture-review/` and `docs/architecture-tasks/` are listed in the document map.
- [ ] A link-checker runs over `docs/` in CI.
- [ ] The "Quick start" section references only documents that exist.

## Definition of Done
Merged; link-checker green in CI.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `thesis`, `mvp-required`

---

# DOC-02 · Rewrite the two RAG documents as target-state plans

## Objective
Stop documenting an aspirational system in the present tense.

## Problem
`docs/rag_pipeline_service_map.md` describes eleven pipeline phases as though built. **Two exist.** It also links source files on another contributor's local filesystem and cites requirement documents that are not in the repository.

## Current State
Verified against the working tree: phases 1 and 4 exist; phases 2, 3, 5–11 do not. The document uses present-indicative headings throughout — "What Happens", "Stores To", "Returns".

Specific defects:
- Every source link is an absolute `file:///c:/Users/edlav/.antigravity/AntiProjects/IRIS/...` URL — another contributor's machine. These resolve for nobody.
- Cites `docs/software-design/M04-RAG-AI-Services.md`, `docs/software-requirements/M03-Semantic-Indexing.md` and `docs/agile_and_scrum_notes.md` — **none exist**.
- `docker_compose_rag_services.md` gives the gateway build context as `./ai-gateway`; the Compose files use `./ai`; **neither exists**.
- `docker_compose_rag_services.md` specifies `ankane/pgvector:v0.8.0-pg16`; the Compose files use `pgvector/pgvector:pg16`.
- Both describe an `ai-gateway` service the SRS does not contain.

## Proposed State
Both documents retitled as target architecture, with a per-phase implementation status and repository-relative links.

## Scope
- Retitle: *"Target RAG Architecture (not yet implemented)"*
- Add a status column per phase: implemented / partial / not started
- Replace all `file:///c:/Users/edlav/...` links with repository-relative paths
- Remove or restore the three missing citations
- Reconcile `./ai` vs `./ai-gateway`, and the two pgvector image names
- Reflect the `FW-01`, `FW-02`, `FW-03` and `FW-05` decisions

## Out of Scope
Deleting the documents — the *thinking* is valuable and the target may well be right at scale.

## Technical Approach
Keep the analysis; change the tense and add status. The concurrency reasoning in `docker_compose_rag_services.md` should be corrected to distinguish `NFR-P1`'s 100 concurrent *sessions* from 100 concurrent *RAG queries*.

## Dependencies
`FW-01`, `FW-02`, `FW-03`, `FW-05` decisions.

## Risks
None.

## Security Impact
None.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] Both titles state that the architecture is a target, not the current state.
- [ ] Every phase carries an implementation status matching the working tree.
- [ ] `grep -rn "file:///c:" docs/` returns no matches.
- [ ] Every cited document exists or the citation is removed.
- [ ] Build contexts and image names match the Compose files.
- [ ] The `NFR-P1` sessions-vs-queries distinction is stated correctly.

## Definition of Done
Both documents merged; link-checker green; a reader can tell built from planned in under a minute.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `ai`, `thesis`, `mvp-required`

---

# DOC-03 · Reconcile the SRS and SDD with implementation decisions

## Objective
Bring the governing documents into line with what will actually be built, so the thesis is internally consistent.

## Problem
Several decisions taken since the SRS revision are not reflected in it, and the SRS itself carries residue from superseded ones.

## Current State
- **Qdrant residue.** The change history (§31) records "Corrected Qdrant deployment from cloud to self-hosted on-premise", and §384 lists "Qdrant snapshot exports" in the backup table — while §456 and §624 state there is no separate vector database. The backup row contradicts the architecture section.
- **Extraction hierarchy.** §31 records "OpenDataLoader (primary), PyMuPDF (fallback), Tesseract OCR (tertiary)", while §481-489 and §361 specify Docling-serve primary with PyMuPDF/pytesseract fallback. Two different hierarchies.
- **NFR-P3** may be amended by `FW-05` (3 s p95 vs a 3–10 s LLM round-trip).
- **Docling** may be deferred to Phase 2 by `FW-03`.
- **Embedding provider** is "TBD" (§632) pending `FW-06`.
- **SDD** contains one Cohere reference the SRS does not support.

## Proposed State
An SRS/SDD amendment recording each decision, with the change history updated.

## Scope
- Remove the Qdrant backup-table residue
- Reconcile the two extraction hierarchies to one
- Record the `FW-03`, `FW-05`, `FW-06` outcomes
- Remove the SDD's Cohere reference if `FW-02` descopes reranking
- Update the change-history table with reasons

## Out of Scope
Rewriting requirements wholesale. Changing scope.

## Technical Approach
Amendments with dated change-history rows citing the ADR that drove each — so the SRS and the ADR register agree.

## Dependencies
`FW-02`, `FW-03`, `FW-05`, `FW-06`, `ARCH-06`.

## Risks
The SRS is an assessed artefact; amendments may need supervisor sign-off. **Confirm the process before editing.**

## Security Impact
§197's "anonymized chunks only" claim must match what `AI-05` implements, or the SRS asserts a guarantee the code does not provide.

## Performance Impact
NFR-P3's value determines whether `VAL-12` can pass.

## Deployment Impact
The Docling decision changes the specified service list.

## Framework Impact
Aligns the SRS with the actual stack.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] No Qdrant reference remains except in the historical change log.
- [ ] Exactly one extraction hierarchy is specified.
- [ ] Every `FW-0x` decision is reflected, with a dated change-history row citing its ADR.
- [ ] §197's data-handling claim matches the implemented behaviour.
- [ ] The SDD contains no technology the SRS does not support.
- [ ] Amendments are reviewed per the project's documentation process.

## Definition of Done
Amendments merged and reviewed; SRS, SDD, ADRs and code agree.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `srs`, `sdd`, `thesis`, `mvp-required`

---

# DOC-04 · Write `TEST_PLAN.md`

## Objective
Produce the test plan the README already promises, covering levels, scope, entry/exit criteria and the role matrix.

## Problem
`docs/README.md` lists a Test Plan as an existing document for "QA, developers". It does not exist, and neither does any test.

## Current State
No `docs/TEST_PLAN.md`. No tests. `requirements/development.txt:4` still reads `# TODO: add pytest-django and factory-boy when writing tests`.

Most of the content already exists in this backlog: `08-testing-tasks.md` defines the strategy and tiers; `10-mvp-validation-tasks.md` defines eighteen validation procedures with SRS-traceable pass/fail criteria.

## Proposed State
A test plan assembled largely from those two documents, in the format the thesis expects.

## Scope
- Test levels: unit, integration, system, acceptance
- Scope and exclusions
- Entry/exit criteria per level
- Role matrix: who tests what
- Tooling: pytest, pytest-django, factory-boy, Vitest, JMeter, axe-core
- Traceability to the NFR validation methods
- Defect management

## Out of Scope
Writing the tests (`TEST-01`…`TEST-05`).

## Technical Approach
Assemble from `08-` and `10-`; do not invent a parallel strategy.

## Dependencies
`TEST-01`…`TEST-05` inform it; `DOC-06` shares traceability.

## Risks
Low. Avoid promising coverage the team cannot deliver — the seam-first strategy is defensible and honest.

## Security Impact
`TEST-04`'s authorization suite is the NFR-S4 evidence artefact and must be named here.

## Performance Impact
JMeter methods for NFR-P1/P2/R3 belong here.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required** (an assessed thesis artefact)

## Acceptance Criteria
- [ ] `docs/TEST_PLAN.md` exists and is linked from `docs/README.md`.
- [ ] All four test levels are defined with entry/exit criteria.
- [ ] Every NFR with a validation method maps to a named test or validation task.
- [ ] The role matrix names who executes each level.
- [ ] Tooling is listed and matches what is actually installed.
- [ ] Defect severity and management are defined.

## Definition of Done
Merged and linked; reviewed by whoever owns QA.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `testing`, `thesis`, `mvp-required`

---

# DOC-05 · Write `SECURITY.md` and the risk register

## Objective
Produce the two security documents the README promises and the process it describes depends on.

## Problem
`docs/README.md` instructs contributors: *"Before auth/RBAC changes, read SECURITY.md and check SECURITY_RISK_REGISTER."* Neither exists — so the stated process cannot be followed, which is part of why twelve endpoints shipped without authorization.

## Current State
No `SECURITY.md`, no `SECURITY_RISK_REGISTER.md`. Substantial content already exists in `docs/architecture-review/05-security-architecture.md` and `05-security-tasks.md`.

## Proposed State
Both documents written, with the risk register tracking the findings from this review through to closure.

## Scope
- `SECURITY.md`: architecture, controls, NFR mapping (S1–S6), secure development practices, the authorization model, secrets handling, incident response
- `SECURITY_RISK_REGISTER.md`: each finding with likelihood, impact, mitigation, owner and status
- Seed the register with the nine `SEC-0x` findings

## Out of Scope
Fixing the findings (`05-security-tasks.md`).

## Technical Approach
Derive from the review; keep the register live rather than a snapshot — the README already requires review "at each milestone".

## Dependencies
`SEC-01`…`SEC-09` supply content and status.

## Risks
**A public risk register enumerating unfixed vulnerabilities is itself sensitive.** If the repository is public, consider keeping the register private or describing classes rather than exact reproduction steps until fixes land.

## Security Impact
Makes the security posture reviewable and the process followable.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required** (assessed artefact; the README depends on it)

## Acceptance Criteria
- [ ] Both documents exist and are linked from `docs/README.md`.
- [ ] Every NFR-S1…S6 control is described with its implementation and validation.
- [ ] The register contains all nine `SEC-0x` findings with likelihood, impact, owner and status.
- [ ] The authorization model — roles, object-level rules, the `is_staff` decision — is documented.
- [ ] Secrets handling and rotation are documented.
- [ ] Repository visibility is considered before publishing unfixed findings.

## Definition of Done
Both merged and linked; register reflects live status; a milestone review scheduled.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `security`, `thesis`, `compliance`, `mvp-required`

---

# DOC-06 · Write the requirements traceability matrix

## Objective
Map every FR and NFR to the code, API, UI, test and validation task that satisfies it.

## Problem
`docs/README.md` promises a traceability matrix as the entry point for picking work. It does not exist — and without it, nobody can tell which of the 31 FRs and 21 NFRs are actually delivered.

## Current State
No `docs/TRACEABILITY_MATRIX.md`. The SRS defines **31 FRs** across 8 modules (FR-M1-01 … FR-M8-03) and **21 NFRs** (NFR-M1–M3, P1–P5, R1–R4, S1–S6, U1–U3).

This review has already established several mappings — and several gaps: FR-M3-01 (extraction) does not work; FR-M3-03 (embeddings) is not implemented; FR-M4-01/02 (RAG, summarization) are not implemented; FR-M8-03 is implemented but unrouted and shadowed.

## Proposed State
One table: FR/NFR → code module → API endpoint → UI route → test → validation task → status.

## Scope
- All 31 FRs and 21 NFRs
- Status per requirement: implemented / partial / not started
- Link to the `VAL-xx` task that validates each NFR
- **Resolve the `BE-09` question:** whether the ten unused domain models map to live Module 2 requirements

## Out of Scope
Implementing the gaps.

## Technical Approach
Build from the SRS FR/NFR tables outward to code. Expect the "not started" column to be substantial — that honesty is the document's value.

## Dependencies
Informed by every task here. Blocks the `BE-09` model deletion decision.

## Risks
The matrix will show significant gaps. That is the point — better discovered now than at defence.

## Security Impact
Maps NFR-S1…S6 to their controls and evidence.

## Performance Impact
Maps NFR-P1…P5 to their validation tasks.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Required** (assessed artefact)

## Acceptance Criteria
- [ ] All 31 FRs and 21 NFRs appear.
- [ ] Each row names the code module, endpoint, UI route, test and validation task, or states "not implemented".
- [ ] Every NFR links to its `VAL-xx` task.
- [ ] The status column is accurate against the working tree on the day of writing.
- [ ] A decision is recorded on whether the ten unused domain models map to live requirements (`BE-09`).
- [ ] The matrix is linked from `docs/README.md`.

## Definition of Done
Merged and linked; `BE-09`'s held-back deletions resolved; the FR/NFR gap list ticketed.

## Complexity
L

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`documentation`, `traceability`, `thesis`, `srs`, `mvp-required`
