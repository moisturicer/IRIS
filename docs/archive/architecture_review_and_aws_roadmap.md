# Architecture Review & AWS Production Roadmap

Audit of the current codebase against the SRS/SDD, a prioritized cleanup/removal list, a missing-functionality backlog, and a production-grade AWS architecture (with cost analysis) for deploying IRIS's three services — `backend/`, `ai/`, `frontend/` — to AWS.

Scope note: this document is an architecture review and roadmap, not a change log. It reflects the state of the `feat/rag-service` branch at the time of writing, where the AI gateway is mid-refactor into a hexagonal/ports-and-adapters shape.

---

## Context

IRIS is moving from local docker-compose development toward an AWS production deployment. This review answers three questions raised during planning: what's safe to delete, what functionality is missing relative to the SRS, and what a production-grade AWS + RAG architecture should look like — including cost.

The headline finding: **the AI gateway does not currently boot.** `ai/api/chat.py` imports `ChatService`/`EmbeddingService` from `ai/services/`, which is an empty package. The frontend already has a full chat UI (`AIHubPage.tsx`, `RAGChatPage.tsx`) wired to endpoints that don't exist yet in the shape it expects.

Decisions this roadmap is built around:
- **Priority order**: fix the RAG gateway first, then cleanup, then the AWS migration.
- **AWS compute**: ECS Fargate (not EKS/App Runner) for the containerized services.
- **LLM/embedding strategy**: model-agnostic. Local LLMs first (self-hosted), but must be swappable to any third-party provider via config, not code changes — this reinforces the existing `domain/ports.py` ports-and-adapters seam rather than replacing it.
- **Scale target**: single university, modest load (hundreds of concurrent users at peak, thousands of documents) — optimize for low idle cost, not headroom for massive scale.

---

## Current-State Summary

### Per-module status (SRS M01–M08 vs. code)

| Module | Status | Notes |
|---|---|---|
| M01 Backend/Responsive UI | Implemented | JWT auth, axes lockout, DRF throttling all real |
| M02 Document Lifecycle | Partial | Submission/versioning/download requests work; **Department Templates / Office Checklists (FR-M2-01) have zero code** — only legacy flat `UploadSlot` model exists |
| M03 Semantic Indexing | Mostly implemented | Extraction + FTS + embedding job queue are real; embedding call target is broken (see Phase 1) |
| M04 RAG AI Services | **Broken/stub** | `apps/ai/services/*` are one-line stub classes; `ai/` FastAPI gateway has broken imports; frontend has no working backend behind its chat UI |
| M05 Hierarchical Submission Workflow | Implemented | More mature than SRS "draft" label suggests — `PIPELINE_STATUS`, `RecordClearance`, routing logic all real |
| M06 Security & Auth | Implemented | Lockout, RoleRequest, audit events, JWT blacklist all present |
| M07 KPI Dashboard | Partial | Basic dashboards exist; analytics endpoint is an honest documented 501 stub; **Report Generation/Export (FR-M7-02) has no code at all** |
| M08 Admin Portal | Partial | User/role/session/audit admin UI all present; **audit Excel export and all RAG admin config (FR-M8-03) are missing** |

### Dead/redundant code confirmed

- `backend/apps/ai/views/` — an entire orphaned package (`chatbot.py`, `summarize.py`, all `pass`), never imported anywhere, name-collides with the real `apps/ai/views.py` in the same directory.
- `backend/apps/ai/services/*.py` (8 files) — all one-line stub classes; real RAG logic belongs in `ai/` gateway, not here.
- `backend/apps/ai/services/pdf_extractor.py` — dead stub whose class name duplicates the real, working `backend/apps/documents/services/pdf_extractor.py`.
- `backend/apps/storage/models.py:62-71` — `LegacyFolder`, `managed=False`, docstring literally says "DO NOT use in new code," has an unactioned TODO to migrate and delete.
- `backend/apps/records/views_dashboard.py:60-83` — large commented-out implementation sketch, dead.
- `backend/requirements/base.txt` — `pgvector` pinned twice with conflicting versions (`>=0.3` and `>=0.2.4`); stray abandoned-migration comments addressed to "AI engineer."
- `apps/reviews/migrations/0002_recordauthpin_expires_at.py` immediately reverted by `0003_remove_recordauthpin_expires_at.py` — churn, low priority to fix.
- `docs/README.md` references `SECURITY.md`, `SDLC_PROCESS.md`, `TEST_PLAN.md`, `DEVELOPMENT_GUIDE.md`, `SOFTWARE_ENGINEERING_PLAN.md` — **none of these files exist.** Also references root-level SRS/SDD PDFs that don't exist; actual files are oddly named `docs/software-requirements/SRS (2).md` / `docs/software-design/SDD (2).md`.

### Security/consistency gaps (not dead code, but load-bearing)

- `backend/apps/documents/views.py` (lines 226, 302, 336, 378) repeats an inline `is_staff_user = get_role_name(...) in STAFF_ROLES or request.user.is_staff` four times instead of using `core.permissions.IsStaff`/`is_django_staff()` — the latter also checks `is_superuser`, so the ad-hoc version is subtly wrong.
- `backend/apps/storage/views.py` uses bare `IsAuthenticated` on all folder/file CRUD and downloads — **no ownership or role check at all**, despite `core/permissions.py` providing `IsOwnerOrStaff` for exactly this. This is a real access-control gap, not just a style issue.
- **Zero test files exist anywhere in `backend/apps/`** — confirmed across all 8 apps.

### Infra state

- No IaC, no CI/CD of any kind exists (no Terraform/CDK/CloudFormation, no `.github/workflows`).
- `docker-compose.yml` is dev-only throughout: `backend`/celery services run `manage.py runserver`/bind-mounted source instead of the production `Dockerfile` (which itself correctly builds gunicorn + non-root); `frontend` runs a raw `node:20-alpine` + Vite dev server, ignoring the multi-stage Nginx `frontend/Dockerfile` that already exists and is production-appropriate; Postgres/Redis ports are published to the host with plaintext credentials in a tracked file (dev-only, not a real secret leak — `.env` files are correctly gitignored and unpopulated in git).
- `ai/Dockerfile` is not production-ready: runs as root, no HEALTHCHECK baked into the image, unpinned pip installs, and a likely import-path mismatch (`CMD ["uvicorn", "main:app"]` vs. `ai/main.py`'s `from ai.api.chat import ...` absolute-package import).

---

## Phase 1 — Make the RAG gateway actually work

Goal: complete `ai/` to match its own documented design in `docs/rag_pipeline_service_map.md`, keep the ports-and-adapters seam (local-first, swappable), and fix the integration bug that breaks Phase 5 of the pipeline.

**Domain layer** (`ai/domain/ports.py`)
- Keep existing `LLMProvider`/`EmbeddingProvider` ABCs.
- Add a `RerankerProvider` ABC (optional pluggable seam — SDD doesn't require reranking, but since a `CohereReranker` stub already exists in the Django app and the adapter pattern is already the house style, scaffold it as a default no-op adapter now rather than bolting it on later).

**Infrastructure layer** (`ai/infrastructure/`)
- `local_adapter.py`: replace the hardcoded mock string / commented-out call with a real implementation calling an OpenAI-compatible local inference server (Ollama or vLLM) over HTTP — this is the *default* provider per the local-first decision.
- `openai_adapter.py`: keep as-is (already real), it becomes the "swap to third-party" path.
- `persistence/` (currently an empty directory): implement the asyncpg connection pool + the pgvector retrieval query (`ORDER BY embedding <=> q_vec LIMIT K`) here — this is Phase 6–7 of the documented pipeline and currently has zero code anywhere in the repo.
- `dependencies.py`: extend the existing provider factory to also wire the retrieval repository and (once added) the reranker.
- Fix `ai/api/schemas.py`: remove the Django imports (`from django.db.models import TextChoices` etc. — Django isn't even in `ai/requirements.txt`, so this is a guaranteed `ImportError`); define clean Pydantic schemas for `AskRequest/AskResponse`, `SearchRequest/SearchResponse`, `EmbedRequest/EmbedResponse`, `SummarizeRequest/SummarizeResponse`.

**Service layer** (`ai/services/` — currently empty except `__init__.py`)
- `embedding_service.py`: batch-embed text chunks (used by `/embed`) and single-embed a query (used by `/ask`, `/search`).
- `retrieval_service.py`: query encoding + pgvector top-K retrieval, calling the new `persistence/` repository.
- `chat_service.py`: orchestrates retrieve → (optional rerank) → prompt augmentation (Phase 9, pure string building) → LLM call (Phase 10).
- `summarization_service.py`: Phase 11 — Redis-cache-first summarization, matching the caching behavior already documented.

**API layer** (`ai/api/`)
- Split the single `chat.py` into `ask.py`, `search.py`, `embed.py`, `summarize.py` to match what `docs/rag_pipeline_service_map.md` already documents as the target route layout (the doc is correct — the code just never caught up to it).
- Mount all four routers in `ai/main.py`.

**Fix the Phase 5 integration bug**: `backend/apps/ai/tasks.py:23` calls `POST /api/v1/ai/internal/embed/`, but no such path exists even after the rebuild above unless it's added. Pick one canonical embed path (recommended: a single `/api/v1/ai/embed` used both for the internal Celery call and any external/admin-triggered embed, dropping the invented `/internal/` prefix) and align both sides.

**Dockerfile fixes** (`ai/Dockerfile`): pin all dependency versions, add a non-root `USER`, add a `HEALTHCHECK`, and fix the CMD/import-path mismatch so `ai.main:app` resolves the same way in the container as it does locally.

**Verification**: `docker-compose up ai-gateway`, seed one record with an embedding, `curl -X POST /api/v1/ai/ask` and confirm a grounded answer with citations comes back through the local adapter; then flip `LLM_PROVIDER=openai` in `ai/.env` with no code change and re-run the same request to prove the adapter swap works end to end — the concrete test of "model-agnostic."

---

## Phase 2 — Cleanup & removals

1. Delete `backend/apps/ai/views/` (the orphaned package) entirely.
2. Delete all 8 stub files under `backend/apps/ai/services/`.
3. Write the data migration for `backend/apps/storage/models.py` `LegacyFolder`, then drop the model — the TODO already documents this, it just needs doing.
4. Refactor the 4 repeated inline `is_staff_user = ...` expressions in `backend/apps/documents/views.py` to use `core.permissions.IsStaff` / `is_django_staff()`.
5. **Security fix**: add `IsOwnerOrStaff`/`IsStaff` permission classes to `backend/apps/storage/views.py` — currently the biggest concrete gap found in this review.
6. Delete the dead commented-out block in `backend/apps/records/views_dashboard.py:60-83`.
7. Fix the duplicate/conflicting `pgvector` version pins in `backend/requirements/base.txt`; remove the stray abandoned-migration comments; add `opendataloader_pdf` (used in code, missing from requirements) or confirm it's been superseded by Docling and remove the import instead.
8. Fix `docs/README.md`'s index to stop pointing at files that don't exist — either create minimal versions of `SECURITY.md`/`SDLC_PROCESS.md`/etc. or remove the dead links; rename the oddly-named `SRS (2).md`/`SDD (2).md`.
9. Add a baseline test suite: `pytest-django` + `factory-boy` (already a TODO in `requirements/development.txt`) starting with `accounts` (auth/permissions) and `records` (the core pipeline) — zero coverage today across all 8 apps is the single biggest risk to doing Phases 1/3/AWS-migration safely.

`backend/apps/storage/` vs `backend/apps/documents/` is **not** recommended for removal/merging — they serve genuinely different domain purposes (general-purpose personal file browser vs. per-record attachments), and merging would concentrate rather than reduce complexity. The real problem there is the missing permission check (item 5), not duplication.

---

## Phase 3 — Missing functionality (prioritized backlog)

1. **Department Templates / Office Checklists** (FR-M2-01) — highest priority; `docs/document_requirements_architecture.md` already specifies the target three-layer model, current code only has the flat legacy `UploadSlot`. Blocks correct document-requirement enforcement per department.
2. **RAG admin configuration** (FR-M8-03) — a `RAGConfiguration` singleton + admin UI to control chunking strategy, top-K, provider selection, etc. without redeploying. Natural companion to the Phase 1 ports/adapters work.
3. **Audit log Excel export** (FR-M8-02) — no code exists; straightforward addition to `backend/apps/audit/views.py` alongside the pattern already used for records' `pyexcel` bulk import.
4. **KPI report generation/export** (FR-M7-02) — no backend view/serializer and no frontend page exist at all; scope this properly once M07's "draft/unstable" SRS status is resolved, per the caution already noted about that module.

---

## AWS Cost Analysis (single-university scale, us-east-1 on-demand list prices)

Estimates only — actual cost depends on real traffic/document volume; treat as planning-order-of-magnitude, not a quote. All Fargate/RDS/ElastiCache prices assume on-demand; Savings Plans / Reserved Instances typically cut 20–50% once usage is predictable (worth revisiting after ~2 months of real usage data).

| Component | Sizing | Est. monthly cost |
|---|---|---|
| NAT Gateway | 1 gateway + modest data processing | ~$35–55 |
| Application Load Balancer | base hourly + low LCU usage | ~$20–30 |
| ECS Fargate — `backend` | 2 tasks × 0.5 vCPU / 1GB | ~$36 |
| ECS Fargate — `ai-gateway` | 2 tasks × 0.5 vCPU / 1GB | ~$36 |
| ECS Fargate — `celery-default` | 1 task × 0.25 vCPU / 0.5GB | ~$9 |
| ECS Fargate — `celery-extraction` | 1 task × 0.5 vCPU / 1GB | ~$18 |
| ECS Fargate — `celery-embedding` | 1 task × 0.5 vCPU / 1GB | ~$18 |
| ECS Fargate — `celery-beat` | 1 task × 0.25 vCPU / 0.5GB (singleton) | ~$9 |
| ECS Fargate — `docling-serve` | 1 task × 1 vCPU / 4GB | ~$42 |
| **Fargate subtotal** | | **~$168** |
| RDS PostgreSQL (pgvector) | `db.t4g.medium`, single-AZ, 100GB gp3 | ~$70–80 |
| ElastiCache Redis | `cache.t4g.micro`, single node | ~$12 |
| S3 (documents + frontend static) | few hundred GB, modest requests | ~$10–20 |
| CloudFront | modest traffic | ~$5–15 |
| ECR | image storage | ~$2–5 |
| Secrets Manager | ~5 secrets | ~$2 |
| CloudWatch Logs + Container Insights | modest retention | ~$10–20 |
| Route 53 | 1 hosted zone + queries | ~$1 |
| Data transfer out (misc.) | | ~$10–30 |
| **Baseline infra subtotal (no local-LLM GPU lane)** | | **~$350–450/mo** |

**Local LLM GPU lane** (the local-first decision's main cost lever — sized separately since it depends entirely on usage pattern):

| Pattern | Instance | Est. monthly cost |
|---|---|---|
| Always-on 24/7 | `g5.xlarge` on-demand | +~$730 |
| Always-on 24/7 (cheaper GPU) | `g4dn.xlarge` on-demand | +~$385 |
| Scheduled ~8h/day (business hours) | `g4dn.xlarge` on-demand | +~$125 |
| Scale-on-demand via queue depth, spot pricing | `g4dn.xlarge` spot, ~8h/day equivalent | +~$35–50 |

**Total estimated range**:
- Skip local GPU lane entirely at launch, use the OpenAI adapter only (pay-per-token, separate from AWS bill): **~$350–450/mo** AWS infra + OpenAI usage cost.
- Local-first with scheduled/spot GPU lane (recommended v1 given "modest, bursty" load): **~$400–500/mo**.
- Local-first with an always-on GPU lane: **~$750–1,200/mo** — only justify this once query volume is high enough that scale-to-zero cold-starts become a real UX problem.

Recommendation: launch with the scale-on-demand/spot GPU pattern (or skip the GPU lane and default to the OpenAI adapter for the first weeks) — the ports/adapters design means switching the default provider later is a config change, not a re-architecture, so there's no cost to deferring the GPU investment until real usage data justifies it.

---

## AWS Production Architecture (ECS Fargate, single-university scale)

**Networking**: one VPC, 2 AZs. Public subnets hold the ALB and a NAT Gateway; private subnets hold all ECS tasks, RDS, and ElastiCache.

**Compute — ECS Fargate cluster**:
- `backend` service (gunicorn, existing Dockerfile already correct) behind the ALB at `/api/*`, 2 tasks min for HA, autoscale on CPU.
- `ai-gateway` service behind the ALB at `/ai/*` (or a separate subdomain to simplify CORS), 2 tasks, autoscale on CPU/request count.
- `celery-default` / `celery-extraction` / `celery-embedding` — one Fargate service each, scaled on queue depth, no ALB attached.
- `celery-beat` — single Fargate task, min=max=1 (must stay a singleton); consider replacing with EventBridge Scheduler if drift/duplication ever becomes a problem.
- `docling-serve` — Fargate task, memory-heavy (4GB+), CPU-only is fine at this scale.
- **Local LLM inference lane (the one deliberate exception to pure Fargate)**: Fargate has no GPU support, and local-first LLMs need to actually be viable, not just a fallback. Run the self-hosted model (Ollama/vLLM, OpenAI-compatible endpoint) on an ECS **EC2** launch-type service or a small ASG of GPU instances (g4dn.xlarge/g5.xlarge), reached by the `ai-gateway`'s `LocalLLMProvider` adapter over the private network via Cloud Map service discovery. **This is the single biggest cost/ops lever in the whole architecture** — a 24/7 g5.xlarge runs ~$700+/mo; for "modest, bursty" university load, scale it to zero outside active hours or scale-on-queue-depth rather than running it always-on. A CPU-only quantized-model fallback is a valid cheaper v1 if GPU cost isn't justified yet — the ports/adapter design makes this a pure infra decision with zero application code change either way.

**Data**:
- RDS PostgreSQL (not Aurora — not justified at this scale) with the `pgvector` extension, `db.t4g.medium`/`db.r6g.large` depending on document volume; single-AZ acceptable to launch, enable Multi-AZ once budget allows.
- ElastiCache Redis, single small node, serving as Celery broker/result backend and the summarization cache (Phase 11).
- S3: one bucket for document/media storage (backend already has `django-storages[s3]` installed, just needs `production.py`'s TODO'd S3 config filled in), one bucket for the built frontend static assets.

**Frontend**: build the SPA and serve via **S3 + CloudFront**, not a Fargate/Nginx container — cheaper, no server to patch. The existing `frontend/Dockerfile` (multi-stage → Nginx) is unused by dev compose today and becomes unnecessary in this architecture too (keep it only if on-prem/local-parity hosting is ever needed).

**CI/CD**: GitHub Actions — build/test → push to ECR → `aws ecs update-service --force-new-deployment` (or a Terraform-driven deploy). Run `manage.py migrate` as a one-off ECS task in the pipeline, not baked into container startup.

**IaC**: none exists today — start a single Terraform root module covering VPC, ECS cluster + services, RDS, ElastiCache, S3, CloudFront, IAM roles, Secrets Manager. This is new work, not a migration of existing config.

**Secrets/config**: AWS Secrets Manager for `SECRET_KEY`, DB credentials, and any third-party API keys, injected via the ECS task definition's `secrets` block (never plaintext env vars); Parameter Store for non-secret config like `LLM_PROVIDER=local`.

**Observability**: CloudWatch Logs + Container Insights on every task; wire up Sentry (already installed, currently has an unfilled TODO in `production.py`) via a DSN pulled from Secrets Manager; alarms on ALB 5xx rate, ECS CPU/memory, RDS CPU/storage, and Celery queue depth.

---

## RAG Architecture (target end state)

The documented 11-phase pipeline in `docs/rag_pipeline_service_map.md` is architecturally sound and does not need redesigning — it needs the code to catch up to it (Phase 1 above) and a home on the AWS compute above:

| Phase | What | Where (after Phase 1 + AWS) |
|---|---|---|
| 1 | PDF upload | `backend` Fargate service |
| 2–3 | Docling extraction + cleaning | `celery-extraction` Fargate → `docling` Fargate |
| 4 | FTS indexing | `backend`, synchronous Django signal |
| 5 | Embedding generation | `celery-embedding` Fargate → `ai-gateway` (embed route, fixed) |
| 6–7 | Query encoding + pgvector retrieval | `ai-gateway`, new `persistence/` module → RDS |
| 8 | Reranking (optional, pluggable) | `ai-gateway`, new `RerankerProvider` port, no-op by default |
| 9–10 | Prompt augmentation + LLM answer | `ai-gateway` → local GPU lane (default) or third-party adapter (swappable) |
| 11 | Summarization | `ai-gateway` → ElastiCache-backed cache |

The model-agnostic requirement is satisfied entirely by the existing `domain/ports.py` seam: `LLMProvider`/`EmbeddingProvider` (and the new `RerankerProvider`) are the only contract the rest of the system depends on. `local_adapter.py` (Ollama/vLLM) ships as the default; `openai_adapter.py` already exists as the first swappable alternative; adding Anthropic/Bedrock/any other provider later is a new adapter file plus one factory branch in `dependencies.py` — no route, service, or domain code changes required. This is the concrete mechanism behind "switch to any third-party provider."

---

## Verification

- **Phase 1**: `docker-compose up ai-gateway db redis`; seed a record with an embedding; `curl -X POST localhost:8001/api/v1/ai/ask -d '{"question": "..."}'` → expect a grounded answer with citations. Re-run with `LLM_PROVIDER` flipped between `local` and `openai` with no code change to prove the adapter seam works.
- **Phase 2**: grep for any remaining references to deleted modules (`apps.ai.views.chatbot`, `apps.ai.services.pdf_extractor`, etc.) — expect zero hits; run the new baseline test suite; manually re-test `storage/` endpoints as a non-owner, non-staff user and confirm 403 where it previously returned 200.
- **AWS**: `terraform plan`/`apply` against a sandbox account; deploy to a staging environment; run the same `/ask` smoke test from Phase 1 through the public ALB/CloudFront URL end to end.
