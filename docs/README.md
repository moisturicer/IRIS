# IRIS Documentation

**Purpose.** The map of IRIS documentation and the authority hierarchy between the parts.
**Owns.** Which document is authoritative for what, and where to find it.
**Does not own.** Any subject matter itself — every fact lives in exactly one document, and this file points at it.
**Update when.** A document is added, removed, or changes responsibility.

> **Baseline branch: `feat/rag-service`.** `main` carries the ADRs and is merged in; RAG and AI work continues on `feat/rag-service`.
>
> **`SRS.md` and `SDD.md` are frozen (2026-09-03)** — retained as thesis deliverables, out of date, and **not an authority for engineering work.** `docs/adr/` is the baseline. See the hierarchy below.

---

## Source-of-truth hierarchy

| # | Authority | Location | Owns |
|---|---|---|---|
| 1 | **Decisions, requirements and design** | [`adr/`](adr/README.md) | What the system must do, how it is structured, and why. **The authority** |
| 2 | **Engineering** | [`engineering/`](engineering/) | How the team builds, tests, reviews, releases, maintains |
| 3 | **Code and tests** | `backend/`, `frontend/` | Actual behaviour |
| 4 | **Jira** | project IR | Planning and tracking. **Never a requirements authority** |
| — | **Frozen** | [`SRS.md`](SRS.md), [`SDD.md`](SDD.md) | **Thesis deliverables. Out of date, unmaintained, and not consulted or cited for engineering work.** `FR-`/`NFR-` ids survive as labels only |

**When these conflict, the higher one wins and the lower one is corrected.** A contradiction is a defect: record it, do not silently reconcile it.

A requirement is not satisfied because code exists for it. It is satisfied when a test demonstrates it and the evidence is recorded.

---

## The map

### Requirements and design
| Document | Owns |
|---|---|
| [`SRS.md`](SRS.md) | **FROZEN thesis deliverable.** Not consulted, not cited |
| [`SDD.md`](SDD.md) | **FROZEN thesis deliverable.** Not consulted, not cited |
| [`rag_architecture.md`](rag_architecture.md) | **The end-to-end RAG pipeline** — every stage, its seams, its honest status, and the order it gets built |
| [`chunker_architecture.md`](chunker_architecture.md) | Chunk as the retrievable unit, context-path prefixing, idempotent re-chunking, citation provenance. The design [ADR-013](adr/013-chunk-level-rag-pipeline.md) adopts |
| [`rag_third_party_services_architecture.md`](rag_third_party_services_architecture.md) | Provider survey and the prerequisites behind [ADR-015](adr/015-voyage-embedding-and-reranking.md) |
| [`document_requirements_architecture.md`](document_requirements_architecture.md) | Target three-layer department-template / office-checklist model for FR-M2-01 |

### Decisions
| Document | Owns |
|---|---|
| [`adr/`](adr/README.md) | 15 ADRs, 13 in force — MVP scope, transition table, clearance-aware resubmission, restart-all comparison, instance-per-tenant, pgvector, FTS degradation, authorization model, deployment topology, evaluation framework, chunk-level RAG, AI gateway as a service, Voyage provider. **006 and 012 are superseded by 013 and 014** |

ADRs are immutable once accepted. A changed decision gets a **new** ADR that supersedes the old one.

### Engineering
| Document | Owns |
|---|---|
| [`engineering/DEFINITION_OF_DONE.md`](engineering/DEFINITION_OF_DONE.md) | **The Definition of Done.** Definition of Ready, review entry, review gate, Done, reopening |
| [`engineering/SDLC.md`](engineering/SDLC.md) | Branching, PRs, CI, review, release, deployment, emergency changes, **the board and pull model** |
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

### Agents
| Document | Owns |
|---|---|
| [`agents/issue-tracker.md`](agents/issue-tracker.md) | Jira access via MCP, the **state mapping** and the **label taxonomy** |
| [`agents/triage-labels.md`](agents/triage-labels.md) | The five canonical triage roles mapped onto IRIS labels |
| [`agents/domain.md`](agents/domain.md) | How agents read `CONTEXT.md` and `docs/adr/` before exploring |

### Archive
| Document | Owns |
|---|---|
| [`archive/`](archive/README.md) | **Nothing.** Superseded documents retained only because active documents and ADR-006 cite them as evidence |

---

## Known contradictions

Recorded rather than silently reconciled. Each needs a decision.

| # | Contradiction | Status |
|---|---|---|
| 1 | **Docling-serve** deferred by ADR-006 while the chunker needs structured input | **Resolved 2026-09-03** — [ADR-016](adr/016-docling-structured-extraction.md) amends ADR-006. No SRS amendment needed; the SRS is frozen |
| 2 | `docker_compose_rag_services.md` and `rag_pipeline_service_map.md` describe an **eleven-phase RAG pipeline**; two phases exist | **Resolved 2026-09-02** — both moved to [`archive/`](archive/README.md). ADR-006 owns the pipeline scope |
| 3 | Both Compose files declare an **`ai-gateway`** service; ADR-010 and ADR-012 reject it | Open — removed by IR-58 |
| 4 | `backend_frontend_architecture_review.md` predates the verified review | **Resolved 2026-09-02** — moved to [`archive/`](archive/README.md); [`architecture-review/`](architecture-review/) supersedes it |
| 5 | `main` and `refactor/docker-service` carried different documentation sets | **Resolved 2026-09-02** — merged. The legacy per-module `software-requirements/M01-M08`, and the byte-identical `SRS (2).md` / `SDD (2).md` copies, were removed |
| 6 | **ADR-011**, [`mvp-validation/FRAMEWORK_DECISION.md`](mvp-validation/FRAMEWORK_DECISION.md) and [`mvp-validation/01-framework-selection.md`](mvp-validation/01-framework-selection.md) each state the evaluation-framework decision | Open — three statements of one decision. ADR-011 is authoritative; the other two should be reduced to the evaluation detail the ADR does not carry |
| 7 | The **SRS service table** lists no FastAPI gateway; [ADR-014](adr/014-ai-gateway-as-a-service.md) deploys one | **Moot 2026-09-03** — the SRS is frozen and is no longer an authority. ADR-014 stands alone |
| 8 | [`security/SECURITY.md`](security/SECURITY.md) §8 records external AI transmission as **UNCONFIRMED**; [ADR-015](adr/015-voyage-embedding-and-reranking.md) sends chunk text to Voyage | **Blocking** — ADR-015 is conditional on written KTTO/IERC sign-off. Synthetic and published data only until then |
| 9 | [`architecture-review/04-ai-rag-architecture.md`](architecture-review/04-ai-rag-architecture.md) and [`security/SECURITY.md`](security/SECURITY.md) §7 state `ai/` has no source directory | Stale — `ai/` exists. Both predate ADR-014 |

---

## Conventions

Every engineering document states, at the top: its purpose · what it owns · what it does **not** own · its authority · what it depends on · when to update it.

**No fact appears in two documents.** If it is needed in two places, one states it and the other links.

**File naming.** `SCREAMING_SNAKE.md` for a standalone named document (`SRS.md`, `TEST_PLAN.md`, `DEFINITION_OF_DONE.md`). `NN-kebab-case.md` for an ordered series (`architecture-review/`, `architecture-tasks/`, `mvp-validation/`, `ui-ux/`, `jira-sync/`, `adr/`). `kebab-case` for directories. No spaces, parentheses, or version suffixes in filenames.

*Baseline: `main`. Last reviewed: 2026-09-02.*
