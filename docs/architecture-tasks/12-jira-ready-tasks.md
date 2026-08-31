# 12 — Jira Actions & Task Matrix

Checked against the **live backlog**: `citiris.atlassian.net`, project **IR**, 51 issues, 7 epics, read on 2026-08-31.

---

## Part 1 — Actions on existing Jira issues

### REWRITE EXISTING JIRA TASK (8)

---

#### `IR-9` — "Vector Store Ingestion" · Story · To Do

**Why:** specifies Qdrant. **The SRS specifies pgvector and explicitly excludes a separate vector database service** (§456, §624). The ticket predates the SRS revision.

**Rewrite the "Atomic Domain Tasks" to:**

> **[Backend]** Create a service function passing extracted text from the Celery worker into the embedding pipeline; handle embedding-API failure with retries.
> **[AI]** Chunk the document with an explicit `chunk_text()` function (no LangChain — see ADR *RAG orchestration*). Generate vectors via the configured embedding provider (`AI-05`). Store in `RecordEmbedding.embedding` as a pgvector `VectorField` with an HNSW index.
>
> **Supersedes:** the Qdrant upsert approach. See SRS §456 and §624 — *"There is no separate vector database service or additional network port."*

**Maps to:** `AI-03`, `AI-04`, `AI-05` · **Blocked by:** `BE-04`, `FW-01`

---

#### `IR-15` — "[AI] LangChain Chunking & Qdrant Upsert" · Subtask · To Do

**Why:** both named technologies are excluded — Qdrant by SRS §456/§624, LangChain by absence from every current requirement (1 mention, in the change history only).

**Rewrite title:** `[AI] Text Chunking & pgvector Embedding Storage`

**Rewrite tasks to:**

> * Implement `chunk_text(text, size, overlap)` as a pure, unit-tested function. No LangChain — see ADR *RAG orchestration*.
> * Generate vectors via the configured embedding provider (`AI-05`).
> * Store in `RecordEmbedding` using a pgvector `VectorField`; add an HNSW index in a migration.
> * Remove all `pickle` usage.

**Maps to:** `AI-03`, `AI-04` · **Blocked by:** `FW-01`, `FW-02`

---

#### `IR-35` — "[AI] Qdrant Retrieval, Cohere Reranking & LLM Orchestration" · Subtask · To Do

**Why:** all three named technologies are unsupported by the SRS. Cohere has **0 SRS mentions**, and `docs/rag_pipeline_service_map.md` itself notes reranking *"was not carried forward into the formal SRS/SDD."*

**Rewrite title:** `[AI] pgvector Retrieval & Grounded Answer Generation`

**Rewrite tasks to:**

> * Execute cosine-similarity retrieval via pgvector's `<=>` operator with `LIMIT k`.
> * **Filter retrieval by record visibility** — a user must never receive a citation to a record they cannot see (`SEC-02`, `BE-06`).
> * Build the prompt explicitly from retrieved chunks; call the LLM via the provider protocol.
> * Return `{answer, citations}` where every citation resolves to a permitted record.
>
> **Descoped:** Cohere reranking (0 SRS mentions). **Superseded:** Qdrant, LangChain.

**Maps to:** `AI-06` · **Blocked by:** `FW-01`, `FW-02`, `AI-03`

---

#### `IR-41` — "[Backend] State Transition API & Validation Matrix" · Subtask · To Do

**Why:** partially implemented already. `reviews/services.py` contains 11 guarded transitions and the `RecordClearance` model. The remaining work is **consolidation**, not greenfield construction — and the ticket as written risks a second, parallel implementation.

**Rewrite tasks to:**

> * **Note:** `reviews/services.py` already implements 11 guarded transitions with `InvalidPipelineTransition`. Do not rebuild it.
> * Consolidate the **7 transitions currently outside it** (`records/views.py:135,208,254,334,690`, `records/services.py:33`) into one declarative transition table.
> * Add `apply(record, event, actor)` wrapping each transition in `transaction.atomic()`.
> * The Excel importer becomes a declared `legacy_import` edge rather than a direct `pipeline_status = "published"` assignment.
> * Table-driven tests covering every legal and representative illegal edge.

**Maps to:** `WF-01`, `WF-05`, `WF-04`, `TEST-03` · **Blocked by:** `BE-05`, `TEST-01`

---

#### `IR-39` — "[Frontend] Build Data Table Component" · Subtask · To Do

**Why:** the component **already exists**. `components/shared/DataTable.tsx` (124 lines) wraps `@tanstack/react-table` and includes pagination at `:96-118`. Building a second one would duplicate it.

**Rewrite title:** `[Frontend] Extend & Adopt the Existing DataTable`

**Rewrite tasks to:**

> * **Note:** `components/shared/DataTable.tsx` already exists with pagination. Extend it; do not rebuild.
> * Add column sorting (closes the `TODO` at `DataTable.tsx:3`).
> * Add inline row actions for Approve/Reject.
> * Adopt it across the 14 feature files that currently hand-roll `<table>` (used by only 2 today).
> * Wire in `hooks/useDataTable.ts`, which has 0 importers, or delete it.
> * Add an `overflow-x: auto` container for `NFR-U3` (360 px, no horizontal scroll).

**Maps to:** `FE-05`, `FE-08` · **Blocked by:** `FE-04`

---

#### `IR-7` — "[Security] Implement Django API Permission Decorators" · Subtask · **In Review**

**Why:** the status is wrong and the second half is incomplete. The permission **classes exist** (`core/permissions.py` declares eleven), but the task also says *"Decorate all sensitive backend API views."* **Twelve endpoints have no object-level check at all.**

**Rewrite tasks to:**

> * **Note:** `IsStudent`, `IsReviewer`, `IsAdmin` and eight more already exist in `core/permissions.py`. Five are referenced nowhere.
> * Apply `IsOwnerOrStaff` to the **6 unprotected `documents` endpoints** (`SEC-03`) and the **6 unprotected `storage` endpoints** (`SEC-04`).
> * Apply record visibility to `RecordViewSet.retrieve`, which is currently unfiltered (`SEC-02`).
> * Replace the 5 hand-written owner-or-staff checks with the existing class.
> * Remove the `is_django_staff` blanket bypass (`SEC-05`, pending ADR `ARCH-04`).
>
> **Move back to In Progress** — NFR-S4 is not currently satisfied.

**Maps to:** `SEC-02`, `SEC-03`, `SEC-04`, `SEC-05`, `BE-03` · **Status change:** In Review → In Progress

---

#### `IR-12` — "[Backend] Document Submission Endpoint & Celery Setup" · Subtask · **Done**

**Why:** marked Done; two of its three stated tasks do not work.

- ✅ `/api/documents/submit/` exists
- ❌ *"Configure a Celery worker and Redis queue"* — no task routing exists; workers consume `default`/`extraction`/`embedding` while tasks publish to `celery`. **No worker consumes the queue tasks publish to.**
- ❌ *"Write the background task to execute asynchronous extraction"* — the task exists but imports three libraries absent from `requirements/base.txt`, so it always fails.
- ❌ The endpoint has **no ownership check** — any user can upload into any record.

**Action: reopen.** Add:

> * Add `CELERY_TASK_ROUTES`; ensure every task's queue has a consumer (`BE-03`).
> * Add `pymupdf` to requirements so extraction can succeed (`AI-01`).
> * Add an ownership check to `SubmitDocumentView` (`SEC-03`).
> * Acceptance: an uploaded PDF reaches `PdfExtraction.status == "done"` end to end.

**Maps to:** `BE-03`, `AI-01`, `SEC-03` · **Status change:** Done → In Progress

---

#### `IR-4` — "[Security] Audit JWT Configuration & CORS" · Subtask · **In Review**

**Why:** the audit missed four findings; the status implies completion.

- JWT rotation and blacklisting are correctly configured ✅
- ❌ **NFR-S2 is not met** — 30-minute inactivity expiry does not occur; a 7-day rotating refresh token with silent client refresh means idle sessions never expire (`SEC-08`)
- ❌ `CORS_ALLOW_ALL_ORIGINS = True` with `CORS_ALLOW_CREDENTIALS = True` in development (`SEC-09`)
- ❌ The access token persists in `localStorage` after logout (`FE-01`/`SEC-07`)
- ❌ No refresh deduplication against `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION` — concurrent 401s cause a hard logout

**Action: reopen** with the four findings as acceptance criteria.

**Maps to:** `SEC-08`, `SEC-09`, `FE-01` · **Status change:** In Review → In Progress

---

### REMOVE / DEFER EXISTING JIRA TASK (4)

| Issue | Action | Reason |
|---|---|---|
| `IR-18` "[Security] Build WatermarkService" · In Progress | **Defer** | Depends on the download path, which is broken at import (`BE-01`) and has misplaced handlers (`BE-02`). `records/views.py:582` carries `# TODO(SRS): apply per-user watermark`. Resume after `BE-01`/`BE-02`. Not MVP-blocking. |
| `IR-25` "KPI Pipeline Metrics Polling" · Story | **Defer to Phase 2** | SRS §31 records Module 7 (KPI Dashboard) as **"Phase 2"**. Deferring aligns Jira with the SRS. |
| `IR-48` "[Frontend] Metrics Polling & Chart Rendering" · Subtask | **Defer to Phase 2** | Child of IR-25. Also note `recharts` is installed with **zero importers** — do not build against it until Phase 2 (`FE-07`). |
| `IR-49` "[Backend] KPI Aggregation & Redis Caching" · Subtask | **Defer to Phase 2** | Child of IR-25. |

### CLOSE AS DELIVERED (2)

| Issue | Action |
|---|---|
| `IR-50` "Architecture Refactoring Validation & Task Breakdown" | **Close.** All four acceptance criteria met by `docs/architecture-review/` and `docs/architecture-tasks/`. No production code changed. |
| `IR-51` "Architecture Grill-Me & MVP Decision Review" | **Close.** All six acceptance criteria met: findings documented, decision-required items in `01-architecture-tasks.md` and `09-framework-tasks.md`, MVP go/no-go in `10-mvp-validation-tasks.md`, framework evaluation in `09-`, tasks under `docs/`, no production code changed. |

### STATUS CORRECTIONS (3 further)

| Issue | Current | Should be | Evidence |
|---|---|---|---|
| `IR-2` "[Frontend] Build Login UI & Axios Interceptors" | In Review | In Progress | The refresh interceptor never calls `setTokens`, writes to `localStorage` nothing reads, and has no deduplication (`FE-01`) |
| `IR-3` "[Backend] Build Authentication API Endpoints" | **Done** | In Progress | Endpoints exist, but `config/urls.py` cannot load — `records/views.py` raises `NameError` at import, so **no endpoint responds** (`BE-01`) |
| `IR-11` "[Frontend] Build SubmissionWizard & Upload Logic" | In Progress | — | No change; note it depends on `SEC-03` for ownership enforcement |

---

## Part 2 — Backlog coverage gaps

**Not one of the 51 existing issues covers any of the following.** All are new.

| Area | New tasks | Severity |
|---|---|---|
| **Application boot** | `BE-01`, `BE-02`, `BE-03`, `BE-04`, `AI-01`, `DEP-01`, `DEP-02` | 5 MVP Blockers |
| **Security defects** | `SEC-01`…`SEC-09` | 5 MVP Blockers |
| **Testing** | `TEST-01`…`TEST-05` | 2 MVP Blockers |
| **CI/CD** | `ARCH-01` | 1 MVP Blocker |
| **Deployment hardening** | `DEP-03`…`DEP-06` | backups, observability, secrets, hosting |
| **MVP validation** | `VAL-01`…`VAL-18` | every NFR |
| **Architecture decisions** | `ARCH-03`…`ARCH-06`, `FW-01`…`FW-06` | 8 blocking decisions |
| **Documentation** | `DOC-01`…`DOC-06` | 7 dead links; 4 promised documents missing |

> Jira has 51 issues and **no ticket for testing, CI, or any of the five defects that stop IRIS running.**

---

## Part 3 — Suggested epic mapping

New tasks map onto the existing epics where possible; three new epics are proposed.

| Epic | Existing | New tasks to add |
|---|---|---|
| `IR-26` Epic 1: User Management & Auth | ✓ | `SEC-08`, `FE-01`, `FE-03` |
| `IR-27` Epic 2: Document Ingestion & RAG | ✓ | `AI-01`, `AI-02`, `AI-03`, `AI-04`, `AI-05`, `BE-03`, `BE-04` |
| `IR-28` Epic 3: AI Search & Conversation | ✓ | `AI-06`, `AI-08` |
| `IR-29` Epic 4: Analysis & Summarization | ✓ | `AI-07` |
| `IR-30` Epic 5: Workflow Engine | ✓ | `WF-01`…`WF-05`, `BE-05`, `BE-06` |
| `IR-31` Epic 6: Compliance & Audit | ✓ | `SEC-07`, `WF-03` |
| `IR-32` Epic 7: Analytics Dashboard | ✓ | *(defer — Phase 2)* |
| **NEW — Epic 8: Platform Stability & Security** | — | `BE-01`, `BE-02`, `SEC-01`…`SEC-06`, `SEC-09` |
| **NEW — Epic 9: Engineering Practice** | — | `ARCH-01`, `TEST-01`…`TEST-05`, `FE-02`, `DOC-01`…`DOC-06` |
| **NEW — Epic 10: Deployment & Operations** | — | `DEP-01`…`DEP-06`, `ARCH-02` |

Architecture decisions (`ARCH-03`…`ARCH-06`, `FW-01`…`FW-06`) are best held as a small decision board outside the delivery epics, since each blocks work across several.

---

## Part 4 — Full task matrix

**Legend.** MVP: **B**locker · **R**equired · **Rec**ommended · **P**ost-MVP · **O**ptional. Complexity: XS <1h · S <1d · M 1–3d · L 3–5d · XL >5d.

| ID | Task | Area | Type | Priority | MVP | Cx | Dependencies | Existing Jira? |
|---|---|---|---|---|---|---|---|---|
| ARCH-01 | CI pipeline on every push | Arch | Task | Critical | **B** | S | TEST-01, FE-02 | — none |
| ARCH-02 | Reconcile Docker topology with SRS | Arch | Task | Critical | **B** | M | BE-03, FW-03, FW-05 | — none |
| ARCH-03 | **DECISION** Storage ownership model | Arch | Task | Critical | **B** | XS | — | — none |
| ARCH-04 | **DECISION** `is_staff` semantics | Arch | Task | Critical | **B** | XS | — | — none |
| ARCH-05 | **DECISION** Record PIN semantics | Arch | Task | High | R | XS | — | — none |
| ARCH-06 | ADR register | Arch | Task | Medium | Rec | S | — | — none |
| BE-01 | Fix 6 undefined names — restore boot | Backend | Bug | Critical | **B** | XS | — | **IR-3 (status wrong)** |
| BE-02 | Relocate 4 misplaced methods | Backend | Bug | Critical | **B** | S | BE-01 | — none |
| BE-03 | Celery task routing | Backend | Bug | Critical | **B** | S | ARCH-02 | **IR-12 REWRITE** |
| BE-04 | Un-shadow `apps/ai`, add migrations | Backend | Task | Critical | R | M | BE-01 | — none |
| BE-05 | `core/enums.py` TextChoices | Backend | Task | High | Rec | S | — | — none |
| BE-06 | `Record` queryset scopes | Backend | Task | High | Rec | M | BE-05 | — none |
| BE-07 | Log swallowed exceptions | Backend | Task | High | R | XS | — | — none |
| BE-08 | Fix 2 N+1s, FTS signal | Backend | Task | Medium | Rec | XS | — | — none |
| BE-09 | Remove dead backend code | Backend | Task | Medium | Rec | S | TEST-01 | — none |
| FE-01 | Token module + refresh dedup | Frontend | Bug | Critical | R | S | — | **IR-2 (status wrong)**, IR-4 |
| FE-02 | ESLint flat config + typecheck | Frontend | Task | Critical | R | S | — | — none |
| FE-03 | One `useRole` module | Frontend | Task | High | R | S | — | — none |
| FE-04 | TanStack Query server state | Frontend | Story | High | Rec | L | **FE-01**, FW-04 | — none |
| FE-05 | Shared list/table modules | Frontend | Story | Medium | P | L | FE-04 | **IR-39 REWRITE** |
| FE-06 | react-hook-form + Zod only | Frontend | Task | Medium | Rec | M | — | — none |
| FE-07 | Delete dead FE code + 4 deps | Frontend | Task | Medium | Rec | M | FE-02, ARCH-03, AI-08 | — none |
| FE-08 | a11y + responsive primitives | Frontend | Task | Medium | Rec | M | FE-05 | — none |
| AI-01 | Restore extraction (PyMuPDF) | AI | Bug | Critical | **B** | XS | BE-03 | **IR-13** (aligned) |
| AI-02 | Docling-serve integration | AI | Story | High | R/P | M | AI-01, FW-03 | IR-13 |
| AI-03 | pgvector VectorField + HNSW | AI | Story | Critical | R | M | BE-04, AI-05, FW-01 | **IR-9, IR-15 REWRITE** |
| AI-04 | Chunking without LangChain | AI | Task | High | R | S | AI-01, FW-02 | **IR-15 REWRITE** |
| AI-05 | Provider protocols + config | AI | Story | Critical | R | M | FW-06 | — none |
| AI-06 | Retrieval + grounded answers | AI | Story | High | R | L | AI-03/04/05, BE-06, FW-05 | **IR-35 REWRITE** |
| AI-07 | Structured summarization | AI | Story | Medium | R | M | AI-01, AI-05 | IR-20, IR-37, IR-38 |
| AI-08 | Conversation persistence | AI | Story | Medium | Rec | M | AI-06, BE-04 | IR-19, IR-33, IR-34 |
| SEC-01 | Remove nginx `/media/` route | Security | Bug | Critical | **B** | XS | — | — none |
| SEC-02 | Record `retrieve` visibility | Security | Bug | Critical | **B** | S | BE-01 | **IR-7 REWRITE** |
| SEC-03 | 6 document endpoints authz | Security | Bug | Critical | **B** | S | BE-01 | **IR-7 REWRITE** |
| SEC-04 | Storage endpoints authz | Security | Bug | Critical | **B** | S | **ARCH-03** | **IR-7 REWRITE** |
| SEC-05 | Remove `is_staff` bypass | Security | Bug | Critical | **B** | S | **ARCH-04** | **IR-7 REWRITE** |
| SEC-06 | PIN enforces a grant | Security | Story | High | R | M | ARCH-05 | — none |
| SEC-07 | Audit immutability + coverage | Security | Story | High | R | M | SEC-05, WF-03 | IR-24, IR-47 |
| SEC-08 | 30-min inactivity expiry | Security | Story | High | R | M | FE-01 | **IR-4 REWRITE** |
| SEC-09 | Prod config, secrets, CORS | Security | Task | High | R | S | DEP-05 | **IR-4 REWRITE** |
| WF-01 | Lifecycle transition table | Workflow | Story | High | Rec | L | BE-05, TEST-01 | **IR-41 REWRITE** |
| WF-02 | One `ReviewPolicy` | Workflow | Task | High | Rec | M | BE-05, SEC-05 | — none |
| WF-03 | Audit review decisions | Workflow | Task | High | R | S | WF-05 | **IR-42** (aligned) |
| WF-04 | Excel import as declared edge | Workflow | Task | Medium | Rec | M | WF-01 | — none |
| WF-05 | Transactions on transitions | Workflow | Bug | High | R | S | — | — none |
| DEP-01 | Make Docker stack buildable | Deploy | Bug | Critical | **B** | S | BE-03, FW-03, FW-05 | — none |
| DEP-02 | Prod port + built frontend | Deploy | Bug | Critical | **B** | S | **SEC-01** | — none |
| DEP-03 | Backups + restore drill | Deploy | Task | High | R | M | DEP-01 | — none |
| DEP-04 | Logging, health checks, Sentry | Deploy | Task | Medium | Rec | M | BE-07 | — none |
| DEP-05 | Remove hardcoded credentials | Deploy | Task | High | R | XS | — | — none |
| DEP-06 | Hosting decision + ADR | Deploy | Task | Medium | Rec | M | DEP-01, FW-03 | — none |
| TEST-01 | pytest + import-smoke tests | Testing | Task | Critical | **B** | S | BE-01 | — none |
| TEST-02 | CI enforcement of tests | Testing | Task | Critical | **B** | S | ARCH-01, TEST-01 | — none |
| TEST-03 | Lifecycle table tests | Testing | Task | High | Rec | M | TEST-01, WF-01 | — none |
| TEST-04 | Authorization regression suite | Testing | Task | Critical | R | M | TEST-01, SEC-02…05 | — none |
| TEST-05 | Frontend test harness | Testing | Task | Medium | Rec | M | FE-02 | — none |
| FW-01 | **RATIFY** pgvector not Qdrant | Framework | Task | High | R | XS | — | **IR-9, IR-15** |
| FW-02 | **RATIFY** no LangChain | Framework | Task | High | R | XS | — | **IR-15, IR-35** |
| FW-03 | **DECISION** Docling for MVP? | Framework | Task | High | R | XS | — | — none |
| FW-04 | **DECISION** TanStack Query? | Framework | Task | Medium | Rec | XS | — | — none |
| FW-05 | **DECISION** Gateway + NFR-P3 | Framework | Task | High | R | S | — | — none |
| FW-06 | **DECISION** Provider + governance | Framework | Task | Critical | R | XS | — | — none |
| VAL-01 | Validate authentication | Validation | Task | Critical | R | S | SEC-08, FE-01 | — none |
| VAL-02 | Validate authorization | Validation | Task | Critical | R | M | SEC-01…05, TEST-04 | — none |
| VAL-03 | Validate document upload | Validation | Task | High | R | S | SEC-03, DEP-02 | — none |
| VAL-04 | Validate document processing | Validation | Task | Critical | R | M | AI-01…05, BE-03 | — none |
| VAL-05 | Validate workflow end to end | Validation | Task | Critical | R | M | WF-01, WF-05 | — none |
| VAL-06 | Validate reviewer routing | Validation | Task | High | R | M | WF-02, SEC-05 | — none |
| VAL-07 | Validate RAG ingestion | Validation | Task | High | R | M | AI-03, AI-04 | — none |
| VAL-08 | Validate RAG retrieval | Validation | Task | Critical | R | M | AI-06, BE-06 | — none |
| VAL-09 | Validate answer groundedness | Validation | Task | High | R | M | AI-06 | — none |
| VAL-10 | Validate citation correctness | Validation | Task | High | R | S | AI-06 | — none |
| VAL-11 | Validate summarization | Validation | Task | Medium | R | M | AI-07 | — none |
| VAL-12 | Validate AI latency | Validation | Task | Critical | R | S | AI-06, **FW-05** | — none |
| VAL-13 | Validate usability (SUS ≥ 75) | Validation | Task | High | R | L | VAL-05 | — none |
| VAL-14 | Validate a11y + 360 px | Validation | Task | High | R | M | FE-08 | — none |
| VAL-15 | Validate concurrency + load | Validation | Task | High | R | L | WF-05, DEP-02 | — none |
| VAL-16 | Validate deployment | Validation | Task | Critical | R | M | DEP-01/02/05/06 | — none |
| VAL-17 | Validate recovery + backups | Validation | Task | High | R | M | DEP-03, DEP-04 | — none |
| VAL-18 | Validate operating cost | Validation | Task | High | R | M | AI-05, FW-06 | — none |
| DOC-01 | Fix 7 dead README links | Docs | Task | High | R | XS | — | — none |
| DOC-02 | RAG docs as target-state | Docs | Task | High | R | S | FW-01…05 | — none |
| DOC-03 | Reconcile SRS/SDD | Docs | Task | High | R | M | FW-02/03/05/06 | — none |
| DOC-04 | Write `TEST_PLAN.md` | Docs | Task | High | R | M | TEST-01…05 | — none |
| DOC-05 | Write `SECURITY.md` + register | Docs | Task | High | R | M | SEC-01…09 | — none |
| DOC-06 | Traceability matrix | Docs | Task | High | R | L | all | — none |

**Totals:** 86 tasks — **13 MVP Blockers**, 45 MVP Required, 17 MVP Recommended, 2 Post-MVP, 0 Optional (`FE-10` folded into `FE-07`), plus 9 decision/ratification tasks.

---

## Part 5 — Sprint suggestion

| Sprint | Theme | Tasks | Outcome |
|---|---|---|---|
| **0** (2 d) | Decisions | ARCH-03, ARCH-04, ARCH-05, FW-01, FW-02, FW-03, FW-05, FW-06 | Eight blocking decisions recorded as ADRs. Cheap, and unblocks everything |
| **1** (3 d) | Make it run | BE-01, BE-02, BE-03, BE-04, AI-01, DEP-01, DEP-02 | The API boots; Compose builds; extraction works |
| **2** (3 d) | Close the holes | SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, DEP-05 | No unauthenticated documents; no IDOR; separation of duties restored |
| **3** (3 d) | Guardrails | TEST-01, TEST-02, TEST-04, ARCH-01, FE-02, FE-01 | CI green; regressions blocked; token handling fixed |
| **4** (5 d) | SRS delivery — AI | AI-03, AI-04, AI-05, AI-06, AI-02 | RAG works, on pgvector, per the SRS |
| **5** (5 d) | SRS delivery — workflow | BE-05, BE-06, WF-01…WF-05, TEST-03 | Lifecycle consolidated, transactional, audited |
| **6** (5 d) | Frontend + docs | FE-03, FE-04, FE-06, FE-07, DOC-01…DOC-03 | Server state owned; docs honest |
| **7** (5 d) | Validation | VAL-01…VAL-18 | Every NFR measured with evidence |
| **8** | Hardening | DEP-03, DEP-04, DEP-06, DOC-04…DOC-06, remaining Recommended | Backups, observability, thesis artefacts |

**Sprints 0–3 are ~11 working days** and take IRIS from *"does not start and serves every uploaded document anonymously"* to *"starts, enforces access, and cannot silently regress."* That is the minimum defensible position, and everything after it is delivery rather than repair.
