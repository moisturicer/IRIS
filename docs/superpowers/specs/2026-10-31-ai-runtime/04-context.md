# Spec 4: Large-context Manuscript reading and recoverable Conversation compaction

**Jira spec:** [IR-715](https://citiris.atlassian.net/browse/IR-715)

**Design accepted; implementation not started.** 31 October 2026. Authority: ADR-049. Parent epic: IR-146.

## Problem Statement

A large model window is wasted when history, per-read caps and Passage eviction leave only a small fragment of relevant research. Long Conversations need continuity without unbounded prompts, silent truncation or summaries that outlive their source access.

## Solution

Give each agent Conversation one complete-request context budget, useful full-Manuscript reading and automatic/manual compaction with recoverable originals. Use verified provider capacity up to million-token windows while keeping independent time/spending bounds and honest coverage.

## User Stories

1. As a researcher, I want complete selected Manuscripts available when useful and affordable, so that detailed comparisons can examine methods and limitations together.
2. As a reader, I want small requests to avoid unnecessary full-paper loading, so that simple questions remain efficient.
3. As a reader, I want late and middle sections to remain reachable, so that long-paper answers do not depend only on the introduction.
4. As a reader, I want a read to disclose which ranges were covered, so that partial evidence is not presented as a full reading.
5. As a reader, I want pages and Passage bindings to survive large reads, so that I can verify a claim after context is reorganized.
6. As a reader, I want original Figure/Formula gaps distinguished from extracted text, so that full text does not imply the model interpreted every visual.
7. As an operator, I want verified model capacity used for the full request, so that tool definitions and continuation items cannot cause surprise overflow.
8. As a budget owner, I want context occupancy separated from cumulative spend, so that a cached large prompt is not assumed free.
9. As a reader, I want space reserved to finish the answer, so that research does not fill the window and leave no room to respond.
10. As a reader, I want automatic compaction before overflow, so that long Conversations can continue.
11. As a reader, I want a manual Compact conversation action, so that I can condense older context deliberately.
12. As a reader, I want recent exchanges and critical evidence retained, so that compaction preserves the active task.
13. As a reader, I want goals preferences selected/excluded Records preserved, so that the agent does not restart my instructions.
14. As a reader, I want shown Record ordering preserved, so that the second Record keeps its meaning after compaction.
15. As a reader, I want original Turns recoverable, so that the agent can check exact details rather than guess from a summary.
16. As a reader, I want compaction failure to preserve valid preceding context, so that a failed summary does not erase useful history.
17. As a reader, I want permission changes invalidate derived summaries, so that compaction does not launder revoked content.
18. As an operator, I want portable compaction to work without native provider support, so that provider upgrades do not lock Conversations into one vendor.
19. As an operator, I want opaque continuation rebuilt when incompatible, so that a changed prefix or model does not corrupt continuation.
20. As a reader, I want context usage labelled estimated when necessary, so that the interface does not claim false token precision.
21. As a reader, I want deleting a Conversation to remove its derived context, so that compact handoffs do not become an undeletable copy.
22. As an evaluation reviewer, I want long-context behavior measured independently, so that loaded token volume is not mistaken for answer quality.

## Implementation Decisions

- One Context module prepares the actual serialized provider request and reports allocation/coverage. Verify model/endpoint input/output/thinking and byte limits through adapter capabilities. Include instructions, schemas, history, tool results, source text, opaque items and framing; unknown capacity is not one million.
- Separate single-request occupancy, cumulative AskRun allowance and persistent Conversation storage. Reserve applicable output/reasoning, safety margin, next-tool-result capacity and finalization/repair before loading evidence. Conservative byte-based paid admission remains separate from model-token estimates; count opaque payload bytes without logging content.
- Replace independent fixed Passage/history/read bottlenecks on the new path with one token-aware allocation policy. Keep bounded storage/query/batch sizes. Load full active extracted Manuscript text in document order when relevant and affordable, deduplicate overlapping chunks and preserve exact canonical source/page mappings.
- For oversized selections, return bounded source-version-linked ranges and continuations, not silent clipping or an exhaustive-reading claim. Track original source references, inspected ranges and currently model-visible content independently. Stable citation identities do not depend on current prompt order.
- Automatically compact at a configurable pre-overflow threshold sized to leave space for compaction and finalization. Manual Compact conversation uses the same owner-checked mechanism. Thresholds/caps are deployment profile values, validated for capacity; there is no universal production token allocation.
- The portable handoff records goal/preferences, shown ordering, selections/exclusions, plan state, supported findings with original dependencies, unresolved questions/limitations and original Turn references. Retain recent complete exchanges and critical current evidence as space permits. Use the same AGENT model for summary inference; compaction is admitted paid work, not a free or hidden specialist call.
- Only complete tool-call/result groups are compacted. Retain originals in Conversation storage until deletion/retention policy, and provide bounded owner/source-authorized detail recovery. Generated summaries are context, not new research evidence or trusted instructions.
- Commit a handoff with source turn range, Conversation/access/source revisions, model/adapter identity, format version and usage. Concurrent new Turns remain in the suffix or force reconstruction. Failed/stale/empty compaction leaves preceding valid context unchanged and cannot repeat without consuming attempt/time/spend limits.
- Native compaction is optional and capability-tested behind the same interface. Signed/opaque state may depend on the exact preceding prefix/tool schemas; unchanged bytes do not guarantee compatibility. Rebuild incompatible or revoked artifacts and never forward them to another model blindly.
- Context status/task progress and optional analytical answer summary are distinct public fields. Token displays identify estimates. Compacting does not erase original history; Conversation/account deletion invalidates/removes derived handoffs, context caches and provider state while retaining only minimal required non-content spending audit.

## Testing Decisions

- Primary seam: authenticated long Conversation, full-paper questions, compact action, reopened history and final citations. Verify reader continuity and source support rather than one exact summary string.
- Use deterministic adapter fixtures with tiny and million-token-capable declared windows to test complete serialized occupancy, oversized input/result handling, output reserves and opaque payload accounting without paid calls.
- Inject facts in middle/late sections, overlapping page chunks, incomplete extraction, two selected Records and source replacement. Verify coverage/continuation honesty and exact citation recovery after eviction.
- Exercise multiple compactions, failure, concurrent Turns, original-detail recovery, altered paper order, revoked dependencies and changed provider prefix/tool/model compatibility. No partial tool exchange or stale summary may become active.
- Prior art: history token-window tests, whole-paper Overview/brief source readers, current controller state/revocation tests, A02/A04/A05/A09 contracts and IR-605 extended reviewed Conversation sets. Real long-context quality remains human-reviewed evidence.

## Out of Scope

- Always loading the entire repository or filling every model window.
- Guaranteeing perfect verbatim memory after lossy compaction.
- Graph memory, multiple memory platforms or a new vector database.
- Raw reasoning display or cross-reader context sharing.
- Unapproved provider-native retention or paid long-context campaigns.

## Further Notes

Authority: ADR-049, accepted design on 31 October 2026 following the owner’s instruction to choose the recommended options and publish specs/subtickets. Parent epic: IR-146. Related prior work: IR-605 evaluation and IR-703 immediate controller fixes. This is specified implementation work, not evidence of completion or approval for paid inference, institutional transmission, production settings, deletion or deployment. Production profile values must be explicit and validated; absent values refuse paid enablement. Subtickets are unassigned, ready-for-agent and linked by native dependencies; a blocked prerequisite is not permission to skip its tests.

### Acceptance criteria

- [ ] The complete outgoing request fits the verified capacity with output/repair allowances and no silent destructive clipping.
- [ ] Useful complete Manuscript text reaches the model when affordable, including middle/late evidence and stable citations.
- [ ] Oversized reads return explicit partial coverage and resumable source-bound continuations.
- [ ] Automatic and manual compaction preserve task intent, shown ordering, selections and original references.
- [ ] Original Turns remain recoverable under current owner/source access and deletion rules.
- [ ] Failed/stale compaction cannot replace valid context or reset the AskRun allowance.
- [ ] Revocation and provider incompatibility invalidate derived/native state before reuse.
- [ ] Public context estimates/progress leak neither raw reasoning nor opaque/private source state.

### Implementation slices

- **IR-732 — Budget complete provider requests against verified model capacity.** Unify context occupancy with explicit reserves and separate run spending. Prerequisites: IR-727, IR-725.
- **IR-733 — Read full Manuscripts with stable page coverage and continuations.** Adapt local readers to context-aware document-order expansion. Prerequisites: IR-719, IR-732.
- **IR-734 — Compact the active Conversation safely using portable handoffs.** Implement automatic/manual bounded compaction and atomic activation. Prerequisites: IR-732, IR-724, IR-720.
- **IR-735 — Recover original details and publish safe context status.** Add owner-checked detail recovery, deletion and progress integration. Prerequisites: IR-734, IR-733.
- **IR-736 — Prove large-context and compaction continuity contracts.** Deliver extended deterministic cases for the IR-605-compatible harness. Prerequisites: IR-733, IR-735.
