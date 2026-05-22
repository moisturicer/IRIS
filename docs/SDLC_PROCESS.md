# IRIS — SDLC Process

Defines the **software development life cycle** for IRIS: phases, artifacts, quality gates, version control, and release practices. Complements the [Software Engineering Plan](SOFTWARE_ENGINEERING_PLAN.md).

---

## 1. Lifecycle overview

| Phase | Primary activities | Key artifacts | Gate |
|-------|------------------|---------------|------|
| **1. Initiation & planning** | Scope, milestones, risks | Engineering plan, risk register | Plan approved by lead |
| **2. Requirements** | SRS review, traceability, open decisions | Traceability matrix, OD log | FR accepted or deferred |
| **3. Design** | SDD + API contracts, wireframes | SDD sections, API draft, UI plan | Design review (no M5/M7 lock-in without sign-off) |
| **4. Implementation** | Backend API → frontend → tests | Code, migrations, PR | CI/manual checks pass |
| **5. Verification** | Test execution, security checks | Test results, updated risks | Exit criteria in [TEST_PLAN](TEST_PLAN.md) |
| **6. Deployment** | Staging → production | Release notes, changelog | Deploy checklist |
| **7. Operations** | Monitor, patch, audit retention | Logs, incidents | Post-release review |

Phases **2–5** repeat per feature or sprint.

---

## 2. Requirements phase

### 2.1 Inputs

- SRS (functional `FR-M*`, non-functional `NFR-*`)
- SDD (components, sequences) where current
- Stakeholder notes (RDCO, KTTO, IT)

### 2.2 Activities

1. Identify **FR-ID** for the sprint task.  
2. Check [TRACEABILITY_MATRIX](TRACEABILITY_MATRIX.md) — status must not be *Verified* until tested.  
3. If Module **5** or **7**, confirm against [SOFTWARE_ENGINEERING_PLAN §10](SOFTWARE_ENGINEERING_PLAN.md#10-open-decisions-spec-uncertainty) — do not implement blocked UI.  
4. Log gaps in open decisions table or new SRS change request.

### 2.3 Outputs

- Updated traceability row  
- Optional: `docs/features/FR-Mx-xx-short-name.md` (one-pager per feature)

### 2.4 Acceptance

- Requirement is **testable** (given/when/then or checklist).  
- API and permission rules are stated before UI polish.

---

## 3. Design phase

### 3.1 Design hierarchy

1. **Data model** — Django models, migrations (`backend/apps/`)  
2. **API** — serializers, views, permissions (`core/permissions.py`)  
3. **UI** — routes, pages, wireframe states (`frontend/src/`)  

API and permissions **before** pixel-perfect UI.

### 3.2 Design review checklist

- [ ] Matches SRS primary flow  
- [ ] Alternative flows (lockout, 403, session expiry) documented  
- [ ] RBAC: which roles can call each endpoint  
- [ ] Audit events identified (login fail, approve, 403 bypass attempt)  
- [ ] Mobile width 360px for student-facing forms (NFR-U3)  
- [ ] No secrets in frontend bundle  

### 3.3 Spec-stable vs spec-pending

| Build now | Wait for sign-off |
|-----------|-------------------|
| Generic tables, forms, app shell | KTTO routing screen |
| `pipeline_status` from API | RDCO KPI dashboard |
| Approve / decline / return + comment | Per-stage digital signature UX |

---

## 4. Implementation phase

### 4.1 Branching model

| Branch | Use |
|--------|-----|
| `main` | Production-ready history |
| `develop` | Optional integration branch |
| `feature/<name>` | One feature or FR group |
| `fix/<name>` | Bugfix |
| `docs/<name>` | Documentation-only |

**Naming:** `feature/fr-m1-02-disclosure-form`, `fix/login-lockout-timezone`

### 4.2 Commit conventions (recommended)

```
<type>(<scope>): <short description>

[optional body]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`  
Scopes: `auth`, `records`, `review`, `api`, `ui`, `deps`

### 4.3 Pull request workflow

1. Rebase or merge latest `main` / `develop`.  
2. PR description must include:  
   - **FR-ID(s)** / **NFR-ID(s)**  
   - Summary of behavior change  
   - Test notes (manual steps or automated)  
   - Screenshots for UI (mobile + desktop if applicable)  
3. Reviewer checks:  
   - RBAC on API (not only hidden nav)  
   - No `.env` or credentials  
   - Docs updated if behavior changed  
4. Merge after approval; delete feature branch.

### 4.4 Coding standards

| Area | Standard |
|------|----------|
| Backend | Django/DRF patterns; permissions on every sensitive view |
| Frontend | TypeScript strict; shared `ROLES` / `PIPELINE_STATUS` from `lib/constants.ts` |
| RBAC | Backend `core/permissions.py` ↔ frontend `lib/constants.ts` names **must match** DB `Role.name` |
| Secrets | `python-decouple` / env only |
| AI keys | Server-side only; never `VITE_*` for Anthropic |

### 4.5 Per-feature implementation order

1. Model + migration  
2. Serializer + permission classes  
3. URL + view/tests  
4. `frontend/src/api/*.ts` + types  
5. Page + components  
6. Update traceability + frontend plan + changelog  

---

## 5. Verification phase

See [TEST_PLAN.md](TEST_PLAN.md).

### 5.1 Minimum before merge

- Happy path manually tested  
- At least one negative case (wrong role, invalid input)  
- No regression on login / session for auth-touching PRs  

### 5.2 Before UAT

- Role matrix executed  
- Security checklist in [SECURITY.md](SECURITY.md) § Deployment  
- Risk register reviewed  

---

## 6. Deployment phase

### 6.1 Environments

| Env | Branch trigger | Notes |
|-----|----------------|-------|
| Local | N/A | `DEBUG=True`, CORS loose in dev settings |
| Staging | `develop` or release tag | `DEBUG=False`, production-like |
| Production | `main` + tag | HTTPS, strong secrets, Celery workers |

### 6.2 Pre-deployment checklist

- [ ] `DEBUG=False`  
- [ ] Unique `SECRET_KEY`  
- [ ] `ALLOWED_HOSTS` set  
- [ ] `FRONTEND_URL` production domain  
- [ ] Migrations applied  
- [ ] Celery + Redis running  
- [ ] SMTP configured for email verify  
- [ ] CORS not `ALLOW_ALL` (production settings)  
- [ ] Static/media backup strategy documented  

### 6.3 Release steps

1. Freeze scope → update [CHANGELOG](../CHANGELOG.md)  
2. Tag version `vX.Y.Z`  
3. Deploy backend (Gunicorn) + frontend build (Nginx)  
4. Smoke test: login, one record read, audit log write  
5. Post-release: monitor errors, axes lockouts, disk  

---

## 7. Operations & maintenance

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Dependency updates (security patches) | Monthly | Dev |
| DB backup verification | Monthly | IT |
| Audit log retention check (NFR-S5, 12 mo) | Quarterly | IT + lead |
| Risk register review | Per milestone | Lead |
| SRS/SDD version sync | When PDF revision ships | Product |

### 7.1 Incident severity

| Level | Example | Response |
|-------|---------|----------|
| P1 | Suspected data breach, auth bypass | Contain, rotate secrets, notify IT/security |
| P2 | Service down | Restore from backup / restart workers |
| P3 | Degraded AI / email | Communicate; non-core paths work |

---

## 8. Quality gates (summary)

| Gate | Criteria |
|------|----------|
| **G1 — Start implementation** | FR traced; design notes or SDD section identified |
| **G2 — Merge PR** | Review approved; manual test notes; no secrets in diff |
| **G3 — Sprint / milestone done** | Traceability updated; risks reviewed |
| **G4 — UAT entry** | P0 features *Ready for UAT* in matrix |
| **G5 — Production** | [SOFTWARE_ENGINEERING_PLAN §13](SOFTWARE_ENGINEERING_PLAN.md#13-success-criteria-release-readiness) |

---

## 9. Meetings and cadence (recommended)

| Meeting | Cadence | Outcome |
|---------|---------|---------|
| Sprint planning | Biweekly | FR IDs assigned |
| Daily standup | Optional | Blockers |
| Design / spec review | As needed for M5/M7 | OD table updated |
| Demo | End of sprint | Stakeholder feedback |
| Retrospective | End of sprint | Process tweaks to this doc |

---

## 10. Tooling

| Tool | Purpose |
|------|---------|
| Git / GitHub | Version control, PRs |
| PostgreSQL | Primary datastore |
| Redis + Celery | Async tasks |
| Django Admin | Emergency data ops (staff only) |
| Vite dev server | Frontend local |
| JMeter (planned) | NFR-P1 load test |
| pytest-django (planned) | Automated API tests |

---

## 11. Related documents

- [SOFTWARE_ENGINEERING_PLAN.md](SOFTWARE_ENGINEERING_PLAN.md)  
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md)  
- [SECURITY.md](SECURITY.md)  
- [TEST_PLAN.md](TEST_PLAN.md)  

---

*Process version 1.0 — May 2026*
