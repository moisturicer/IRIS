# 11 — Documentation

Six tasks. For a thesis, documentation is an **assessed artefact**, not overhead — and `docs/` currently overstates what was built.

---

# DOC-01 · Fix the dead links in `docs/README.md`

## Objective
Make the engineering documentation hub honest about what exists.

## Problem
`docs/README.md` presents itself as the central index and links nine documents. **Seven do not exist.**

## Evidence

| Linked | Exists? |
|---|---|
| `SOFTWARE_ENGINEERING_PLAN.md` · `SDLC_PROCESS.md` · `SECURITY.md` · `SECURITY_RISK_REGISTER.md` · `TEST_PLAN.md` · `TRACEABILITY_MATRIX.md` · `DEVELOPMENT_GUIDE.md` | **No** (7) |
| `FRONTEND_IMPLEMENTATION.md` · `CHANGELOG.md` | Yes |

`docs/backend_frontend_architecture_review.md` also cites a companion `architecture_review_and_aws_roadmap.md` that is absent. The README's "Quick start for new contributors" instructs readers to read three documents, two of which do not exist.

## Current State
The documentation index is unusable, and the process it describes cannot be followed.

## Proposed State
Every link resolves, or is explicitly marked planned with an owner and a ticket.

## Scope
Audit every link; remove, mark planned, or repoint. Add `docs/adr/`, `docs/architecture-review/` and `docs/architecture-tasks/`, which exist and are unlisted.

## Out of Scope
Writing the missing documents (`DOC-04`, `DOC-05`, `DOC-06`).

## Technical Approach
Ten minutes of editing, plus a CI link-checker over `docs/` to prevent recurrence.

## Dependencies
None.

## Risks
None.

## Security Impact
The README instructs *"before auth/RBAC changes, read SECURITY.md"* — which points at nothing. That is a process gap, and part of why twelve endpoints shipped unchecked.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
The panel reads `docs/`. A hub of broken links is a credibility cost that takes ten minutes to remove.

## MVP Classification
MVP REQUIRED

## Priority
P0 — Week 1

## Complexity
XS

## Acceptance Criteria
- [ ] Every link in `docs/README.md` resolves.
- [ ] Planned documents are marked "planned" with an owner and ticket.
- [ ] `docs/adr/`, `docs/architecture-review/` and `docs/architecture-tasks/` are listed.
- [ ] A link-checker runs over `docs/` in CI.
- [ ] "Quick start" references only existing documents.

## Testing Requirements
Link-checker in CI (`F-01`).

## Documentation Requirements
This task is documentation.

## Definition of Done
Merged; link-checker green.

---

# DOC-02 · Rewrite the RAG documents as target-state plans

## Objective
Stop documenting an aspirational system in the present tense.

## Problem
`docs/rag_pipeline_service_map.md` describes eleven pipeline phases as though built. **Two exist.**

## Evidence
Phases 1 (upload) and 4 (FTS) exist; phases 2, 3, 5–11 do not. The document uses present-indicative headings throughout — "What Happens", "Stores To", "Returns".

Specific defects: every source link is an absolute `file:///c:/Users/edlav/.antigravity/AntiProjects/IRIS/...` URL — another contributor's machine, resolving for nobody · it cites `docs/software-design/M04-RAG-AI-Services.md`, `docs/software-requirements/M03-Semantic-Indexing.md` and `docs/agile_and_scrum_notes.md`, **none of which exist** · `docker_compose_rag_services.md` gives the gateway build context as `./ai-gateway` while the Compose files use `./ai`, and **neither exists** · it specifies `ankane/pgvector:v0.8.0-pg16` while Compose uses `pgvector/pgvector:pg16` · both describe an `ai-gateway` service the SRS does not contain.

## Current State
A reader cannot distinguish built from planned.

## Proposed State
Both documents retitled as target architecture, with per-phase implementation status and repository-relative links.

## Scope
Retitle · add a status column (implemented / partial / not started) · replace all absolute local links · remove or restore the three missing citations · reconcile `./ai` vs `./ai-gateway` and the two pgvector image names · reflect [ADR-006](../adr/006-minimum-rag-pipeline.md), [ADR-007](../adr/007-pgvector-vector-store.md) and [ADR-010](../adr/010-deployment-topology.md) · correct the concurrency reasoning to distinguish NFR-P1's 100 concurrent *sessions* from 100 concurrent *RAG queries*.

## Out of Scope
Deleting the documents — the thinking is valuable and the target may be right at scale.

## Technical Approach
Keep the analysis; change the tense; add status.

## Dependencies
The RAG and deployment ADRs.

## Risks
None.

## Security Impact
None.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
Documentation that overstates delivery is a credibility risk at defence.

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
S

## Acceptance Criteria
- [ ] Both titles state the architecture is a target, not current state.
- [ ] Every phase carries a status matching the working tree.
- [ ] `grep -rn "file:///c:" docs/` returns nothing.
- [ ] Every cited document exists or the citation is removed.
- [ ] Build contexts and image names match the Compose files.
- [ ] The sessions-vs-queries distinction is stated correctly.

## Testing Requirements
Link-checker green.

## Documentation Requirements
This task is documentation.

## Definition of Done
Merged; a reader can tell built from planned in under a minute.

---

# DOC-03 · SRS and SDD reconciliation

## Objective
Bring the governing documents into line with what will be built. *(Executed as part of `F-03`; recorded here for completeness.)*

## Problem
Cuts not recorded in the SRS become undocumented deviations — worse than the original scope.

## Evidence
Qdrant residue (§384 vs §456/§624) · two extraction hierarchies (§31 vs §481-489/§361) · NFR-P3's unachievable 3-second target · embedding provider "TBD" (§632) against a data-handling commitment (§197) · a Cohere reference in the SDD the SRS does not support.

## Current State
The documents describe a different system from the one being built.

## Proposed State
Amended SRS and SDD with a dated change history citing ADRs.

## Scope
See `F-03`.

## Out of Scope
Rewriting requirements wholesale.

## Technical Approach
Dated change-history rows citing the driving ADR.

## Dependencies
**Blocked on the SRS amendment procedure** (external blocker #4). All eleven ADRs feed it.

## Risks
Amendments may need supervisor or panel sign-off — confirm the process before editing.

## Security Impact
§197's claim must match `R-02`'s implementation.

## Performance Impact
NFR-P3's amended value determines whether `V-10` can pass.

## SaaS Impact
Records the SaaS intent, which the current SRS does not.

## Research/Thesis Impact
High — internal consistency is assessed.

## MVP Classification
MVP REQUIRED

## Priority
P0 — Week 3

## Complexity
M

## Acceptance Criteria
See `F-03`.

## Testing Requirements
None.

## Documentation Requirements
Amended SRS, SDD and change history.

## Definition of Done
Merged and reviewed per the confirmed process.

---

# DOC-04 · `TEST_PLAN.md`

## Objective
Produce the test plan the README already promises.

## Problem
`docs/README.md` lists a Test Plan as existing documentation for "QA, developers". It does not exist, and neither does any test.

## Evidence
No `docs/TEST_PLAN.md`. Zero test files.

## Current State
Promised, absent.

## Proposed State
A test plan assembled largely from `09-testing.md` and `10-mvp-validation.md`.

## Scope
Test levels (unit, integration, system, acceptance) · scope and exclusions · entry/exit criteria per level · role matrix · tooling (pytest, pytest-django, factory-boy, Vitest, JMeter, axe-core) · traceability to NFR validation methods · defect management.

## Out of Scope
Writing the tests.

## Technical Approach
Assemble from the two existing documents; do not invent a parallel strategy. The seam-first approach is defensible and honest — do not promise coverage the team cannot deliver.

## Dependencies
`T-01`…`T-04`, `V-01`…`V-15`.

## Risks
Low.

## Security Impact
`T-02`'s output is the NFR-S4 evidence artefact and must be named here.

## Performance Impact
JMeter methods for NFR-P1/P2/R3 belong here.

## SaaS Impact
None.

## Research/Thesis Impact
An assessed artefact.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] `docs/TEST_PLAN.md` exists and is linked from `docs/README.md`.
- [ ] All four levels defined with entry/exit criteria.
- [ ] Every NFR with a validation method maps to a named test or validation task.
- [ ] A role matrix names who executes each level.
- [ ] Tooling matches what is actually installed.

## Testing Requirements
None.

## Documentation Requirements
This task is documentation.

## Definition of Done
Merged and linked; reviewed by whoever owns QA.

---

# DOC-05 · `SECURITY.md` and the risk register

## Objective
Produce the two security documents the README promises and the process depends on.

## Problem
`docs/README.md` instructs *"before auth/RBAC changes, read SECURITY.md and check SECURITY_RISK_REGISTER."* Neither exists — so the stated process cannot be followed.

## Evidence
No `SECURITY.md`, no `SECURITY_RISK_REGISTER.md`. Substantial content exists in `docs/architecture-review/05-security-architecture.md`, `05-security.md` and [ADR-009](../adr/009-authorization-model.md).

## Current State
Promised, absent — and twelve endpoints shipped unchecked.

## Proposed State
Both written, with a live register tracking findings to closure.

## Scope
`SECURITY.md`: architecture, controls, NFR-S1…S6 mapping, secure development practices, the authorization model, secrets handling, incident response. `SECURITY_RISK_REGISTER.md`: each finding with likelihood, impact, mitigation, owner, status — seeded with the seven `S-0x` findings.

## Out of Scope
Fixing the findings.

## Technical Approach
Derive from the review; keep the register live — the README already requires review at each milestone.

## Dependencies
`S-01`…`S-07` supply content and status.

## Risks
**A public register enumerating unfixed vulnerabilities is itself sensitive.** If the repository is public, keep the register private or describe classes rather than reproduction steps until fixes land.

## Security Impact
Makes the posture reviewable and the process followable.

## Performance Impact
None.

## SaaS Impact
Institutional buyers ask for security documentation during procurement.

## Research/Thesis Impact
An assessed artefact.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] Both exist and are linked from `docs/README.md`.
- [ ] Every NFR-S1…S6 control is described with implementation and validation.
- [ ] The register contains all seven `S-0x` findings with likelihood, impact, owner, status.
- [ ] The authorization model — roles, object-level rules, the `is_staff` decision — is documented.
- [ ] Repository visibility is considered before publishing unfixed findings.

## Testing Requirements
None.

## Documentation Requirements
This task is documentation.

## Definition of Done
Merged and linked; register reflects live status; a milestone review scheduled.

---

# DOC-06 · Requirements traceability matrix

## Objective
Map every FR and NFR to the code, API, UI, test and validation task that satisfies it — and state honestly what does not.

## Problem
`docs/README.md` promises a traceability matrix as the entry point for picking work. It does not exist — so nobody can tell which of the 31 FRs and 21 NFRs are delivered.

## Evidence
No `docs/TRACEABILITY_MATRIX.md`. The SRS defines **31 FRs** (FR-M1-01 … FR-M8-03) and **21 NFRs** (M1–M3, P1–P5, R1–R4, S1–S6, U1–U3).

Known gaps: FR-M3-01 does not work · FR-M3-03 not implemented · FR-M4-01/02 not implemented · FR-M8-03 implemented but shadowed and unrouted · FR-M2-06/07 removed from MVP scope.

## Current State
No traceability. The `B-09` question — whether ten unused domain models map to live Module 2 requirements — cannot be resolved without it.

## Proposed State
One table: FR/NFR → code module → API endpoint → UI route → test → validation task → status.

## Scope
All 31 FRs and 21 NFRs · status per requirement (implemented / partial / **deferred to Phase 2** / not started) · a link to the `V-xx` task validating each NFR · **resolve `B-09`'s held-back models**.

## Out of Scope
Implementing the gaps.

## Technical Approach
Build from the SRS tables outward to code. Expect a substantial "deferred" column — that honesty is the document's value, and it is the artefact that makes [ADR-001](../adr/001-mvp-scope-boundary.md)'s cuts defensible at defence.

## Dependencies
Informed by every task. **Blocks `B-09`'s model deletion.** Feeds `F-03`.

## Risks
The matrix will show significant gaps. That is the point — better discovered now than at defence.

## Security Impact
Maps NFR-S1…S6 to controls and evidence.

## Performance Impact
Maps NFR-P1…P5 to validation tasks.

## SaaS Impact
None.

## Research/Thesis Impact
**High.** This is the artefact that lets the team say "delivered / partial / Phase 2" with evidence rather than hand-waving.

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
L

## Acceptance Criteria
- [ ] All 31 FRs and 21 NFRs appear.
- [ ] Each row names code module, endpoint, UI route, test and validation task, or states "not implemented".
- [ ] Every NFR links to its `V-xx` task.
- [ ] Status is accurate against the working tree on the day of writing.
- [ ] A decision is recorded on whether the ten unused domain models map to live requirements.
- [ ] Linked from `docs/README.md`.

## Testing Requirements
None.

## Documentation Requirements
This task is documentation.

## Definition of Done
Merged and linked; `B-09`'s held-back deletions resolved; the FR/NFR gap list ticketed.
