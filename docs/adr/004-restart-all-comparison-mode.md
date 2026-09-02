# ADR-004: Restart-all as a configurable comparison policy

## Status

Accepted — 2026-09-01

## Context

The original evaluation plan measured the contribution by counting **preserved clearances**: for each resubmission, how many offices' completed reviews were retained rather than repeated.

That metric does not work as primary evidence. Given a log of which office declined, the preserved count is *deterministically computable* — (offices engaged) − (declining office). There is no variance, no uncertainty, and **no possible outcome in which IRIS performs badly**. It compares IRIS against a hypothetical worse version of IRIS that the authors defined. A panel will call it an arithmetic identity presented as a result.

Two further problems: preserved *reviews* are not preserved *effort* (re-reviewing an already-cleared document costs perhaps 10–20% of the original), and a two-week pilot may produce single-digit resubmissions.

The only uncontaminated comparison available is **IRIS against itself under a different resubmission policy**. Comparing against CIT-U's manual process measures digitisation, not the clearance model — any software beats paper.

Inspection of `reviews/services.py:378-395` shows the insertion point is small: the clearance-office decline branch resets one office; a restart-all policy resets all clearance rows to `pending` and routes to the first clearance stage for the record type.

## Decision

Implement **restart-all as a configurable resubmission policy** in the ADR-002 transition table.

- `CLEARANCE_AWARE` (default) — reset only the declining office; preserve the rest.
- `RESTART_ALL` — reset every clearance row to `pending`; route to the first clearance stage for the record type.

The policy is institution-level configuration, **defaulting to `CLEARANCE_AWARE` in production**.

The evaluation runs the same SME participants over the same scenario set under both policies, measuring task success, time-on-task, offices re-reviewed, preserved clearances and workflow completion time (ADR-011).

**The comparison runs on a separate evaluation instance, never on the customer's production instance.** Instance-per-tenant (ADR-005) makes this free.

## Alternatives Considered

**Keep preserved-clearance counting as primary evidence.** Rejected — see Context. It cannot produce a negative result.

**Compare against CIT-U's manual process only.** Rejected as primary; retained as supporting context. It is confounded by digitisation. It is still worth gathering during Weeks 1–3 because it establishes the real-world problem the contribution addresses.

**Build a separate restart-all implementation.** Rejected. Duplicating the resubmission path for evaluation invites divergence between the two, and the divergence would be indistinguishable from the effect being measured.

**Simulate restart-all from logs rather than executing it.** Rejected — that is the arithmetic identity again with extra steps. The point of the experiment is that participants actually perform the repeated reviews and the time is actually measured.

## Decision Rationale

Half a dev-day converts the central claim from arithmetic into a within-subjects experiment with a genuinely possible negative result. Nothing else in the plan has that return.

It is cheap *only because* ADR-002 exists. Without a transition table it would be a second code path; with one it is an alternate row set.

It also yields a real product capability: institutions with different governance may legitimately require full re-review after any decline. The research control and the configuration option are the same mechanism — which is the strongest form of justification for building something.

## Consequences

**Positive.** A defensible experimental design. A per-institution configuration option. A finding that survives peer scrutiny in either direction.

**Negative.** Doubles participant time in the evaluation — each scenario is walked twice. Scenario count must be sized accordingly; ordering effects need counterbalancing.

**Risk — must be managed.** A policy flag that resets clearances could corrupt live customer workflows if enabled on the production instance. Mitigation: the flag is set per instance, the evaluation runs on a dedicated instance, and the production default is `CLEARANCE_AWARE`. This is a hard operational rule, not a preference.

## MVP Impact

**MVP Required, P1, thesis-critical.** ~0.5 dev-days as part of `W-01`.

## SaaS Impact

Positive. Resubmission policy joins offices and routing as institution-configurable, strengthening the "configurable model" claim in ADR-002.

## Security Impact

Low, with one operational control: the policy must not be changeable through an ordinary staff-facing endpoint. It is deployment configuration, not an in-app setting.

## Deployment Impact

Requires a second, short-lived instance for the evaluation window. Trivial under ADR-005 — one more Compose stack with a different database.

## Research Impact

Defining. This is what makes ADR-003's claim testable rather than merely asserted.

## Related Requirements

FR-M5-01, FR-M5-03. NFR-U1 (satisfaction) and the effectiveness/efficiency measures in ADR-011.

## Related Tasks

`W-02` (implementation), `V-04` (scenario design), `V-05` (execution), `T-03` (tests covering both policies). See [`04-workflow.md`](../architecture-tasks/04-workflow.md) and [`10-mvp-validation.md`](../architecture-tasks/10-mvp-validation.md).
