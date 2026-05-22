# IRIS — Requirements Traceability Matrix (RTM)

Maps **SRS functional and non-functional requirements** to implementation artifacts and verification status. Update rows in the same PR that implements or verifies a requirement.

**Legend — Status**

| Status | Meaning |
|--------|---------|
| **Planned** | Not started |
| **In progress** | Active development |
| **Implemented** | Code merged; not fully tested |
| **Verified** | Tested per [TEST_PLAN](TEST_PLAN.md) |
| **Deferred** | Blocked on spec (e.g. M5/M7) |
| **N/A** | Out of current release scope |

---

## Module 1 — Backend optimization & responsive UI

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M1-01 | Login, JWT, 3-strike lockout, role redirect | `apps/accounts`, axes | `LoginPage`, `AuthAlert`, `AccountLockedModal` | AUTH-01–03 | **Implemented** |
| FR-M1-02 | IP disclosure form (responsive) | `apps/records` | `AddRecordPage`, steps, schema | REC-01–03 | **In progress** |

---

## Module 2 — RAG indexing

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M2-01 | PDF text extraction | `apps/ai` | — | AI-* | **Planned** |
| FR-M2-02 | Vector storage | `apps/ai` | — | AI-* | **Planned** |
| FR-M2-03 | Indexing status notification | `apps/notifications` | Toast / notifications | AI-* | **Planned** |

*Expand rows from SRS §3.2.2 when implementing.*

---

## Module 3 — RAG chatbot

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M3-01 | Conversational RAG UI | `apps/ai`, `api/ai.ts` | `AIHubPage` | AI-01 | **Planned** |

---

## Module 4 — Summarizer

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M4-01 | Full-text summarize | `apps/ai` | Record detail action | AI-03 | **Planned** |

---

## Module 5 — Hierarchical submission workflow

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M5-01 | Multi-stage approval chain | `records.services`, reviews | `PendingRecordsPage`, `EvaluationPage` | REV-* | **Deferred** (partial generic UI) |

**Note:** SRS chain (Adviser → KTTO → ITSO → IERC → RDCO) may differ from current `PIPELINE_STATUS` in code. Do not mark **Verified** until OD-01 closed in [SOFTWARE_ENGINEERING_PLAN](SOFTWARE_ENGINEERING_PLAN.md).

| Sub-feature | Wireframe / UI | Status |
|-------------|----------------|--------|
| KTTO routing interface | Figure 32 | **Deferred** |
| RDCO archiving interface | Figure 33 | **Deferred** |
| Return for revision | Evaluation form | **In progress** |

---

## Module 6 — Security and authentication

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M6-01 | JWT auth & session management | SimpleJWT, settings | `api/client.ts`, auth store | AUTH-01,07 | **Implemented** |
| FR-M6-02 | DPA consent & audit logging | `apps/audit` | Consent modal (TODO) | SEC-01 | **Planned** |
| FR-M6-03 | RBAC enforcement | `core/permissions.py` | `RoleRoute`, `useRole` | SEC matrix | **In progress** |

---

## Module 7 — KPI / admin dashboards

| FR-ID | Requirement (summary) | Backend | Frontend | Tests | Status |
|-------|----------------------|---------|----------|-------|--------|
| FR-M7-* | RDCO pipeline KPI dashboard | TBD | TBD | TBD | **Deferred** |

*Add FR rows when Module 7 SRS is finalized.*

---

## Module 6 extension — Project features (repo)

| ID | Requirement (summary) | Backend | Frontend | Status |
|----|----------------------|---------|----------|--------|
| EXT-01 | Self-service signup | accounts | `SignupPage` | **Implemented** |
| EXT-02 | Email verification | accounts | `EmailVerifyPage` | **Implemented** |
| EXT-03 | Role request approval | accounts admin | TODO `RoleRequestsPage` | **Planned** |

---

## Non-functional requirements

| NFR-ID | Requirement (summary) | Evidence | Status |
|--------|----------------------|----------|--------|
| NFR-S1 | Encryption at rest | IT volume encryption | **Planned** (ops) |
| NFR-S2 | 30 min idle session expiry | FE idle handler (TODO), JWT config | **In progress** |
| NFR-S3 | HTTPS TLS 1.2+ | Nginx/prod deploy | **Planned** |
| NFR-S4 | Role boundary enforcement | Permissions + TEST_PLAN §5 | **In progress** |
| NFR-S5 | Audit 12 mo retention, immutable UI | `audit` app, ops policy | **In progress** |
| NFR-P1 | 100 concurrent users, <2s avg | JMeter report | **Planned** |
| NFR-U3 | Mobile 360px+ | Responsive auth/disclosure | **In progress** |

---

## API endpoint index (informal)

*Formalize in `docs/API.md` when stable.*

| Method | Path | FR / purpose | Auth |
|--------|------|--------------|------|
| POST | `/api/auth/login/` | FR-M1-01 | Anon |
| POST | `/api/auth/register/` | EXT-01 | Anon |
| POST | `/api/auth/token/refresh/` | FR-M6-01 | Refresh |
| GET | `/api/records/` | M1/M5 | JWT |
| POST | `/api/records/` | FR-M1-02 | JWT |
| GET | `/api/dashboard/stats/` | Dashboard | JWT |

*Append rows as endpoints are added.*

---

## Change log (matrix)

| Date | Change |
|------|--------|
| 2026-05 | Initial RTM from SRS structure and repo snapshot |

---

## How to update

1. Pick **FR-ID** from SRS.  
2. Fill **Backend** / **Frontend** columns with app paths or PR link.  
3. Link **Tests** to [TEST_PLAN](TEST_PLAN.md) TC-ID.  
4. Set **Status** only after appropriate test level.  

---

*SRS source: `IRIS Software Engineering_SRS.pdf` v1.0 (17/04/2026)*
