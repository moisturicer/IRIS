# 13 — Jira Reconciliation

Checked against the live backlog: `citiris.atlassian.net`, project **IR**, 51 issues, 7 epics.

**Outcome: 51 issues → ~18 active**, of which ~9 are new work Jira does not currently contain.

| Action | Count |
|---|---|
| REWRITE — contradicts the SRS or already implemented | 8 |
| DEFER — Phase 2 | 9 |
| REOPEN — status is demonstrably false | 5 |
| CLOSE — delivered by this review | 2 |
| Unchanged | ~8 |
| **NEW — no Jira coverage at all** | **~30** |

---

## REWRITE

### `IR-9` — "Vector Store Ingestion" · Story · To Do

**Why:** specifies Qdrant. **The SRS specifies pgvector and explicitly excludes a separate vector database** (§456, §624). The ticket predates the May 2026 SRS revision.

> **[Backend]** Service function passing extracted text from the Celery worker into the embedding pipeline; retry on embedding-API failure.
> **[AI]** Generate vectors via the configured embedding provider (`R-02`). Store in `RecordEmbedding.embedding` as a pgvector `VectorField` with an HNSW index. **No chunking in MVP** — embed title and abstract only ([ADR-006](../adr/006-minimum-rag-pipeline.md)).
>
> **Supersedes** the Qdrant upsert approach. See SRS §456, §624 and [ADR-007](../adr/007-pgvector-vector-store.md).

→ `R-02`, `R-03` · blocked by `B-04`

### `IR-15` — "[AI] LangChain Chunking & Qdrant Upsert" · Subtask · To Do

**Why:** both named technologies are excluded — Qdrant by SRS §456/§624, LangChain by absence from every current requirement (one mention, in a change-history line).

**Retitle:** `[AI] Embedding Generation & pgvector Storage`

> * Generate vectors via the configured provider protocol (`R-02`).
> * Store in `RecordEmbedding` using a pgvector `VectorField`; HNSW index in a migration.
> * Remove all `pickle` usage.
> * **No LangChain** — see [ADR-006](../adr/006-minimum-rag-pipeline.md). **Chunking deferred** to Phase 2.

→ `R-03` · blocked by `B-04`

### `IR-35` — "[AI] Qdrant Retrieval, Cohere Reranking & LLM Orchestration" · Subtask · To Do

**Why:** all three are unsupported by the SRS. **Cohere has zero SRS mentions**, and `docs/rag_pipeline_service_map.md` itself notes reranking *"was not carried forward into the formal SRS/SDD."*

**Retitle:** `[AI] pgvector Retrieval & Grounded Answer Generation`

> * Cosine-similarity retrieval via pgvector's `<=>` operator with `LIMIT k`.
> * **Filter retrieval by record visibility** — a user must never receive a citation to a record they cannot see (`B-05`, `S-02`).
> * Build the prompt explicitly; call the LLM via the provider protocol.
> * Return `{answer, citations}`.
> * **Timeboxed to 3 dev-days ending Week 6**; falls back to search-only.
>
> **Descoped:** Cohere reranking. **Superseded:** Qdrant, LangChain.

→ `R-04`

### `IR-41` — "[Backend] State Transition API & Validation Matrix" · Subtask · To Do

**Why:** partially implemented. `reviews/services.py` already contains 11 guarded transitions and the `RecordClearance` model. As written, the ticket risks a second parallel implementation.

> * **Note:** `reviews/services.py` already implements 11 guarded transitions. **Do not rebuild it.**
> * Consolidate the **7 transitions outside it** (`records/views.py:135,208,254,334,690`; `records/services.py:33`) into one declarative table.
> * Add `apply(record, event, actor)` wrapping each transition in `transaction.atomic()`.
> * Add a configurable **restart-all resubmission policy** for research comparison ([ADR-004](../adr/004-restart-all-comparison-mode.md)).
> * Excel import becomes a declared `legacy_import` edge.
> * Table-driven tests across both policies.

→ `W-01`, `W-02`, `W-03`, `W-06`, `T-03` · blocked by `F-02`, `T-01` · **thesis-critical**

### `IR-39` — "[Frontend] Build Data Table Component" · Subtask · To Do

**Why:** the component **already exists**. `components/shared/DataTable.tsx` (124 lines) wraps `@tanstack/react-table` and includes pagination at `:96-118`.

**Retitle:** `[Frontend] Extend the Existing DataTable`

> * **Note:** `DataTable.tsx` exists with pagination. Extend it; do not rebuild.
> * Add column sorting (closes the TODO at `DataTable.tsx:3`) and inline row actions.
> * **Deferred to Phase 2** — broad adoption across feature pages is not MVP scope.

→ Phase 2

### `IR-7` — "[Security] Implement Django API Permission Decorators" · Subtask · **In Review**

**Why:** status is wrong and the second half is incomplete. The permission **classes exist** (eleven in `core/permissions.py`), but *"decorate all sensitive backend API views"* did not happen — **twelve endpoints have no object-level check**.

> * **Note:** `IsStudent`, `IsReviewer`, `IsAdmin` and eight more already exist. Five are referenced nowhere.
> * Apply `IsOwnerOrStaff` to the **6 unprotected `documents` endpoints** (`S-03`).
> * Apply record visibility to `RecordViewSet.retrieve`, currently unfiltered (`S-02`).
> * Replace the 5 hand-written owner-or-staff checks.
> * Remove the `is_django_staff` blanket bypass (`S-05`).
> * `apps/storage`'s 6 unprotected endpoints are resolved by **deleting the app** (`SC-01`).
>
> **Move to In Progress** — NFR-S4 is not satisfied.

→ `S-02`, `S-03`, `S-05`, `SC-01`, `T-02` · **status: In Review → In Progress**

### `IR-12` — "[Backend] Document Submission Endpoint & Celery Setup" · Subtask · **Done**

**Why:** marked Done; two of three stated tasks do not work.

- ✅ `/api/documents/submit/` exists
- ❌ *"Configure a Celery worker and Redis queue"* — no task routing; workers consume `default`/`extraction`/`embedding` while tasks publish to `celery`. **No worker consumes the queue tasks publish to**
- ❌ *"Background task to execute asynchronous extraction"* — imports three libraries absent from requirements, so it always fails
- ❌ No ownership check — any user can upload into any record

> Reopen. Add `CELERY_TASK_ROUTES` (`B-03`) · add `pymupdf` (`R-01`) · add an ownership check (`S-03`). **Acceptance: an uploaded PDF reaches `PdfExtraction.status == "done"` end to end.**

→ `B-03`, `R-01`, `S-03` · **status: Done → In Progress**

### `IR-4` — "[Security] Audit JWT Configuration & CORS" · Subtask · **In Review**

**Why:** the audit missed four findings.

- ✅ JWT rotation and blacklisting correctly configured
- ❌ **NFR-S2 not met** — 30-minute inactivity expiry does not occur (`S-06`)
- ❌ `CORS_ALLOW_ALL_ORIGINS` with `CORS_ALLOW_CREDENTIALS` in development (`S-04`)
- ❌ Access token persists in `localStorage` after logout (`FE-01`)
- ❌ No refresh deduplication against `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION` — concurrent 401s force a hard logout

> Reopen with the four findings as acceptance criteria.

→ `S-04`, `S-06`, `FE-01` · **status: In Review → In Progress**

---

## DEFER — Phase 2

| Issue | Reason |
|---|---|
| `IR-19`, `IR-33`, `IR-34` — conversational RAG, chat UI, conversation CRUD | Single-shot Q&A satisfies FR-M4-01's core claim ([ADR-006](../adr/006-minimum-rag-pipeline.md)). 840 lines of chat UI exist unrouted and are removed by `FE-03` |
| `IR-20`, `IR-36`, `IR-37`, `IR-38` — summarization | Separate LLM feature, UI and cost line; outside the pilot workflow |
| `IR-25`, `IR-48`, `IR-49` — KPI dashboard | **Already Phase 2 in SRS §31.** Weeks 11–12 analytics come from `W-04`'s audit export instead |
| `IR-10`, `IR-16`, `IR-17`, `IR-18` — download requests, watermarking | Not in the pilot workflow. `B-02` fixes the code so it imports; `IR-18`'s `WatermarkService` is a forensic subsystem |
| `IR-21`, `IR-39`, `IR-40` — data-table dashboard | `DataTable` exists; broad adoption is Phase 2 |

---

## REOPEN — status is demonstrably false

| Issue | Current | Should be | Evidence |
|---|---|---|---|
| `IR-3` "[Backend] Build Authentication API Endpoints" | **Done** | In Progress | Endpoints exist, but `config/urls.py` cannot load — `records/views.py` raises `NameError` at import, so **no endpoint responds** (`B-01`) |
| `IR-12` | **Done** | In Progress | See REWRITE |
| `IR-2` "[Frontend] Build Login UI & Axios Interceptors" | In Review | In Progress | The refresh interceptor never calls `setTokens`, writes to `localStorage` nothing reads, and has no deduplication (`FE-01`) |
| `IR-4` | In Review | In Progress | See REWRITE |
| `IR-7` | In Review | In Progress | See REWRITE |

---

## CLOSE — delivered

| Issue | Evidence |
|---|---|
| `IR-50` "Architecture Refactoring Validation & Task Breakdown" | All four acceptance criteria met by `docs/architecture-review/` and `docs/architecture-tasks/`. No production code changed |
| `IR-51` "Architecture Grill-Me & MVP Decision Review" | All six met: findings documented; decision-required items in `docs/adr/`; MVP go/no-go in `10-mvp-validation.md`; framework evaluation in the ADRs; tasks under `docs/`; no production code changed |

---

## NEW — no Jira coverage whatsoever

**Jira holds 51 issues and not one covers testing, CI, or any of the five defects that stop IRIS running.**

| Area | Tasks | Severity |
|---|---|---|
| **Boot blockers** | `B-01`, `B-02`, `D-01`, `D-02` | 4 MVP Blockers |
| **Security** | `S-01`…`S-07`, `SC-01` | 4 MVP Blockers |
| **Testing** | `T-01`…`T-05` | 1 MVP Blocker |
| **CI/CD** | `F-01` | 1 MVP Blocker |
| **Deployment** | `D-03`…`D-05` | Interim deployment, backups, observability |
| **Workflow / thesis** | `W-01`…`W-06` | **The contribution** |
| **SaaS** | `SA-01`…`SA-04` | Tenancy, onboarding, export |
| **Validation** | `V-01`…`V-15` | Every NFR |
| **Documentation** | `DOC-01`…`DOC-06`, `F-03` | 7 dead links; 4 promised documents missing |

---

## Suggested epic mapping

| Epic | New tasks |
|---|---|
| `IR-26` Epic 1: User Management & Auth | `S-06`, `FE-01`, `FE-05` |
| `IR-27` Epic 2: Document Ingestion & RAG | `R-01`…`R-06`, `B-03`, `B-04` |
| `IR-28` Epic 3: AI Search & Conversation | *(defer — Phase 2)* |
| `IR-29` Epic 4: Analysis & Summarization | *(defer — Phase 2)* |
| `IR-30` Epic 5: Workflow Engine | `W-01`…`W-06`, `F-02`, `B-05` |
| `IR-31` Epic 6: Compliance & Audit | `S-07`, `W-04` |
| `IR-32` Epic 7: Analytics Dashboard | *(defer — Phase 2)* |
| **NEW — Epic 8: Platform Stability & Security** | `B-01`, `B-02`, `S-01`…`S-05`, `SC-01` |
| **NEW — Epic 9: Engineering Practice** | `F-01`, `T-01`…`T-05`, `FE-04`, `DOC-01`…`DOC-06` |
| **NEW — Epic 10: Deployment & Operations** | `D-01`…`D-05`, `SA-01`…`SA-04` |
| **NEW — Epic 11: MVP Validation & Research Evaluation** | `V-01`…`V-15` |

Architecture decisions live in `docs/adr/`, not Jira — each blocks work across several epics.

---

## Sprint suggestion

| Weeks | Theme | Tasks | Outcome |
|---|---|---|---|
| **1–2** | Boot, secure, deploy | `B-01` `B-02` `D-01` `D-02` `S-01` `S-02` `S-03` `S-04` `SC-01` `D-03` · `DOC-01` | An accessible MVP that does not leak. Validation (`V-01`, `V-02`, `V-03`) runs in parallel — non-coding work for two team members |
| **3** | Requirements refactor | `F-03`, `DOC-02` | SRS/SDD match reality; every cut formalised |
| **4–5** | Foundation + workflow | `F-02` `T-01` `F-01` `B-03` `B-04` `S-05` `FE-01` `FE-02` · `T-03` characterisation tests | CI green; enums in place; tests before the risky refactor |
| **6–7** | **Contribution + RAG** | `W-01` `W-02` `W-03` · `R-01`…`R-06` **timeboxed** | The thesis contribution built and configurable; RAG working or degraded to search |
| **8–9** | Test and harden | `T-02` `V-06`…`V-13` · `B-06`…`B-09` `FE-03`…`FE-05` `S-06` `S-07` `D-05` | NFR evidence gathered; defects ticketed |
| **10** | Instrument and prepare | **`W-04`** · `D-04` `V-04` `SA-02` | **Research instrumentation live before the pilot.** Backup drill done. Scenarios and evaluation instance ready |
| **11–12** | Pilot and evaluate | `V-05` `V-15` | Usage, payment and evaluation evidence |
| **13–15** | Research and commercial | `DOC-04`…`DOC-06` `SA-01` `SA-03` `SA-04` | Paper, traceability, commercial artefacts |

**The Week 10 boundary is hard.** `W-04` must be live before Week 11 or there is no research data, and the system effectively freezes once a customer is using it.
