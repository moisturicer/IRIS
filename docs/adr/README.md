# Architecture Decision Records

Decisions that shape IRIS, with the reasoning that produced them and the alternatives that were rejected. An ADR exists so a decision is made once and can be revisited deliberately — not re-litigated by the next person to read the code.

**Status values:** `Proposed` · `Accepted` · `Superseded by ADR-XXX` · `Deprecated`

---

## Index

**Twenty active decisions.** Read these for "what does IRIS do today and why." **ADR-021 and ADR-022 are Accepted but not yet built**: they settle the MVP workflow (2026-09-15), and their implementation is IR-255. Until that lands, the code still runs the fixed pipeline they replace.

| ADR | Title | Status | Impact |
|---|---|---|---|
| [001](001-mvp-scope-boundary.md) | MVP scope boundary for Semester 2 | Accepted · **amended 4× (013, 016, 019, 020)** | Scope |
| [002](002-workflow-transition-table.md) | Workflow as a declarative transition table | Accepted · **amended 2026-09-09** · **amended by [021](021-reviewer-directed-routing.md)** | Architecture · Research · SaaS |
| [003](003-clearance-aware-resubmission.md) | Clearance-aware resubmission | Accepted | **Research contribution** |
| [004](004-restart-all-comparison-mode.md) | Restart-all as a configurable comparison policy | Accepted | **Research evaluation** |
| [005](005-instance-per-tenant.md) | Instance-per-tenant rather than pooled multi-tenancy | Accepted | SaaS · Security |
| [007](007-pgvector-vector-store.md) | pgvector as the vector store | Accepted | Architecture · Deployment |
| [008](008-ai-degradation-to-fts.md) | Graceful degradation to PostgreSQL FTS — no local model, ever | Accepted | Reliability |
| [009](009-authorization-model.md) | Authorization model and `is_staff` semantics | Accepted | **Security** |
| [010](010-deployment-topology.md) | Five-service topology and interim VPS deployment | Accepted · **amended by 014** | Deployment |
| [011](011-evaluation-framework.md) | ISO 9241-11 as the evaluation spine | Accepted · **amended 2026-09-10** | Research |
| [013](013-chunk-level-rag-pipeline.md) | Chunk-level RAG pipeline with reranking | Accepted · **amended 2026-09-04, 2026-09-08** | Scope · Cost · Security · **Research** |
| [014](014-ai-gateway-as-a-service.md) | The AI gateway is adopted as a deployed service, subject to five preconditions | Accepted · **completed by 017** | Architecture · Security · Deployment |
| [015](015-voyage-embedding-and-reranking.md) | Voyage for embedding and reranking, always — `voyage-context-4` | Accepted | Architecture · Security · Cost |
| [016](016-docling-structured-extraction.md) | Docling-serve restored as the extraction path | Accepted · **amended 2026-09-04 (twice)** | Architecture · Scope · **Research** |
| [017](017-asgi-deployment-for-gateway-streaming.md) | ASGI deployment so Django can call the gateway asynchronously | Accepted | Architecture · Deployment · Performance |
| [018](018-conditional-parallel-office-routing.md) | Conditional parallel-office routing | **Accepted** — 2026-09-07 · **partially superseded by [021](021-reviewer-directed-routing.md)** | Architecture · Research |
| [019](019-persisted-unified-conversation-history.md) | Persisted conversation history, unified across Ask IRIS and Paper Chat | Accepted | Architecture · **Research** |
| [020](020-per-record-assessment-brief.md) | The IRIS Assessment Brief — per-record decision support at intake | **Accepted** — 2026-09-10 | Scope · Security · **Research** |
| [021](021-reviewer-directed-routing.md) | Intake, specialist review, and reviewer-directed routing | **Accepted** — 2026-09-15 · not yet built (IR-255) | Architecture · Security · **Research** |
| [022](022-explicit-document-requests.md) | Explicit document requests, distinct from resubmission | **Accepted** — 2026-09-15 · not yet built (IR-262/263) | Architecture · Scope |
| [030](030-migrate-on-container-boot.md) | Compose containers migrate on boot, unconditionally | **Accepted** — 2026-09-21 | Deployment · Reliability |

**Numbering note:** ADR-018 was drafted on `main` as "016" while `feat/rag-service` (not yet merged into `main` at the time) already had its own ADR-016 (`docling-structured-extraction`). It was renumbered to 018 to avoid a collision once the branches reconciled, rather than reusing 016.

**Two superseded decisions, kept for the record — not for "what does IRIS do today."** This project's rule is to supersede an ADR rather than edit or delete it (see *Writing a new ADR* below), so these stay, but neither describes current behavior:

| ADR | Title | Status | Superseded by |
|---|---|---|---|
| [006](006-minimum-rag-pipeline.md) | Minimum RAG pipeline, no orchestration framework | Superseded | [013](013-chunk-level-rag-pipeline.md), amended by [016](016-docling-structured-extraction.md) |
| [012](012-ai-provider-abstraction-not-a-service.md) | AI provider abstraction in Django, not a separate service | Superseded | [014](014-ai-gateway-as-a-service.md) |

---

## Provenance

**The one-paragraph version of the AI-architecture back-and-forth**, so a reader doesn't have to open four documents to follow it: 006 said keep AI inside Django, no separate service. Someone built one anyway. 010 removed it from Compose (no source existed yet). The service then got built out for real, and 012 looked at what it actually was — unauthenticated, permissive CORS, a database driver implying a second permission path — and rejected deploying it, keeping only its provider-abstraction *design*. 014 reversed that **the same day**, judging the async/streaming case strong enough to accept the gateway anyway, but only under five preconditions that convert 012's objections into gates rather than dismissing them. 017 then closed the one precondition-adjacent gap 014 left open: Django's own deployment couldn't yet call anything asynchronously, which would have made the gateway's async benefit real on one side of the wire only. **Current state: the gateway is accepted, gated on five preconditions, none fully met yet — `apps/ai` calls the provider ports in-process until they are.**

**ADRs 013–016 reverse the AI/RAG decisions in 006 and 012.** ADR-016 (2026-09-03) closes the one point 013 left standing: ADR-006's incidental avoidance of Docling outlived its stated reason once 014 adopted the gateway. It was **amended 2026-09-04**, during IR-107, to drop the PyMuPDF fallback it originally retained — a flat-text fallback yields chunks with no regions, which is the loss the decision exists to prevent, so Docling-serve unavailability now fails and retries instead of degrading silently.

**ADRs 013–015 (2026-09-02) reverse the AI/RAG decisions in 006 and 012.** The review that produced 001–012 audited `refactor/docker-service`, where no part of the AI pipeline functioned. `feat/rag-service` implements pgvector, the extraction service and the gateway restructure, and the chunker is designed in [`../chunker_architecture.md`](../chunker_architecture.md). The superseded records are kept unedited: their cost and security arguments still hold, and 013's fallback *is* 006's pipeline.

**013 and 016 were amended again 2026-09-04, on the instruction of the project lead: RAG is reclassified as thesis-critical**, reversing both ADRs' §Research Impact claim that RAG was "a supporting capability, not the thesis contribution." `CLAUDE.md`'s Scope rule is corrected to match. Unaffected: what ADR-003/ADR-004's controlled comparison measures — that experiment is still of the clearance-aware resubmission workflow mechanism, not RAG.

**ADR-001's out-of-scope list has now been reversed four times**, and the Status line on ADR-001 carries the table. 013 took full-text chunking, 016 took Docling-serve, 019 took conversational RAG with history, and 020 took document summarization — the last two being the two halves of one exclusion line in ADR-013 §Decision, which 019 split deliberately rather than bundling. Each reversal draws on the same ~27 dev-day budget ADR-001 was costed against, so each is expected to name what it displaces; ADR-020 §Decision Rationale is explicit that four reversals is the point at which a scope boundary stops constraining anything. Read ADR-001's body together with that table, never alone.

**ADR-021 and ADR-022 (2026-09-15) settle the MVP workflow.** They are the first pair to change ADR-002's structure rather than extend it. Read them together with [`../workflow_routing_architecture.md`](../workflow_routing_architecture.md), which maps the current code onto the new model and holds the migration plan, the test migration plan and the Jira breakdown.

What 021 decides:

- The fixed office pipeline becomes reviewer-directed routing over concurrent assignments.
- **Intake & Triage is its own party**, distinct from RDCO, although RDCO staff run it.
- Specialist offices record findings; they never reject.
- `pipeline_status` stores only durable facts. Waiting states are derived.
- Proposals leave Discover.

Decision authority depends on record type. RDCO decides every Thesis/Research and Project. For a Proposal, **the Adviser or RDCO** decides and completes, and RDCO is not a mandatory gate.

What 022 decides: "please upload this document" becomes a request object, not a decline comment.

021 partially supersedes 018, including 018's rule that ITSO reviews Projects only.

**021 was drafted three times in one day, and one rule was withdrawn along the way.** The first draft merged intake into a single `rdco` party. The project lead rejected that, because it implies RDCO reviews a paper substantively before handing it to a specialist office. The second draft left two questions open. The project lead then settled both, and separately withdrew a draft instruction that every Proposal must reach RDCO.

Two questions are recorded as research and project-management considerations. **Neither reopens the workflow:**

- whether ad-hoc routing moves ADR-003's novelty argument into CMMN territory;
- what this work displaces from ADR-001's budget.

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
