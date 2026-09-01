# ADR-003: Clearance-aware resubmission

## Status

Accepted — 2026-09-01. **This ADR records the primary research contribution.**

## Context

IRIS routes research and IP submissions through parallel clearance by up to three offices (ITSO, IERC, KTTO) after RDCO intake, with routing differentiated by record type:

| Type | Route |
|---|---|
| Proposal | `draft → adviser_review → approved → completed` |
| Thesis/Research | `draft → rdco_intake → parallel_review (IERC + KTTO) → rdco_review → published` |
| Project | `draft → rdco_intake → itso_review → parallel_review (IERC + KTTO) → rdco_review → published` |

When one office declines, the naive implementation resets the entire clearance state and every office re-reviews from scratch — including offices that had already cleared the record and whose concerns were never at issue.

The existing implementation (`reviews/services.py:348-407`) already avoids this: on a clearance-office decline it resets **only** the declining office's `RecordClearance` row and routes back to that office's stage, preserving the others. On a sequential-stage decline it resets everything, which is correct because the record has not yet reached parallel clearance.

This behaviour was implemented before it was named. This ADR names it and makes it the thesis claim.

## Decision

**Clearance-aware resubmission is IRIS's primary research contribution**, stated as:

> A type-differentiated institutional IP workflow in which parallel multi-office clearance maintains per-office clearance state, such that resubmission after a decline resets only the declining office and preserves the completed work of unaffected offices.

The model is preserved and made explicit in ADR-002's transition table. Per-office state lives in `RecordClearance`, keyed `(record, office)` with `unique_together`.

The claim is evaluated by controlled comparison against a restart-all policy (ADR-004), measured under ISO 9241-11 (ADR-011).

## Alternatives Considered

**Claim the whole workflow as the contribution** — type differentiation *plus* parallel clearance *plus* clearance-aware resubmission. Rejected as indefensible. Type-differentiated routing is a switch statement; parallel clearance is a BPMN parallel gateway. Neither is novel in isolation, and claiming them invites the objection below with no answer.

**Claim RAG over an institutional corpus.** Rejected. It is a commodity integration, not a contribution, and the team has no prior RAG experience — a weak claim in an unfamiliar area is the worst combination.

**Claim the integration of workflow and RAG.** Rejected as vague. "We built two things and connected them" is a system description, not a research claim.

**Restart-all is fine; the optimisation is obvious.** This is the strongest form of the objection and is taken seriously below.

## Decision Rationale

**The anticipated objection**, which the team must be able to answer at defence:

> *"This is a BPMN workflow with parallel gateways. Camunda and Flowable have done this for fifteen years. Where is the contribution?"*

The honest answer is that **only clearance-aware resubmission survives that objection.** Standard BPMN parallel gateways do not natively express *"on rejection at branch B, reset branch B only, re-enter, and preserve branches A and C."* Expressing it in BPMN requires either compensating events or restructuring the model per rejection path. The domain model here — per-office clearance state as a first-class entity, with a resubmission policy defined over it — is the contribution. Everything else is context.

That framing has a consequence: **the claim must be evaluated, not merely described.** A paper asserting "we preserve clearances" without measuring whether that helps is an architecture description. Hence ADR-004.

## Consequences

**Positive.** A narrow, defensible claim with a clear novelty argument and a designed evaluation. The implementation largely exists, so the risk is in evaluation rather than construction.

**Negative.** A narrow claim must be defended precisely. The team needs a literature position on BPM engines and institutional workflow systems (DSpace, EPrints, Inteum, Wellspring) — reading work for Weeks 13–14, not coding work.

**Risk.** The contribution may prove to have a small measurable effect. That is a legitimate finding and the evaluation is designed to permit it (ADR-004), but the team must be prepared to report it rather than reach for a favourable framing.

## MVP Impact

**MVP Required, P1, thesis-critical.** Largely implemented; the work is consolidating it into the transition table and instrumenting it.

## SaaS Impact

Resubmission policy becomes a per-institution configuration option — a genuine product capability that emerged from the research design rather than being invented for it.

## Security Impact

Neutral. Note that `resubmit_record` deletes clearance rows on sequential-decline resubmission, so `RecordClearance` cannot serve as the audit trail — hence the separate audit requirement in ADR-009 and task `W-04`.

## Deployment Impact

None.

## Research Impact

Defining. Every evaluation metric, the instrumentation, and the comparison design exist to test this claim.

## Related Requirements

FR-M5-01, FR-M5-03. SRS Module 5 is marked draft and should be updated in the Week 3 refactor to state the model explicitly.

## Related Tasks

`W-01`, `W-02`, `W-04` (instrumentation), `T-03` (transition tests), `V-04`/`V-05` (evaluation). See [`04-workflow.md`](../architecture-tasks/04-workflow.md).
