# Security

**Purpose.** How IRIS protects institutional research and IP data, and what is currently wrong.
**Owns.** Authentication, authorization, file access, API security, secrets, boundaries, external AI, privacy, audit, dependencies, deployment security, and the open risk list.
**Does not own.** Requirements ([`../SRS.md`](../SRS.md) NFR-S1…S6) · the authorization decision ([`../adr/009-authorization-model.md`](../adr/009-authorization-model.md)) · process ([`../engineering/SDLC.md`](../engineering/SDLC.md)).
**Authority.** Authoritative for security posture and known defects.
**Update when.** A control changes, a defect is found or closed, or a boundary moves.

> **A separate risk register is not maintained.** The open-defect table in §11 is the register. Two documents listing the same risks would drift, and the audit showed no need for the split.

---

## 1 · What is being protected

Unpublished research, IP disclosures before filing, ethics submissions, and personal data of students, advisers and reviewers. **A disclosure leak before filing can destroy patentability** — the consequence is not reputational, it is legal and irreversible.

Under RA 10173 (Data Privacy Act), personal data in submissions and consent records is in scope.

---

## 2 · Authentication

JWT via SimpleJWT. Token rotation and blacklisting after rotation are **correctly configured** — this part of the earlier audit stands.

| Control | State |
|---|---|
| HS256, rotation, blacklist-after-rotation | ✅ Correct |
| Access token lifetime | ⚠️ Configured, but **30-minute inactivity expiry does not occur** — NFR-S2 unmet |
| Refresh handling in the client | ❌ Interceptor writes `localStorage` nothing reads, never calls `setTokens`, no deduplication against rotation — concurrent 401s force a hard logout |
| Account lockout | ⚠️ Event types exist in the audit model; enforcement unverified |

---

## 3 · Authorization

Governed by [ADR-009](../adr/009-authorization-model.md). **This is the weakest area of the system.**

`core/permissions.py` defines eleven permission classes. **Five are referenced nowhere.** The classes were written; applying them did not happen.

| Defect | Detail |
|---|---|
| **Record visibility** | `RecordViewSet.get_queryset` filters **only on `list`**. `retrieve` returns any record to any authenticated user, including unpublished drafts and their review comments |
| **Document endpoints** | Six `documents/` endpoints have **no object-level check** — any user can upload into any record |
| **`is_staff` bypass** | `is_django_staff()` returns true for `is_staff` or `is_superuser`. Migration `accounts/0005` sets `is_staff=True` for RDCO, KTTO, ITSO and IERC — so `IsAdmin`'s `ADMIN_ROLES` **constrains nobody**, and `_can_review` short-circuits |
| **Audit access** | Backend uses `IsAdminUser`, which under that seeding admits **all four offices**. The frontend constant `AUDIT_LOG_ROLES = [RDCO]` is correct; the backend is not |
| **Storage app** | Six further endpoints with no authorization |

**Twelve endpoints in total have no object-level check.**

**The rule going forward:** one `visible_to(user)` predicate, defined once, applied on **every** action — and reused by RAG retrieval, so a citation can never point at a record the viewer cannot open.

---

## 4 · File and document access

**Was the highest-severity finding. Closed by [IR-152](https://citiris.atlassian.net/browse/IR-152) (`S-01`), PR #26.**

`frontend/nginx.conf` used to serve the media volume directly:

```nginx
location /media/ {              # removed
    alias /usr/share/nginx/html/media/;
    expires 30d;
}
```

`RecordUpload.file` uses `upload_to="documents/"`, so filenames derive from the uploaded name and are guessable — every uploaded document was readable at `https://host/media/documents/<filename>` with no authentication. Demonstrated on a real upload before the fix:

```
before: GET /media/abstracts/thesis-manuscript.pdf  ->  200
after :                                             ->  404
```

It was masked only by the production port mismatch, so fixing the port first would have exposed every document in the system. That ordering constraint is now discharged.

**Three routes served those files, and all three are gone:** the nginx `location` block, the `media_files` mount into the prod web container, and Django's `static(MEDIA_URL)` route under `DEBUG` — the last of which meant uploads were unauthenticated in every developer environment, not just production.

Files are served only through `RecordUploadDownloadView` / `RecordFileDownloadView`, which check record ownership and write an audit event. Regression guards live in `apps/documents/tests.py`; note that the two asserting on `nginx.conf` and `docker-compose.prod.yml` **skip inside the backend container**, which mounts only `backend/`, so they run only on a full checkout.

If download throughput ever matters, the answer is `X-Accel-Redirect` — nginx serves the bytes, Django still authorises — never a public alias.

---

## 5 · API security

- All endpoints require authentication except login, signup and activation
- Object-level authorization is the gap (§3)
- **404 and 403 must be indistinguishable** for a record the user may not see — a 403 confirms the record exists
- Result counts must be computed **after** visibility filtering; a pre-filter count discloses existence in a smaller package

---

## 6 · Secrets and configuration

| Defect | Required state |
|---|---|
| Hardcoded database credentials | From environment; **rotate anything previously committed** |
| `CORS_ALLOW_ALL_ORIGINS` with `CORS_ALLOW_CREDENTIALS` | Explicit `CORS_ALLOWED_ORIGINS` allowlist |
| `ALLOWED_HOSTS` unset | Explicit host list |
| `DEBUG` | `False` in production |

`backend/.env.example` documents required keys and holds no real values. **The application should refuse to start on a missing required secret** rather than defaulting silently. CI runs a secret scan on every push.

---

## 7 · Boundaries

Five services: `db`, `redis`, `backend`, `worker`, `frontend`. Only the frontend is published. PostgreSQL and Redis are not exposed outside the Compose network.

**`ai-gateway` is declared in both Compose files, and since `7f73e97` an `ai/` source tree exists for it.** It is not deployed and must not be: the service defines **no authentication** on either endpoint while holding the provider API key, and sets `allow_credentials=True` with `allow_methods=["*"]`. [ADR-010](../adr/010-deployment-topology.md) rejects a separate gateway — it would duplicate authentication and visibility filtering, creating a second place for every defect in §3 to recur. The code as written is that duplication, already exhibiting the defects. [ADR-012](../adr/012-ai-provider-abstraction-not-a-service.md) records the decision not to adopt it.

**Tenancy:** instance-per-tenant ([ADR-005](../adr/005-instance-per-tenant.md)). Each institution gets its own database and media volume, so cross-tenant leakage is *structurally impossible* rather than prevented by a filter. Given twelve live instances of "a query that forgot its filter", this was the decisive argument against pooled multi-tenancy.

---

## 8 · External AI services

**Permission for external AI data transmission is UNCONFIRMED.** Do not assume it.

Until confirmed in writing:
- No unpublished research content leaves the deployment
- [ADR-008](../adr/008-ai-degradation-to-fts.md)'s PostgreSQL full-text fallback is the product; RAG is additive
- If refused, RAG becomes Phase 2 and search still works — `search_vector` already exists

When permitted: only what retrieval requires, never whole documents by default; the provider and data handling are recorded; **retrieval is visibility-filtered before the prompt is built.**

---

## 9 · Privacy

DPA consent is captured at submission (FR-M6-02) and logged with user, timestamp and IP. Consent text must be **readable**, not a click-through.

Staged data policy: **synthetic data only** until governance approval · approved real data thereafter · sensitive data never without explicit approval. The Weeks 1-2 validation instance carries synthetic data only.

Research artefacts aggregate; they do not copy institutional records.

---

## 10 · Audit

`AuditEvent` defines 14 types — all authentication, file or account. **No workflow event exists.**

Two consequences: the audit log cannot answer any question about the workflow, and the research metrics have no source. Immutability (NFR-S5) has no database-level guard, and the frontend type declares only 7 of the 14 types, so half cannot be filtered.

---

## 11 · Open risks

| # | Risk | Severity | Status | Item |
|---|---|---|---|---|
| 1 | ~~Every uploaded document publicly readable via `/media/`~~ | **Critical** | **Closed** — route removed, 200 → 404 verified | IR-152 (PR #26) |
| 2 | Any authenticated user can read any record via `retrieve` | **Critical** | Open | IR-60 |
| 3 | Six `documents/` endpoints without ownership checks | **Critical** | Open | IR-60 |
| 4 | Six `storage` endpoints without authorization | **High** | Open — closed by deletion | IR-62 |
| 5 | `is_staff` seeding voids role-based restriction | **High** | Open | Epic C |
| 6 | Hardcoded credentials, permissive CORS, unset `ALLOWED_HOSTS` | **High** | Open | IR-61 |
| 7 | Audit readable by all four offices, not only RDCO | **Medium** | Open | Epic C |
| 8 | No session inactivity expiry (NFR-S2) | **Medium** | Open | Epic C |
| 9 | Audit log not immutable (NFR-S5) | **Medium** | Open | Epic C |
| 10 | No automated tests — no regression detection on any control | **High** | Open | Epic C |
| 11 | External AI transmission permission unconfirmed | **Medium** | **Decision required** | — |
| 12 | No backups, no rehearsed restore before the pilot | **High** | Open | Epic D |

**None of risks 1, 2, 3, 4 or 6 may remain open when a public URL is published.** That is the deployment gate, and it is enforced by IR-63.

---

## 12 · Reporting a vulnerability

Report privately to the team lead. Do not open a public issue. Include what you found, how to reproduce it, and what it exposes. During the pilot, a vulnerability affecting real institutional data is escalated immediately and the instance is taken offline if disclosure is ongoing.
