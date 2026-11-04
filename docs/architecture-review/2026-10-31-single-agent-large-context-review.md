# Ask IRIS: one bounded agent with large context and compaction

31 October 2026. **Research findings and proposed architecture; not an accepted decision or implemented feature.** Requested by the AI-track owner. Provider-independent, as confirmed during this review. No production limits or model are approved by this document.

## 1. Recommendation and example

Replace the planner-to-writer handoff with one model conversation that can request research tools, inspect results, revise its task list, and produce the final answer. Give that conversation a context allocation based on the selected model's actual capacity, including million-token models. Add recoverable conversation compaction while retaining original messages and source references.

For example, a reader asks: “Compare these four papers in detail, including methods, results, and limitations. Check whether they really support the same conclusion.” The agent can:

1. Record a short task list: read the four papers; compare methods and conditions; investigate contradictions; write the comparison.
2. Load the papers in document order, with stable page and source identifiers, if they fit the available context.
3. Notice that two papers use different evaluation datasets, request the relevant table or section, and revise the comparison.
4. Answer from the same conversation that did the investigation. Code checks citation bindings and access before delivering it.
5. Continue a later discussion using the working context. When it grows too large, retain a compact handoff plus recent turns; fetch original passages again when details matter.

“One agent” means one model configuration and continuous model/tool conversation. It still needs a model request after tools return. It does not mean all research can occur inside one HTTP request to a model. Long context is capacity to use where useful, not a requirement to fill every request.

## 2. Review scope and authority

This review inspects the local working tree, including existing uncommitted work. Base commit at inspection: `1bff1993`. It must not be confused with the latest merged or deployed application. Existing worksheet and outage changes are separate work and remain untouched.

Current authority is [ADR-042](../adr/042-general-tools-conversation-contract.md). It explicitly requires `PLAN` for actions and `ANSWER` for prose. It also excludes mandatory model-visible planning ceremonies and permits only neutral lifecycle activity in the reader protocol. Therefore adopting one agent and a visible task list requires a recorded amendment, not an undocumented implementation reversal. [ADR-026](../adr/026-conversational-retrieval-and-memory.md) governs the older retrieval-based memory and rewriting approach; its affected clauses also need reconciliation. Preserve access, citations, source policy, cancellation, admission, and atomic validated delivery.

Related work: [IR-703](https://citiris.atlassian.net/browse/IR-703) was In Review when inspected. Its description records fixes for the answer prompt being refused above its reserve, abstracts being absent from answer sources, and nonworking tools being offered. Those fixes should be integrated rather than independently reimplemented. This proposal goes beyond that issue. A new architecture work item has not been identified or created; flag that before substantive implementation. The Jira search was selective, not an exhaustive backlog audit.

## 3. What limits the current implementation

| Inspected code | Current behavior | Consequence |
|---|---|---|
| `backend/apps/ai/controller/loop.py`, `Controller._gather`, `_ready` | `PLAN` calls tools, then `AnswerComposer` calls `ANSWER` | Changing both profiles to the same model would still leave a handoff and a fresh answer prompt |
| `controller/loop.py`, `previous = [...]` at the end of each round | Retains the most recent assistant tool call and its results; rebuilds current results from gathered envelopes | Earlier useful evidence can survive, but the complete ordered model exchange and earlier continuation artifacts do not |
| `controller/loop.py`, `_gather` | Tool-free model text is parsed as a compose/clarify decision | The agent cannot simply finish with its own validated draft |
| `config/settings/base.py`, research limits | Defaults include 3,000 tokens per read, 30 ledger passages, 120,000 cumulative prompt tokens, and 90 seconds for research | Increasing only the provider context window cannot make a million tokens usable |
| `research/ledger.py` | Drops the weakest passages past its passage cap | Useful earlier evidence can disappear as more is read |
| `research/synthesis.py`, `LedgerRetriever.retrieve(limit=30)` | A separate limit selects the first authorized ledger passages for the answer | Expanding the reading allowance alone does not expand final-answer context |
| `history.py`, `research/prompts.py` | Recent history defaults to 3,000 estimated tokens; candidate query bound is 50 turns | Long conversations are windowed rather than carried as a full agent session |
| `controller/loop.py` and `controller/compose.py` | The answer reserve is also used as an input allowance under enforced admission | Local code can refuse the answer before calling the provider; IR-703 addresses this immediate defect |
| `providers/openai_compatible.py`, `providers/tool_calling.py` | Chat-completions-shaped tool messages and opaque continuation support already exist | A useful starting point, but not yet a universal adapter for native compaction or all provider response item types |

The 16,000-token research context setting is used by older planner/synthesis paths; it is not a universal ceiling enforced identically by every controller call. Likewise, the controller's 4-round/6-tool-call profile is a **fake-test fixture**, not a production limit. Evaluate the actual caller and configured budget instead of treating every default or fixture as a live limit.

IRIS already has the important foundations: active document versions, page-aware chunks, permission-checked tools, run-scoped handles, durable questions, shared provider admission, and source-linked validation. The paper overview already assembles document chunks in order. Reuse those capabilities.

Additional path-specific findings:

- The legacy answer service retrieves up to four older turns through `memory.py`; the controller does not call that recall path. It sees recent windowed history and structured paper state, not an accumulated conversation memory.
- `read_papers` divides the default 3,000-token allowance among the selected papers. Five papers get nominal shares of only 600 tokens each; the first chunk may exceed a share to guarantee progress.
- Read cursors are in-memory and run-scoped, with 64 issued cursors at most. They are not durable cross-question bookmarks.
- The queued question default deadline is 30 seconds from submission (`AI_DURABLE_ASK_DEADLINE_SECONDS`); queue time can consume it before research starts. Raising the research layer's 90-second limit alone does not change that deadline.
- Paper briefs already fit full prompts against configured model windows and preserve verified source quotes through split reading (`briefs/reading.py`). Reuse the counting and source-coverage ideas, while keeping the agent's core tool path free of automatic brief-generation calls.
- IR-703's worktree retains both the planner/writer handoff and latest-exchange-only replay. Its context-fitting fixes do not implement the architecture proposed here.

## 4. Alternatives

| Approach | Gain | Cost / limitation |
|---|---|---|
| Raise existing limits and use the same model for PLAN and ANSWER | Smallest change; useful short-term relief | Still reconstructs a separate answer prompt and loses the continuous agent exchange; does not satisfy the architectural goal |
| **One agent inside the existing Django runtime** | Continuous reasoning/tool context; preserves IRIS permissions, jobs, and evaluation; supports different providers | Requires a new session/context model, adapter work, and changes to accepted architecture |
| Move execution wholesale into an external agent framework/service | Can obtain useful loop and compaction primitives | Adds runtime and operational complexity; does not solve IRIS source authorization or citations; framework defaults are not safe production budgets |

Recommend the second. Borrow designs from neighboring repositories; keep Django responsible for retrieval, source access, and paid execution.

## 5. Proposed agent execution

Use one named `AGENT` inference responsibility. Preserve per-task audit labels such as normal generation, validation repair, and compaction, but have them resolve to the pinned agent model and data policy. Other product features, such as generating an AI Overview, remain separate tasks. No separate planning model is mandatory for a reader request.

The loop receives the current user request, task state, selected sources, authorized history, tool schemas, and remaining limits. It appends complete ordered assistant outputs and matching tool results. Preserve provider-required opaque items as protocol items, not display text. The next model output can request more tools, ask a clarification, or offer the final draft.

The application executes tools and validates a final draft. Validation is a deterministic stage, not a mandatory second writer model. If actionable checks fail, feed the issues back into the **same session**, with at most the approved repair allowance. This checks binding/access/coverage invariants; it cannot prove every sentence is semantically correct. Human quality evaluation remains necessary.

When the gathering allowance is exhausted, enter finalization mode: disable further research tools and tell the same model to answer from what it has, within the protected answer/repair reserve. Do not let another search consume that reserve. A truncated model response is not a completed answer; inspect stop reasons explicitly. The adapter must disable tools in a continuation-compatible way. If changing tool definitions invalidates retained provider artifacts, use its supported finalization mechanism or reconstruct a compatible session.

Avoid adding a compulsory preliminary query-rewriting call. The agent can resolve a follow-up from its session and choose its search query. Inspect tool internals as well: screening, extraction, and briefs can hide extra model calls. The core agent needs deterministic search/read/metadata tools returning original evidence. Existing cached briefs may be offered explicitly as derived summaries, never represented as newly reading the whole paper. Embedding and reranking services can still support search; they do not become separate planning or answer agents.

Specifically, current `extract_evidence` can invoke `BRIEF`, and its screening mode invokes `SCREEN`. `read_papers(view="brief")` is cache-only. The new path should make these distinctions explicit instead of claiming that all current tools are already deterministic.

Plan updates are optional for complex tasks. A small `update_plan` tool can record bounded steps with pending/in-progress/completed status and a plan revision. “Find relevant papers” is a task step; raw reasoning and provider diagnostics are not. The tool changes only conversation task state, confers no permissions, and cannot extend limits. Task completion is the agent's assessment, not a verified coverage claim. One simple explanation should not require a plan call.

## 6. Context capacity and accounting

Give context management one interface: prepare the next model input and report how much room remains. Its implementation owns capability checking, counting, source expansion, compaction decisions, and continuation validity. Keep three separate quantities:

1. **Context capacity:** what fits in a single model request.
2. **Run allowance:** total time, paid attempts, input/output usage, and cost across requests.
3. **Conversation storage:** original messages and evidence references retained by IRIS.

These are not interchangeable. A model can support a million-token request while the application's run allowance cannot fund it. Conversely, preserving a long transcript in storage does not mean it is sent in every prompt.

Each adapter declares verified model/endpoint capabilities: context and output limits, counting method, request-byte constraints, tools, opaque continuation behavior, caching, compaction, and supported final-output forms. An unknown context limit cannot silently mean one million. A gateway may expose fewer features than the upstream model; probe and test the actual endpoint.

For a model whose window includes input and output:

`usable input = min(model capacity, deployment context ceiling) - output/reasoning reserve - safety allowance`

Count system instructions, tool definitions, history, source text, model continuation items, and framing. Apply the adapter's accounting rules rather than assuming every provider counts thinking identically. On a hypothetical 1,000,000-token window, reserving 48,000 for output/thinking and 16,000 for uncertainty leaves at most 936,000 input tokens. These are illustrative arithmetic, not proposed production defaults.

Keep an allowance for the next tool result and a usable final answer. Compact or stop gathering before overflowing. Do not fill the window and leave no capacity for output, repair, or compaction itself. Larger evidence budgets also require adequate transport sizes, model timeouts, worker leases, and admission reservations.

The existing admission system deliberately uses conservative byte-based input units plus framing. Keep those accounting semantics distinct from model-token occupancy; do not relabel one as the other. Any change to reservations needs tests proving worst-case spend is still bounded. Cache discounts affect cost, not window occupancy. Do not assume cached tokens are free.

Count the actual serialized provider payload privately, including opaque artifacts. Current admission serializes dataclasses with `default=str`, while artifact payloads are hidden from their representation (`admission/llm.py`, `providers/tool_calling.py`); a larger session must not assume this representation measures what is actually sent. Never log artifact contents merely to measure their size.

Pin one model for the active run. Avoid silent per-round fallback to a smaller-window model or a model that cannot consume its opaque artifacts. Recovery must rebuild from portable authorized state for a supported model, or return a recoverable unavailable outcome. Record the switch and charge all attempts.

## 7. Full-document reading and evidence

Retain search for finding relevant documents. Add an explicit full-document read mode, implemented through the existing active chunks, with page and section markers, source version, returned ranges, and continuation. Raise the current small read and passage caps through coordinated token policy, not by returning unbounded data from every tool.

If selected documents fit, the same agent can receive all their available extracted content in document order. If they do not fit, use targeted sections or versioned pagination and disclose the gaps. A result must distinguish “all available extracted text loaded” from “all original PDF content interpreted”: diagrams, tables, equations, and extraction failures may require a further reading capability. Full-document context is not evidence that every document in the repository was searched.

Store source identity/version and exact source bindings outside the disposable prompt. A context eviction should not erase provenance, and a passage reference should not imply that its text is currently in the model's view. Track inspected ranges and currently loaded evidence separately. Deduplicate overlapping chunk text in full-document presentation while preserving the mapping back to the original pages/passages. Stable evidence identifiers must not change when prompt ordering changes.

The agent decides when the evidence seems sufficient; code enforces current access, Paper Chat scope, coverage claims, counts, deadlines, and spend. A document saying “ignore your instructions” remains document content. Conversation summaries and task plans cannot promote such content into trusted instructions.

## 8. Compaction and conversation continuity

Compaction replaces older material **in the active model context** with a shorter handoff. It preserves the original transcript under the Conversation's existing ownership and deletion lifecycle. It is lossy and cannot promise verbatim recall. Provide both automatic compaction before a context threshold and a reader action such as “Compact conversation.”

The handoff includes:

- Current goal and explicit preferences.
- Selected/excluded papers and the exact order previously shown.
- Plan state and unresolved questions.
- Findings with canonical source/version references and important disagreements.
- Inspected ranges, uninspected ranges, and known limitations.
- Original turn references so the agent can recover a detail instead of guessing.

Keep recent turns verbatim and keep current critical evidence where it fits. Compact only complete tool exchanges; never strand an unanswered tool call or alter signed provider artifacts. Preserving an artifact byte-for-byte does not guarantee validity after its conversation prefix changes. The adapter must check continuation compatibility and omit/rebuild incompatible active artifacts using the provider-supported procedure; retain originals in storage under the same access and retention controls. The user-facing compact action is distinct from the optional analytical summary displayed alongside an answer.

Support two strategies behind one interface:

| Strategy | Gain | Cost / limitation |
|---|---|---|
| Application-owned structured handoff using the same agent model | Portable, inspectable, and can be rebuilt after source revocation | Extra inference and latency; summary omissions are possible; tests must measure continuity |
| Native provider compaction when the adapter supports it | Can preserve provider-specific continuation better | Provider-specific behavior and billing; opaque state cannot be selectively inspected or scrubbed |

The portable handoff is the default architectural contract. Native compaction is an optional optimization, not a dependency. A summarization request, whether performed by IRIS or inside a provider request, is real paid work; “one agent” does not eliminate that cost. Do not compact on every question.

Every compacted artifact records the source turn range, conversation revision, source/version dependencies, model/adapter identity, format version, and time. Recheck dependencies before reuse. If access changes and an opaque artifact may contain revoked content, invalidate it in full and rebuild from authorized state; a provider session ID is not an access check. Apply the same rule to the plan, retained excerpts, summaries, and tool queries derived from them.

Commit the handoff only when complete and still based on the current conversation revision. If generation fails, keep the preceding valid context and retry within remaining limits; never replace useful history with an empty summary. A concurrent new user message requires retaining the newer suffix or rebuilding against its revision.

## 9. Durable execution and reader experience

Extend the existing AskRun mechanism. Checkpoint the session revision, ordered exchange references, evidence bindings, plan state, continuation identity, spent allowance, and compaction revision. Redelivery resumes or safely reconstructs from that checkpoint without resetting spend or committing the same output twice. Do not hold a database transaction open during a provider request.

Keep the plan visible as short task descriptions, with truthful status, and keep final answers separate from it. Add a context indicator whose numbers are marked estimated when necessary. Automatic compaction can show “Condensing earlier context”; manual compaction reports success/failure and retains chat history. Reader text should not expose tool names or raw provider reasoning. These UI changes require a protocol version and ADR-042 amendment, including reconnect/history/export behavior.

Depth can vary by request: a small question should use little context, while a detailed paper comparison can request larger bounds inside the deployment policy. Bounds still include tool calls, no-progress detection, time, cancellation, paid attempts, and cumulative cost. A context compaction or plan update must never reset them. If the budget ends, answer supported parts and state the material gaps; do not mark unfinished plan steps complete.

## 10. Delivery order and acceptance

1. Record the approved architecture amendment and create linked work items. Reconcile ADR-042, ADR-026, and affected inference responsibilities. Integrate IR-703's fixes.
2. Build the provider-independent ordered session and single-agent loop. Reuse tools, admission, citations, and final validation. Demonstrate a direct answer and a multistep research answer with no planner-to-writer handoff.
3. Introduce capability-aware context accounting and full-document reading. Verify text near the end and middle of long documents reaches the model and remains citable. Remove independent passage-count bottlenecks from the new path.
4. Add portable compaction, dependency invalidation, and crash-safe checkpoints. Add native compaction only where capability tests justify it.
5. Expose the task list, context status, and compact action through the versioned reader protocol; check live, replay, reconnect, and export.
6. Compare answer quality and resource cost against the existing controller before rollout.

Required evidence includes:

- Correct retention and matching of parallel tool calls, results, and opaque continuation items.
- A large synthetic prompt near the configured capacity fits without destructive silent truncation; oversized tool results return a continuation.
- Accurate page/source citations after full-document reading, evictions, repeated compactions, and source replacement.
- “The second paper” and explicit exclusions survive long conversations and compaction.
- Revoked material cannot reappear in summaries, plan text, provider state, tool arguments, or final answers.
- Compaction failure, cancellation, concurrent turns, worker crash/redelivery, and smaller-model recovery preserve state and paid bounds.
- Native compaction unavailable or malformed does not corrupt the portable session.
- Same-model core execution contains no mandatory resolver/planner/writer/brief generation calls hidden in the tool path.
- A09 tool failures still retain independent findings. Existing worksheet sign-off and human double review remain necessary for counted quality evidence.

Use a locked, versioned evaluation expansion for long-document and long-conversation cases. Test late/middle evidence, conflicting findings, unanswerable questions, image-only facts, irrelevant long content, and multiple compaction cycles. Do not alter a held-out set in response to its model outputs. Compare completion, factual/citation support, continuity, access safety, cost, and end-to-end latency separately. More loaded tokens is not a quality score.

## 11. Neighboring repository review

Source inspection covered the following eight local repositories, including code/notebook cells rather than only their READMEs. No sibling application or tests were executed. Git revision lookup was denied for sibling directories; these are working-tree observations without commit pins. Capture provenance and file-specific reuse terms before incorporating source. The proposed implementation can adapt these ideas without adding their runtimes.

| Repository and inspected source | Useful pattern for IRIS | Limitation / adaptation needed |
|---|---|---|
| `agents`: [agent.ts](../../../agents/src/agent.ts), particularly lines 258, 364, 559 and 913; [compaction tests](../../../agents/tests/simple/agent.test.ts) | One typed model/tool loop; separate stored history from the next model input; proactive and error-recovery compaction hooks; latest-summary-plus-suffix context | Hooks do not supply a summary policy or a durable store. Default 100 turns is not an IRIS budget. Some tools start during streaming, so preserve application admission and cancellation checks before dispatch |
| `teammind`: [retrieve.ts](../../../teammind/packages/ai/src/storage/retrieve.ts), lines 133, 369 and 487 | Expand retrieved fragments into full document content when appropriate | Its 75% retrieved-chunk threshold is a heuristic, not an IRIS rule. Missing chunk-count metadata can trigger expansion. The full read needs its own current authorization, source version, and token check |
| `teammind`: [reason-search.ts](../../../teammind/packages/ai/src/agents/tools/reason-search.ts), lines 54, 108 and 172 | Research step IDs within an invocation and running/completed events | IDs are index-based, not durable across replanning/retries. It generates an internal plan inside a research tool, including extra model work; do not reproduce that hidden planning call. One planned query can fan out to multiple searches |
| `Agent_Memory_Techniques`: [memory_compaction.ipynb](../../../Agent_Memory_Techniques/all_techniques/15_memory_compaction/memory_compaction.ipynb), lines 259 and 277; [token_buffer_memory.ipynb](../../../Agent_Memory_Techniques/all_techniques/05_token_buffer_memory/token_buffer_memory.ipynb), line 258 | Multiple representations of older material, with the original available for detail recovery | Demonstrations, not a production memory implementation. The token buffer can retain one oversized message and excludes system/output allowances; some notebook methods are split into invalid cells. Its cold storage is in memory |
| `multiturn-context-aware-workflow`: [rag_pipelines.py](../../../multiturn-context-aware-workflow/code/backend/rag_pipelines.py), lines 179 and 370 | Explicit current/completed steps and awaiting-input state | Process-local sessions and simulated backend actions; useful for state transitions rather than durable execution |
| `Controllable-RAG-Agent`: [functions_for_pipeline.py](../../../Controllable-RAG-Agent/functions_for_pipeline.py), lines 574 and 1059 | Revisit a plan after retrieval and explicitly assess evidence sufficiency | Graph-routed grading/planning chains, growing context, and no checkpointer in the compiled example; copying this structure would preserve the separate-call behavior the user wants removed |
| `GenAI_Agents`: [human_in_the_loop_approval_agent.ipynb](../../../GenAI_Agents/all_agents_tutorials/human_in_the_loop_approval_agent.ipynb), lines 275 and 348 | Persist a pending state before pausing; validate arguments again on resume | Uses an in-memory checkpointer and simulated effects; not crash-safe production recovery. Local LICENSE restricts commercial reuse without permission |
| `RAG_Techniques`: [hierarchical_indices.py](../../../RAG_Techniques/all_rag_techniques_runnable_scripts/hierarchical_indices.py), line 71 | Coarse discovery followed by detailed reading | Page-number-only filters need document/version keys; this example returns selected fragments rather than a whole document. Local LICENSE restricts commercial reuse without permission |
| `Lorekeeper-Protocol`: [dm_engine.py](../../../Lorekeeper-Protocol/backend/dm_engine.py), line 8; [wiki_synthesizer.py](../../../Lorekeeper-Protocol/backend/wiki_synthesizer.py), line 76 | Inspectable materialized conversation state separate from the immediate answer | Loads the full Markdown vault, performs lossy rewrites, and does not provide atomic multi-file updates. Generated wiki prose cannot become research evidence |

Best fit: adapt `agents`' loop/context interface and `teammind`'s document expansion and step statuses. Use IRIS's database and existing durable-run controls for persistence. The memory and graph examples provide experiments and failure cases, not a reason to adopt another platform.

## 12. External documentation checked

Checked 31 October 2026. These sources describe provider capabilities; they are not evidence that the current IRIS adapter implements them.

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling): model/tool execution proceeds through repeated exchanges, which supports the single-conversation design.
- [OpenAI compaction](https://developers.openai.com/api/docs/guides/compaction): supports server-side and standalone compaction with opaque artifacts. An adapter must preserve its supported continuation form.
- [Claude context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows): instructions, messages, tools, and generated output contribute to capacity; limits and thinking behavior depend on the model.
- [Claude compaction](https://platform.claude.com/docs/en/build-with-claude/compaction): offers native compaction and discusses client-owned summarization. This informs the adapter strategy rather than choosing a provider.

## 13. Verification status

Read-only source inspection and official documentation lookup; no paid inference or runtime behavior was tested for this proposal. Only this review document is added by this architecture investigation. Existing working-tree changes were preserved. No ADR was marked accepted, no implementation was changed, and no Jira item was transitioned.
