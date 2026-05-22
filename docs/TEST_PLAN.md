# IRIS — Test Plan

Verification strategy for IRIS aligned with the SRS, [SDLC Process](SDLC_PROCESS.md), and [Security](SECURITY.md) requirements.

**Document version:** 1.0  
**Status:** Living document

---

## 1. Purpose and scope

### 1.1 Purpose

Define **what** is tested, **how**, and **when** tests are required so releases meet functional and non-functional requirements without relying on ad-hoc manual checks alone.

### 1.2 In scope

- Authentication, session, lockout (Module 1 / 6)  
- RBAC and API authorization (NFR-S4)  
- IP disclosure and record CRUD (Module 1)  
- Generic review actions (Module 5 — until spec expands)  
- Notifications, audit read paths  
- Security negative cases (403, lockout, session expiry)  
- MVP performance baseline (NFR-P1 — 100 users) before production  

### 1.3 Out of scope (current phase)

- Full KTTO routing UI test cases (pending SRS)  
- RDCO KPI dashboard accuracy (pending Module 7)  
- Enterprise 1,000-user stress tier  
- Formal penetration test (recommend before production; optional third party)  

---

## 2. Test levels

| Level | Tool / method | Owner | When |
|-------|---------------|-------|------|
| **Unit** | pytest (backend), Vitest (optional FE) | Dev | Per module |
| **API / integration** | pytest-django, DRF client, Postman collection | Dev/QA | Per endpoint |
| **System / manual** | Browser, role accounts | QA/Dev | Per sprint |
| **E2E** | Playwright (planned) | QA | Pre-UAT |
| **Performance** | Apache JMeter | QA/Ops | Pre-production |
| **UAT** | Stakeholder scripts | CIT-U | Milestone M5 |
| **Security** | Role matrix + checklist | Dev/Security | Pre-prod |

---

## 3. Test environment

| Item | Requirement |
|------|-------------|
| Database | PostgreSQL with seeded roles, colleges, courses |
| Backend | `python manage.py runserver` or staging URL |
| Frontend | `npm run dev` or production build |
| Redis + Celery | Required for email verification tests |
| Test accounts | One user per role (see §5) |
| Email | SMTP sandbox or manual `is_verified=True` for dev |

---

## 4. Entry and exit criteria

### 4.1 Entry (start test cycle for a milestone)

- [ ] Build deployed to staging (or agreed local setup)  
- [ ] Migrations applied  
- [ ] Seed data documented  
- [ ] Traceability matrix shows features *Ready for test*  
- [ ] Known defects logged (no blocking P1 without waiver)  

### 4.2 Exit (UAT / release candidate)

- [ ] All **P0** FRs *Verified* in [TRACEABILITY_MATRIX](TRACEABILITY_MATRIX.md)  
- [ ] Role matrix §5 executed — no critical failures  
- [ ] Security PR checklist completed for release branch  
- [ ] No open **Critical/High** risks without acceptance in [SECURITY_RISK_REGISTER](SECURITY_RISK_REGISTER.md)  
- [ ] Changelog updated  

---

## 5. Role-based test matrix (NFR-S4)

Execute as **API** (preferred) and **UI** smoke. Expected: forbidden roles receive **403** (or 401 if unauthenticated).

| Action | Student | Adviser | KTTO | RDCO | ITSO | TBI |
|--------|:-------:|:-------:|:----:|:----:|:----:|:---:|
| Login / refresh token | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Submit IP disclosure | ✓ | — | — | — | — | — |
| View own records | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| View published catalog | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Review pending queue | — | ✓ | ✓ | ✓ | — | ✓ |
| Approve/decline evaluation | — | ✓* | ✓* | ✓* | — | ✓* |
| Admin users list | — | — | ✓ | ✓ | ✓ | ✓ |
| Audit log read | — | — | ✓ | ✓ | ✓ | ✓ |
| Import records | — | ✓ | ✓ | ✓ | ✓ | ✓ |

\*Only when record is in that role’s pipeline stage (after M5 FSM finalized).

**Negative tests (mandatory):**

- Student `POST` approve on another user’s record → **403** + audit.  
- Unauthenticated `GET /api/records/` → **401**.  
- Locked account login after 3 failures → lock message / 403 per axes.  

---

## 6. Functional test cases (priority)

### 6.1 Authentication — FR-M1-01, FR-M6-01

| TC-ID | Description | Steps | Expected |
|-------|-------------|-------|----------|
| AUTH-01 | Valid login | Valid credentials | JWT returned; redirect to app |
| AUTH-02 | Invalid password | Wrong password ×1–2 | Generic error; attempt count shown (UI) |
| AUTH-03 | Account lockout | Wrong password ×3 | 15 min lock; modal; axes blocks login |
| AUTH-04 | Unverified email | Login before verify | 403 / warning; no full access |
| AUTH-05 | Register + verify | Signup → email link | Account active; can login |
| AUTH-06 | Session expired | Idle 30 min or `?reason=session_expired` | Redirect login; banner |
| AUTH-07 | Refresh rotation | Use refresh token | New access; old refresh blacklisted if rotated |

### 6.2 IP disclosure — FR-M1-02

| TC-ID | Description | Expected |
|-------|-------------|----------|
| REC-01 | Submit required fields + PDF | 201; status draft/review |
| REC-02 | Abstract > 500 chars | Validation error |
| REC-03 | Mobile 360px layout | Usable form, no horizontal scroll |
| REC-04 | DPA not accepted (when implemented) | Cannot submit |

### 6.3 Review — FR-M5-01 (generic until M5 final)

| TC-ID | Description | Expected |
|-------|-------------|----------|
| REV-01 | Approve with comment | Status advances per API rules |
| REV-02 | Decline with comment | Status declined; notify student |
| REV-03 | Return for revision | Mandatory comment; student notified |
| REV-04 | Wrong role approve | 403; audit security event |

### 6.4 Security & compliance — FR-M6-02, FR-M6-03, NFR-S5

| TC-ID | Description | Expected |
|-------|-------------|----------|
| SEC-01 | DPA consent logged | Audit entry with user, timestamp |
| SEC-02 | Audit UI read-only | No delete button; API no DELETE for audit |
| SEC-03 | HTTPS redirect | Prod HTTP → HTTPS |

### 6.5 AI (when in scope) — Modules 2–4

| TC-ID | Description | Expected |
|-------|-------------|----------|
| AI-01 | Chat with indexed doc | Response or graceful error |
| AI-02 | AI service down | Banner; core app still works |
| AI-03 | Summarize record | Summary or error message |

---

## 7. Non-functional tests

| NFR | Test approach | Pass criteria |
|-----|---------------|---------------|
| NFR-P1 | JMeter 100 VU, 30 min | Avg response < 2s; zero session failures |
| NFR-S2 | Manual idle + token expiry | Logout at 30 min inactivity |
| NFR-S3 | SSL Labs / curl | TLS 1.2+ on prod |
| NFR-S4 | Role matrix §5 | No unauthorized data in response body |
| NFR-S5 | Ops review | Retention policy + backup restore sample |
| NFR-U3 | Browser 360px width | Login, disclosure, key pages usable |

---

## 8. Automation roadmap

| Priority | Package | Coverage target |
|----------|---------|-----------------|
| P0 | pytest-django | Auth login, lockout, permissions on records/reviews |
| P1 | pytest + factories | Workflow transitions when M5 stable |
| P2 | Playwright | Login → submit → logout |
| P3 | JMeter | NFR-P1 baseline |

Add to `backend/requirements/development.txt` when implemented:

```
pytest-django>=4.8
factory-boy>=3.3
```

---

## 9. Defect management

| Severity | Definition | SLA (team agreement) |
|----------|------------|----------------------|
| P1 | Security bypass, data loss, prod down | Fix before release |
| P2 | Major feature broken | Fix in current sprint |
| P3 | Minor UI / edge case | Backlog |
| P4 | Cosmetic | Backlog |

Track in GitHub Issues with labels: `bug`, `security`, `regression`.

---

## 10. UAT package (stakeholder)

Deliver to RDCO/KTTO for sign-off:

1. Test environment URL + test accounts (per role)  
2. Printed role matrix §5 results  
3. Demo script: register → disclose → review → publish  
4. Known limitations (M5/M7 pending)  
5. Open decisions from engineering plan §10  

**UAT sign-off form (template):**

| FR-ID | Pass / Fail / Deferred | Comments | Signatory |
|-------|------------------------|----------|-----------|
| FR-M1-01 | | | |
| FR-M1-02 | | | |
| … | | | |

---

## 11. Test deliverables per release

| Deliverable | Location |
|-------------|----------|
| Test plan | This document |
| Traceability | [TRACEABILITY_MATRIX](TRACEABILITY_MATRIX.md) |
| Manual results | `docs/test-results/YYYY-MM-DD-milestone.md` (create when running UAT) |
| Automated tests | `backend/tests/` (future) |
| Performance report | `docs/test-results/jmeter-mvp.pdf` (future) |

---

## 12. References

- [SOFTWARE_ENGINEERING_PLAN](SOFTWARE_ENGINEERING_PLAN.md)  
- [SECURITY](SECURITY.md)  
- [frontend/docs/FRONTEND_IMPLEMENTATION.md](../frontend/docs/FRONTEND_IMPLEMENTATION.md) — auth manual test steps  

---

*Update test cases when SRS Modules 5 and 7 are finalized.*
