# ADR-005: Instance-per-tenant rather than pooled multi-tenancy

## Status

Accepted — 2026-09-01

## Context

IRIS is intended as institutional SaaS/PaaS. CIT-U is the first customer; other universities and research organisations are the target market. Institutions differ in offices, reviewer structures, workflow stages, clearance requirements, document types, routing rules and terminology.

The default reflex for SaaS is pooled multi-tenancy: one database, a `tenant_id` on every table, every query filtered. Costed against this codebase that is **~14 dev-days** — a `Tenant` model, foreign keys across ~15 models, a data migration, tenant-scoped querysets everywhere, tenant resolution middleware, file and vector isolation, audit isolation, cross-tenant authorization tests, and an onboarding flow.

The total implementation budget for the semester is ~27 dev-days, of which ~12 are already committed to making the system boot and closing twelve authorization defects.

That last fact is the decisive one. **The team currently has twelve live instances of "a query that forgot its filter."** Pooled multi-tenancy's characteristic failure mode is exactly that bug, with cross-institution consequences.

## Decision

**Instance-per-tenant for the MVP.** Each institution gets its own deployment: own database, own media volume, own Compose stack. No `tenant_id`, no tenant resolution, no pooled query filtering.

Institutional differences are handled by **configuration within the instance** — the ADR-002 transition table supplies offices, stages, routing and resubmission policy.

The pooled multi-tenant model is **designed on paper** for the commercial defence and documented as the scale path, with the migration route recorded. It is not built.

## Alternatives Considered

| Option | Isolation | Cost | Verdict |
|---|---|---|---|
| Shared DB + `tenant_id` | Weakest — one missing filter leaks across institutions | ~14 dev-days | **Rejected** |
| Schema-per-tenant | Strong | ~10 dev-days | Rejected — most of the plumbing cost, less of the isolation benefit than separate databases |
| **Instance-per-tenant** | **Strongest — no shared surface** | **~1 dev-day** | **Accepted** |

Comparison on the dimensions that matter at this stage:

| | Shared + `tenant_id` | Schema-per-tenant | Instance-per-tenant |
|---|---|---|---|
| Cross-tenant bug risk | High | Medium | **Structurally impossible** |
| Backups | One dump; filtered restore is painful | Per-schema | **Per-institution, trivial** |
| Data export on exit | Query-and-filter export | Schema dump | **`pg_dump`, done** |
| Migrations | One run | Loop over schemas | Loop over instances |
| Cost per tenant | Lowest | Low | Higher |
| Scales economically to | 1000s | 100s | **~10** |
| Onboarding | Insert a row | Create a schema | Provision a stack |

## Decision Rationale

**The MVP has one tenant; Semester 3 has perhaps three.** At that scale instance-per-tenant is not a compromise — it is the correct engineering answer, and it happens to cost 1 day instead of 14.

It also dissolves most of the SaaS question list. Tenant data isolation, file isolation, vector isolation, audit isolation, cross-tenant authorization, per-tenant backup and data export all become non-questions: they are properties of the deployment, not code the team must write and test correctly. Only *"what is configurable per institution"* survives, and ADR-002 answers it.

**Commercial credibility.** *"We deploy an isolated instance per institution, with a documented path to pooled multi-tenancy at scale"* is a credible answer to a panel and to an early enterprise buyer — isolation is frequently a *selling point* in institutional procurement. *"We built pooled multi-tenancy and it leaked"* is not. The pitch deck must not claim scale beyond ~10 institutions.

A third benefit emerged in review: ADR-004's restart-all comparison needs an instance where clearance state can be reset without touching customer data. Instance-per-tenant supplies it free.

## Consequences

**Positive.** Perfect isolation. Trivial backup, restore and offboarding. ~13 dev-days returned to the budget. No class of cross-tenant authorization bug is possible.

**Negative.** Per-tenant operational cost — each institution is a stack to deploy, monitor, migrate and upgrade. Beyond ~10 institutions this becomes the dominant cost and the decision must be revisited.

**Risk.** Migration drift — instances on different code versions. Mitigation: a documented upgrade procedure and a version endpoint per instance.

## Revisit when

Any one of: more than ~8 institutions onboarded · per-tenant hosting cost exceeds per-tenant revenue · self-service signup becomes a requirement · a customer requires cross-institution reporting.

## MVP Impact

**MVP Required, P1.** ~1 dev-day, mostly deployment documentation.

## SaaS Impact

Defining. What must still be abstracted despite instance-per-tenant: **offices, workflow stages, routing rules, resubmission policy, document types and terminology** — all via ADR-002. What must *not* be hardcoded: CIT-U's four office names, its three record types, and its stage sequence. These are the assumptions that would make institution #2 a fork rather than a deployment.

## Security Impact

Strongly positive, and the primary reason for the decision. The most common serious SaaS vulnerability — cross-tenant data access via a missing query filter — is made structurally impossible rather than defended against by discipline the team has not yet demonstrated.

## Deployment Impact

One Compose stack per institution. Onboarding is provisioning, not a database insert. Migrations loop over instances.

## Research Impact

Enables the ADR-004 evaluation instance. Supports the generality claim: the same artefact configured differently, not forked.

## Related Requirements

Not directly specified in the SRS — the SRS assumes a single CIT-U deployment. The Week 3 refactor should record the SaaS intent and this tenancy decision.

## Related Tasks

`SA-01`…`SA-04`. See [`07-saas.md`](../architecture-tasks/07-saas.md).
