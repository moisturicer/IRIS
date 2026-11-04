# Spec 5: Versioned research publication, upgrades and IR-605 cutover evidence

**Jira spec:** [IR-716](https://citiris.atlassian.net/browse/IR-716)

**Design accepted; implementation not started.** 31 October 2026. Authority: ADR-049. Parent epic: IR-146.

## Problem Statement

Readers need current source versions and reliable upgrades without mixing old/new vectors, exposing stale permissions or replacing the working pipeline based on an attractive demo. The new runtime must preserve institutional data and earn cutover through the existing evaluation workflow.

## Solution

Publish AI-derived research revisions from committed institutional changes, activate only validated source/index versions, and upgrade providers with pinned compatibility. Extend IR-605 for the new engine and long-context cases, then perform one controlled replacement with rollback.

## User Stories

1. As a Record owner, I want Manuscript revisions to become researchable reliably, so that I do not manually repair missing indexing.
2. As a reader, I want research to use the active Manuscript revision, so that answers do not silently use superseded content.
3. As a reader, I want stale processing jobs unable to reactivate older content, so that out-of-order work cannot undo a revision.
4. As an operator, I want duplicate ingestion to work idempotent, so that queue redelivery does not repeat paid indexing.
5. As a reader, I want failed extraction distinguished from a paper reporting nothing, so that processing gaps are not research findings.
6. As a Record owner, I want deletion/access changes to take effect before index cleanup finishes, so that projection lag cannot preserve access.
7. As an operator, I want derived research data to have one writer, so that Django and AI workers do not race over active revisions.
8. As an operator, I want a pending Embedding Space built alongside the active one, so that model upgrades do not overwrite live vectors.
9. As a reader, I want queries and documents to use compatible vectors, so that an apparently valid search does not compare incompatible models.
10. As an operator, I want coverage verified before activation, so that a half-indexed corpus is not published as complete.
11. As an operator, I want a compatible prior revision available for rollback, so that an unsuccessful upgrade can be reversed.
12. As a reader, I want in-flight research to pin its model and protocol, so that deployment does not change an investigation midway.
13. As an evaluation owner, I want to reuse IR-605 collection and reviews, so that existing evaluation work remains useful.
14. As an evaluation owner, I want the new runtime to have its own honest engine identity, so that it is not disguised as an old controller.
15. As an evaluation owner, I want matched-condition comparisons separated from expanded allowances, so that more spending is not presented as architectural efficiency.
16. As a reviewer, I want long-document and compaction cases reviewed and frozen, so that new capabilities are evaluated before release.
17. As a reviewer, I want families with insufficient examples to remain inconclusive, so that small samples are not presented as reliable.
18. As a budget owner, I want cold/warm costs and failed attempts retained, so that cost per successful task includes real work.
19. As a security owner, I want any access/disclosure breach block cutover, so that average answer quality cannot hide a serious failure.
20. As a release owner, I want worker database browser and load evidence recorded, so that missing execution environments do not count as passes.
21. As an operator, I want development Conversation cleanup strictly scoped, so that research Records and spending/evaluation history are not accidentally discarded.
22. As a reader, I want one new implementation after validated cutover, so that behavior is consistent rather than split across permanent engines.
23. As a release owner, I want human approval separate from implementation completion, so that publishing code does not authorize deployment.

## Implementation Decisions

- Django remains the source of authoritative Record/Manuscript/account/access facts. Emit committed revision/deletion work through an outbox; AI-owned ingestion consumes it idempotently with retries/reconciliation. Current canonical access facts, not delayed events, govern every research read and send.
- Issue scoped processing authority with committed work: each ingestion grant identifies the outbox item, exact Manuscript revision and allowed purpose. It cannot read unrelated Records, become a reader login or bypass row protection. Recheck current source/disclosure state before paid processing; stale/revoked jobs stop safely. Grant renewal, if required, revalidates the canonical work item rather than extending obsolete authority.
- Move derived extraction/chunk/embedding publication to AI ownership with one migration/writer authority. Preserve the existing structured extraction choice and pure chunk/repository contracts where useful. Pin Manuscript/extraction/content versions so duplicate or superseded work cannot activate stale derived content.
- Build immutable pending research revisions and Embedding Spaces, verify source coverage, dimensions, embedding query/document semantics and retrieval quality, then activate atomically. Both Record- and Passage-level vectors must carry space identity; complete the current Record-vector parallel-space limitation before a true side-by-side embedding upgrade.
- Pin model/adapter, prompt/tool/protocol, context and stored-state versions per AskRun. Deploy compatible readers before writers change stored formats; drain/fence or safely reconstruct supported runs before removing old versions. Provider model switches and embedding-space upgrades are separate controlled operations.
- Reuse IR-605 authenticated replay, packets, human labels/double review/adjudication, manifest checks, repeated runs, cost reporting and IR-608 safety evidence. Add an explicitly named new engine/arm and transport adapter while keeping baseline collectors/readers capable of interpreting old exported artifacts. Do not re-label a new runtime as an old engine.
- Architecture comparisons match model, corpus, questions, data policy, limits and cache conditions, with normalized effective model identities and per-attempt purpose logs. Larger-allowance capabilities and model changes are separate reports. No permanent reader engine selector or second routine retrieval stack is added for evaluation.
- Version and review long-Manuscript/long-Conversation/compaction/revocation/interruption cases before counted collection. Freeze held-out prompts, labels, rubric and thresholds before opening outputs. Preserve original baseline evidence and report which arms/scenarios are unavailable.
- Selected initial quality objectives are task completion at least 90%, claim/citation/applicable page support at least 95%, with at least ten distinct cases before reporting a family and at least three repeated runs. Apply existing denominators per reported repetition/family and report Wilson intervals, unreviewed/inconclusive cases and limitations. Any access/disclosure breach or missing required safety evidence blocks cutover. Matched-condition aggregate metrics must not regress from the frozen baseline.
- Predeclare workload and performance/cost profile before paid collection. Measure queue-inclusive ordinary/deep p95, concurrency, tool/model time, memory/connections/lock pressure, all physical attempts and cost per successful task; report cold/warm and missing usage separately. Fake providers prove contracts only. Funding, provider/data transmission approval and production numeric caps are external operational gates, not invented spec defaults.
- Perform a controlled cutover only after recorded safety/quality/load/browser evidence and human release approval. Transfer writers once, drain/fence old runs, then retire old execution. Keep a version-compatible deployment rollback. Existing development Conversations may be reset through a separately reviewed scoped operation; preserve institutional Records/Manuscripts/accounts/workflow, spending and required evaluation artifacts.

## Testing Decisions

- Primary seam: authenticated reader questions and resulting current-version citations, evaluated through IR-605. Assert published behavior rather than ingestion function ordering or exact internal queue layout.
- Real database/independent-worker tests inject duplicate/out-of-order ingestion, failed extraction/indexing, source deletion/revocation, lost outbox notification and activation races. Only the newest complete permitted revision can become active.
- Build two embedding identities and verify query/document compatibility, promotion refusal for incomplete coverage, Record/Passage space isolation and safe rollback. Use stored vectors/fakes for contract evidence, not vendor quality claims.
- Extend evaluator preflight for new engines, schema versions, effective model equality, compatible imported baseline artifacts and deliberately mismatched budgets. Preserve independent reviewers, held-out freeze, minimum-family rules and explicit missing usage.
- Run browser/protocol, worker recovery, database grants and load exercises as separate evidence classes. A required check without its environment is not_measured, not passed. Prior art: current ingestion/idempotency/repository tests, Embedding Space promotion checks, IR-605 repeated-campaign reports and IR-608 scenarios.

## Out of Scope

- Creating another evaluation framework instead of extending IR-605.
- Lowering minimum-family counts, replacing human review with an AI judge, or tuning on held-out outputs.
- Unapproved live campaigns, provider adoption or production deployment.
- Automatic deletion of existing database data during implementation.
- A new vector platform, independent database cluster or permanent dual reader engine.

## Further Notes

Authority: ADR-049, accepted design on 31 October 2026 following the owner’s instruction to choose the recommended options and publish specs/subtickets. Parent epic: IR-146. Related prior work: IR-605 evaluation and IR-703 immediate controller fixes. This is specified implementation work, not evidence of completion or approval for paid inference, institutional transmission, production settings, deletion or deployment. Production profile values must be explicit and validated; absent values refuse paid enablement. Subtickets are unassigned, ready-for-agent and linked by native dependencies; a blocked prerequisite is not permission to skip its tests.

### Acceptance criteria

- [ ] Committed institutional changes generate recoverable idempotent ingestion work; stale/duplicate jobs cannot activate superseded content.
- [ ] Published research content and citations identify the active permitted source revision.
- [ ] Record/Passage vectors remain keyed to compatible Embedding Spaces; incomplete promotion is refused.
- [ ] IR-605 accepts the explicitly versioned new engine while preserving old artifact scoring and all comparability/review gates.
- [ ] Long-context/compaction cases are reviewed and locked; counted runs satisfy repetition/family/safety requirements.
- [ ] Matched and expanded-capability results are reported separately with measured usage or explicit missing markers.
- [ ] A cutover report includes quality objectives, baseline comparison, real recovery/access/browser evidence and predeclared load/cost profile results.
- [ ] Cutover/rollback/reset procedures enforce one writer and preserve institutional and required spending/evaluation data; no automatic deployment is performed.

### Implementation slices

- **IR-737 — Publish committed institutional research changes through durable work.** Implement outbox/reconciliation with explicit institutional and AI ownership. Prerequisites: IR-718, IR-723.
- **IR-738 — Move versioned extraction indexing and active-source publication to AI workers.** Reuse extraction/chunk contracts under the new owner and worker pools. Prerequisites: IR-737, IR-719, IR-725.
- **IR-739 — Support parallel Embedding Spaces and safe promotion rollback.** Make Record/Passage vector identity consistent for true upgrades. Prerequisites: IR-738.
- **IR-740 — Extend IR-605 for the new engine and large-context evaluation.** Adapt collection/manifests/case packs while preserving review/scoring rules. Prerequisites: IR-727, IR-732.
- **IR-741 — Record IR-605 quality safety and scalability acceptance evidence.** Implement reproducible campaign/load reporting and deployment-profile checks. Prerequisites: IR-740, IR-721, IR-726, IR-731, IR-736, IR-739.
- **IR-742 — Prepare controlled AI cutover retirement and version-compatible rollback.** Deliver the release/reset/ownership procedures without executing deployment. Prerequisites: IR-741.
