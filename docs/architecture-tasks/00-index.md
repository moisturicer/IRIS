# 00 — Task Index

Implementation backlog derived from the architecture decisions in [`docs/adr/`](../adr/README.md), verified against the working tree on `refactor/docker-service` @ `7a9d515` and reconciled against the live Jira backlog (project **IR**, 51 issues).

> **This replaces the previous `docs/architecture-tasks/` set.** That backlog was built before the design interview and assumed a different scope and budget. It is in git history. Two conflicting backlogs in one directory is the drift problem this review exists to fix.

---

## The binding constraint

| | |
|---|---|
| Team | 4 people |
| Capacity | 8 effective dev-hours/person/week (conservative, team-selected) |
| **Total implementation budget** | **~27 dev-days for the semester** |
| Weeks 1–3 | ~7 dev-days (validation phase, part-time coding) |
| Weeks 4–7 | ~16 dev-days (primary window) |
| Weeks 8–10 | ~5 dev-days (alongside testing) |

Every classification below was made against that number. Where something is deferred, it is because the budget does not fund it — not because it lacks merit.

---

## Documents

| Doc | Contents | Tasks |
|---|---|---|
| [01-foundation.md](01-foundation.md) | CI, enums, requirements refactor | 3 |
| [02-backend.md](02-backend.md) | Boot blockers, Celery, `apps/ai`, querysets | 9 |
| [03-frontend.md](03-frontend.md) | Tokens, pilot surface, dead code | 5 |
| [04-workflow.md](04-workflow.md) | **Thesis-critical** — transition table, policies, instrumentation | 6 |
| [05-security.md](05-security.md) | Media, authorization, `is_staff`, config | 7 |
| [06-rag.md](06-rag.md) | Minimum pipeline, timeboxed | 6 |
| [07-saas.md](07-saas.md) | Instance-per-tenant, configuration boundaries | 4 |
| [08-deployment.md](08-deployment.md) | Five services, interim VPS, backups | 5 |
| [09-testing.md](09-testing.md) | pytest, authorization matrix, transitions | 4 |
| [10-mvp-validation.md](10-mvp-validation.md) | Three-phase validation, NFR evidence | 15 |
| [11-documentation.md](11-documentation.md) | SRS refactor, traceability, security docs | 6 |
| [12-scope-cuts.md](12-scope-cuts.md) | KEEP / REDUCE / REPLACE / DEFER / REMOVE / DO NOT BUILD YET | — |
| [13-jira-reconciliation.md](13-jira-reconciliation.md) | 51 issues → ~18 active | — |

**70 task specifications. ~30 are P0/P1 and fit the budget.** The remainder are P2/P3 or deferred, recorded so the cuts are visible rather than implied.

---

## Priority definitions

| | Meaning | Window |
|---|---|---|
| **P0** | System does not run, or is unsafe to expose publicly | Weeks 1–3 |
| **P1** | Thesis-critical, or required for the pilot | Weeks 4–7 |
| **P2** | Required for a defensible MVP | Weeks 8–10 |
| **P3** | Valuable, unfunded this semester | Phase 2 |

---

## Immediate blockers

Nothing else can be validated, demonstrated or safely deployed until these clear.

### Boot blockers

| ID | Task | Cx |
|---|---|---|
| `B-01` | Six undefined names in `records/views.py` — `NameError` at import kills the whole URLconf | XS |
| `B-02` | Four methods indented into `DownloadRedeemView` instead of `DownloadRequestViewSet` | S |

### Docker / Compose blockers

| ID | Task | Cx |
|---|---|---|
| `D-01` | Both Compose files build `ai-gateway` from `./ai`, which does not exist | S |
| `D-02` | Prod maps `80:80`; nginx-unprivileged listens on 8080 — frontend unreachable | S |

### Public-deployment safety blockers

**No public URL until every one of these is done.**

| ID | Task | Cx |
|---|---|---|
| `S-01` | nginx serves `/media/` unauthenticated — every uploaded PDF is public | XS |
| `S-02` | `RecordViewSet.retrieve` has no visibility filter — any user reads any record | S |
| `S-03` | Six `documents/` endpoints lack object-level authorization | S |
| `S-04` | Hardcoded DB credentials, `CORS_ALLOW_ALL_ORIGINS`, unset `ALLOWED_HOSTS` | S |
| `SC-01` | Delete `apps/storage` — six unauthorized endpoints, not in MVP scope | XS |

### CI blockers

| ID | Task | Cx |
|---|---|---|
| `T-01` | Zero tests. An import-smoke test catches three of the five current blockers | S |
| `F-01` | No CI. Every blocker above is machine-detectable and none was detected | S |

---

## Thesis-critical tasks

**Protected from scope cuts.** These demonstrate and measure the contribution in [ADR-003](../adr/003-clearance-aware-resubmission.md).

| ID | Task | Demonstrates |
|---|---|---|
| `W-01` | Declarative transition table | Type differentiation · routing · parallel clearance |
| `W-02` | Restart-all resubmission policy | The controlled comparison ([ADR-004](../adr/004-restart-all-comparison-mode.md)) |
| `W-03` | Transaction boundaries on transitions | Office-specific clearance integrity |
| `W-04` | Audit decisions + time-on-task instrumentation | Preserved clearances · turnaround · auditability |
| `T-03` | Transition tests across both policies | Correctness of the model |
| `V-03` | Manual-process baseline collection | Real-world comparator |
| `V-04` | Scenario-based evaluation design | Controlled N when pilot volume is small |
| `V-05` | Final evaluation execution | The result |

If capacity slips, cut from `06-rag.md` and `03-frontend.md` before touching this list.

---

## Schedule

| Window | Days | Work |
|---|---|---|
| **Weeks 1–3** | 7.5 | `B-01` `B-02` (1.5) · `D-01` `D-02` (2) · `S-01` (0.5) · `S-02` `S-03` (2) · `SC-01` (0.5) · `D-03` deploy (1) |
| **Weeks 4–7** | 13.5 | `S-05` (1) · `B-03` `R-01` (2) · `T-01` `F-01` (2) · `FE-01` (1) · `F-02` `W-01` `W-02` (4.5) · RAG timeboxed (3) |
| **Weeks 8–10** | 5 | `W-04` instrumentation (2) · validation fixes (2) · `D-04` backup drill (1) |

**~2.5 days of slack remain in Weeks 4–7. It is reserved for RAG** — the item most likely to overrun, and the only one with a pre-committed fallback ([ADR-006](../adr/006-minimum-rag-pipeline.md)).

---

## Open external blockers

Not resolvable by the team; each has a named owner and a real lead time.

| # | Blocker | Owner | Blocks |
|---|---|---|---|
| 1 | **Written pilot commitment — named participants, dated window** | CIT-U RDCO | **Highest single risk.** Usage, payment, analytics and evaluation data all depend on it |
| 2 | External AI transmission approval | Research office | Provider choice (`R-02`) |
| 3 | CIT-U hardware specs and access | IT / adviser | Final deployment; mitigated by interim VPS |
| 4 | SRS amendment procedure | Adviser | Week 3 refactor (`DOC-03`) |
| 5 | Payment-evidence acceptability | Adviser | Commercialisation evidence |
| 6 | Evaluation framework approval | Adviser | `V-02` instrument design |
| 7 | RDCO process volume and decline rate | RDCO | Whether evaluation is organic or scenario-based (`V-04`) |

---

## Task template

Every task specifies: Objective · Problem · Evidence · Current State · Proposed State · Scope · Out of Scope · Technical Approach · Dependencies · Risks · Security Impact · Performance Impact · SaaS Impact · Research/Thesis Impact · MVP Classification · Priority · Complexity · Acceptance Criteria · Testing Requirements · Documentation Requirements · Definition of Done.

**Complexity:** XS <1 h · S <1 d · M 1–3 d · L 3–5 d · XL >5 d.
