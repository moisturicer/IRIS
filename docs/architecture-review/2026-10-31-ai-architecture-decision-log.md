# Ask IRIS architecture interview and spec map

Started 31 October 2026. Status: **interview closed by owner; specs and Jira backlog published**. This log preserves the interview history; ADR-049 and the five published specs are the consolidated design.

## Requested outcome

The owner requested an interview covering all five recommended architecture areas, with separate specifications and implementation subtickets for each. Explain decisions in plain language, with context, examples, benefits, and costs.

Provider independence was explicitly selected earlier in this conversation. Rounds 1–2 accepted a FastAPI-hosted AI runtime with local tools and controlled database access, AI ownership of Conversation/execution data, one initial PostgreSQL deployment, and replacement of the old AI path after validation using IR-605. The owner subsequently delegated all remaining recommended choices. [ADR-049](../adr/049-dedicated-ai-runtime-and-local-research.md) consolidates them and supersedes provisional ADR-059.

## Planned specification tracks

| Track | Intended scope | Decisions still needed |
|---|---|---|
| Authorized Evidence | Reader identity, Record access, provider disclosure, source versions, local retrieval, citation provenance | Access enforcement location, trusted identity, freshness, revocation and failure behavior |
| AskRun execution and spending | Queueing, worker ownership, deadlines, cancellation, checkpoints, provider attempts and final Turn commitment | Persistence ownership, recovery semantics, bounds, fairness and uncertainty after remote timeouts |
| Conversation research | Continuous model/tool conversation, task list, evidence sufficiency, final answer validation and repairs | Model behavior, deterministic tools, completion rules, reader progress and fallback behavior |
| Context and compaction | Full Manuscript reading, model capacity, source dependencies, recent Turns, compact handoffs and detail recovery | Allocation policy, compaction strategy, manual action, retention and compatibility |
| Research publication and upgrades | Extraction/indexing revisions, Embedding Spaces, derived-data ownership, activation and rollback | Migration scope, publication consistency, storage placement and upgrade acceptance |

Each completed spec will include scope and exclusions, accepted decision references, examples, measurable acceptance criteria, dependencies, migration/rollback behavior, and linked implementation subtickets. Cross-track requirements belong in the shared architecture decision and are referenced by each affected spec.

Published under IR-146: IR-712 Authorized Evidence, IR-713 AskRun execution, IR-714 Conversation research, IR-715 context/compaction, IR-716 publication/upgrades/evaluated cutover; 26 implementation Subtasks IR-717–IR-742. Native blocking links define prerequisites. All are To Do, unassigned and ready-for-agent. See the [spec/backlog index](../superpowers/specs/2026-10-31-ai-runtime/README.md).

## Design tree

Root decisions, settled in round 1:

- R1, accepted: FastAPI owns AI execution and local tools; Django retains institutional workflow; direct research reads use controlled database access with one authoritative access implementation.
- R2, accepted: detailed research may spend more time and allowance than simple conversational requests; define quality and speed targets separately. Numeric limits remain open.
- R3, accepted with correction: existing Conversations are development-only and may be discarded; historical Conversation/citation-link migration is not required. This does not extend to Records, Manuscripts, accounts, review history, or other data. No deletion has been performed or scheduled.

After relevant root decisions settle:

1. Set data ownership and the trusted identity/access mechanism.
2. Set provider disclosure and current-access checks on every outbound attempt.
3. Set run lifecycle, recovery, queue fairness and paid limits.
4. Set agent planning/tool/answer behavior and validation.
5. Set large-context allocation, full reading and compaction.
6. Set source publication, model upgrades, migration and compatibility.
7. Set quality/performance evaluation and release gates.
8. Check the complete decision tree with the owner, finalize specs, and create linked Jira work.

Questions may run together only when their prerequisites are settled; an answer can reopen later branches.

## Recorded answers

Round 1, 31 October 2026: owner replied, “all recommended answers, but for q3, since its still in development the previous conversations existing in the db are only for development purposes so can be discarded”. R1/R2 accepted; R3 corrected as above. This authorizes designing a disposable development-Conversation cutover, not executing a database cleanup now.

Round 2, accepted on 31 October 2026:

- R4: AI runtime is the sole owner/writer of Conversation, Turn, citations, AskRun and AI progress/spending data after cutover. Django retains institutional data ownership.
- R5: Begin with one PostgreSQL deployment and logically separated institutional versus AI-owned data with restricted credentials. Separate databases are a later measured scaling decision.
- R6: Retire the previous AI execution path after validated cutover rather than maintain two long-term implementations. Preserve deployment rollback. The owner explicitly added: “make use of the IR-605 evaluation”.

IR-605 was read from Jira in this round (tracking status Done). Reuse its authenticated reader collection, run manifests, label/review workflow, scorer, repeated campaigns, cost records and IR-608 safety evidence. Its implementation being complete is not evidence that a counted architecture comparison has passed. The current runner/scorer names specific old engines; the new runtime requires an explicit compatible extension, not relabelling it as an old engine. Preserve existing review, frozen-set and comparability protections. Capacity/load evidence supplements quality evaluation.

Round 3, accepted on 31 October 2026 (owner replied “yes” to all three recommendations):

- R7: Use database-enforced shared research access, not independently maintained Django/FastAPI filters. Restricted credentials are required; reader access and provider disclosure remain distinct. Exact RLS/function/identity implementation follows later.
- R8: Django remains the identity authority. The AI runtime verifies delegated identity and permitted scope rather than maintaining separate logins/accounts. Current access is checked during research, not inferred indefinitely from an identity proof.
- R9: Use IR-605 for matched-condition architecture comparisons and separately labelled larger-allowance capability evaluations. Add versioned long-context/compaction cases without changing inspected held-out cases; retain human review and safety requirements.

Round 4, accepted on 31 October 2026 (owner replied “yes”):

- R10: Row-level protection is the baseline for research reads, supplemented by predefined research operations where useful. Restricted runtime credentials cannot be database owners or bypass row protection. Exact verified identity propagation and privilege implementation require further design.
- R11: When access changes mid-investigation, invalidate affected context and rebuild from remaining allowed material within the original allowance. Recheck before outbound requests and final delivery. Do not finish from an obsolete permission snapshot or merely remove its citations; already-transmitted content cannot be recalled.
- R12: On missing/unknown disclosure facts, withhold affected material from providers while continuing with permitted evidence. Preserve ADR-015's fail-closed rule. Explain limitations without identifying protected material; if nothing supports the request, report inability to complete it.

Round 5, accepted on 31 October 2026 (owner replied “yes”):

- R13: Closing/disconnecting the browser leaves the bounded AskRun running. Explicit Stop cancels it. Original deadlines and spending allowances still apply.
- R14: Recover from verified durable checkpoints under the same remaining allowance; repeat only unrecoverable work. Account conservatively for uncertain provider attempts and prevent duplicate final Turns. A restart does not reset spending.
- R15: Protect short interactive capacity, separate ingestion from research, and apply fair scheduling/per-reader limits without starving deep research. Numeric concurrency is measurement-driven.
- R16: The same model autonomously plans, chooses permitted research tools, assesses evidence and drafts the answer within scope/allowance. Ask only for materially blocking ambiguity. Institutional data remains read-only; AI task-state writes are permitted.

## Owner-directed synthesis and publication

After round 5, the owner instructed: “skip the grilling. Choose all recommended choices and proceed with spec and tickets under the AI/RAG epic”. This supersedes the earlier plan for four more rounds and a separate confirmation. No further interview or test-seam approval was requested.

Recommendations Q17–Q20 are accepted by that instruction: useful full-Manuscript context rather than always filling a window; automatic and manual compaction; recoverable original Turns; concise task lists and truthful progress without raw reasoning. ADR-049 records the remaining recommended technical synthesis, including bounded same-model finalization/one repair, compatible provider reconstruction, versioned publication/Embedding Spaces, operational retention controls, IR-605 acceptance objectives and controlled cutover.

The primary test surface remains the authenticated reader experience already approved for IR-605. Real database-role and independent-worker tests prove properties that cannot be established through process-local fakes. Browser/accessibility and vendor/load measurements stay distinct evidence classes.

The five specs use the requested to-spec structure, extensive numbered user stories, implementation/testing decisions, exclusions and checkable acceptance criteria. Subtickets are implementation slices, not claims of completed work. Documentation publication performs no runtime implementation, paid inference, data deletion or deployment.

## Documentation rules

Record settled tradeoffs as ADRs when they are costly to reverse and important for future readers. Use the repository's three-digit numbering and explicitly reconcile ADR-014, ADR-024, ADR-026, ADR-040/041 and ADR-042 where affected. Do not mark recommendations accepted on the owner's behalf.

Use CONTEXT.md as this repository's existing domain glossary, as directed by docs/agents/domain.md. Add newly resolved domain terms there without creating a second competing glossary. Keep implementation choices in ADRs/specs rather than glossary definitions. Preserve existing uncommitted edits.

## References

- [Architecture findings and proposal](2026-10-31-single-agent-large-context-review.md)
- [Domain-documentation convention](../agents/domain.md)
- [Jira conventions](../agents/issue-tracker.md)
- [Definition of Ready and Done](../engineering/DEFINITION_OF_DONE.md)
