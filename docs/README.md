# IRIS Documentation

**Purpose.** The map of IRIS documentation and the authority hierarchy between the parts.
**Owns.** Which document is authoritative for what, and where to find it.
**Does not own.** Any subject matter itself — every fact lives in exactly one document, and this file points at it.
**Update when.** A document is added, removed, or changes responsibility.

> **Baseline branch: `refactor/docker-service`.** `main` has diverged and carries a different, older documentation set. Do not use `main` as the reference.

---

## Source-of-truth hierarchy

| # | Authority | Location | Owns |
|---|---|---|---|
| 1 | **Requirements** | [`SRS.md`](SRS.md) | What the system must do. FR/NFR ids. **The only requirements baseline** |
| 2 | **Design** | [`SDD.md`](SDD.md) | How the system is structured to meet the requirements |
| 3 | **Decisions** | [`adr/`](adr/README.md) | Architectural decisions and their rationale |
| 4 | **Engineering** | [`engineering/`](engineering/) | How the team builds, tests, reviews, releases, maintains |
| 5 | **Code and tests** | `backend/`, `frontend/` | Actual behaviour |
| 6 | **Jira** | project IR | Planning and tracking. **Never a requirements authority** |

**When these conflict, the higher one wins and the lower one is corrected.** A contradiction is a defect: record it, do not silently reconcile it.

A requirement is not satisfied because code exists for it. It is satisfied when a test demonstrates it and the evidence is recorded.

---

## The map

### Requirements and design
| Document | Owns |
|---|---|
| [`SRS.md`](SRS.md) | Functional and non-functional requirements |
| [`SDD.md`](SDD.md) | System and component design |

### Decisions
| Document | Owns |
|---|---|
| [`adr/`](adr/README.md) | 11 accepted ADRs — MVP scope, transition table, clearance-aware resubmission, restart-all comparison, instance-per-tenant, minimum RAG, pgvector, FTS degradation, authorization model, deployment topology, evaluation framework |

ADRs are immutable once accepted. A changed decision gets a **new** ADR that supersedes the old one.

### Engineering
| Document | Owns |
|---|---|
| [`engineering/WORK_ITEM_LIFECYCLE.md`](engineering/WORK_ITEM_LIFECYCLE.md) | **The Definition of Done.** State meanings, Definition of Ready, pull model, review gate |
| [`engineering/SDLC.md`](engineering/SDLC.md) | Branching, PRs, CI, review, release, deployment, emergency changes |
| [`engineering/DEVELOPMENT.md`](engineering/DEVELOPMENT.md) | Setup, commands, environment, troubleshooting |

### Testing
| Document | Owns |
|---|---|
| [`testing/TEST_PLAN.md`](testing/TEST_PLAN.md) | Test strategy, levels, execution, evidence rules |
| [`testing/TRACEABILITY.md`](testing/TRACEABILITY.md) | **The single traceability mechanism.** Requirement → design → implementation → test → evidence → status |

### Security
| Document | Owns |
|---|---|
| [`security/SECURITY.md`](security/SECURITY.md) | Authentication, authorization, file access, secrets, boundaries, privacy, audit, known defects |

### Research and product
| Document | Owns |
|---|---|
| [`mvp-validation/`](mvp-validation/) | **Research validation methodology.** ISO 9241-11, GQM, SUS, the controlled comparison, respondent plan, analysis plan |
| [`ui-ux/`](ui-ux/) | Interface direction and per-screen specifications for the 16 MVP screens |

> **Research validation and engineering testing are deliberately separate.** `mvp-validation/` answers *does the workflow model improve on the manual process?* `testing/` answers *does the code do what the requirement says?* Do not merge them — dissolving the research methodology into QA documentation would destroy its standing as evidence.

### Planning
| Document | Owns |
|---|---|
| [`architecture-tasks/`](architecture-tasks/00-index.md) | 72 task specifications with MVP classification, priority, complexity |
| [`jira-sync/`](jira-sync/01-revised-capacity-validated-plan.md) | The Semester 2 Kanban plan and its capacity validation |
| [`architecture-review/`](architecture-review/) | The verified architecture audit that produced the ADRs |

---

## Known contradictions

Recorded rather than silently reconciled. Each needs a decision.

| # | Contradiction | Status |
|---|---|---|
| 1 | **Docling-serve** is SRS-specified in four places; ADR-006 defers it | Needs an SRS amendment — **NEEDS ADVISER CONFIRMATION** |
| 2 | `docker_compose_rag_services.md` and `rag_pipeline_service_map.md` describe an **eleven-phase RAG pipeline**; two phases exist | To be rewritten as target-state plans, clearly marked PROPOSED |
| 3 | Both Compose files declare an **`ai-gateway`** service; no `./ai` directory exists and ADR-010 rejects it | Removed by IR-58 |
| 4 | `backend_frontend_architecture_review.md` predates the verified review | Superseded by `architecture-review/`; retained for history |
| 5 | **`main` and `refactor/docker-service` carry different documentation sets** — main has per-module `software-requirements/` and `software-design/` plus 8 engineering docs; the baseline consolidated these into `SRS.md`/`SDD.md` and dropped the engineering set | Engineering set rebuilt here under `engineering/`. The module docs on `main` are **legacy** |

---

## Conventions

Every engineering document states, at the top: its purpose · what it owns · what it does **not** own · its authority · what it depends on · when to update it.

**No fact appears in two documents.** If it is needed in two places, one states it and the other links.

*Baseline: `refactor/docker-service`. Last reviewed: 2026-09-01.*
