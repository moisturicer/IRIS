# ADR-020: The IRIS Assessment Brief — per-record decision support at intake

## Status

Accepted — 2026-09-10. Decided by Lee Jasmin Adolfo (IR-217).

**The Phase 3 evaluation change in §Decision requires adviser confirmation**, on the same footing as [ADR-011](011-evaluation-framework.md)'s own "subject to adviser approval of the framework combination." Everything else here is settled.

**Amends [ADR-001](001-mvp-scope-boundary.md)**, which lists *document summarization* as out of scope for Semester 2. This is the fourth such reversal — after [ADR-013](013-chunk-level-rag-pipeline.md) (full-text chunking), [ADR-016](016-docling-structured-extraction.md) (Docling-serve) and [ADR-019](019-persisted-unified-conversation-history.md) (conversational RAG with history). See §Decision Rationale, which does not treat that as costless.

**Amends [ADR-013](013-chunk-level-rag-pipeline.md) §Decision**, whose exclusion line reads *"Still excluded: conversational memory and history · summarization (FR-M4-02, deferred by ADR-001) · agents · HyDE."* Agents and HyDE remain excluded.

**Amends [ADR-011](011-evaluation-framework.md)**'s Phase 3 definition. ADR-011's body is unedited; the amendment is recorded on its Status line and its substance is here.

**This ADR is the one ADR-019 said would be written.** ADR-019 §Status, reversing the conversational-history half of the same exclusion line, states: *"Document summarization, the other half of ADR-013's same exclusion line (FR-M4-02), is **not** reversed by this ADR; it is being specified separately as an independent capability with its own trigger, provider fallback and consumer, deliberately not bundled with conversation history."* This is that separate specification.

## Context

Two MVP validation areas have no implementation whatsoever: *"AI produces useful analysis from submitted research"* and *"IP/commercialization evaluation produces an actionable recommendation."* `apps/ai/services/summarizer.py` is three lines — `class SummarizationService: pass` — and has been since the app was scaffolded. `apps/ai/urls.py` deliberately routes nothing to it, on the reasoning that a 404 is more honest than a 500 from an empty body.

Nothing in IRIS reads a submitted record. Ask IRIS answers questions *about the repository*: `search_records()` ranks `Record.search_vector`, which holds title and abstract only, filtered to `Record.objects.publicly_visible()`. The chunk corpus [ADR-013](013-chunk-level-rag-pipeline.md) builds — an active `ChunkSet` per record, with `DocumentChunk.record` denormalized precisely so retrieval can filter by record — has never been queried by anything.

`PaperAiOverview.tsx` renders an "AI Overview" on every record's paper view, and appears to contradict the above. It does not. It scopes to the record by prefixing the title to a corpus-wide question and hoping the ranking cooperates. On a record under review — not `publicly_visible()` — that record is excluded from its own overview, so the panel can summarise a *different* paper under this one's heading. The defect is latent only because no provider key is configured today, which drives the panel into its "AI summary unavailable" state. Repairing it is [IR-218](https://citiris.atlassian.net/browse/IR-218), a retrieval fix, and is deliberately **not** this decision.

Three premises in IR-217 were checked against the tree and are wrong:

| IR-217 says | Actually |
|---|---|
| "How it sits with ADR-012" | [ADR-012](012-ai-provider-abstraction-not-a-service.md) is **superseded by [ADR-014](014-ai-gateway-as-a-service.md)**, the same day it was accepted |
| "Reuse the existing generator port" | **There is no port.** ADR-012 item 2 specified `apps/ai/providers/`; that directory does not exist, and no ABC or Protocol exists anywhere in `apps/ai`. There is `LLMGenerator` — one concrete class that reads `ANTHROPIC_API_KEY` and does `import anthropic` inline |
| "The `DisclosurePolicy` gate ADR-015 requires" | `DisclosurePolicy` has **zero occurrences** in the codebase. ADR-015 requires it; nothing implements it |

## Decision

**Build the IRIS Assessment Brief: a stored, per-record artifact generated at RDCO intake, visible to office staff only, that is decision support and never a decision.**

### Shape

Seven sections, the last optional:

1. Executive Summary
2. Key Research Findings
3. IP Signals & Suggested IP Pathway
4. Commercialization Opportunity & Recommendation
5. Attention / Review Flags
6. Evidence & Sources
7. Related Institutional Research *(optional)*

§6 is what makes per-claim citation real rather than aspirational. §7 reuses IR-218's retrieval seam and grows no retrieval of its own.

### Rules

| | |
|---|---|
| **Audience** | Office staff, on in-pipeline records. **The submitting researcher never sees their own brief** in the MVP |
| **Trigger** | Celery, on the `default` queue, fired by the transition **into RDCO intake review** — not on submit. Never awaited in a request |
| **Workflow writes** | **None, absolutely.** No write to `Record.pipeline_status`, no write to any `Review` or clearance row, no gated transition, and **no pre-filled field — not even an editable draft a reviewer confirms.** Enforced by test, and structurally by owning its own table in `apps/ai` with no write path into `reviews` |
| **Flags (§5)** | Substantive observations are permitted — possible prior disclosure, overlap with an existing record, missing consent — and **every flag cites the passage it came from.** No flag may name a disposition or a recommended action. *"This paragraph appears near-verbatim in record #412 [p.3]"* is a flag; *"should be declined for prior disclosure"* is not |
| **Provider** | `LLMGenerator` in-process, exactly as Ask IRIS calls it. No gateway dependency, no second configuration path, **and no port extracted** |
| **Disclosure gate** | A minimal `allows_ai_processing(record)` predicate over IP status, embargo and consent ships **with** the brief. **It defaults to refuse where consent is absent.** Refused content is not sent to the vendor and is not AI-processed — the [ADR-008](008-ai-degradation-to-fts.md) degradation, not a second cheaper path |
| **Degradation** | With no provider configured, **no brief is stored**, and the absence is explicit and distinguishable from "generated, found nothing." A missing brief must never render as a neutral or empty assessment |
| **Staleness** | The brief pins the `content_hash` it was generated from. On resubmit it regenerates **wholly**. When the hash no longer matches the active `ChunkSet`, the brief is displayed as **stale** and not as an assessment |

### Evaluation

**The brief is disabled for [ADR-004](004-restart-all-comparison-mode.md)'s Phase 3 comparison scenarios**, by the per-instance mechanism ADR-004 already established for the `RESTART_ALL` flag.

**Evidence for MVP areas 5 and 7 comes from a separate brief-rating block** appended to the same Phase 3 session: the same SMEs rate briefs on real records for usefulness and accuracy. No clearance decision is taken in it, so it cannot interact with the policy comparison. It sits inside ISO 9241-11 effectiveness as a context-specific measure, which is the same justification ADR-011 already uses for preserved clearances.

## Alternatives Considered

**Hold ADR-001's line and defer the brief to Phase 2.** The cheapest honest answer, and genuinely defensible — it spends the capacity on IR-218 instead, which repairs a real defect rather than adding surface. Rejected because areas 5 and 7 then ship unevidenced, and area 7 in particular has no other route: you cannot assess the patentability of a record already published to the catalogue.

**Aim the brief at readers on published records instead.** Rejected. It sidesteps the evaluation question entirely, which is its attraction, but it cannot close area 7, and the reader-facing surface already exists — folding it in here would conflate a retrieval bug (IR-218) with a scope decision.

**Read "document summarization" narrowly, so this is outside ADR-001 rather than a reversal.** Available, and a panel might accept it: ADR-001's cut list is otherwise reader-facing and administrative — the KPI dashboard, watermarking, the request queues — and workflow decision support is arguably a different animal ADR-001 never considered. Rejected because it is the convenient reading, and *"that cut meant something narrower than it says"* is how a scope boundary dies quietly. Recording it as the fourth explicit reversal costs nothing already spent on the first three and says the more useful thing.

**Let the brief pre-fill a reviewer's comment or suggested IP type as an editable draft.** Rejected, and this is where the decision would most plausibly have failed. A pre-filled field a busy reviewer accepts unchanged is an AI decision wearing a human's name, and nothing afterwards distinguishes the two — especially while [IR-144](https://citiris.atlassian.net/browse/IR-144) leaves `AuditEvent` with fourteen types and **not one workflow event**, so no record exists of whether the reviewer edited it at all.

**Descriptive-only flags** — missing sections, unreadable document, no abstract. Rejected as too weak to justify building: mechanical completeness checks need no language model and belong in the upload validator. Overlap detection against a growing corpus is the one judgment a KTTO officer genuinely cannot make unaided, and it is the most valuable thing in the brief.

**Route the brief through the AI gateway.** Rejected on its face. The gateway cannot boot — `ai/api/chat.py` imports `ai.services.chat_service`, which does not exist — and ADR-014's five preconditions plus [ADR-017](017-asgi-deployment-for-gateway-streaming.md)'s ASGI requirement are unmet. A thesis-critical feature must not be the lever that drags six unmet preconditions into the MVP.

**Extract a real provider port first, finishing ADR-012 item 2.** Tempting, and normally the right instinct. Rejected as speculative generality: [ADR-015](015-voyage-embedding-and-reranking.md) fixes the provider with no alternative in scope, so the second adapter a port would serve is not coming. Better to name `LLMGenerator` as the concrete class it is than to build an abstraction to make a stale sentence true.

**No disclosure gate; rely on the vendor opt-out toggle ADR-015 names.** Rejected outright. You cannot write a thesis about protecting unfiled institutional IP and send unfiled disclosures to a third-party model on the strength of a toggle.

**Block the brief on a full `DisclosurePolicy` module.** Rejected. It converts a one-to-two-day ticket into a blocked epic for no safety gain, since the minimal predicate *is* the enforcement point either way and is designed as the seam the fuller module fills.

**Gate by record type — never brief IP disclosures, only publication-track records.** Rejected as self-defeating: it excludes exactly the records area 7 exists to serve.

**Brief on in both arms of the ADR-004 comparison, as constant context of use.** Rejected — see §Decision Rationale.

**A 2×2 design, policy × brief.** Rejected on arithmetic. ADR-011 already records that the comparison doubles participant time and that N may be single-digit; a 2×2 quadruples it and asks for an interaction term that cannot be estimated at that N.

**Partial regeneration of the brief, mirroring the preserved-clearance rule.** Rejected as a category error, and named as one because the confusion is instructive: [ADR-003](003-clearance-aware-resubmission.md)'s rule preserves *clearances* — human judgments that stay valid because what they judged did not change. Prose cannot be partially regenerated coherently, and extending the rule to a derived artifact would muddy the exact mechanism that is the thesis contribution.

## Decision Rationale

**The evaluation interaction is the hard part, and it is an interaction rather than a confound.** The brief is present in both arms, so it does not vary with the manipulated variable. But under `RESTART_ALL`, offices re-review documents they have already cleared, and that repeated reading *is* the penalty the experiment exists to measure. A brief makes reading cheaper and makes **re**-reading disproportionately cheaper, because on second encounter a reviewer can skim the brief and skip the document. It therefore shrinks the restart-all penalty more than the clearance-aware cost, compressing the measured difference. The direction is conservative — it biases against the project's own hypothesis — but it can convert a real effect into a null, and a null produced by the instrument is not the honest negative result ADR-011 asks for.

**Splitting on ADR-011's own phase boundary was the intended answer and does not survive the calendar.** ADR-011 puts Phase 1 at Weeks 1–2 and Phase 2 (build) at Weeks 3–10; the project is in Phase 2 now. A brief built in Phase 2 cannot be evaluated in a phase that closed before it existed. So "on in Phase 1, off in Phase 3" would have left areas 5 and 7 with no evidence path at all — the precise failure this ADR exists to fix. The separate rating block is what closes that, and it works because it measures a different thing with a different instrument: accuracy and usefulness, not time-on-task, with no clearance decision taken.

**The workflow-write boundary is drawn structurally, not as a rule to remember.** The brief owns its table in `apps/ai` rather than `apps/reviews` specifically so the module holding the clearance tables is not one import away from the write path. A boundary enforced by a test and by module topology survives a contributor who has not read this ADR; a boundary enforced by convention does not.

**On being the fourth reversal.** ADR-001 was costed at ~27 dev-days against a backlog of ~81, and every reversal since has drawn on that same budget. This one is worth naming rather than smoothing over: four reversals is the point at which a scope boundary stops constraining anything, and the honest defence is not *"this was always in scope"* but *"this displaced something, and here is what."* What it displaces is supporting frontend work, per CLAUDE.md's Scope rule.

## Consequences

**Positive.** Two MVP validation areas move from "empty `pass` stub" to implemented and evidenced. KTTO gains overlap detection across a growing corpus, which is the one assessment a human cannot do unaided. The chunk corpus ADR-013 built acquires a second consumer, which makes its cost defensible. The disclosure gate ADR-015 requires finally gets an implementation, driven by the feature that most needs it.

**Negative.** The configuration evaluated for the contribution is **not** the configuration shipped — the brief is off during the Phase 3 comparison. This belongs in the thesis limitations, stated plainly. Participant time grows by the rating block, against a budget ADR-011 already flags as binding. A recurring vendor cost per submitted record, on top of ADR-015's.

**Risk — consent is the weak leg.** Submitters have not agreed to their unfiled disclosure being sent to a third-party model, and the existing RA 10173 notice does not cover it. The gate therefore **defaults to refuse where consent is absent**, which fails closed; the alternative is a consent step in the submit flow, which is scope this ADR does not authorise.

**Risk — a stale brief is worse than no brief.** A reviewer reading a confident assessment of a superseded draft, with nothing on screen saying so, is the dangerous failure. The `content_hash` pin and the explicit stale state exist for that and are not optional.

## Revisit when

Reviewer feedback shows the brief is being deferred to rather than read against — the boundary in §Decision is procedural, and evidence that it is failing in practice is grounds to withdraw the feature, not to weaken the rule. Also revisit if a consent mechanism lands and makes the default-refuse gate unnecessarily restrictive, or when the ADR-014 preconditions are met and generation moves to the gateway with everything else.

## MVP Impact

**MVP Required, thesis-critical.** Closes validation areas 5 and 7. ~1–2 dev-days for generation, storage, the endpoint and the disclosure predicate. Displaces supporting frontend work per CLAUDE.md's Scope rule.

## SaaS Impact

Positive but secondary. A per-record IP and commercialization brief is the most directly saleable capability in the system for a technology transfer office. It is per-feature, not per-tenant, so it does not complicate ADR-005.

## Security Impact

**The largest single expansion of vendor exposure in the architecture to date**, and the reason the disclosure gate is non-negotiable. ADR-015 gates *embedding* — vectors — on `DisclosurePolicy`. The brief sends full passages of pre-publication IP disclosures in a prompt, which is strictly more exposure aimed at strictly more sensitive content. Mitigations: the gate defaults to refuse absent consent; refused content is not AI-processed at all; the brief is staff-only and served through the [IR-153](https://citiris.atlassian.net/browse/IR-153) `visible_to(user)` predicate, so a refusal is a 404 identical to a missing record.

## Deployment Impact

None. No new service, no new queue — `default`, which IR-164 verified is actually consumed. No gateway dependency, so ADR-014's preconditions and ADR-017's ASGI requirement remain untouched by this decision.

## Research Impact

**Defining for areas 5 and 7, and deliberately neutral for the contribution.** The brief is off during the ADR-004 comparison so that what ADR-003's claim is measured against stays the clearance-aware resubmission mechanism alone. The rating block evidences the AI capability without touching that experiment. The `model` and `prompt_version` fields make a brief reproducible for the write-up.

## Related Requirements

**FR-M4-02 (Summarization)** — this ADR moves it from `DEFERRED (ADR-001)` to `DECIDED, NOT BUILT`; `docs/testing/TRACEABILITY.md` is updated accordingly. Also FR-M5-01 · NFR-P3 (a brief is a larger generation than the chat round-trip ADR-011 already records as unachievable at 3 s, which is why generation is never awaited in a request) · NFR-S4.

## Related Tasks

[IR-217](https://citiris.atlassian.net/browse/IR-217) (this decision) · [IR-221](https://citiris.atlassian.net/browse/IR-221) (implementation) · [IR-218](https://citiris.atlassian.net/browse/IR-218) (the retrieval seam §7 reuses) · [IR-144](https://citiris.atlassian.net/browse/IR-144) (workflow audit events, which the write boundary would otherwise rely on) · [IR-215](https://citiris.atlassian.net/browse/IR-215) (Epic G).
