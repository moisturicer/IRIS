# IR-513 — research context and bounded replanning

Approved in the implementation chat on 2026-10-11: after receiving a plain
language explanation of the loop, test boundaries and history policy, the
human user instructed, "do what you recommend". This approves this scope and
ADR-038 D6's conservative policy only. ADR-038 remains Proposed; its broader
architectural approval and reader rollout are not inferred.

## Behavior

The experimental planner plans before searching. An outer decision offers
`plan_research` (a short list of sub-tasks) and `finish`. Each sub-task runs the
closed corpus tools, then returns to an outer sufficiency check. That check
can finish immediately after the first sub-task or replace the remaining
plan. The existing settings bound outer rounds (3), calls per sub-task (4),
all calls in the run (10), wall time and cumulative prompt tokens. Control
calls also spend the run-wide call allowance. Only corpus calls and malformed
inner calls spend the per-sub-task allowance. A sub-task's local allowance
may reset; a replan never resets the run's calls, tokens, clock or tool cache.

Every planner request contains one freshly assembled body of retained passage
text and abstracts with issued handles, recent owned Conversation history
including prior answers, and separately labelled short planner notes. No
memory recall runs. Notes come from the text accompanying a tool call;
dedicated or leaked reasoning is excluded. Notes cannot be sources and do not
reach synthesis or the run audit.

Visibility, fixed Paper Chat scope and disclosure are checked again before
each request. A recent exchange with any now-inaccessible or undisclosable
cited record is omitted in full. This protects content at the cost of losing
context for follow-ups. Planner-derived notes/control text are discarded if
their previously exposed record/history context loses permission.

A separate context token setting bounds a single planner request within the
cumulative run allowance. The application drops the lowest-scoring passages
first, retaining surviving passages verbatim and with stable handles. Dropped
text must not survive in older tool messages. Synthesis similarly fits its
actual prompt, and a deterministic coverage note reports evidence dropping.
If non-passage context alone cannot fit, planning stops rather than evading
the budget. Passage-count dropping also produces a coverage note.

The answer is generated once through the existing grounded answer service.
Only numbered sources mapped to retained ledger passages can resolve as
citations. Invalid note/other citation markers cause the existing whole-answer
withholding policy; no judge or regeneration loop is added.

## Approach and alternatives

Rebuilding requests from the ledger makes permission changes and passage
dropping effective and avoids repeating passage bodies. Its cost is losing a
full tool transcript; the latest call/result pair, computed results and notes
provide continuity. Replaying the entire transcript is simpler but preserves
stale, dropped or newly restricted content, so it is not selected.

Structured control calls make the plan and stage explicit and validate them
with the existing schema machinery. Parsing free-form planning prose would
use fewer declared controls but makes transitions ambiguous; it is not
selected.

## Approved test boundaries and implementation plan

Use `ResearchPlanner.answer` with scripted model requests and the real test
database for full-context/history, gate changes, first-task sufficiency,
round/sub-task/run limits, malformed controls and exactly one answer call.
Use public ledger/synthesis boundaries for weakest-first dropping, stable
source handles, coverage notices and invalid citations. No vendor account is
needed. Extend the existing audit access tests to keep content private.

1. Add a failing captured-request history test; implement safe context assembly.
2. Add a failing explicit outer-loop test; implement validated stages and shared
   spend admission, updating old single-loop scripts to the new protocol.
3. Add failing drop/notes tests; fit prompts and isolate notes from citations.
4. Run focused tests and static checks through the slices, then the full backend
   suite. Record traceability and actual results, review against the branch's
   pinned main baseline with two token-efficient review agents, and fix findings.
5. Commit, push and open the PR; link it from Jira and move IR-513 to In Review.

Files: `backend/apps/ai/research/{planner,prompts,budget,ledger,synthesis,validation}.py`,
research tests, the new context setting and environment example,
`docs/engineering/RESEARCH_PLANNER.md`, ADR-038's D6 confirmation and
`docs/testing/TRACEABILITY.md`. No schema migration or live routing change.
