# 12 — Scope Cuts

Every capability classified against the **~27 dev-day** implementation budget ([ADR-001](../adr/001-mvp-scope-boundary.md)).

| Class | Meaning |
|---|---|
| **KEEP** | Required for the validated MVP |
| **REDUCE** | Keep a minimal version |
| **REPLACE** | Existing approach replaced with something simpler |
| **DEFER** | Explicitly moved to Phase 2 |
| **REMOVE** | Deleted entirely |
| **DO NOT BUILD YET** | Technically interesting, unnecessary for Semester 2 |

**Every deferral must be recorded in the SRS (`F-03`) and the traceability matrix (`DOC-06`).** A cut that exists only here is an undocumented deviation.

---

## KEEP

| Capability | Why it stays | Task | Days |
|---|---|---|---|
| Application boot | Nothing works without it | `B-01`, `B-02` | 1.5 |
| Buildable Docker stack | Nothing deploys without it | `D-01`, `D-02` | 2 |
| Object-level authorization | Real customer data in Week 11; NFR-S4 | `S-02`, `S-03` | 2 |
| Secure media access | Every uploaded PDF is currently public | `S-01` | 0.5 |
| Production config and secrets | Gates the public URL | `S-04` | 1 |
| Interim deployment | Weeks 1–2 requirement | `D-03` | 1 |
| Separation of duties | The contribution depends on it | `S-05` | 1 |
| Celery routing | Background jobs must execute | `B-03` | 1 |
| PDF extraction | FR-M3-01; feeds search | `R-01` | 0.5 |
| **Workflow transition table** | **Thesis contribution + SaaS seam** | `W-01` | 3 |
| **Restart-all policy** | **Makes the contribution evaluable** | `W-02` | 0.5 |
| **Transaction boundaries** | Clearance integrity | `W-03` | 0.5 |
| **Decision audit + instrumentation** | **The research data** | `W-04` | 2 |
| Enums | `W-01`'s prerequisite | `F-02` | 1 |
| Token consolidation | Post-logout token leak | `FE-01` | 1 |
| Test harness + CI | Prevents recurrence of all of the above | `T-01`, `F-01`, `T-02` | 3 |
| Pilot surface reduction | Less to secure and test | `FE-02` | 0.25 |
| FTS + workflow + audit + notifications | Already built and working | — | 0 |

---

## REDUCE

| Capability | From | To | Task |
|---|---|---|---|
| **RAG pipeline** | 11 documented phases | Extraction → abstract-level embeddings → pgvector retrieval → grounded answer + citations. **Timeboxed 3 days; falls back to search-only** | `R-01`…`R-06` |
| **Admin portal (Module 8)** | Custom admin screens | Django admin, plus FR-M8-03 via the existing (un-shadowed) views | `B-04` |
| **Audit coverage** | Full analytics | Decision events + time-on-task — enough for compliance *and* the research metric | `W-04` |
| **Multi-tenancy** | Pooled architecture | Instance-per-tenant + configuration boundaries documented | `SA-01`…`SA-04` |
| **Backup** | Full DR strategy | Nightly `pg_dump` + media archive + **one rehearsed restore** | `D-04` |

---

## REPLACE

| Existing | Replaced with | Why | Task |
|---|---|---|---|
| Qdrant (Jira `IR-9`, `IR-15`, `IR-35`) | **pgvector** | SRS §456/§624 already specify it; no second service | `R-03` |
| LangChain orchestration | **~60 lines of explicit Python** | Deletion test: complexity moves out of a dependency into readable code | `R-04` |
| Cohere reranking | **Nothing** | Zero SRS mentions; `rag_pipeline_service_map.md` notes it was not carried forward | — |
| `ai-gateway` FastAPI service | **RAG inside Django** | Contradicts the SRS service table; SRS §478 names `SemanticSearchView`/`AskView` | `D-01` |
| Ten Compose services | **Five** | Five of ten run no code | `D-01` |
| Three Celery workers + beat | **One worker** | All three consume queues nothing publishes to | `B-03` |
| Six unauthorized `storage` endpoints | **Deleting the app** | Cheaper than securing a feature the pilot never touches | `SC-01` |
| Hand-written owner-or-staff checks ×5 | **`IsOwnerOrStaff`** | The seam exists and was routed around | `S-03` |

---

## DEFER — Phase 2

Each is a legitimate capability that the budget does not fund.

| Capability | Requirement | Why deferred |
|---|---|---|
| Conversational RAG + history | FR-M4-01 (partial) | 840 lines of chat UI exist, unrouted. Single-shot Q&A satisfies the core claim |
| Document summarization | FR-M4-02 | A separate LLM feature, UI and cost line, overlapping Epic 3's value |
| KPI / analytics dashboard | FR-M7-01/02 | **Already Phase 2 in the SRS.** Note the tension: Weeks 11–12 need usage analytics — supply them from `W-04`'s audit export, not a dashboard |
| Watermarking | FR-M6-01 ext. | `records/views.py:582` is still a TODO. A forensic subsystem; not pilot-blocking |
| Download / delete request queues | FR-M2-02/03 | Not in the pilot workflow. `B-02` fixes the code so it imports |
| Excel import + styled template | FR-M2-04 | Nobody migrates legacy records in Semester 2. 115 lines of openpyxl formatting |
| Institutional + personal file storage | FR-M2-06/07 | Removed — see `SC-01` |
| Record access PIN | SDD 3.5.2 | Currently gates nothing. Build properly or drop it; the middle state is worst |
| Full-text chunking | FR-M3-02 ext. | Doubles RAG cost in dev-days and API spend. Abstracts retrieve well at this corpus size |
| Docling-serve | FR-M3-01 | **SRS-specified** — deferral requires the `F-03` amendment. 4 GB for a scanned-PDF path PyMuPDF covers |
| Session inactivity expiry | NFR-S2 | P2, not P0 — real but not a public-exposure blocker |
| Audit immutability | NFR-S5 | P2. Needs a DB-level guard |
| `ReviewPolicy` consolidation | — | P2. `W-01` delivers most of the value |
| Frontend test harness | — | P3. Backend tests catch more per hour |

---

## REMOVE

Deleted outright, not deferred.

| What | Lines | Task |
|---|---|---|
| `apps/storage` (models, views, urls, migration, `INSTALLED_APPS` entry) | ~250 | `SC-01` |
| `ai-gateway` and `docling` Compose services | — | `D-01` |
| `celery-extraction`, `celery-embedding`, `celery-beat` | — | `D-01` |
| nginx `/media/` location | 5 | `S-01` |
| `apps/ai/models/`, `apps/ai/views/` stub packages, 8 `pass` service classes | ~50 | `B-04` |
| Dead AI chat UI (`RAGChatPage` + 7 components + `chatStorage` + `types/chat`) | ~840 | `FE-03` |
| Storage frontend (`StoragePage`, `FolderBrowserPage`, `api/storage.ts`) | ~320 | `FE-03` |
| Superseded guards (`PrivateRoute`, `RoleRoute`, `ForbiddenPage`) | ~120 | `FE-03` |
| `AccessRequestsPage`, `NotificationBell`, `DownloadRequestModal`, `DiscoverSearchContext`, `useDataTable`, duplicate `discoverUtils`, `signupData` | ~250 | `FE-03` |
| `MyRecordsViewSet`, `build_zip_for_record`, 5 unused permission classes, `LegacyFolder`, commented-out view | ~700 | `B-09` |
| npm: `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone` | — | `FE-03` |
| Duplicate `pgvector` requirements entry | 1 | `R-03` |

**~2,500 lines and 4 packages removed.**

---

# SC-01 · Remove `apps/storage`

## Objective
Delete the institutional/personal file-browser app, removing six unauthorized endpoints from the MVP.

## Problem
Six endpoints with no ownership check on any of them, serving a feature no pilot workflow touches. Securing it costs ~1 day; deleting it costs ~0.5 and removes the surface entirely.

## Evidence
`storage/views.py` — all six endpoints are bare `IsAuthenticated`; `StorageFolderDetailView` and `StorageFileDetailView` use unfiltered `Model.objects.all()`. `StorageFolder.parent` is `on_delete=CASCADE`, so deleting a root folder destroys the subtree — with no soft delete and no audit event.

**Deletion is clean.** Verified: no Python reference outside the app itself except `INSTALLED_APPS:39` and one URL include at `config/urls.py:16`. Frontend touch points: `api/storage.ts`, `Sidebar.tsx`, `StoragePage.tsx`, `FolderBrowserPage.tsx`, `router/index.tsx`.

## Current State
Any authenticated user can read, rename, download and delete any other user's folders and files, unaudited and unrecoverable.

## Proposed State
The app and its frontend removed; FR-M2-06/07 recorded as Phase 2.

## Scope
Delete `backend/apps/storage/`; remove from `INSTALLED_APPS` and `config/urls.py`; delete the five frontend touch points; record the deferral in `F-03` and `DOC-06`.

## Out of Scope
Re-implementing storage in Phase 2 — design it properly then, with authorization from the start.

## Technical Approach
Deleting the app leaves its tables in existing databases. For the interim deployment (fresh database) this is moot. Write a migration dropping the tables only if an existing deployment needs it.

## Dependencies
Coordinate with `FE-03`.

## Risks
Low — nothing depends on it. **Confirm with stakeholders that institutional file storage is not expected in the pilot** before deleting rather than hiding.

## Security Impact
**Removes six unauthorized endpoints, two of them destructive.** The single cheapest security improvement available.

## Performance Impact
None.

## SaaS Impact
FR-M2-06 (institutional file storage) is plausible Phase 2 product scope — design it with tenancy and authorization in mind then.

## Research/Thesis Impact
None — outside the contribution and the pilot workflow.

## MVP Classification
REMOVE

## Priority
P0 — Weeks 1–3, before public exposure

## Complexity
XS

## Acceptance Criteria
- [ ] `backend/apps/storage/` no longer exists.
- [ ] `apps.storage` is absent from `INSTALLED_APPS` and `config/urls.py`.
- [ ] `manage.py check` and the test suite pass.
- [ ] `/api/v1/storage/*` returns 404.
- [ ] The five frontend touch points are removed and `npm run build` passes.
- [ ] FR-M2-06/07 are recorded as Phase 2 in the SRS and traceability matrix.

## Testing Requirements
Import-smoke test green; a test asserting `/api/v1/storage/` 404s.

## Documentation Requirements
Deferral recorded in `F-03` and `DOC-06`.

## Definition of Done
Merged; stakeholder confirmation recorded in the ticket.

---

## DO NOT BUILD YET

Technically sound, unnecessary for Semester 2. Each has a stated trigger.

| What | Build it when |
|---|---|
| Pooled multi-tenancy (`tenant_id`) | >8 institutions, or per-tenant cost exceeds per-tenant revenue ([ADR-005](../adr/005-instance-per-tenant.md)) |
| Billing / payment module | The course confirms in-system payment is required — otherwise out-of-band evidence suffices |
| TanStack Query | The frontend is being actively extended and hand-rolled fetch is costing real time |
| Shared table / list modules | After a server-state layer exists; otherwise the shared component takes props that layer removes |
| Form-stack consolidation (drop `formik`/`yup`) | Phase 2 cleanup |
| Domain-event bus | A **second** real subscriber appears. One adapter is a hypothetical seam; two is a real one |
| Abstract `ApprovalRequest` model | Never as specified — deletion test fails, and `RoleRequest` cannot join the hierarchy |
| DRF custom exception handler | Phase 2, alongside API contract work |
| OpenAPI schema + generated client | CI exists to hang it on |
| `django-storages` S3 | Media outgrows one box — note `build_zip`'s `.path` breaks that day |
| Gunicorn `gthread` workers | AI endpoints ship and measured load justifies it |
| FastAPI AI gateway | Measured evidence that AI load degrades CRUD **and** the code to extract exists |
| Full WCAG 2.1 AA audit | Institutional adoption beyond the pilot |
| Migration squashing | Before the first production deployment |
| httpOnly refresh cookies | Phase 2; needs CSRF design and an ADR |
| Component splitting (`DocumentsPage` 793 lines) | Readability only — never ahead of security or the contribution |

---

## Budget reconciliation

| Window | Budget | Allocated | Slack |
|---|---|---|---|
| Weeks 1–3 | ~7 | 7.5 | −0.5 |
| Weeks 4–7 | 16 | 13.5 | **+2.5** |
| Weeks 8–10 | 5 | 5 | 0 |
| **Total** | **~28** | **26** | **+2** |

**The +2.5 days in Weeks 4–7 is reserved for RAG** — the only task with no prior team experience, and the only one with a pre-committed fallback. Weeks 1–3 is marginally over; the mitigation is that `SC-01` (deleting storage) is cheaper than `S-04`-style securing would have been, and validation activities are non-coding work that two team members can run in parallel.
