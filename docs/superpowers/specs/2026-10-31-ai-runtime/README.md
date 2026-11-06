# Ask IRIS dedicated AI runtime: specifications and backlog

**Design accepted 31 October 2026.** The status lines below are as published; implementation has since started and Jira holds the current state. The owner ended the interview and authorized synthesis of all recommended choices and publication under the existing AI/RAG epic.

- Epic: [IR-146 — RAG / AI Pipeline](https://citiris.atlassian.net/browse/IR-146).
- Authority: [ADR-049](../../../adr/049-dedicated-ai-runtime-and-local-research.md), superseding provisional [ADR-059](../../../adr/059-dedicated-ai-runtime-direction.md) (written as ADR-048).
- Evaluation foundation: [IR-605](https://citiris.atlassian.net/browse/IR-605); integrate existing IR-703 controller fixes rather than recreating them.
- Backlog refined on 1 November 2026: five full specs and **32 implementation subtickets** (26 revised, six added). All are To Do; existing assignments are preserved. IR-753 and IR-755 are human-dependent and not-ready/blocked. The verified graph has 52 blocking links, including IR-250; all 29 obsolete links were removed. See the [current child backlog](tickets/README.md) and [refinement evidence](jira-refinement-2026-11-01.json).

## Recommended architecture in plain language

Django keeps accounts, research Records, Manuscripts and review workflow. FastAPI-hosted AI workers own research execution and Conversation data, with local tools reading PostgreSQL through shared row-protected access. A signed reader grant is checked by the trusted database mechanism; a bare user-ID setting grants nothing. One initial PostgreSQL deployment has distinct migration owners and restricted runtime roles.

For a four-Record comparison, the worker reads permitted complete text when useful, keeps a task list, investigates differences and drafts the answer using the same model Conversation. Context compaction preserves original references and recoverable Turns. AskRun bounds queueing, spending, recovery and cancellation, and commits one validated final Turn. A browser disconnect does not cancel research.

This buys local execution and focused upgrade points. It costs an access-policy migration, durable checkpoints, context memory/spending, adapter compatibility and real load testing. Neither FastAPI nor a million-token window guarantees better answers or unlimited capacity.

## Specifications

| Spec | Jira parent | Subtickets |
|---|---|---|
| [Authorized Evidence and database-enforced research access](01-evidence.md) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | [IR-717](https://citiris.atlassian.net/browse/IR-717), [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-719](https://citiris.atlassian.net/browse/IR-719), [IR-720](https://citiris.atlassian.net/browse/IR-720), [IR-721](https://citiris.atlassian.net/browse/IR-721), [IR-750](https://citiris.atlassian.net/browse/IR-750) |
| [Durable AskRun execution, recovery and shared spending](02-execution.md) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | [IR-722](https://citiris.atlassian.net/browse/IR-722), [IR-723](https://citiris.atlassian.net/browse/IR-723), [IR-724](https://citiris.atlassian.net/browse/IR-724), [IR-725](https://citiris.atlassian.net/browse/IR-725), [IR-726](https://citiris.atlassian.net/browse/IR-726) |
| [Single-model Conversation research with local tools and validated answers](03-agent.md) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | [IR-727](https://citiris.atlassian.net/browse/IR-727), [IR-728](https://citiris.atlassian.net/browse/IR-728), [IR-729](https://citiris.atlassian.net/browse/IR-729), [IR-730](https://citiris.atlassian.net/browse/IR-730), [IR-731](https://citiris.atlassian.net/browse/IR-731) |
| [Large-context Manuscript reading and recoverable Conversation compaction](04-context.md) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | [IR-732](https://citiris.atlassian.net/browse/IR-732), [IR-733](https://citiris.atlassian.net/browse/IR-733), [IR-734](https://citiris.atlassian.net/browse/IR-734), [IR-735](https://citiris.atlassian.net/browse/IR-735), [IR-736](https://citiris.atlassian.net/browse/IR-736), [IR-754](https://citiris.atlassian.net/browse/IR-754) |
| [Versioned research publication, upgrades and IR-605 cutover evidence](05-publication.md) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | [IR-737](https://citiris.atlassian.net/browse/IR-737), [IR-738](https://citiris.atlassian.net/browse/IR-738), [IR-739](https://citiris.atlassian.net/browse/IR-739), [IR-740](https://citiris.atlassian.net/browse/IR-740), [IR-741](https://citiris.atlassian.net/browse/IR-741), [IR-742](https://citiris.atlassian.net/browse/IR-742), [IR-751](https://citiris.atlassian.net/browse/IR-751), [IR-752](https://citiris.atlassian.net/browse/IR-752), [IR-753](https://citiris.atlassian.net/browse/IR-753), [IR-755](https://citiris.atlassian.net/browse/IR-755) |

## Test surface

The primary interface is the authenticated reader experience: submitted question, activity, delivered/reopened Conversation, citations, Stop and reconnect. Reuse IR-605 collection/review/scoring. Database row protection and shared-worker races additionally require real PostgreSQL and independent-process tests; browser/accessibility and actual vendor capacity are separate evidence classes. Do not overfit one internal tool sequence.

## Subtickets and dependencies

**Current as of 1 November 2026.** The 32 child bodies and exact 52-link dependency graph are published and verified; use the [current child index](tickets/README.md) for scope and dependencies. The five parent spec bodies retain their original grouping.

| Issue | Complete outcome | Required blockers |
|---|---|---|
| [IR-717](https://citiris.atlassian.net/browse/IR-717) | Open a research session with a verified reader identity | None |
| [IR-718](https://citiris.atlassian.net/browse/IR-718) | Read the same permitted research in Django and the AI runtime | [IR-717](https://citiris.atlassian.net/browse/IR-717) |
| [IR-722](https://citiris.atlassian.net/browse/IR-722) | Submit and reopen one AI-owned research run | [IR-717](https://citiris.atlassian.net/browse/IR-717) |
| [IR-719](https://citiris.atlassian.net/browse/IR-719) | Find and read permitted Passages through local research tools | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-720](https://citiris.atlassian.net/browse/IR-720) | Prevent withheld or revoked evidence from reaching a provider | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-250](https://citiris.atlassian.net/browse/IR-250) |
| [IR-723](https://citiris.atlassian.net/browse/IR-723) | Keep queued research running after the browser disconnects | [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-727](https://citiris.atlassian.net/browse/IR-727) | Answer a direct question through the pinned AGENT provider contract | [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-725](https://citiris.atlassian.net/browse/IR-725) | Admit and account for every outgoing provider attempt | [IR-722](https://citiris.atlassian.net/browse/IR-722), [IR-720](https://citiris.atlassian.net/browse/IR-720) |
| [IR-737](https://citiris.atlassian.net/browse/IR-737) | Track a committed Manuscript change as recoverable research work | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-723](https://citiris.atlassian.net/browse/IR-723) |
| [IR-732](https://citiris.atlassian.net/browse/IR-732) | Fit the complete outgoing request within verified model capacity | [IR-727](https://citiris.atlassian.net/browse/IR-727), [IR-725](https://citiris.atlassian.net/browse/IR-725) |
| [IR-738](https://citiris.atlassian.net/browse/IR-738) | Extract a Manuscript revision without activating stale research | [IR-737](https://citiris.atlassian.net/browse/IR-737) |
| [IR-728](https://citiris.atlassian.net/browse/IR-728) | Investigate and answer using one bounded model Conversation | [IR-719](https://citiris.atlassian.net/browse/IR-719), [IR-732](https://citiris.atlassian.net/browse/IR-732) |
| [IR-721](https://citiris.atlassian.net/browse/IR-721) | Remove revoked evidence from reopened Conversations and review exports | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-724](https://citiris.atlassian.net/browse/IR-724) | Resume a worker-interrupted investigation without restarting its allowance | [IR-723](https://citiris.atlassian.net/browse/IR-723), [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-729](https://citiris.atlassian.net/browse/IR-729) | Correct an invalid draft once before delivering the answer | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-730](https://citiris.atlassian.net/browse/IR-730) | Follow research progress and control depth from the reader screen | [IR-728](https://citiris.atlassian.net/browse/IR-728), [IR-723](https://citiris.atlassian.net/browse/IR-723) |
| [IR-750](https://citiris.atlassian.net/browse/IR-750) | Resolve selected Records and answer exact metadata counts | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-733](https://citiris.atlassian.net/browse/IR-733) | Answer from full Manuscripts with honest reading coverage | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-751](https://citiris.atlassian.net/browse/IR-751) | Publish a fully indexed current Manuscript for research | [IR-738](https://citiris.atlassian.net/browse/IR-738), [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-740](https://citiris.atlassian.net/browse/IR-740) | Collect and rescore the new runtime through IR-605 | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-726](https://citiris.atlassian.net/browse/IR-726) | Stop and reconnect to the same investigation across worker races | [IR-724](https://citiris.atlassian.net/browse/IR-724) |
| [IR-731](https://citiris.atlassian.net/browse/IR-731) | Keep supported findings when a research tool fails | [IR-729](https://citiris.atlassian.net/browse/IR-729), [IR-730](https://citiris.atlassian.net/browse/IR-730), [IR-750](https://citiris.atlassian.net/browse/IR-750) |
| [IR-734](https://citiris.atlassian.net/browse/IR-734) | Continue a long Conversation through automatic compaction | [IR-724](https://citiris.atlassian.net/browse/IR-724) |
| [IR-752](https://citiris.atlassian.net/browse/IR-752) | Build a new Embedding Space while current search stays usable | [IR-751](https://citiris.atlassian.net/browse/IR-751) |
| [IR-753](https://citiris.atlassian.net/browse/IR-753) | Review and freeze long-context evaluation cases before collection | [IR-740](https://citiris.atlassian.net/browse/IR-740) |
| [IR-741](https://citiris.atlassian.net/browse/IR-741) | Produce an honest release-evidence report with explicit missing gates | [IR-740](https://citiris.atlassian.net/browse/IR-740) |
| [IR-735](https://citiris.atlassian.net/browse/IR-735) | Recover original details after compaction and respect deletion | [IR-734](https://citiris.atlassian.net/browse/IR-734) |
| [IR-739](https://citiris.atlassian.net/browse/IR-739) | Promote or roll back a verified Embedding Space safely | [IR-752](https://citiris.atlassian.net/browse/IR-752) |
| [IR-754](https://citiris.atlassian.net/browse/IR-754) | Compact a Conversation from the reader screen | [IR-735](https://citiris.atlassian.net/browse/IR-735), [IR-730](https://citiris.atlassian.net/browse/IR-730) |
| [IR-742](https://citiris.atlassian.net/browse/IR-742) | Rehearse one-writer cutover and version-compatible rollback | [IR-741](https://citiris.atlassian.net/browse/IR-741), [IR-739](https://citiris.atlassian.net/browse/IR-739), [IR-726](https://citiris.atlassian.net/browse/IR-726) |
| [IR-736](https://citiris.atlassian.net/browse/IR-736) | Continue research across repeated compactions and incompatible native state | [IR-733](https://citiris.atlassian.net/browse/IR-733), [IR-754](https://citiris.atlassian.net/browse/IR-754) |
| [IR-755](https://citiris.atlassian.net/browse/IR-755) | Collect human-reviewed quality and approved capacity evidence | [IR-721](https://citiris.atlassian.net/browse/IR-721), [IR-726](https://citiris.atlassian.net/browse/IR-726), [IR-731](https://citiris.atlassian.net/browse/IR-731), [IR-736](https://citiris.atlassian.net/browse/IR-736), [IR-739](https://citiris.atlassian.net/browse/IR-739), [IR-741](https://citiris.atlassian.net/browse/IR-741), [IR-753](https://citiris.atlassian.net/browse/IR-753) |

## Delivery order

1. Establish signed delegated identity, restricted roles and one research-read policy; prove parity with current institutional rules.
2. Establish AI-owned AskRun/Conversation commitment, durable dispatch, checkpoint recovery and shared physical-attempt spending.
3. Build the named AGENT/provider contract, continuous loop and deterministic local tools alongside complete-request context and full reading.
4. Integrate compaction, detail recovery, final assurance and accessible reader progress; prove source/revocation and recovery behavior.
5. Publish versioned research revisions and parallel Embedding Spaces, extend IR-605, collect approved evaluation/load evidence and prepare a controlled cutover/rollback.

Cross-spec dependencies are native Jira blocking links at subtask granularity, avoiding parent-level cycles that prevent parallel implementation. ready-for-agent means specified, not permission to ignore prerequisites or bypass operational approval.

**Existing institutional-data blocker:** [IR-250](https://citiris.atlassian.net/browse/IR-250) also blocks [IR-720](https://citiris.atlassian.net/browse/IR-720)'s ordinary real-Record disclosure enablement. It owns canonical embargo facts, their writer and deliberate backfill. The new runtime must keep refusing unknown disclosure facts and integrate that work rather than inventing permission; synthetic fixtures can test the mechanism before live enablement.

## Evaluation and rollout

Keep matched model/corpus/question/data-policy/allowance architecture comparisons separate from larger-allowance capability evaluation and model comparisons. Preserve held-out freeze, named human label review, two independent reviews/adjudication, three repetitions, distinct-case family minimum ten, own metric denominators and uncertainty reporting.

The selected initial quality objectives are 90% task completion and 95% claim/citation/applicable-page support for reported repetitions/families, no access/disclosure breach and no matched-condition aggregate regression from the frozen baseline. Missing/inconclusive required evidence blocks cutover. Predeclare workload and latency/cost profile before collection; measure queue-inclusive ordinary/deep p95, usage, cost per successful task, memory and database pressure. A fake smoke is not paid capacity or human-reviewed quality evidence.

Numeric production spending/deadline/concurrency limits and provider/data/funding approvals remain explicit operational configuration. Implementations must reject paid enablement when required values are absent. No live campaign, deployment or deletion is authorized by ticket publication.

Existing development Conversations need not migrate. A later explicitly scoped reset must preserve institutional research, workflow/account history, paid-attempt audit and required evaluation artifacts. The new implementation replaces the old path after evidence and human release approval; no permanent reader-facing engine choice is added.

## Publication evidence

The five Story tickets are children of IR-146; their 32 implementation tickets are Jira Subtasks. Labels use the project taxonomy. Local parent specs preserve the original published bodies; the current child index mirrors the refined subtickets. The authority remains ADR-049. All work remains unimplemented. Issue bodies, hierarchy, status, labels, preserved assignment and the exact dependency graph were verified after refinement; no missing or obsolete blockers remain. The original jira-publication.json is historical; jira-refinement-2026-11-01.json records the current state.
