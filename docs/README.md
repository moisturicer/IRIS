# IRIS — Engineering Documentation Hub

Central index for **software engineering**, **SDLC**, **security**, and **quality** documentation. Official product requirements remain in the SRS/SDD PDFs at the repo root; these documents describe *how the team builds, secures, tests, and ships* IRIS.

---

## Document map

| Document | Purpose | Audience |
|----------|---------|----------|
| [Software Engineering Plan](SOFTWARE_ENGINEERING_PLAN.md) | Vision, scope, phases, milestones, roles, deliverables | PM, leads, whole team |
| [SDLC Process](SDLC_PROCESS.md) | Lifecycle phases, gates, branching, reviews, release | Developers, QA |
| [Security Overview](SECURITY.md) | Architecture, controls, NFR mapping, secure dev practices | Developers, security reviewer |
| [Security Risk Register](SECURITY_RISK_REGISTER.md) | Threats, likelihood/impact, mitigations, owners | Leads, auditors |
| [Test Plan](TEST_PLAN.md) | Test levels, scope, entry/exit criteria, role matrix | QA, developers |
| [Requirements Traceability Matrix](TRACEABILITY_MATRIX.md) | SRS FR/NFR → code, API, UI, tests | BA, QA, leads |
| [Development Guide](DEVELOPMENT_GUIDE.md) | Local setup, build order, per-feature workflow | Developers |
| [Frontend Implementation Plan](../frontend/docs/FRONTEND_IMPLEMENTATION.md) | UI phases, wireframes, routes | Frontend |
| [Changelog](../CHANGELOG.md) | Version history | Everyone |

---

## Source-of-truth hierarchy

1. **SRS** (`IRIS Software Engineering_SRS.pdf`) — functional & non-functional requirements  
2. **SDD** (`IRIS Software Engineering_SDD.pdf`) — design detail (when aligned with SRS)  
3. **This `docs/` folder** — process, security, testing, traceability (living)  
4. **Code + `.env.example`** — implemented behavior  

When SRS and SDD conflict, or Modules **5** (workflow) and **7** (KPI/admin dashboards) are marked draft, record decisions in the engineering plan § *Open decisions* and do not hard-code unstable flows in the UI.

---

## Quick start for new contributors

1. Read [README](../README.md) — run backend + frontend locally.  
2. Read [SDLC Process](SDLC_PROCESS.md) — how we work day to day.  
3. Pick a task from [TRACEABILITY_MATRIX](TRACEABILITY_MATRIX.md) or [DEVELOPMENT_GUIDE](DEVELOPMENT_GUIDE.md).  
4. Before auth/RBAC changes, read [SECURITY.md](SECURITY.md) and check [SECURITY_RISK_REGISTER](SECURITY_RISK_REGISTER.md).

---

## Maintenance rules

- Update **traceability** and **changelog** in the same PR as feature work when an FR/NFR is touched.  
- Review **security risk register** at each milestone (alpha, beta, UAT, production).  
- Bump **Software Engineering Plan** milestone dates when scope shifts (especially M5/M7).

---

*Last updated: May 2026*
