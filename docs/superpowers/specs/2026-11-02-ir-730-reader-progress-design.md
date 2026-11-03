# IR-730 reader progress implementation design

Status: design and test boundaries approved by the user; implemented behind a disabled
deployment flag. Verification and enablement limits are in
`docs/testing/evidence/IR-730/README.md`.
Authority: ADR-049, accepted runtime specification `2026-10-31-ai-runtime/03-agent.md`,
and the refined IR-730 acceptance criteria. No new architecture decision is proposed.

## Verified starting point

- Jira IR-730: Follow research progress and control depth from the reader screen.
- IR-723 and IR-728 are Done in Jira (checked 2 November 2026).
- `Investigation` already journals bounded plan revisions and stable step IDs.
- `RunStore` owns authenticated submit/status/cancel/reopen operations. Reopen currently
  includes the internal pin and needs a reader-safe projection.
- Model-capacity estimates exist in `ai/agent/context.py`; unknown capacity must stay unknown.
- The reader currently follows Django's `public-1` SSE contract, while AI-owned runs use
  `runs-1` and UUID Conversation IDs. These cannot be substituted silently.
- There are unrelated uncommitted manuscript/document changes in this checkout.

## Approaches

1. **Recommended: extend the versioned AI-run reader contract and reuse reader components.**
   One durable projection supplies live and reopened progress. This requires coordinated
   API/client work, but directly reflects the actual loop and preserves ownership.
2. Add task visuals only to the existing Django stream. This is smaller, but cannot expose
   the AI-owned loop without a second bridge and does not satisfy IR-730 by itself.
3. Replace the entire reader at once. This simplifies eventual ownership but brings history
   migration and traffic cutover into a ticket that explicitly does not authorize them.

## Proposed behavior and boundaries

Persist only actual bounded plan updates and safe context measurements in AI-owned run
state. Derive reader snapshots from committed events, with revision ordering. Simple
requests need no plan. Queued/running/terminal activity stays separate from research task
completion; never invent percentages or automatically mark every task done.

Use an explicit allowlist for public submit/status/cancel/reopen and reader replay/export
shapes. Exclude private reasoning, internal pins/model/provider identifiers, tool payloads,
and diagnostic codes. Context occupancy is labelled an estimate; absent verified capacity
shows unavailable information rather than a guessed total.

Reuse shared presentation in Ask IRIS and Paper Chat: concise task list, run state, context
estimate, Stop/reconnect and a more-thorough option for the next request. The option maps
only to the existing configured ordinary/deep profiles. Reader identity, selected Record,
provider and allowance stay server controlled. Keep the mistake/citation notice visible.
Compaction controls require an explicit available capability; otherwise omit them.

Keep the new reader transport explicitly versioned and separate from numeric legacy
Conversation identities. Do not enable paid providers, migrate reader history, switch live
traffic, expose gateway service secrets in the browser, or invent deployment limits.
Same-origin routing must preserve Django-issued reader grants and private service auth.

Likely files: `ai/runs/store.py`, `ai/api/runs.py`, `ai/agent/executor.py`, a focused public
projection module and their tests; frontend API/types, shared Conversation client and
progress components, Ask IRIS/Paper Chat composition and tests; `docs/testing/TRACEABILITY.md`.
Any persistence change uses a new AI-owned migration, never edits an applied migration.

## Proposed TDD boundaries

1. Authenticated run API with restricted-role PostgreSQL: actual task revisions, safe
   estimates, owner/scope checks, reconnect/reopen agreement and terminal outcomes.
   This checks the durable public contract, not visual layout or paid model quality.
2. Shared reader transport against contract fixtures: version checks, idempotent submit,
   reconnect, Stop and depth requests. This checks client behavior, not database grants.
3. Ask IRIS and Paper Chat through accessible user controls: actual task states, busy/error
   handling, keyboard Stop, thoroughness, persistent notice and hidden unavailable
   compaction. Browser checks cover narrow layout; DOM tests alone cannot prove layout.

Run one failing behavior then implement its slice. Run focused tests and frontend type
checking regularly; run the full applicable suites once at completion. Review the final
ticket diff along standards and specification axes before committing ticket-owned files
on the current branch. Report environmental skips and failures explicitly.
