# 07 — SaaS

Four tasks, three of them documentation. Governed by [ADR-005](../adr/005-instance-per-tenant.md): **instance-per-tenant, no `tenant_id`**, saving ~13 dev-days and making the classic cross-tenant leak structurally impossible.

The single piece of *code* that makes institution #2 possible is the transition table (`W-01`), not tenancy plumbing.

---

# SA-01 · Define institutional configuration boundaries

## Objective
Record precisely what varies per institution and what stays fixed, so CIT-U-specific assumptions do not accumulate in the domain model.

## Problem
What makes a second institution *impossible* is not the absence of `tenant_id` — that is a mechanical retrofit. It is CIT-U's structure being baked into code.

## Evidence
Hardcoded to CIT-U today: `ROLE_TO_OFFICE` (`reviews/services.py:68`) · `RecordClearance.OFFICE_CHOICES` (`reviews/models.py:56`) · `STAFF_ROLES`/`ADMIN_ROLES` (`core/permissions.py:12-14`) · `Record.PIPELINE_STATUS` (12 CIT-U stages) · the `if rt == "Proposal"` routing branches across three modules · seeded roles, colleges, departments and courses in `accounts/migrations/0003`.

## Current State
Institution #2 would require a fork.

## Proposed State
A documented configuration boundary, with the varying parts expressed as data via `F-02` and `W-01`.

## Scope
Document what is per-institution: **offices and their roles · workflow stages · routing rules per record type · resubmission policy · document types and upload slots · terminology · notification templates · branding**.

Document what stays fixed for the MVP: the record model, the review/clearance model, the audit schema, authentication.

## Out of Scope
Building configuration UI (Phase 2). Pooled multi-tenancy (`SA-03`).

## Technical Approach
Configuration lives in the transition table plus enum defaults an institution overrides. No new mechanism.

## Dependencies
`F-02`, `W-01`.

## Risks
Over-generalising into an enterprise workflow platform. The boundary above is deliberately narrow — the pragmatic middle ground, not a generic engine.

## Security Impact
None directly. Documents which boundaries must become tenant-aware if pooled multi-tenancy is ever adopted.

## Performance Impact
None.

## SaaS Impact
Defining.

## Research/Thesis Impact
Supports the generality claim in [ADR-002](../adr/002-workflow-transition-table.md): the same artefact configured differently, not forked. Material for the commercial defence.

## MVP Classification
MVP REQUIRED (documentation)

## Priority
P1

## Complexity
S

## Acceptance Criteria
- [ ] A table lists every per-institution configuration point and where it lives.
- [ ] A table lists what is deliberately fixed and why.
- [ ] A worked example expresses a hypothetical second institution's offices and routing in the same table format.
- [ ] No CIT-U office name appears outside `core/enums.py` and seed data.

## Testing Requirements
None (documentation). `F-02`'s grep assertion covers the office-name criterion.

## Documentation Requirements
This task is documentation; feeds the SDD (`F-03`) and the commercial defence.

## Definition of Done
Merged; the worked example reviewed by the team as plausible.

---

# SA-02 · Instance provisioning and onboarding runbook

## Objective
Make onboarding a new institution a repeatable procedure rather than tribal knowledge.

## Problem
Instance-per-tenant trades code complexity for operational procedure. Without a runbook that trade is a liability.

## Evidence
No deployment or onboarding documentation exists. `docs/README.md` links a `DEVELOPMENT_GUIDE.md` that does not exist.

## Current State
No documented procedure for standing up an instance.

## Proposed State
`docs/RUNBOOK.md` covering provisioning, configuration, seeding, verification and handover.

## Scope
Provision a host · generate secrets · deploy the five-service stack · configure offices, stages and routing · seed roles and reference data · create the first admin · verify with a smoke checklist · hand over credentials.

## Out of Scope
Automation — a documented manual procedure is appropriate below ~10 institutions.

## Technical Approach
Written procedure with copy-pasteable commands, validated by following it to stand up the evaluation instance (`W-02`).

## Dependencies
`D-03`, `S-04`.

## Risks
Drift between the runbook and reality. Mitigation: it is exercised twice this semester — interim VPS and evaluation instance.

## Security Impact
Per-instance secret generation is part of the procedure; prevents credential reuse across institutions.

## Performance Impact
None.

## SaaS Impact
The operational half of [ADR-005](../adr/005-instance-per-tenant.md). Per-tenant operational cost is instance-per-tenant's main weakness; a good runbook is what keeps it manageable.

## Research/Thesis Impact
Evidence for the commercial defence that onboarding is a defined, costed process.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
S

## Acceptance Criteria
- [ ] A person who has not deployed IRIS can stand up an instance following the runbook alone.
- [ ] The procedure was followed end-to-end at least once and corrections folded back in.
- [ ] Secret generation is included, with no shared secrets between instances.
- [ ] A post-deployment smoke checklist is included, covering the `S-01` media check.

## Testing Requirements
The runbook is validated by executing it for the evaluation instance.

## Documentation Requirements
`docs/RUNBOOK.md`, linked from `docs/README.md` (`DOC-01`).

## Definition of Done
Merged; validated by a second person standing up the evaluation instance.

---

# SA-03 · Pooled multi-tenancy migration path

## Objective
Document how IRIS would move from instance-per-tenant to pooled multi-tenancy, so the scale story is credible without building it.

## Problem
"We chose instance-per-tenant" invites "and what happens at 100 institutions?" A documented path answers it; silence does not.

## Evidence
[ADR-005](../adr/005-instance-per-tenant.md) records the comparison and the revisit triggers.

## Current State
The decision is recorded; the path is not.

## Proposed State
A design document covering the model, the boundaries that acquire a tenant dimension, and the migration.

## Scope
Which models need `institution_id` (~15) · tenant resolution strategy · which querysets must become tenant-scoped · file, vector and audit isolation under pooling · cross-tenant authorization testing · the data migration from N instances to one pool · **the revisit triggers**: >8 institutions, per-tenant cost exceeding per-tenant revenue, self-service signup, or cross-institution reporting.

## Out of Scope
Implementation. Explicitly `DO NOT BUILD YET`.

## Technical Approach
Design on paper. Note that every rule in [ADR-009](../adr/009-authorization-model.md) acquires a tenant dimension under pooling — which is precisely why it is not being attempted while twelve authorization defects are being closed.

## Dependencies
`SA-01`.

## Risks
That it is read as a plan rather than a contingency. Mark it clearly as not-built.

## Security Impact
Documents that pooling introduces a failure mode instance-per-tenant does not have, and what would be required to control it.

## Performance Impact
None.

## SaaS Impact
Completes the scale narrative.

## Research/Thesis Impact
Commercial defence material.

## MVP Classification
DO NOT BUILD YET (documentation only)

## Priority
P3

## Complexity
S

## Acceptance Criteria
- [ ] The document lists every model requiring a tenant key.
- [ ] It states the revisit triggers explicitly.
- [ ] It describes the N-instances → pool migration.
- [ ] It is clearly marked as designed, not implemented.

## Testing Requirements
None.

## Documentation Requirements
`docs/adr/` supporting note or a design document linked from [ADR-005](../adr/005-instance-per-tenant.md).

## Definition of Done
Merged and linked from the ADR.

---

# SA-04 · Data export and offboarding

## Objective
Ensure an institution can leave with its data — a standard procurement requirement and a legal one under RA 10173.

## Problem
No export or offboarding procedure exists. Institutional buyers ask about exit before they sign.

## Evidence
No documented export path. Under instance-per-tenant the mechanism is trivial and unwritten.

## Current State
Undefined.

## Proposed State
A documented procedure producing a complete, usable export, plus a defined deletion process.

## Scope
Full database dump · media archive · a human-readable export of records, reviews, clearances and audit events (CSV or JSON) · documented retention and deletion, including backups · a confirmation artefact.

## Out of Scope
A self-service export UI (Phase 2).

## Technical Approach
`pg_dump` plus a media tar plus a management command emitting the human-readable export. Under [ADR-005](../adr/005-instance-per-tenant.md) this is a per-institution operation by construction — no filtering, no risk of including another institution's data.

## Dependencies
`D-04` (backup tooling overlaps).

## Risks
Low. The main risk is discovering at contract time that it was never tested — so exercise it once.

## Security Impact
Export contains confidential IP; it must be encrypted in transit and at rest, and deletion must cover backups or the retention claim is false.

## Performance Impact
None.

## SaaS Impact
A procurement requirement. Instance-per-tenant makes it a genuine selling point.

## Research/Thesis Impact
Commercial defence material; supports the RA 10173 compliance narrative.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
S

## Acceptance Criteria
- [ ] The procedure produces a database dump, a media archive and a human-readable export.
- [ ] The export was performed once against the interim deployment and the output verified complete.
- [ ] Deletion covers primary storage and backups, with a stated retention window.
- [ ] Export artefacts are encrypted.

## Testing Requirements
One export drill against the interim deployment, output verified.

## Documentation Requirements
In `docs/RUNBOOK.md` and referenced from the service agreement.

## Definition of Done
Merged; export drill performed and dated.
