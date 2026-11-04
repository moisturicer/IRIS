# Spec 3: Single-model Conversation research with local tools and validated answers

**Jira spec:** [IR-714](https://citiris.atlassian.net/browse/IR-714)

**Design accepted; implementation not started.** 31 October 2026. Authority: ADR-049. Parent epic: IR-146.

## Problem Statement

A separate planner and answer writer lose the continuous investigation context and can fail between finding research and explaining it. Readers want a capable bounded agent that chooses useful research steps, understands evidence and returns natural cited answers without internal traces.

## Solution

Use one model Conversation for planning, local research tools, evidence assessment and answer drafting. Show a concise task list for complex work, keep simple questions lightweight, validate the final draft and repair at most once through the same Conversation.

## User Stories

1. As a reader, I want one agent to interpret and answer my full request, so that research is not lost in a planner-to-writer handoff.
2. As a reader, I want the agent to choose relevant research tools, so that I do not prescribe a rigid tool sequence.
3. As a reader, I want simple explanations answered without an unnecessary checklist, so that ordinary interaction stays lightweight.
4. As a researcher, I want complex to work have an understandable task list, so that I can see what remains to be investigated.
5. As a reader, I want task progress to reflect actual execution, so that the display does not fabricate completion percentages.
6. As a reader, I want private reasoning and tool diagnostics kept separate, so that the interface remains clear and safe.
7. As a reader, I want the agent to investigate conflicting findings, so that a comparison does not flatten real disagreements.
8. As a reader, I want methods and evaluation conditions compared fairly, so that numbers from incompatible experiments are not ranked as equivalent.
9. As a reader, I want clarification only when ambiguity blocks progress, so that research does not stall on avoidable questions.
10. As a reader, I want full original intent retained when search queries change, so that retrieval wording does not replace my request.
11. As a reader, I want shown paper ordering and exclusions respected, so that follow-up references keep their meaning.
12. As a reader, I want direct background explanations distinguished from paper findings, so that general knowledge is not presented as a repository result.
13. As a reader, I want citations to resolve to current permitted Passages, so that I can verify important claims.
14. As a reader, I want useful supported findings to survive one tool failure, so that a partial outage does not erase completed work.
15. As a reader, I want missing fields distinguished from no matches and outages, so that I understand the actual evidence gap.
16. As a reader, I want a more thorough request to use a bounded larger profile, so that I can ask for detail without selecting a model.
17. As an operator, I want model and protocol pinned for each to run, so that upgrades do not change in-flight interpretation.
18. As a budget owner, I want research to stop before the final-answer reserve is consumed, so that tool loops cannot spend the answer allowance.
19. As a reader, I want one actionable repair to correct an invalid draft, so that validation improves the answer without an endless judge loop.
20. As a reader, I want final factual prose delivered after checks, so that an invalid answer is not already streamed to me.
21. As a developer, I want deterministic local tools to return evidence, so that hidden specialist inference does not fragment the agent.
22. As an evaluation reviewer, I want the same reader behavior measured through IR-605, so that new architecture results remain comparable.

## Implementation Decisions

- Replace mandatory PLAN/ANSWER orchestration with one named AGENT inference responsibility carrying the selected model/data policy. Preserve task-specific audit purposes without a second mandatory planner/writer. Eliminate compulsory follow-up resolver calls on this path; the agent forms queries from authorized Conversation state.
- The agent interface accepts the original request, authorized Conversation/scope, task state and pinned deployment profile and yields safe progress plus a draft/result. Preserve complete ordered assistant/tool exchanges, stable IDs, matching parallel results, stop reasons and provider-required opaque items. The application executes tools; model text cannot grant access or reset limits.
- Use local deterministic resolve/search/read/aggregate operations through Authorized Evidence. The same agent performs screening, extraction and comparison from returned original evidence. Do not silently invoke SCREEN/BRIEF/another writer inside these tools. Optional cached briefs are explicitly derived and retain original Passage dependencies.
- Offer an optional bounded task-list update tool for complex research. It writes only AI-owned plan state with stable step IDs/status/revision. Completion is an agent assessment, not a certified coverage claim. Plans cannot expand Paper Chat, confer permissions or extend allowance.
- Interpret depth from the user’s request; allow a more-thorough instruction/control to choose a larger preconfigured bounded profile. Do not add a reader engine/model selector or require per-tool consent. Read-only institutional scope and separate public-research opt-in remain unchanged.
- At tool/round/no-progress/time/token/cost limits, enter finalization with further research disabled in a provider-compatible way. Reserve a final answer and at most one repair before gathering. A length-truncated, reasoning-only or tool-only completion is not a completed answer.
- Separate deterministic assurance from model generation. Validate source identity/version/current access, stable citation bindings, typed computed facts/numbers and completeness claims. One actionable correction returns to the same model exchange under remaining bounds. Omit/qualify unsupported units where independently supported content remains; fail safely on source/authorization fences.
- Pin model/endpoint, adapter/dialect, prompt/tool/protocol/state versions per run. The adapter preserves continuation artifacts without rendering/logging their payload and supports supported tool/final response forms. Do not silently switch into a smaller model or incompatible native state. Explicit reconstruction is bounded and reauthorized.
- The public response retains separate activity, task plan, optional context estimate/compaction status, validated analytical summary, answer and citations. No raw reasoning, provider IDs, tool arguments/results or debug reason codes in live/history/replay/export. Keep the persistent mistake/citation notice and accessible Stop/progress controls.
- Final factual answers are atomic after validation. Reopened state matches delivered state; concurrent revisions never silently remap displayed ordinals. Protocol evolution is a versioned adapter, not a second competing answer route.

## Testing Decisions

- Primary seam: authenticated reader request/stream, delivered and reopened Conversation, citations and progress. Assert task outcomes across several valid tool orders rather than one planner script.
- Deterministic provider adapters exercise direct, tool-assisted, parallel-call, malformed-call, conflicting-evidence, clarification, tool-failure and finalization/one-repair cases. Assert actual outgoing requests have no hidden resolver/planner/brief/screen calls.
- Test cancellation/revocation between model/tool steps through the existing reader/worker contracts. Check source-fenced final answers, restored shown ordering and no raw/opaque/private data in public serializers.
- Browser/accessibility checks cover task list, Stop, context/progress states, replay, narrow layouts, keyboard access and the persistent notice. A neutral lifecycle event cannot be mistaken for a completed research step.
- Prior art: A01–A15 general-tools fixtures, current controller answer assurance and continuation tests, public projection tests, IR-605 replay/human review and IR-608 safety/browser evidence.

## Out of Scope

- Institutional writes, permission changes, workflow approval or arbitrary execution by the model.
- Raw chain-of-thought display or invented progress.
- Multiple collaborating reasoning agents or automatic second-writer synthesis.
- Enabling public web research or a new provider.
- Unvalidated factual token streaming.

## Further Notes

Authority: ADR-049, accepted design on 31 October 2026 following the owner’s instruction to choose the recommended options and publish specs/subtickets. Parent epic: IR-146. Related prior work: IR-605 evaluation and IR-703 immediate controller fixes. This is specified implementation work, not evidence of completion or approval for paid inference, institutional transmission, production settings, deletion or deployment. Production profile values must be explicit and validated; absent values refuse paid enablement. Subtickets are unassigned, ready-for-agent and linked by native dependencies; a blocked prerequisite is not permission to skip its tests.

### Acceptance criteria

- [ ] A direct question and multistep comparison use one pinned AGENT conversation without a mandatory planner/writer handoff.
- [ ] Complete tool exchanges persist and resume, including parallel IDs and compatible opaque artifacts.
- [ ] Core research tools execute locally and do not hide extra specialist-model calls.
- [ ] Complex tasks expose safe plan state; simple questions need no task list.
- [ ] Finalization protects answer allowance and permits at most one bounded repair.
- [ ] A09 failures preserve independent findings and distinguish the actual evidence limitation.
- [ ] Public live/reopened/replayed/exported responses contain no raw reasoning or private tool/provider state.
- [ ] The final validated answer and citation/state revision agree and remain owner/access checked.

### Implementation slices

- **IR-727 — Define the named AGENT protocol and compatible provider adapters.** Unify typed model/tool/final output and pinned continuation behavior. Prerequisites: IR-717, IR-722.
- **IR-728 — Run the bounded single-model loop with deterministic local tools.** Replace split orchestration and hidden specialist inference. Prerequisites: IR-727, IR-719, IR-725.
- **IR-729 — Validate and repair final drafts inside the agent Conversation.** Reuse source/fact checks without another mandatory writer. Prerequisites: IR-728, IR-720.
- **IR-730 — Show safe research plans context status and accessible controls.** Update reader protocol and Ask IRIS/Paper Chat presentation. Prerequisites: IR-727, IR-726, IR-735.
- **IR-731 — Prove the new agent through the authenticated reader contract.** Complete general-tools and public-projection regression evidence. Prerequisites: IR-729, IR-730, IR-736.
