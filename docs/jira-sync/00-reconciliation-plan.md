# Jira Reconciliation Plan — awaiting approval

**Site:** `citiris.atlassian.net` · **Project:** IR · **Backlog read:** 51 issues (7 epics, 16 stories, 26 subtasks, 2 tasks)
**Sources:** `docs/adr/` (11 ADRs) · `docs/architecture-tasks/` (72 specs) · `docs/mvp-validation/` (16) · `docs/ui-ux/` (16)

> **Nothing has been written to Jira.** This plan is for approval first, as instructed.

---

## 0 · Two notes before the plan

**`docs/architecture-grill/` does not exist.** The design-interview conclusions were written into `docs/adr/` (ADR-001…011) and `docs/architecture-tasks/` instead. Those were used as the source. No content is missing — only the directory name differs.

**The current board carries no signal.** All 51 issues are priority `Medium`, and **every single one has zero labels and zero components.** There is no MVP classification, no phase, no thesis marker, no area anywhere on the board today. That is the main thing this sync fixes — more than the ticket count.

---

## 1 · What the board looks like now

| | Count | Observation |
|---|---|---|
| Epics | 7 | 3 of them (AI Conversation, Summarization, Analytics) are entirely post-MVP |
| Stories | 16 | |
| Subtasks | 26 | |
| Tasks | 2 | `IR-50`, `IR-51` — both delivered, both still `To Do` |
| **Labels in use** | **0** | |
| **Distinct priorities** | **1** (`Medium`) | |
| Issues marked `Done` | 2 | **Both are demonstrably false** — the app does not import |
| Issues in `In Review` | 9 | 5 are false; the reviewed code does not run |

**Jira contains no issue for any of the five defects that stop IRIS running**, and none for testing, CI, deployment, or the thesis contribution's measurement.

---

## 2 · Proposed board shape

**56 active cards.** Down from 51 existing + 72 task specs + 16 UI/UX proposals = 139 candidate items.

| Disposition | Count |
|---|---|
| **Active MVP cards** | **56** |
| Existing issues kept or rewritten into those 56 | 24 |
| Existing issues deferred to POST-MVP (no work this semester) | 21 |
| Existing issues recommended for removal | 2 |
| Existing issues closed as delivered | 2 |
| Task specs deliberately given **no card** (P3 / DO NOT BUILD) | 8 |

### The rule that keeps this small

> **A Jira card exists only for work that will actually be pulled this semester.**

P3 items and `DO NOT BUILD YET` items get **no card at all**. They stay documented in `docs/architecture-tasks/12-scope-cuts.md`, where they are already recorded with reasons. Putting them on the board would recreate exactly the noise this sync is meant to remove.

Related specs are **merged into one card** where they are one pull for one person: `B-01`+`B-02` are the same file in the same sitting; `S-05`+`T-02` are a fix and the test that proves it.

---

## 3 · Epics

| Existing/New | Key | Action | Proposed Title | MVP | Reason |
|---|---|---|---|---|---|
| Existing | IR-26 | KEEP | Epic 1: User Management & Authentication | MVP REQUIRED | Scope unchanged |
| Existing | IR-27 | REWRITE | Epic 2: Document Ingestion & RAG Pipeline | MVP REQUIRED | Scope narrows to pgvector; Qdrant/LangChain/Cohere removed per ADR-006/007 |
| Existing | IR-28 | REWRITE | Epic 3: Search & Retrieval | MVP REQUIRED | Drop "Conversational Interface" — ADR-006 excludes conversational memory. Single-shot Q&A survives |
| Existing | IR-29 | DEFER | Epic 4: Document Analysis & Summarization | POST-MVP | Separate LLM feature, UI and cost line. Outside the pilot workflow |
| Existing | IR-30 | KEEP | Epic 5: Workflow Engine | MVP REQUIRED | **THESIS-CRITICAL** — holds the contribution |
| Existing | IR-31 | KEEP | Epic 6: Compliance & Audit Logging | MVP REQUIRED | |
| Existing | IR-32 | DEFER | Epic 7: Real-Time Analytics Dashboard | POST-MVP | Already Phase 2 in SRS §31; `recharts` has zero importers |
| **New** | — | CREATE | **Epic 8: Platform Stability & Security** | MVP BLOCKER | No epic covers the five defects that stop the system running |
| **New** | — | CREATE | **Epic 9: Engineering Practice** | MVP BLOCKER | No epic covers CI, testing or documentation. Zero tests exist |
| **New** | — | CREATE | **Epic 10: Deployment & Operations** | MVP BLOCKER | No epic covers Docker, VPS, backups, SaaS tenancy |
| **New** | — | CREATE | **Epic 11: MVP Validation & Research Evaluation** | MVP REQUIRED | No epic covers validation, baseline or final evaluation |
| **New** | — | CREATE | **Epic 12: UI/UX & Design System** | MVP REQUIRED | No epic covers the interface; the contribution is currently invisible in it |

---

## 4 · Phase W1–W2 — boot, secure, deploy, validate

**12 cards.** Everything here gates everything else. No public URL until every security card is done.

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | Restore application boot — fix six undefined names and four misplaced methods | Backend | W1-W2 | **BLOCKER** | P0 | — | `B-01`+`B-02`. `records/views.py` raises `NameError` at import; `config/urls.py:11` includes it, so **no endpoint responds**. Merged — one file, one sitting |
| New | — | CREATE | Make the Docker stack buildable | Deployment | W1-W2 | **BLOCKER** | P0 | — | `D-01`. Both Compose files build `ai-gateway` from `./ai`, which does not exist |
| New | — | CREATE | Fix the production port and serve the built frontend | Deployment | W1-W2 | **BLOCKER** | P0 | — | `D-02`. Prod maps `80:80`; nginx-unprivileged listens on 8080 |
| New | — | CREATE | Remove the unauthenticated `/media/` route | Security | W1-W2 | **BLOCKER** | P0 | — | `S-01`. Every uploaded PDF is public at a guessable URL. **Currently masked only by the port bug — fixing D-02 without this exposes every document** |
| Existing | IR-7 | REWRITE | Object-level authorization on records and documents | Security | W1-W2 | **BLOCKER** | P0 | — | `S-02`+`S-03`. Permission classes exist; "decorate all sensitive views" did not happen. 12 endpoints unprotected. Also move **In Review → In Progress** |
| Existing | IR-4 | REWRITE | Production configuration, secrets and CORS | Security | W1-W2 | **BLOCKER** | P0 | — | `S-04`. Audit missed 4 findings: hardcoded DB credentials, `CORS_ALLOW_ALL_ORIGINS` with credentials, unset `ALLOWED_HOSTS`, no 30-min expiry. **In Review → In Progress** |
| New | — | CREATE | Remove `apps/storage` | Security | W1-W2 | **BLOCKER** | P0 | — | `SC-01`. Six unauthorized endpoints; deleting is cheaper than securing a feature the pilot never touches |
| Existing | IR-3 | REOPEN | Authentication API endpoints — verify against a running system | Backend | W1-W2 | REQUIRED | P0 | — | Marked `Done`, but no endpoint can respond while the URLconf fails to import. **Done → In Progress** |
| New | — | CREATE | Deploy the MVP to the interim VPS and seed the validation environment | Deployment | W1-W2 | **BLOCKER** | P0 | — | `D-03` + validation-environment prep, merged. **Gated behind all five security cards.** Synthetic data only — ADR governs staged data |
| New | — | CREATE | Design the MVP validation instrument | MVP Validation | W1-W2 | REQUIRED | P0 | — | `V-02`. Pilot-tested before use |
| New | — | CREATE | Recruit and schedule stakeholders and respondents | MVP Validation | W1-W2 | REQUIRED | P0 | — | Own card because it has **external lead time** the team does not control. Customers, end users, SMEs, decision-makers |
| New | — | CREATE | Conduct initial stakeholder validation and record feedback | MVP Validation | W1-W2 | REQUIRED | P0 | — | `V-01`. Demonstrations, interviews, observation, gap documentation. "Record feedback" folded in as acceptance criteria |
| New | — | CREATE | Collect the manual-process baseline | Research | W1-W2 | REQUIRED | P0 | **YES** | `V-03`. The real-world comparator for the contribution. **NEEDS RDCO DATA** — no fabrication |

---

## 5 · Phase W3 — requirements refactor

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | Week 3 requirements and design refactor | Documentation | W3 | REQUIRED | P0 | — | `F-03`+`DOC-03`. Reconcile SRS/SDD with reality and with validation findings. **Carries the Docling-serve deferral amendment** — SRS-specified in four places |
| New | — | CREATE | Correct documentation that contradicts the build | Documentation | W3 | REQUIRED | P1 | — | `DOC-01`+`DOC-02`. 7 dead links; RAG documents describe an 11-phase pipeline of which 2 phases exist |

---

## 6 · Phase W4–W7 — foundation, contribution, RAG

**23 cards.** The primary implementation window (~16 dev-days).

### Foundation

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | CI pipeline with dependency and secret scanning | Testing | W4-W7 | **BLOCKER** | P1 | — | `F-01`+`T-05`. Every current blocker is machine-detectable and none was detected |
| New | — | CREATE | Backend test harness and import-smoke tests | Testing | W4-W7 | **BLOCKER** | P1 | — | `T-01`. Zero tests exist. An import smoke test catches 3 of the 5 blockers |
| New | — | CREATE | `core/enums.py` — one `TextChoices` per concept | Backend | W4-W7 | REQUIRED | P1 | — | `F-02`. Prerequisite for the transition table |
| New | — | CREATE | Restore the AI app and the Celery pipeline | Backend | W4-W7 | **BLOCKER** | P1 | — | `B-03`+`B-04`. **No worker consumes the queue tasks publish to**; `apps/ai` models are shadowed by field-less stubs |
| New | — | CREATE | `Record` queryset scopes | Backend | W4-W7 | REQUIRED | P1 | — | `B-05`. One visibility predicate, used everywhere including RAG retrieval |
| Existing | IR-7 | SPLIT | Remove the `is_staff` bypass and add the authorization regression suite | Security | W4-W7 | REQUIRED | P1 | — | `S-05`+`T-02`. Migration `accounts/0005` sets `is_staff=True` for all four offices, so `IsAdmin`'s `ADMIN_ROLES` constrains nobody. The suite is the proof |
| Existing | IR-2 | REWRITE | Consolidate token storage and fix the refresh path | Frontend | W4-W7 | REQUIRED | P1 | — | `FE-01`. Interceptor writes `localStorage` nothing reads, never calls `setTokens`, no dedup against rotation+blacklist. **In Review → In Progress** |
| Existing | IR-6 | REWRITE | Reduce the pilot surface and remove dead frontend code | Frontend | W4-W7 | REQUIRED | P1 | — | `FE-02`+`FE-03`. 37 page components → 16 MVP screens; remove "coming soon" dead ends |

### Workflow — the contribution

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Existing | IR-41 | REWRITE | Declarative transition table | Workflow | W4-W7 | REQUIRED | P1 | **YES** | `W-01`. **Do not rebuild `reviews/services.py`** — it already has 11 guarded transitions. Consolidate the 7 transitions outside it. Type differentiation, routing, parallel clearance. Also the SaaS configuration seam and the experimental control |
| Existing | IR-22 | REWRITE | Configurable restart-all resubmission policy | Workflow | W4-W7 | REQUIRED | P1 | **YES** | `W-02`. ADR-004. The controlled comparison. **The evaluation must allow either result** |
| New | — | CREATE | Transaction boundaries on transitions | Workflow | W4-W7 | REQUIRED | P1 | **YES** | `W-03`. Office-specific clearance integrity; a transition and its audit event must be atomic |
| **New** | — | **CREATE** | **Serialize clearance state — `clearances[]`, `route[]`, `resubmission{}`** | Backend | W4-W7 | **BLOCKER** | P1 | **YES** | **`W-07` — new, from the UI/UX phase.** `RecordClearance` is **never serialized**, so the contribution is invisible to every user and every evaluator. Nothing in Jira or the task backlog covered this |
| New | — | CREATE | Workflow transition tests across both policies | Testing | W4-W7 | REQUIRED | P1 | **YES** | `T-03`. Correctness of the model under both `PRESERVE` and `RESTART_ALL` |

### RAG — timeboxed

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Existing | IR-13 | KEEP | PyMuPDF text extraction | RAG | W4-W7 | REQUIRED | P1 | — | `R-01`. Already specifies PyMuPDF — matches ADR-006. Add `pymupdf` to requirements |
| Existing | IR-15 | REWRITE | Embedding generation and pgvector storage | RAG | W4-W7 | REQUIRED | P1 | — | `R-02`+`R-03`. **Qdrant and LangChain both excluded** (SRS §456, §624; ADR-006/007). Remove all `pickle` usage. No chunking in MVP |
| Existing | IR-35 | REWRITE | pgvector retrieval and grounded answer generation | RAG | W4-W7 | REQUIRED | P1 | — | `R-04`+`R-06`. Cohere has **zero SRS mentions**. **Timeboxed to 3 dev-days ending Week 6** — pre-committed fallback to search-only. **Retrieval must filter by visibility** — no citation to an unreadable record |
| New | — | CREATE | Graceful degradation to PostgreSQL FTS | RAG | W4-W7 | REQUIRED | P1 | — | `R-05`. ADR-008. **Separately pullable on purpose** — if the R-04 timebox expires, this still ships and search still works. `search_vector` already exists and nothing queries it |

### UI/UX

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | Design-system and accessibility primitive fixes | UI/UX | W4-W7 | REQUIRED | P1 | — | `UX-01`. `Input` has no `aria-invalid`/`aria-describedby`; `Modal` has no focus trap. **~1.5 hrs, and every later screen inherits it.** Do this first |
| **New** | — | **CREATE** | **`ClearanceTrack`, `ClearanceStatus`, `PreservationNotice`** | UI/UX | W4-W7 | REQUIRED | P1 | **YES** | `UX-02`. The contribution's only visual representation. 7 states as icon+label+colour; `preserved` distinguished **by text**, not colour. One `PreservationNotice` component keeps the wording identical in all four places it appears |
| New | — | CREATE | Record detail with the Clearance Track | UI/UX | W4-W7 | REQUIRED | P1 | **YES** | `UX-03`. State before identity; 8 blocks; decline banner and resubmission panel |
| New | — | CREATE | Merge the review queues and make the decision screen self-sufficient | UI/UX | W4-W7 | REQUIRED | P1 | **YES** | `UX-04`. Four list pages → one queue. Reviewers currently cannot see peer clearance state, and opening a document **discards the typed comment** |
| Existing | IR-11 | REWRITE | Submission wizard — type first, route preview, explicit submit | UI/UX | W4-W7 | REQUIRED | P1 | — | `UX-05`. Governs **NFR-U2** (10 minutes, 5/5 participants). The draft/submit boundary is the most likely failure |
| New | — | CREATE | Institutional configuration boundaries | SaaS | W4-W7 | REQUIRED | P1 | — | `SA-01`. Which knobs are per-institution. Feeds the label contract — 20 frontend files hardcode CIT-U office names |

---

## 7 · Phase W8–W9 — harden and gather evidence

**13 cards.**

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | Code hygiene and lint gate | Backend | W8-W9 | RECOMMENDED | P2 | — | `B-06`+`B-07`+`B-09`+`FE-04`+`FE-05`. Swallowed exceptions, `.username` fallback, dead code, ESLint flat config, one `useRole` |
| Existing | IR-47 | REWRITE | Session expiry and audit log immutability | Security | W8-W9 | REQUIRED | P2 | — | `S-06`+`S-07`. NFR-S2 30-min inactivity does not occur; NFR-S5 needs a DB-level guard |
| New | — | CREATE | Logging, health checks and error reporting | Deployment | W8-W9 | RECOMMENDED | P2 | — | `D-05`. Needed to operate the pilot |
| New | — | CREATE | `TEST_PLAN.md` and `SECURITY.md` with the risk register | Documentation | W8-W9 | REQUIRED | P2 | — | `DOC-04`+`DOC-05`. Both promised and both missing |
| New | — | CREATE | Requirements traceability matrix | Documentation | W8-W9 | REQUIRED | P1 | — | `DOC-06`. Required for the defence |
| Existing | IR-24 | REWRITE | Search screen with degraded mode | UI/UX | W8-W9 | REQUIRED | P2 | — | `UX-07`. **`AIHubPage` renders "Coming Soon" for both modes** — there is no search box in the product. Call it "Search", not "AI Hub", so the FTS fallback reads as a mode not a failure |
| New | — | CREATE | Home, audit and history screen corrections | UI/UX | W8-W9 | RECOMMENDED | P2 | — | `UX-06`+`UX-08`. Home becomes a work list, no charts. History must show resubmission events |
| New | — | CREATE | Accessibility and responsive verification | UI/UX | W8-W9 | REQUIRED | P2 | — | `UX-09`. WCAG 2.1 AA on 16 screens; **no horizontal scroll at 360 px (NFR-U3)**. 77 contrast failures, 87 unlabelled icons, zero `sr-only` utilities today |
| New | — | CREATE | NFR evidence — authentication and authorization | MVP Validation | W8-W9 | REQUIRED | P1 | — | `V-06`+`V-07`. NFR-S2, S4, S5, S6 |
| New | — | CREATE | NFR evidence — processing, AI and performance | MVP Validation | W8-W9 | REQUIRED | P1 | — | `V-08`+`V-10`+`V-13`. NFR-P1…P5, R3, S1, S3. **Includes the 100-concurrent-session target** |
| New | — | CREATE | NFR evidence — usability | MVP Validation | W8-W9 | REQUIRED | P1 | — | `V-11`. NFR-U1, **NFR-U2 (5/5 must pass)** |
| New | — | CREATE | NFR evidence — reliability, recovery and cost | MVP Validation | W8-W9 | REQUIRED | P2 | — | `V-14`+`V-15`. NFR-R2, R4, plus operating cost for the commercial defence |
| Existing | IR-42 | REWRITE | Workflow and reviewer routing evidence | Research | W8-W9 | REQUIRED | P1 | **YES** | `V-09`. FR-M5-01. Evidence that type differentiation and parallel clearance behave as specified |

---

## 8 · Phase W10 — instrument before the pilot

**4 cards. The Week 10 boundary is hard.**

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| Existing | IR-46 | REWRITE | **Audit review decisions and instrument time-on-task** | Workflow | W10 | **BLOCKER** | P1 | **YES** | **`W-04`. The single unrecoverable item.** `AuditEvent` has 14 types, **all auth/file/account — zero workflow events.** No `SUBMITTED`, no `RESUBMITTED`, no `CLEARANCE_PRESERVED`. The evaluation metrics have **no source**. Events not written during the pilot cannot be reconstructed, and there is no second pilot |
| New | — | CREATE | Scenario-based evaluation design | Research | W10 | REQUIRED | P1 | **YES** | `V-04`. Controlled N when pilot volume is small. Within-subjects, counterbalanced |
| New | — | CREATE | Backups and a rehearsed restore | Deployment | W10 | REQUIRED | P2 | — | `D-04`. **Before Week 11** — the system effectively freezes once a customer is using it |
| New | — | CREATE | Instance provisioning and onboarding runbook | SaaS | W10 | RECOMMENDED | P2 | — | `SA-02`. Instance-per-tenant (ADR-005) — a runbook, not a screen |

---

## 9 · Phase W11–W12 — pilot and evaluate

| Existing/New | Key | Action | Proposed Title | Area | Phase | MVP | Pri | Thesis | Reason |
|---|---|---|---|---|---|---|---|---|---|
| New | — | CREATE | Final evaluation execution | Research | W11-W12 | REQUIRED | P1 | **YES** | `V-05`. ISO 9241-11 + GQM + SUS + task and workflow metrics. **The result** |
| New | — | CREATE | Data export and offboarding | SaaS | W11-W12 | RECOMMENDED | P2 | — | `SA-04`. `pg_dump` plus a volume copy under instance-per-tenant |

---

## 10 · DEFER — POST-MVP, no work this semester

**21 existing issues.** Status changes to reflect reality; no deletion.

| Key | Title | Reason |
|---|---|---|
| IR-19 | NL Research Query & Persistent History | **SPLIT** — single-shot Q&A survives in IR-35; *persistent history* deferred (ADR-006) |
| IR-34 | Conversation CRUD Endpoints | `Conversation`/`ChatMessage` are field-less stubs |
| IR-20, IR-36, IR-37, IR-38 | Full-text AI summarization (story + 3 subtasks) | Separate LLM feature, UI and cost line |
| IR-25, IR-48, IR-49 | KPI pipeline metrics (story + 2 subtasks) | **Already Phase 2 in SRS §31.** Week 11–12 analytics come from `W-04`'s audit export |
| IR-10, IR-16, IR-17, IR-18 | Download requests and watermarking | Not in the pilot workflow. `WatermarkService` is a forensic subsystem |
| IR-21, IR-39, IR-40 | Data table dashboard | `DataTable.tsx` **already exists** with pagination — the ticket says "build". Broad adoption is Phase 2 |
| IR-29, IR-32 | Epic 4, Epic 7 | Both epics entirely post-MVP |

**Task specs given no card** (documented in `12-scope-cuts.md`): `W-06` Excel import · `B-08` N+1 queries · `T-04` frontend test harness · `SA-03` pooled multi-tenancy (**DO NOT BUILD YET**) · `W-05` `ReviewPolicy` consolidation (`W-01` delivers most of the value) · Docling-serve · full-text chunking · record access PIN.

---

## 11 · RECOMMEND REMOVE — 2

| Key | Title | Reason |
|---|---|---|
| IR-33 | [Frontend] Conversational Chat Window & Sidebar | Marked `In Review`. `RAGChatPage` + 7 components (748 lines) are **routed to nothing**, built against models that are field-less stubs. ADR-006 excludes conversational memory. Recommend **unroute and close**, not delete from git |
| IR-46 | [Backend] Security Logger Utility Class | **Superseded by `W-04`**, which needs workflow event types, not a logger wrapper. Recommend rewriting IR-46 into `W-04` (§8) rather than keeping both |

---

## 12 · CLOSE — delivered

| Key | Title | Evidence |
|---|---|---|
| IR-50 | Architecture Refactoring Validation & Task Breakdown | All 4 acceptance criteria met by `docs/architecture-review/` + `docs/architecture-tasks/`. No production code changed |
| IR-51 | Architecture Grill-Me & MVP Decision Review | All 6 met: `docs/adr/` (11 ADRs), MVP go/no-go, framework evaluation. No production code changed |

---

## 13 · Status corrections — 5 issues assert something false

| Key | Current | Proposed | Evidence |
|---|---|---|---|
| IR-3 | **Done** | In Progress | `config/urls.py` cannot import — no endpoint responds |
| IR-12 | **Done** | In Progress | 2 of 3 stated tasks do not work: no queue routing, extraction imports 3 absent libraries, no ownership check |
| IR-2 | In Review | In Progress | Refresh interceptor never calls `setTokens` |
| IR-4 | In Review | In Progress | Audit missed 4 findings |
| IR-7 | In Review | In Progress | 12 endpoints have no object-level check |

---

## 14 · Label scheme

Applied to every card. This is what makes the board pull-based without assignment.

| Group | Labels |
|---|---|
| MVP | `mvp-blocker` `mvp-required` `mvp-recommended` `post-mvp` `optional` `do-not-build` |
| Phase | `phase-w1-w2` `phase-w3` `phase-w4-w7` `phase-w8-w9` `phase-w10` `phase-w11-w12` `post-semester` |
| Area | `area-architecture` `area-backend` `area-frontend` `area-workflow` `area-security` `area-rag` `area-saas` `area-deployment` `area-testing` `area-mvp-validation` `area-uiux` `area-research` `area-documentation` `area-commercialization` |
| Thesis | `thesis-critical` |
| Flow | `blocked` `ready-to-pull` |

**Priority** maps to the Jira field: P0 → `Highest`, P1 → `High`, P2 → `Medium`, P3 → `Low`.

**No assignees.** Team members pull. `ready-to-pull` means every dependency is done.

---

## 15 · Decision required — 5

These block work and I will not guess at them.

| # | Question | Blocks | Status |
|---|---|---|---|
| 1 | **Is external AI data transmission permitted?** | `R-02`, `R-04` — the entire RAG track | **UNCONFIRMED.** Standing instruction: do not assume permission. If refused, ADR-008's FTS fallback becomes the product and RAG becomes Phase 2 |
| 2 | **Does the programme expect a commercial validation track?** (SBCVM sense 3, Lean Canvas, BMC, willingness-to-pay) | A `Commercialization` epic and ~4 cards for W11-W15 | **NEEDS ADVISER CONFIRMATION.** Documented as a gap in `mvp-validation/00`. **No cards proposed until confirmed** — creating them unasked is exactly the backlog inflation to avoid |
| 3 | **Will the SRS amendment for Docling-serve deferral be accepted?** | `F-03`, `R-01` | Docling is SRS-specified in four places. Deferral needs the Week 3 amendment |
| 4 | **Is CIT-U infrastructure confirmed for deployment?** | `D-03`, `SA-02` | Interim VPS assumed. Migration path stays documented, not built |
| 5 | **Jira issue-type check** | All new cards | New cards proposed as **Story under Epic**. If the project's scheme requires Task or Subtask, I will map accordingly at apply time |

---

## 16 · Summary of proposed changes

| Action | Count |
|---|---|
| **CREATE** — new cards | **37** (32 work cards + 5 epics) |
| **REWRITE** — existing, retitled and rescoped | **14** |
| **KEEP** — existing, unchanged scope | **3** |
| **SPLIT** | **2** (IR-7, IR-19) |
| **MERGE** — folded into another card | **3** (IR-40, IR-45, IR-46) |
| **DEFER** — POST-MVP | **21** |
| **RECOMMEND REMOVE** | **2** |
| **CLOSE** — delivered | **2** |
| **STATUS CORRECTION** | **5** |
| **Label/priority applied** | **all 56 active cards** |

### Final MVP Kanban summary

| | Count |
|---|---|
| **Total active MVP cards** | **56** |
| P0 blockers (W1-W2, W3) | **14** |
| P1 thesis-critical | **11** |
| P1 supporting | **19** |
| P2 supporting | **12** |
| Post-MVP / deferred | **21 existing + 8 specs** |
| Recommended for removal | **2** |
| Unresolved dependencies | **5** (§15) |

**Hard deadlines.** `W-04` must be live by end of Week 10 or there is no research data. No public URL until `S-01`, `S-02`, `S-03`, `S-04`, `SC-01` are all done. The RAG timebox expires end of Week 6 with a pre-committed fallback.
