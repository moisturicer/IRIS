# Current child-ticket backlog — AI runtime

**Published and verified 1 November 2026.** The owner approved 32 tracer-bullet outcomes. All 26 existing subticket keys were preserved and six new subtickets were created. The five parent specs and epic were not edited.

Ticket titles, all 167 acceptance checks, labels, parent relationships and existing assignments/statuses were verified against Jira after writing. The graph matches all 52 intended blocking links exactly: 29 new links were added and 29 obsolete links removed. No missing or extra blockers remain. The IR-250 blocker and both IR-605/IR-703 related-work links are preserved.

The accepted architecture remains ADR-049. This index refines delivery scope rather than changing requirements. Each linked local ticket mirrors its published body; implementation has not started as part of this ticket-editing task.

## Tickets

| Ticket | Parent | Complete outcome | Required blockers |
|---|---|---|---|
| [IR-717](https://citiris.atlassian.net/browse/IR-717) ([local](01-ir-717.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Open a research session with a verified reader identity | None |
| [IR-718](https://citiris.atlassian.net/browse/IR-718) ([local](02-ir-718.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Read the same permitted research in Django and the AI runtime | [IR-717](https://citiris.atlassian.net/browse/IR-717) |
| [IR-722](https://citiris.atlassian.net/browse/IR-722) ([local](03-ir-722.md)) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | Submit and reopen one AI-owned research run | [IR-717](https://citiris.atlassian.net/browse/IR-717) |
| [IR-719](https://citiris.atlassian.net/browse/IR-719) ([local](04-ir-719.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Find and read permitted Passages through local research tools | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-720](https://citiris.atlassian.net/browse/IR-720) ([local](05-ir-720.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Prevent withheld or revoked evidence from reaching a provider | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-250](https://citiris.atlassian.net/browse/IR-250) |
| [IR-723](https://citiris.atlassian.net/browse/IR-723) ([local](06-ir-723.md)) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | Keep queued research running after the browser disconnects | [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-727](https://citiris.atlassian.net/browse/IR-727) ([local](07-ir-727.md)) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | Answer a direct question through the pinned AGENT provider contract | [IR-722](https://citiris.atlassian.net/browse/IR-722) |
| [IR-725](https://citiris.atlassian.net/browse/IR-725) ([local](08-ir-725.md)) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | Admit and account for every outgoing provider attempt | [IR-722](https://citiris.atlassian.net/browse/IR-722), [IR-720](https://citiris.atlassian.net/browse/IR-720) |
| [IR-737](https://citiris.atlassian.net/browse/IR-737) ([local](09-ir-737.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Track a committed Manuscript change as recoverable research work | [IR-718](https://citiris.atlassian.net/browse/IR-718), [IR-723](https://citiris.atlassian.net/browse/IR-723) |
| [IR-732](https://citiris.atlassian.net/browse/IR-732) ([local](10-ir-732.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Fit the complete outgoing request within verified model capacity | [IR-727](https://citiris.atlassian.net/browse/IR-727), [IR-725](https://citiris.atlassian.net/browse/IR-725) |
| [IR-738](https://citiris.atlassian.net/browse/IR-738) ([local](11-ir-738.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Extract a Manuscript revision without activating stale research | [IR-737](https://citiris.atlassian.net/browse/IR-737) |
| [IR-728](https://citiris.atlassian.net/browse/IR-728) ([local](12-ir-728.md)) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | Investigate and answer using one bounded model Conversation | [IR-719](https://citiris.atlassian.net/browse/IR-719), [IR-732](https://citiris.atlassian.net/browse/IR-732) |
| [IR-721](https://citiris.atlassian.net/browse/IR-721) ([local](13-ir-721.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Remove revoked evidence from reopened Conversations and review exports | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-724](https://citiris.atlassian.net/browse/IR-724) ([local](14-ir-724.md)) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | Resume a worker-interrupted investigation without restarting its allowance | [IR-723](https://citiris.atlassian.net/browse/IR-723), [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-729](https://citiris.atlassian.net/browse/IR-729) ([local](15-ir-729.md)) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | Correct an invalid draft once before delivering the answer | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-730](https://citiris.atlassian.net/browse/IR-730) ([local](16-ir-730.md)) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | Follow research progress and control depth from the reader screen | [IR-728](https://citiris.atlassian.net/browse/IR-728), [IR-723](https://citiris.atlassian.net/browse/IR-723) |
| [IR-750](https://citiris.atlassian.net/browse/IR-750) ([local](17-ir-750.md)) | [IR-712](https://citiris.atlassian.net/browse/IR-712) | Resolve selected Records and answer exact metadata counts | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-733](https://citiris.atlassian.net/browse/IR-733) ([local](18-ir-733.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Answer from full Manuscripts with honest reading coverage | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-751](https://citiris.atlassian.net/browse/IR-751) ([local](19-ir-751.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Publish a fully indexed current Manuscript for research | [IR-738](https://citiris.atlassian.net/browse/IR-738), [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-740](https://citiris.atlassian.net/browse/IR-740) ([local](20-ir-740.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Collect and rescore the new runtime through IR-605 | [IR-728](https://citiris.atlassian.net/browse/IR-728) |
| [IR-726](https://citiris.atlassian.net/browse/IR-726) ([local](21-ir-726.md)) | [IR-713](https://citiris.atlassian.net/browse/IR-713) | Stop and reconnect to the same investigation across worker races | [IR-724](https://citiris.atlassian.net/browse/IR-724) |
| [IR-731](https://citiris.atlassian.net/browse/IR-731) ([local](22-ir-731.md)) | [IR-714](https://citiris.atlassian.net/browse/IR-714) | Keep supported findings when a research tool fails | [IR-729](https://citiris.atlassian.net/browse/IR-729), [IR-730](https://citiris.atlassian.net/browse/IR-730), [IR-750](https://citiris.atlassian.net/browse/IR-750) |
| [IR-734](https://citiris.atlassian.net/browse/IR-734) ([local](23-ir-734.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Continue a long Conversation through automatic compaction | [IR-724](https://citiris.atlassian.net/browse/IR-724) |
| [IR-752](https://citiris.atlassian.net/browse/IR-752) ([local](24-ir-752.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Build a new Embedding Space while current search stays usable | [IR-751](https://citiris.atlassian.net/browse/IR-751) |
| [IR-753](https://citiris.atlassian.net/browse/IR-753) ([local](25-ir-753.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Review and freeze long-context evaluation cases before collection | [IR-740](https://citiris.atlassian.net/browse/IR-740) |
| [IR-741](https://citiris.atlassian.net/browse/IR-741) ([local](26-ir-741.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Produce an honest release-evidence report with explicit missing gates | [IR-740](https://citiris.atlassian.net/browse/IR-740) |
| [IR-735](https://citiris.atlassian.net/browse/IR-735) ([local](27-ir-735.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Recover original details after compaction and respect deletion | [IR-734](https://citiris.atlassian.net/browse/IR-734) |
| [IR-739](https://citiris.atlassian.net/browse/IR-739) ([local](28-ir-739.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Promote or roll back a verified Embedding Space safely | [IR-752](https://citiris.atlassian.net/browse/IR-752) |
| [IR-754](https://citiris.atlassian.net/browse/IR-754) ([local](29-ir-754.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Compact a Conversation from the reader screen | [IR-735](https://citiris.atlassian.net/browse/IR-735), [IR-730](https://citiris.atlassian.net/browse/IR-730) |
| [IR-742](https://citiris.atlassian.net/browse/IR-742) ([local](30-ir-742.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Rehearse one-writer cutover and version-compatible rollback | [IR-741](https://citiris.atlassian.net/browse/IR-741), [IR-739](https://citiris.atlassian.net/browse/IR-739), [IR-726](https://citiris.atlassian.net/browse/IR-726) |
| [IR-736](https://citiris.atlassian.net/browse/IR-736) ([local](31-ir-736.md)) | [IR-715](https://citiris.atlassian.net/browse/IR-715) | Continue research across repeated compactions and incompatible native state | [IR-733](https://citiris.atlassian.net/browse/IR-733), [IR-754](https://citiris.atlassian.net/browse/IR-754) |
| [IR-755](https://citiris.atlassian.net/browse/IR-755) ([local](32-ir-755.md)) | [IR-716](https://citiris.atlassian.net/browse/IR-716) | Collect human-reviewed quality and approved capacity evidence | [IR-721](https://citiris.atlassian.net/browse/IR-721), [IR-726](https://citiris.atlassian.net/browse/IR-726), [IR-731](https://citiris.atlassian.net/browse/IR-731), [IR-736](https://citiris.atlassian.net/browse/IR-736), [IR-739](https://citiris.atlassian.net/browse/IR-739), [IR-741](https://citiris.atlassian.net/browse/IR-741), [IR-753](https://citiris.atlassian.net/browse/IR-753) |

## What changed

The six new tickets are [IR-750](https://citiris.atlassian.net/browse/IR-750), [IR-751](https://citiris.atlassian.net/browse/IR-751), [IR-752](https://citiris.atlassian.net/browse/IR-752), [IR-753](https://citiris.atlassian.net/browse/IR-753), [IR-754](https://citiris.atlassian.net/browse/IR-754), [IR-755](https://citiris.atlassian.net/browse/IR-755). They split exact metadata tools, active indexed publication, pending Embedding Space construction, human evaluation-case approval, manual compaction and live campaign collection out of overloaded implementation bundles.

Every feature includes its own tests and demonstration. Integrated scenarios now deliver saved-surface revocation, Stop/reconnect, partial-outage answers and long-context/native-state continuity rather than deferring basic tests to separate proof-only tasks.

Capacity/disclosure gates precede real agent sends. Recovery waits for the actual queued agent protocol. Reader progress, core outage handling and reporting/preflight tooling can be developed without waiting for unrelated long-context or live campaign completion.

## Parallel work and human gates

Start IR-717 and the existing IR-250 independently. IR-718 and IR-722 follow IR-717 in parallel. Each subsequent task becomes pullable when its listed blockers complete; do not wait for a whole stage unnecessarily.

IR-753 needs named human label review before its held-out pack is approved. IR-755 needs explicit funding/provider/data approvals, environments and independent human reviews before live collection. Both are To Do with not-ready/blocked, not AFK-ready. The other tasks retain ready-for-agent specification labels, subject to their native blockers and normal human PR review.

IR-742 prepares and rehearses cutover/rollback before measured evidence is available; it must refuse live execution without IR-755's passing readiness manifest and named release approval. No live campaign, deployment, traffic switch, data reset or runtime implementation occurred during backlog refinement.

## Verification and history

- [Current refinement publication](../jira-refinement-2026-11-01.json): real keys, bodies, final edges and removed-link history.
- [Approved review package](../../../../jira-sync/drafts/ai-runtime-ticket-improvements/README.md): numbered proposal, source snapshot and scope/story mapping.
- [Final verification](../jira-refinement-verification-2026-11-01.json): 32 child bodies, five unchanged parents and exact dependency reconciliation.
- Original jira-publication.json records the earlier 31 October publication of 26 children; it is historical, not the current child count.

Existing assignments on IR-717 and the five parents were preserved. No parent fields were edited; linking a child does not authorize rewriting its parent specification. Required review and implementation evidence still apply.
