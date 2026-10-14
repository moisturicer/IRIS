# Full-reading Record comparison (IR-549)

The opt-in comparison workflow consumes IR-556's cited paper briefs, builds a
table in application code, then asks the existing answer model to describe that
table. It replaces the legacy comparison's shared passage budget only when
`AI_COMPARISON_ENABLED` is enabled. Other deployments retain their existing lane.

## Approval and enablement

This implementation does not accept the Proposed ADR-036 paper-brief amendment
or authorize institutional transmission, paid evaluation, or deployment.
`AI_COMPARISON_ENABLED=False` remains the default. Accepted requirements and ADRs
remain authoritative over Jira. The 14 October IR-549 scope replaces proposal
13's small shared-passage example for this disabled implementation, while
architectural acceptance remains a separate human decision.

Enablement requires `AI_DURABLE_ASK`, `AI_PAPER_BRIEFS_ENABLED`, research routing,
and `AI_PROVIDER_ADMISSION=enforce`. The answer model's verified context windows
must be configured as IR-556 requires. Every provider attempt still passes the
deployment-wide campaign, lane, account, pricing and queue controls.

`AI_COMPARISON_MAX_RECORDS` defaults to 6 and must be at least 2. The client
retrieves this value from `/api/v1/ai/status/` before sending selected IDs; the
server validates the same bounds. `AI_COMPARISON_DEADLINE_SECONDS` defaults to
300. Attempts, input/output tokens and cost require explicit
`AI_COMPARISON_MAX_ATTEMPTS`, `AI_COMPARISON_MAX_INPUT_TOKENS`,
`AI_COMPARISON_MAX_OUTPUT_TOKENS` and `AI_COMPARISON_MAX_COST_USD`. Blank controls
refuse submission, without dispatching provider work. They are not budget
approvals. The run snapshots its comparison ceilings and fixes its deadline at
submission; retrying a worker never resets either. Shared campaign limits still
apply if the comparison ceilings are higher than ordinary chat's.
Each brief also has a stable reservation `work_key`, so its reported usage is
attributed independently while the encompassing comparison retains all charges
against its run ceiling. Older standalone reservations resolve through their
original brief run key.

## Request and answer contract

Use the existing `/api/v1/ai/ask/stream/` and an owned `conversation_id`. Name
complete titles, or supply distinct positive `comparison_record_ids` with 2 to N
IDs. The Record-picker UI is separately tracked in IR-574. Paper Chat scope and
injection screening continue to constrain route overrides. An unresolved or
ambiguous title requires clarification before any subset is compared.

The durable worker requests each current brief on first use, with each Record's
complete reading bounded by that model's own context window. There is no source
count or shared passage limit for the new table. Question-specific detail may
read that Record's current sections again; one Record's context does not reduce
another's. Provider and run exhaustion remain explicit failure conditions.

`done.comparison` and reopened Turns carry Records, dimension rows and cells,
per-Record coverage and `removed_claims`. Cells retain exact quote/chunk/page
pointers. `not_reported` is distinct from failed verification. The prose model
receives the table rather than the original corpus. Literal citation, number
and title checks reuse IR-512. Failed claims are removed individually and the
coverage note reports their count. Literal checks do not establish semantic
entailment or real-provider answer quality; independent subject review remains
required.

The existing progress line reports reading paper i of N, building the comparison
and checking citations. Table page controls use the established citation
navigation. No private question or quote is inserted into a URL. The table
precedes prose, and narrow screens scroll within the table region.

## Source safety and persistence

Visibility, disclosure eligibility, active ChunkSet identity and quote support
are checked before generation and before output. The stored comparison retains
source identities privately; these are removed from its public shape. Citation
quotes are stored only as chunk/page/span/hash pointers on the Turn and are
resolved from the current chunk on read, following ADR-026's storage rule. Replay
checks current access and versions again. A changed or restricted source
withholds the comparison's content instead of exposing an obsolete table or
description. Comparison Turns are excluded from model history until their full
provenance can be reauthorized for that use. No prior Turns are deleted.

## Evaluation boundary

IR-542's committed baseline currently contains b01–b07 and no labelled comparison
case. Its proxy audit also records no labelled named-record comparisons.
Therefore this PR cannot report a measured full-reading-versus-legacy quality
improvement from that pack. The new deterministic HTTP fixtures separately
exercise supported numbers/pages, absence, failures, stale sources and removed
claims. They demonstrate application behavior, not model correctness.

Before rollout, a human must add and confirm comparison labels with Record,
page and supporting quote, then run both designs on identical questions and
source versions. Record claim support, rendered-page accuracy, honest absence,
elapsed time and reported input/output tokens; mark missing provider usage
unknown. Review answer correctness, claim support and citation support separately.
No paid evaluation is run by the implementation tests.
