# Spec 1: Authorized Evidence and database-enforced research access

**Jira spec:** [IR-712](https://citiris.atlassian.net/browse/IR-712)

**Design accepted; implementation not started.** 31 October 2026. Authority: ADR-049. Parent epic: IR-146.

## Problem Statement

Readers need research tools that can search and read complete permitted Manuscripts without exposing private Records. Moving tools out of Django must not create a second, conflicting interpretation of ownership, reviewer access, disclosure or source freshness.

## Solution

Give local AI research tools one authorized Evidence module backed by shared PostgreSQL row protection and trusted Django-issued identity. Readers sign in once; tools obtain current permitted content and exact source bindings, with safe partial results when some material cannot be used.

## User Stories

1. As a reader, I want to sign in once to use research, so that I do not maintain a second AI account.
2. As a Record owner, I want to research my permitted draft, so that I can work with unpublished material within institutional policy.
3. As a reader, I want other owners’ private Records excluded from search, so that I cannot discover confidential work.
4. As an adviser, I want to read only Records currently available to my account, so that my research follows current assignments.
5. As an office reviewer, I want to retain my institutionally defined access, so that the redesign does not silently change my role.
6. As a Paper Chat reader, I want research to remain on my selected Record, so that a tool cannot broaden scope without my action.
7. As a reader, I want to search titles and content under the same access rules, so that one search mode cannot reveal more than another.
8. As a reader, I want exact counts computed over my permitted population, so that the numbers describe what I can actually read.
9. As a reader, I want semantic subsets distinguished from catalogue totals, so that a screened sample is not presented as exhaustive.
10. As a reader, I want full Manuscript reads to recheck access, so that long reading cannot bypass the search protections.
11. As a researcher, I want reader access distinguished from provider disclosure, so that confidential content is not transmitted merely because I may view it.
12. As a Record owner, I want unknown embargo or consent handled conservatively, so that missing facts do not authorize disclosure.
13. As a reader, I want research to continue using independently permitted evidence, so that one withheld source does not erase useful findings.
14. As a reader, I want citation pages and source versions recorded, so that I can check the underlying Passage.
15. As a reader, I want revoked content removed from reused context, so that yesterday’s access does not grant access today.
16. As a reader, I want private and missing references to have safe indistinguishable behavior, so that errors do not confirm hidden Records exist.
17. As an operator, I want database identities reset between pooled transactions, so that one reader never inherits another reader’s access.
18. As an operator, I want invalid and expired grants rejected, so that the AI runtime cannot invent a reader identity.
19. As a security reviewer, I want provider attempts to revalidate disclosure dependencies, so that summaries and retries follow the same policy as original reads.
20. As a developer, I want one policy implementation shared by both runtimes, so that fixes apply consistently to every research operation.
21. As an operator, I want privileged maintenance separated from runtime accounts, so that routine execution cannot bypass row protection.
22. As an evaluation reviewer, I want review packets limited to my current access, so that evaluation does not become another disclosure path.

## Implementation Decisions

- Django remains the account and identity issuer. Issue a dedicated signed, short-lived research grant bound to deployment/audience, reader, Conversation/AskRun, selected scope, expiry and authorization generation. Roles and current Record access come from canonical database facts, not copied token allowlists.
- Distinguish grant purposes. Ordinary authenticated Django Record reads use request-scoped identity without needing a Conversation/AskRun; AI reader grants require the actual run binding. Ingestion uses a separate Django-issued job grant for one committed outbox item, Manuscript revision and processing purpose. Neither a worker identity nor a client-supplied user ID grants unrestricted reading; current source/disclosure checks still apply. Test cross-purpose replay and unrelated-revision denial.
- Use a dedicated HMAC signing key shared only by the Django issuer and protected PostgreSQL verifier. The AI runtime transports the signed grant and cannot mint it. Verify signatures inside the trusted database mechanism; unsigned user IDs or session settings are never accepted as principals. Rotation uses key identifiers and overlapping verification only within bounded validity.
- Apply row-level protection to Record research reads and dependent content, vector, metadata and provenance relations. Force protection where applicable; runtime roles neither own protected tables nor carry bypass privileges. Restrict verifier/function execution and search paths; missing context denies access. Maintenance uses separate credentials.
- Set verified identity/scope transaction-locally, using short transactions. Validate grant and current account state, authorization generation and scope on each read. Pool reuse, savepoints and retries cannot reuse another reader’s context. Grant renewal rechecks ownership/account state and never increases the original research allowance.
- Migrate current intended visibility into one database authority. First run parity tests against existing role/owner/adviser/catalogue rules, then switch both runtime readers. Remove the independently maintained research-read predicate after parity; do not change unrelated workflow-write authorization.
- The Evidence interface returns authorized Record references, versioned Passages, typed metadata facts and coverage/continuations. All local search, full reads, outlines, pages, counts and citation resolution use it. Models cannot supply identity, credentials or arbitrary SQL; Record selections become validated run-scoped handles.
- Separate reader permission from provider disclosure. Check current access, source versions, consent/IP/embargo and the chosen provider policy before each physical outbound attempt, including embeddings, reranking, compaction and retries. Unknown governing facts deny transmission. Preserve the existing missing-embargo refusal until authoritative data is implemented.
- Bind cached content and derived Conversation artifacts to source/access dependencies. On revocation or source replacement, invalidate affected raw excerpts, tool results, plans, handoffs and opaque provider state; rebuild permitted context before the next send/commit. Already-sent provider content cannot be recalled; do not claim instantaneous external revocation.
- Return safe partial results without hidden titles, identities or counts. Exact aggregation includes authorized metadata only; provider-disallowed content cannot enter a model-facing payload. Treat document instructions as untrusted content.
- Keep one PostgreSQL deployment initially, with institutional ownership distinct from AI-owned state and restricted accounts. Database connections and query work are bounded; direct access does not mean unrestricted access or a model-controlled query engine.

## Testing Decisions

- Primary seam: authenticated Ask IRIS requests, streamed activity, delivered/reopened Turns and reviewer packets. Assert permitted outputs and non-disclosure rather than one SQL query shape or tool order.
- Necessary lower seam: real PostgreSQL under actual restricted Django/AI roles. Test owner, adviser, office, other authenticated reader, anonymous/disabled account, soft deletion, scope and direct dependent-table reads; compare migrated outcomes with the current policy.
- Attack signed context with wrong signature/audience/deployment/reader/run/scope, expired grant, stale authorization generation, raw setting forgery and consecutive pooled-reader transactions. Verify owner/bypass privileges cannot accidentally reach runtime credentials.
- Change access, consent, source version and metadata between reads, immediately before a provider attempt and before final commit. Assert no affected content in outgoing payloads, final answers, citations, history, progress or unauthorized review artifacts.
- Prior art: existing Record visibility tests, route authorization matrix, controller revocation/continuation regressions, disclosure policy tests and IR-605/IR-608 safety collection. Fake providers record transmitted inputs; real provider calls are unnecessary for policy correctness.

## Out of Scope

- Separate AI logins or copied account passwords.
- New institutional role/access policy beyond preserving intended current behavior.
- Arbitrary SQL/code/browser tools for the model.
- Permission to transmit institutional data or enable paid providers.
- Runtime data cleanup or a second research database.

## Further Notes

Authority: ADR-049, accepted design on 31 October 2026 following the owner’s instruction to choose the recommended options and publish specs/subtickets. Parent epic: IR-146. Related prior work: IR-605 evaluation and IR-703 immediate controller fixes. This is specified implementation work, not evidence of completion or approval for paid inference, institutional transmission, production settings, deletion or deployment. Production profile values must be explicit and validated; absent values refuse paid enablement. Subtickets are unassigned, ready-for-agent and linked by native dependencies; a blocked prerequisite is not permission to skip its tests.

### Acceptance criteria

Existing-work dependency: IR-250 supplies the canonical embargo facts/writer/backfill for ordinary real-Record disclosure enablement and blocks IR-720. Preserve unknown-fact refusal until it lands; do not duplicate or silently bypass that institutional decision.

- [ ] The same role/ownership fixtures produce equal allowed Record sets in Django and AI research reads.
- [ ] Missing, forged, expired or scope-mismatched context returns no protected data, including dependent text/vectors and aggregates.
- [ ] A pooled connection used by two different readers never carries access between them.
- [ ] Every local research tool uses the shared Evidence authority and preserves page/source-version bindings.
- [ ] Unknown disclosure facts prevent provider transmission while permitted independent findings remain usable.
- [ ] Revocation/source changes invalidate dependent active context before its next verified send or commit.
- [ ] Public denied/missing outcomes and unauthorized packets reveal no private Record identities.
- [ ] Runtime credentials cannot change institutional Records, access signing secrets or bypass research row protection.

### Implementation slices

- **IR-717 — Establish delegated reader grants and restricted database identities.** Implement grant issue/verification/renewal and the restricted role split. Prerequisites: none within this program.
- **IR-718 — Enforce one row-protected research-read policy in both runtimes.** Move intended research visibility into shared database enforcement. Prerequisites: IR-717.
- **IR-719 — Run local research tools through authorized Evidence.** Move search/read/outline/page/count execution behind the Evidence interface. Prerequisites: IR-718.
- **IR-720 — Fence disclosure and revoke derived evidence before reuse.** Apply current transmission policy and dependency invalidation at outbound boundaries. Prerequisites: IR-718.
- **IR-721 — Prove cross-runtime access parity and evidence safety.** Deliver the database and authenticated-reader security contract evidence. Prerequisites: IR-719, IR-720.
