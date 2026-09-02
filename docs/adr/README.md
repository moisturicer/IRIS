# Architecture Decision Records

Decisions that shape IRIS, with the reasoning that produced them and the alternatives that were rejected. An ADR exists so a decision is made once and can be revisited deliberately — not re-litigated by the next person to read the code.

**Status values:** `Proposed` · `Accepted` · `Superseded by ADR-XXX` · `Deprecated`

---

## Index

| ADR | Title | Status | Impact |
|---|---|---|---|
| [001](001-mvp-scope-boundary.md) | MVP scope boundary for Semester 2 | Accepted | Scope |
| [002](002-workflow-transition-table.md) | Workflow as a declarative transition table | Accepted | Architecture · Research · SaaS |
| [003](003-clearance-aware-resubmission.md) | Clearance-aware resubmission | Accepted | **Research contribution** |
| [004](004-restart-all-comparison-mode.md) | Restart-all as a configurable comparison policy | Accepted | **Research evaluation** |
| [005](005-instance-per-tenant.md) | Instance-per-tenant rather than pooled multi-tenancy | Accepted | SaaS · Security |
| [006](006-minimum-rag-pipeline.md) | Minimum RAG pipeline, no orchestration framework | **Superseded by 013** | Scope · Cost |
| [007](007-pgvector-vector-store.md) | pgvector as the vector store | Accepted | Architecture · Deployment |
| [008](008-ai-degradation-to-fts.md) | Graceful degradation to PostgreSQL FTS | Accepted | Reliability |
| [009](009-authorization-model.md) | Authorization model and `is_staff` semantics | Accepted | **Security** |
| [010](010-deployment-topology.md) | Five-service topology and interim VPS deployment | Accepted · **amended by 014** | Deployment |
| [011](011-evaluation-framework.md) | ISO 9241-11 as the evaluation spine | Accepted | Research |
| [012](012-ai-provider-abstraction-not-a-service.md) | AI provider abstraction in Django, not a separate service | **Superseded by 014** | Architecture · Security · Deployment |
| [013](013-chunk-level-rag-pipeline.md) | Chunk-level RAG pipeline with reranking | Accepted | Scope · Cost · Security |
| [014](014-ai-gateway-as-a-service.md) | The AI gateway is adopted as a deployed service | Accepted | Architecture · Security · Deployment |
| [015](015-voyage-embedding-and-reranking.md) | Voyage for embedding and reranking | Accepted, **conditional on governance sign-off** | Architecture · Security · Cost |

---

## Provenance

**ADRs 013–015 (2026-09-02) reverse the AI/RAG decisions in 006 and 012.** The review that produced 001–012 audited `refactor/docker-service`, where no part of the AI pipeline functioned. `feat/rag-service` implements pgvector, the extraction service and the gateway restructure, and the chunker is designed in [`../chunker_architecture.md`](../chunker_architecture.md). The superseded records are kept unedited: their cost and security arguments still hold, and 013's fallback *is* 006's pipeline.

ADRs 001–012 record the conclusions of a structured architecture review conducted 31 August – 1 September 2026, in three passes:

1. **`docs/architecture-review/`** — validation of the prior architecture review against the working tree, the SRS and the SDD.
2. **A structured design interview** (five rounds) that stress-tested every conclusion against the team's real capacity, the SaaS business model, and the thesis contribution.
3. **`docs/architecture-tasks/`** — the resulting implementation backlog.

The interview's reasoning is preserved here rather than in a separate transcript: each ADR's *Alternatives Considered* and *Decision Rationale* sections carry the arguments that were made and rejected. That is deliberate — a rejected alternative is only useful if the reason travels with it.

## Governing constraints

Every decision below was made against these, and several would be wrong without them:

| Constraint | Value |
|---|---|
| Team | 4 people |
| Capacity | 8 effective dev-hours/person/week (conservative) |
| Implementation budget | **~27 dev-days total** across the semester |
| Primary window | Weeks 4–7 (~16 dev-days) |
| Thesis contribution | Type-differentiated workflow with clearance-aware resubmission |
| RAG | Supporting capability, not the contribution |
| First customer | CIT-U, pilot in Weeks 11–12 |
| Product intent | Institutional SaaS/PaaS |

**The budget is the binding constraint.** Where a decision looks conservative, it is because ~27 dev-days does not fund the alternative — not because the alternative is wrong at a different scale. Each ADR states what would trigger revisiting it.

## Writing a new ADR

Copy the section structure from any existing record: Status · Context · Decision · Alternatives Considered · Decision Rationale · Consequences · MVP Impact · SaaS Impact · Security Impact · Deployment Impact · Research Impact · Related Requirements · Related Tasks.

Number sequentially. Never edit an accepted ADR's Decision — supersede it with a new one and mark the old `Superseded by ADR-XXX`. The history is the point.
