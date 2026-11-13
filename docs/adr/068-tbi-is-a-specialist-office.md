# ADR-068: TBI is a specialist office for commercialization

## Status

**Accepted** — 2026-11-14 (IR-977): approved by Jive Tyler Revalde and merged (PR #720), as relayed by Hermoine Zozobrado. The decisions come from a design session with Hermoine Zozobrado on 2026-11-13–14. Not built yet.

It amends [ADR-018](018-conditional-parallel-office-routing.md) (KTTO's review question is IP; commercial potential is TBI's, and `for_commercialization` hints at TBI) and [ADR-066](066-ip-applications-beside-publishing.md) (a publishing-gate override notifies the office that owns the application). It follows [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) for TBI's pool, seats and coordinators, and [ADR-051](051-system-admin-account-deletion-and-consent.md) §4 for who grants its role.

## Context

Observed on `main`, 2026-11-13:

- **IRIS has three specialist offices**, ITSO, IERC and KTTO, plus RDCO, which decides (`core/enums.py`: `Office`, `ReviewStage`/`Party`, `RoleName`). Office staff can read every paper (`Record.objects.visible_to`). The System Admin grants office roles and the coordinator flag (ADR-051 §4, ADR-032 §4).
- **KTTO holds two questions.** ADR-018's table gives it "commercial potential, industry-partnership viability, technology-transfer readiness". ADR-066 gave it a paper's IP applications. The author's `is_ip` and `for_commercialization` flags both hint at KTTO (`apps/reviews/routing.py`).
- **IPAMS**, the system IRIS replaces, made TBI a role that shared KTTO's step: one "KTTO / TBI" tracker row, where whichever approved counted. IR-969's design session (2026-11-07–08) decided TBI becomes its own office.
- **ADR-066 already gives TBI the commercialization application**, beside publishing, designed in IR-979. Its publishing gate notifies KTTO when RDCO overrides it, written when KTTO was the only office with applications.
- **Adding an office is a code change.** `docs/institution_configuration_boundary.md` §4b lists about a dozen backend sites that name the offices, including `CLEARANCE_OFFICES` (`apps/reviews/clearance_state.py`), where clearance-aware resubmission lives. About 47 frontend files hardcode office names (§5).
- **No data depends on the change.** iris-demo holds 2 published papers and none in review (2026-11-13). `seed_demo`'s commercialization papers route to KTTO with the reason "Commercialisation review."

## Decision

### TBI in the review

1. **TBI, the Technology Business Incubator, is a fourth specialist office.** RDCO, or an Adviser or office that may route onward, can send a paper to TBI exactly as to ITSO, IERC or KTTO. Its question is the paper's **commercial potential**: industry partnership, market readiness and whether to pursue commercialization.
2. **TBI works exactly like the other specialist offices.**
   - A routed paper lands in TBI's pool; a member claims it or a coordinator assigns it (ADR-032).
   - It records a Finding and a Clearance with the same outcomes as the others.
   - **Clearance-aware resubmission covers it:** when TBI requires revisions, only TBI's clearance resets, and the other offices' clearances are kept.
   - Its due date comes from a `Turnaround` row like any office's. With no row, it has no clock (ADR-043 §2).
   - It is audited and notified through the same events as the other offices.
3. **KTTO's review question becomes IP**: whether the paper holds something to protect, and whether it should be filed before publication. Commercial potential moves to TBI. This amends ADR-018's office table.
4. **The author's `for_commercialization` flag hints at TBI.** `is_ip` still hints at KTTO, and `requires_ethics_review` at IERC. A paper with both `is_ip` and `for_commercialization` is suggested for KTTO and TBI, which review it in parallel. The hint stays a suggestion the router can change.
5. **Display order:** Adviser, ITSO, IERC, KTTO, **TBI**, RDCO, in the review tracker, the routing picker and the owner's submission status. The order is display only; the offices still review in parallel.

### TBI's people

6. **TBI is a role with members and coordinators**, like the other offices. A member claims and reviews from the pool. A coordinator also assigns, reassigns and withdraws TBI's seats, extends its due dates and sees TBI's whole My Reviews (ADR-032 §4). The **System Admin** grants the role and the coordinator flag (ADR-051 §4).
7. **TBI staff read every paper**, like other office staff. `Record.objects.visible_to` gains the role in its staff clause, and stays the one visibility rule for the API and Ask IRIS retrieval.

### TBI beside publishing

8. **TBI owns the commercialization application** (ADR-066 decision 1). It mirrors KTTO's IP application: its own steps, document slots on Setup, pool and audit. Its design is IR-979's.
9. **A publishing-gate override notifies the office that owns the application**: KTTO for an IP application, TBI for a commercialization application. The paper's owners are notified as before. This amends ADR-066 decision 13.

### How it is built

10. **TBI is added at each site that names the offices**, the list in `docs/institution_configuration_boundary.md` §4b, together with a **guard test that every office set and map names the same offices**. Missing a site, above all `CLEARANCE_OFFICES`, then fails a test instead of silently dropping TBI from clearance-aware resubmission. The single office registry stays a recorded finding (§4b), not done here.
11. **No data migration.** No paper in review moves: KTTO finishes any commercialization question it already holds, and TBI receives papers routed after it exists. `seed_demo` routes its commercialization papers to TBI and adds `tbi@iris.test` (a member) and `tbi.coordinator@iris.test` (a coordinator).
12. **Outside the MVP, but part of the main workflow**, like ADR-066. MVP validation doesn't wait for it.

## Alternatives Considered

- **TBI only owns commercialization applications, outside the review.** No change to the thesis-critical workflow, and a much smaller build. Rejected: RDCO couldn't ask TBI about a paper during its review, and commercial potential is part of the publishing decision, as KTTO's IP question is.
- **TBI shares KTTO's step, as in IPAMS.** No new office. Rejected: one row where either office's approval counts means neither office's answer is recorded as its own, and clearance-aware resubmission can't tell which office asked for revisions.
- **KTTO keeps commercial potential, and TBI only handles applications.** Rejected: the same question would sit with two offices.
- **Collapse the office sets into one registry first, then add TBI.** The next office becomes one line. Rejected for now: it is a refactor of the thesis-critical workflow ahead of the feature, while TBI is the only office CIT-U is adding. The guard test catches a missed site.
- **TBI staff read only papers routed to TBI or with a commercialization application.** Least privilege. Rejected: it needs a second visibility rule beside `visible_to`, the one predicate retrieval also uses, for one office.
- **Move papers already at KTTO for commercialization to TBI.** Rejected: none exist on iris-demo, and moving a live review changes who holds a seat mid-decision.

## Decision Rationale

TBI asks a question no other office answers, so it gets its own row, its own clearance and its own place in clearance-aware resubmission, which IPAMS's shared step couldn't give it. Making it a specialist office like the others, rather than a new kind of office, means the existing pool, seat, deadline, audit and resubmission rules apply to it unchanged. The guard test is what makes adding it by hand safe.

## Consequences

- **The review gains a party.** Every surface that lists offices shows TBI, and the authorization matrix gains TBI's role.
- **Adding the office is still a dozen-site change.** The next office will be the same work, until the registry is built.
- **TBI can read papers it was never sent**, as every office can.
- **KTTO's scope narrows to IP.** A commercialization question already at KTTO stays there until it is answered.
- **Setup's "Commercialization Assessment" description** names TBI as an office once this is built, and the slot itself waits on IR-979 (ADR-066).
- **ADR-018 and ADR-066** each carry a note pointing here.

## MVP Impact

None. MVP validation doesn't wait for it. It is part of the main workflow, so it comes soon after.

## SaaS Impact

Another institution may have no incubator, or call it something else. As with the other offices, the name is a label (`docs/institution_configuration_boundary.md` §2) and the office itself is code until the registry exists.

## Security Impact

- The authorization matrix (`apps/tests/test_access_matrix.py`) gains the TBI role on every route an office role reaches, with the same 404 for what it can't see.
- TBI joins `STAFF_ROLES` and `REVIEWER_ROLES`, so it reads every paper and can be seated. It does not join `ADMIN_ROLES`.
- Only the System Admin grants the role or the coordinator flag.

## Deployment Impact

- **Migrations:** a `Role` row ("TBI") seeded by a data migration, and generated `AlterField` migrations for the fields whose choices name the offices.
- **No new setting or service.** A `Turnaround` row for TBI is entered like the others' when the institution sets one.
- On iris-demo, the System Admin grants TBI to its staff after deploying.

## Research Impact

The workflow contribution's rule is unchanged, and now covers four specialist offices. A test shows clearance-aware resubmission preserving other offices' clearances when TBI requires revisions, and preserving TBI's when another office does. None on RAG beyond `visible_to` gaining a staff role.

## Related Requirements

None. IR-977 and IR-969's design session are the source. Implementation tickets add their `docs/testing/traceability/IR-XXX.md`.

## Related Tasks

IR-977 (this design), IR-979 (the commercialization application), IR-978 and ADR-066 (IP applications and the publishing gate), IR-969 (Setup), ADR-018 (office scopes), ADR-032 (pools and coordinators), ADR-051 (who grants roles), `docs/institution_configuration_boundary.md` §4b.
