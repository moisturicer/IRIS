# Archive

**Purpose.** Superseded documents retained because active documents cite them as evidence.
**Owns.** Nothing. No document here is authoritative for any subject.
**Update when.** A document is superseded and something still references it.

> **Nothing in this folder is current.** Each document below was superseded by a later, verified one. They are kept because deleting them would break citations in `architecture-review/` and in ADR-006 — and ADRs are immutable once accepted, so their evidence must remain readable.
>
> Do not use these to answer a question about how IRIS works. Follow the "Superseded by" column instead.

---

## Contents

| Document | Why it was superseded | Superseded by | Still cited from |
|---|---|---|---|
| [`backend_frontend_architecture_review.md`](backend_frontend_architecture_review.md) | Written against `feat/rag-service` before the verified audit. Seven of its nine defects and ten of its fifteen candidates were confirmed; the rest were revised or rejected against the real tree | [`../architecture-review/01-existing-review-validation.md`](../architecture-review/01-existing-review-validation.md) | `architecture-review/00`, `01` · `architecture-tasks/11` |
| [`rag_pipeline_service_map.md`](rag_pipeline_service_map.md) | Documents an eleven-phase RAG pipeline in the present tense. **Two phases exist** | [`../adr/006-minimum-rag-pipeline.md`](../adr/006-minimum-rag-pipeline.md) · [`../architecture-review/04-ai-rag-architecture.md`](../architecture-review/04-ai-rag-architecture.md) | ADR-006 · `architecture-review/01`, `04` · `architecture-tasks/11` |
| [`docker_compose_rag_services.md`](docker_compose_rag_services.md) | Specifies a ten-service topology justified by "100 concurrent RAG users" — a figure in no requirement document. Names build contexts and images that do not match either Compose file | [`../adr/010-deployment-topology.md`](../adr/010-deployment-topology.md) · [`../adr/012-ai-provider-abstraction-not-a-service.md`](../adr/012-ai-provider-abstraction-not-a-service.md) | `architecture-review/01`, `04` |
| [`architecture_documentation_reconciliation.md`](architecture_documentation_reconciliation.md) | Compared the documentation sets on `main` and `feat/rag-service` while they diverged. The branches have since been reconciled and this cleanup completed its recommendations | This folder, and [`../README.md`](../README.md) | — |

---

## Why these were not deleted

Three of the four are cited as **evidence** by documents that remain authoritative. ADR-006's context section quotes `rag_pipeline_service_map.md` directly, and an accepted ADR cannot be edited to remove the citation. `architecture-review/01-existing-review-validation.md` is a claim-by-claim verdict on `backend_frontend_architecture_review.md` and is unreadable without its subject.

The fourth records how the two documentation sets diverged, which is the reason this folder exists.
