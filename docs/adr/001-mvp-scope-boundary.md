# ADR-001: MVP scope boundary for Semester 2

## Status

Accepted — 2026-09-01

## Context

The Semester 1 backlog contains 7 epics and 51 Jira issues. The Semester 2 course requires a deployed, working system with real customer usage, payment evidence, and a defensible research evaluation, across an 18-week semester whose primary implementation window is Weeks 4–7.

Costing the full backlog against conservative capacity (4 people × 8 effective hours/week) gives **~27 dev-days of implementation across the entire semester**, against a backlog of roughly 81 dev-days for the "should build" set. The backlog is oversubscribed by 3–5×.

Compounding this, the system as inherited does not run: `apps/records/views.py` raises `NameError` at import, so the URLconf cannot load; neither Compose file builds because both reference an `./ai` directory that does not exist; twelve endpoints have no object-level authorization; and nginx serves every uploaded document unauthenticated.

Scope must therefore be cut deliberately, or it will be cut by the calendar.

## Decision

The Semester 2 MVP is **the smallest system that demonstrates the thesis contribution, runs a real institutional workflow securely, and can be deployed and evaluated**.

**In scope:** authentication and role provisioning · record submission with PDF upload · type-differentiated routing · parallel office clearance · clearance-aware resubmission · publication · PostgreSQL full-text search · a minimum RAG capability · audit trail · notifications.

**Out of scope for Semester 2:** conversational RAG with history · document summarization · the KPI/analytics dashboard · watermarking · download and delete request queues · Excel import · the `apps/storage` file browser · the PIN access gate · full-text chunking · Docling-serve · pooled multi-tenancy · billing.

Every capability is classified `KEEP` / `REDUCE` / `REPLACE` / `DEFER` / `REMOVE` / `DO NOT BUILD YET` in [`docs/architecture-tasks/12-scope-cuts.md`](../architecture-tasks/12-scope-cuts.md).

Screens: 16 keep · 10 hide · 5 defer · 6+ remove.

## Alternatives Considered

**Attempt the full backlog.** Rejected. At optimistic capacity (18 h/person/week, which the team explicitly declined to assume) the coverage is 44%. At the conservative capacity actually adopted it is 20%. A plan that requires 3× the available capacity fails in Week 6 with nothing deployable.

**Cut by deferring only the AI epics.** Rejected as insufficient. Removing Epics 3, 4 and 7 leaves roughly 55 dev-days against 27. The cut has to reach further, into the storage app, the request queues, and the import path.

**Cut security or testing instead of features.** Rejected outright. A real customer loads data in Week 11; twelve open authorization defects are not a thesis exercise at that point. Testing is what prevents the five current blockers from recurring — an import-smoke test alone would have caught three of them.

**Ship a proof-of-concept and document the rest.** Rejected. The course requires actual usage by paying customers, which a proof-of-concept cannot support.

## Decision Rationale

Optimise for a *working, secure, evaluable* system rather than feature count. The thesis contribution is the workflow model; every feature that does not support demonstrating, securing or measuring it competes with the ones that do.

The SRS already contains precedent for staged delivery — Module 7 (KPI Dashboard) is marked Phase 2 in the change history. This decision extends an existing principle rather than inventing one.

Cutting `apps/storage` is illustrative: six endpoints with no authorization, serving FR-M2-06/07, which no pilot workflow touches. Deleting it is half a day and removes an entire security surface. Securing it would cost a day and ship a feature nobody uses.

## Consequences

**Positive.** The budget closes with ~2.5 days of slack in Weeks 4–7 — the only contingency in the plan, reserved for RAG. Test and security surface shrinks materially. Every remaining task is defensible against "why is this here?"

**Negative.** Several SRS requirements will be unmet at defence and must be formally reclassified as Phase 2 (see ADR-011 and the Week 3 SRS refactor). The team must be able to defend each cut. The traceability matrix will show substantial "not implemented" — that honesty is the artefact's value, but it must be presented deliberately rather than discovered.

**Risk.** Cuts not formalised in the SRS become undocumented deviations, which is worse than the original scope. The Week 3 requirements refactor is therefore mandatory, not optional.

## MVP Impact

Defines it.

## SaaS Impact

Scope cuts do not compromise the SaaS path. The one structural capability retained — configurable workflow routing (ADR-002) — is what makes institution #2 possible; everything cut is per-feature, not per-tenant.

## Security Impact

Strongly positive. Removing `apps/storage`, the download/delete queues and the PIN gate eliminates thirteen endpoints, six of which currently have no authorization at all.

## Deployment Impact

Service count falls from ten to five (ADR-010), memory from a claimed ~8 GB to ~2 GB.

## Research Impact

Protective. The thesis-critical task set is ring-fenced from further cuts; every deferred item is outside the contribution.

## Related Requirements

FR-M2-04, FR-M2-06, FR-M2-07, FR-M4-01, FR-M4-02, FR-M7-01, FR-M7-02, FR-M8-01, FR-M8-03 — all affected. See [`13-jira-reconciliation.md`](../architecture-tasks/13-jira-reconciliation.md).

## Related Tasks

All of [`docs/architecture-tasks/`](../architecture-tasks/00-index.md); specifically [`12-scope-cuts.md`](../architecture-tasks/12-scope-cuts.md).
