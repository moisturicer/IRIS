# ADR-016: Conditional parallel-office routing

## Status

**Proposed** — 2026-09-04. Not accepted. Implemented behind this ADR so the change has a paper
trail before the team formally decides; do not treat the code as settling the question this
document raises. AI does not approve its own architectural decisions — a human reviewer does.

## Context

Today, which offices review a Thesis/Research or Project disclosure is fixed by `record_type`
alone (`reviews/services.py`, hardcoded): every Thesis/Research goes through IERC **and** KTTO;
every Project goes through ITSO, then IERC **and** KTTO. All three offices' scopes are
type-specific and mostly independent of each other:

| Office | SRS-defined scope |
|---|---|
| ITSO | Technical verification, patent drafting assessment, prior-art checking — protectability and novelty |
| KTTO | Commercial potential, industry-partnership viability, technology-transfer readiness |
| IERC | Ethics compliance — human/animal subjects, sensitive data |

Not every disclosure touches all of these. A thesis with no human-subjects component has no
ethics question for IERC. A project with no commercialization intent has nothing for KTTO to
evaluate. Requiring all applicable-by-type offices unconditionally means every submission pays
the review cost of every possible IP angle, regardless of whether that angle exists in the work.

This surfaced while implementing IR-88 (Submit Disclosure wizard): the wizard's own document
checklist, driven by the same per-type logic, showed 13 mandatory documents for a single
Thesis/Research submission — several IP-type-specific (Patent Draft, Trademark, Copyright) and
required regardless of whether the disclosure claims that kind of IP at all. Against **NFR-U2**
(10-minute first-submission target, 5 of 5 participants must pass — the tightest usability
constraint in the SRS), this is very likely a source of failure, not just an inconvenience.

## Decision

**Which parallel offices (ITSO/IERC/KTTO) review a disclosure becomes conditional, requested by
the submitter and confirmed by RDCO — not fixed by `record_type` alone.** The bookends stay
exactly as ADR-002 and ADR-003 already describe: RDCO always does intake and final sign-off for
Thesis/Research and Project; the Adviser is the sole reviewer for Proposal. ITSO remains
structurally Project-only — Thesis/Research never enters `itso_review`, requested or not.

Mechanically:

- Four new fields on `Record`: `requires_ethics_review` (no existing flag covers IERC's scope),
  `requested_itso`, `requested_ierc`, `requested_ktto`.
- The frontend suggests office requests from signals the submitter already provides —
  `is_ip` → ITSO (Project only), `for_commercialization` → KTTO, `requires_ethics_review` →
  IERC — pre-checked, independently overridable. `community_extension` maps to no office; none
  of the three's SRS scope covers it.
- `apps/reviews/services.py::approve_record()`, at `rdco_intake`, creates `RecordClearance` rows
  for whichever offices were requested, instead of a hardcoded set. A record requesting nothing
  goes straight to `rdco_review` — a clearance stage with no office attached would just
  auto-clear, which is worse than not existing. Project's ITSO-before-IERC sequencing
  (`submit_clearance`'s ITSO-clears branch) is preserved in shape, conditional in which offices
  it actually populates: IERC is only created there if requested, and if nothing else is
  pending once ITSO clears, the record advances straight to `rdco_review` rather than a
  now-empty `parallel_review`.
- RDCO's ability to **amend** the requested set at intake (add an office the submitter missed,
  remove one that doesn't apply) is **not implemented by this ADR** — `EvaluationPage` currently
  shows the request read-only. Filed as a fast-follow (see Jira link below) rather than expanded
  into this change.
- The submission wizard's document checklist is reduced to the manuscript only. Every other
  document (ethics clearance form, similarity report, KTTO's disclosure form, etc.) is requested
  later, by the office that actually needs it, once the record is routed there — via the
  existing `DocumentsPage` (`/records/:id/documents`), which already supports per-slot upload
  against an existing record. This required no new document infrastructure.

## What this does NOT change

**ADR-002's transition table is untouched.** `pipeline_status` transitions remain a declarative
`(from_status, event, actor_role) → to_status` mapping; this ADR only changes what decides
*which offices populate a `RecordClearance` row*, which was never part of that table — it was a
hardcoded side-effect inside `approve_record()`. **ADR-003's clearance-aware resubmission is
untouched** — it operates on whatever `RecordClearance` rows exist, however they got selected.

## Alternatives Considered

**Build FR-M2-01 properly first** (Department Templates + Office Checklists + conditional
rules, per SRS §3.2.2.1 — filed separately as IR-118). Rejected for *this* change: it is a
multi-day, unscoped feature addressing document *requirements*, not office *routing*. This ADR
solves the routing half now, narrowly, without blocking on or duplicating that larger effort.

**Keep type-fixed routing, just trim the document list.** Solves the NFR-U2 symptom without the
underlying cause: every Thesis/Research would still force an unrelated ethics review onto work
with no ethics question, because IERC's inclusion was never actually about ethics — it was
about type.

**Free-text "which office do you think this needs?"** Rejected: unstructured input would need
a human or a model to parse it before routing could happen at all, reintroducing exactly the
kind of fabricated-AI-feature risk already ruled out elsewhere in this submission flow (see
`iris-submit-disclosure-design` memory on the mockup's unbacked AI pre-fill).

## Decision Rationale

Fixing the document-checklist symptom without touching routing would have left the actual
cause in place: IERC's involvement was never really about ethics, it was about type. Once the
signals that determine IERC/KTTO/ITSO relevance are already collected as form fields for other
reasons (IP flags), deriving office suggestions from them costs one migration and a handful of
`useEffect`s — far cheaper than either building FR-M2-01's full conditional-rules engine now or
leaving the over-inclusion in place and accepting the NFR-U2 risk.

## Consequences

**Positive.** A disclosure with no ethics or commercialization angle no longer pays for review
stages that would auto-clear on cursory review. `submit_clearance`'s ITSO branch is genuinely
simpler than before (reuses `_all_clearances_done` instead of a separate unconditional creation).

**Negative.** A submitter can under-request (uncheck something that actually applies). RDCO's
read-only view of the request at intake is the only present safeguard; the amend-UI fast-follow
is what makes that safeguard real rather than nominal — until it exists, an under-requested
disclosure can only be caught if RDCO happens to notice and manually adds a `RecordClearance`
row outside the wizard.

**Risk.** This ADR is Proposed, not Accepted. It changes routing behavior on the same code path
ADR-002 and ADR-003 both depend on. A reviewer should specifically check the six new
`apps/reviews/tests.py` cases against the sequencing described above before accepting.

## MVP Impact

Backend (`Record` fields, migration, `approve_record`/`submit_clearance`) and the student-facing
request UI are implemented. RDCO's amend UI is not — tracked separately.

## SaaS Impact

Neutral-to-positive. The signal→office mapping (`is_ip`→ITSO, `for_commercialization`→KTTO,
`requires_ethics_review`→IERC) is presently hardcoded in `PaperDetailsStep`; a second
institution with different office names or a different mapping would need this parameterized,
same as ADR-002 already anticipates for the transition table itself.

## Security Impact

None beyond what already governs `RecordClearance` creation and review permissions.

## Deployment Impact

One migration (`records/0009_add_office_routing_fields.py`), additive, no backfill needed —
existing records default every new field to `False`.

## Research Impact

None directly — the thesis contribution (ADR-003) is unaffected; this changes which offices
enter clearance, not how clearance-aware resubmission behaves once they do.

## Related Requirements

Extends the routing described in ADR-002 and ADR-003. Motivated by NFR-U2. Adjacent to, but
does not implement, FR-M2-01 (IR-118).

## Related Tasks

IR-88 (Submit Disclosure wizard, where this was found). RDCO amend-UI fast-follow: filed
separately in Jira.
