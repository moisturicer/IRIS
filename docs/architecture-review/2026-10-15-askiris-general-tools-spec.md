# Proposed specification: Ask IRIS general tools and conversational answers

**Version 1 · 15 October 2026 · PROPOSED.** Jira parent: [IR-588](https://citiris.atlassian.net/browse/IR-588). Child keys IR-589–IR-599 and dependencies are recorded in the [delivery pack](../jira-sync/drafts/askiris-general-tools/README.md). The [final proposal](2026-10-15-askiris-final-proposal.md) explains the product decision; this specification defines testable behavior. Creating tickets does not accept an ADR, approve vendor use, fund evaluation or enable production.

## 1. Scope and non-negotiable behavior

**G1 — General research actions.** Replace exclusive listing/count/comparison/research routing with composable tools. Models may combine tools in different orders or use none for an eligible conversational request. Fixed code remains for domain invariants, not answer prose.

**G2 — Natural answers.** Ordinary research answers are model-composed from authorized evidence and structured facts. No code-generated workflow report is the answer. Genuine operational errors may use concise application wording.

**G3 — Conversation continuity.** Resolve topics, pronouns, displayed ordering, selected papers and exclusions from structured, currently readable conversation context. Preserve the original user request; a retrieval query is not a replacement for the user's intent.

**G4 — Quiet implementation.** No reader surface exposes tool names/arguments/results-as-debug-data, routing labels, classifier confidence, provider identifiers, or reasons for tool selection. Remove “Answer approach,” “Why this approach?” and lane override controls. This applies even inside an expandable panel.

**G5 — Honest reasoning UI.** Neutral live progress plus optional collapsed analytical summary; no raw chain of thought, fake reasoning animation, or fabricated explanation of unseen processing. A summary is neither evidence nor an authorization decision.

**G6 — Domain boundaries.** Existing identity, visibility, Paper Chat scope, disclosure, citation provenance, budget and cancellation constraints remain application-enforced. Models cannot change them. A wider Paper Chat scope still requires the explicit user action the existing product supports.

**G7 — Institutional first.** Web capability is absent unless enabled for the deployment and opted into for the request/conversation. Local failure alone does not enable it.

Out of scope: autonomous writes to records, browser automation with user credentials, arbitrary SQL/code execution, new vector database, multi-agent orchestration, wholesale gateway migration, upload classifier replacement, or training a foundation model.

## 2. Runtime architecture

The existing HTTP/Conversation/AskRun boundary constructs an immutable RunContext. A new controller uses the existing tool-calling provider abstraction and registry. The controller returns one of: tool request(s), clarification, or ready-to-compose. Only the application executes tools. Final prose is composed through `InferenceTask.ANSWER`; controller inference uses `PLAN`, with a revised prompt and contract. Keep named profiles and their data policies. Do not create an untasked provider accessor.

The controller sees the original message, conversation state, recent authorized context, offered tool schemas, results and remaining budget. It receives no capability not available to this user/run. No mandatory `plan_research`, `continue_plan`, `subtask_done` or `finish` ceremony is exposed as a model tool. An internal structured finish signal is enough. Public output is always composed through the final-answer boundary, including clarifications.

For a simple question, one search and one answer may suffice. For discovery plus comparison, the model may search, inspect candidates, choose a pair, read/extract evidence and compose. Independent reads may run concurrently only under the same admission and scope controls. Tool order is evidence-driven, not fixed by verbs such as “compare.”

Keep direct conversational transformations and approved general explanations available. Institution-specific facts and paper findings require evidence. A failed search never becomes an uncited assertion about the corpus. General explanation is labeled by its basis where it could be confused with paper findings; do not label every sentence mechanically.

## 3. Tool contract

### 3.1 Common request rules

All tools use closed JSON schemas, bounded strings/arrays and explicit enum values. Unknown fields and invalid handles fail predictably. The application injects identity, effective scope, source policy, deadline, run ID and spend; none are model arguments. A tool cannot accept arbitrary database IDs or free-form SQL. User-supplied record selections are validated before becoming model-visible handles.

Handles are opaque and run-scoped. Persist canonical record references in conversation state, then reauthorize and reissue handles for each run. A model cannot reuse another run's handle. Page cursors are opaque, scoped to caller/query/source version and bounded; they cannot expand scope or restart the budget.

### 3.2 Model-visible tools

| Tool | Input contract | Output contract | Existing implementation to adapt |
|---|---|---|---|
| `resolve_papers` | `references[]` containing a title/alias or a validated conversation ordinal; optional topic hint | Candidate record handles, match basis, ambiguity groups; never silently select an ambiguous paper | `_named_records` exact matching as a helper; authorized Record lookup; new alias/ranking layer |
| `search_research` | `query`, `target: papers|passages`, optional issued `records[]`, typed metadata filters, bounded `limit`, optional cursor | Ranked records/passages with evidence, match kind and query-scoped coverage | `find_records`, `search_passages`, record fusion and scoped retrieval |
| `read_papers` | Issued `records[]`, `view: outline|sections|pages|brief`, compatible selectors and optional per-record cursor | Ordered outline or evidence; section/page spans; partial/full coverage of the requested selection; per-record continuation | `read_record_sections`, active ChunkSet, IR-556 paper brief machinery |
| `aggregate_records` | `operation: count|facets`, allowlisted filters and supported group-by fields | Typed exact metadata facts with predicate, population identity and snapshot; separate AI-eligibility coverage where permitted | `count_records`, `corpus_facets`, metadata count implementation |
| `extract_evidence` | Issued records, bounded requested fields/criteria, `purpose: describe|compare|screen` | Per-record sourced fields, metric/unit/context, supported/not_reported/unsupported state; screening judgments when requested | Existing briefs, comparison extraction/validation, screening/cache |

Model-facing names are proposed API names, not labels shown to readers. Keep old functions behind adapters during migration; no duplicate retrieval or access stack.

**Resolution:** exact titles/IDs are fast paths, not prerequisites. An ordinal is valid only against the relevant displayed set and state revision. Unknown and unauthorized references have non-enumerating public behavior. “Find two papers” is discovery, not a title-resolution failure.

**Search:** filters use actual IRIS fields, including completion year rather than an invented publication year. Separate exact named-paper matches from related candidates. Do not treat top-k search as exhaustive. Preserve document diversity and per-paper context. The model cannot set retrieval weights or thresholds; measure and configure them in application policy.

**Reading:** outline returns actual section identifiers. Sections accept identifiers returned by the outline, not guessed headings; page requests use valid pages. Each record has its own continuation. A truncated read can resume beyond the first chunks without replaying the whole prefix. `brief` reuses the versioned whole-paper brief; it does not claim newly reading every page when served from cache. Long papers use the existing bounded sectioned strategy. Every read checks active version and disclosure.

**Aggregation:** exact metadata counts are computed by the database. Semantic topic totals cannot use this path unless there is a defined stored predicate. Topic relevance requires screening and produces a subset classification, never an exact whole-corpus total. A computed number carries the population and predicate it describes.

**Extraction:** common scholarly fields reuse the existing brief. Additional user-requested dimensions use source-linked extraction with bounded field counts; they are not restricted to a fixed comparison table. Allow fields to be missing. Screening retains the existing maximum twenty-candidate contract unless separately amended; finding a named paper does not automatically screen twenty records. Cross-paper synthesis belongs to the answer model, not this tool. Numeric superiority requires compatible task, dataset, metric and conditions, not merely numbers existing in both sources.

### 3.3 Common result envelope

Every result contains `schema_version`, `status`, `items`, `evidence`, `facts`, `coverage`, `continuation`, and safe machine-readable `limitations`. Status is one of `ok`, `empty`, `partial`, `ambiguous`, `unavailable`, `denied`. Internal error codes stay private. Denied results contain no protected identity or hidden-count information.

Evidence references identify record, active source version, content kind, page/section and exact underlying passage where available. Metadata facts have metadata provenance rather than a forged passage citation. Brief-derived facts retain their source links. Public web evidence, when enabled later, has its own namespace and canonical URL. Generated summaries and planner notes are never evidence.

Coverage specifies its subject: search candidates, requested pages/sections, screened subset, or exact metadata population. Include selected/assessed/uncertain/unassessed counts only where defined and authorized. “Complete” must always name the scope completed. Unknown total is null, not zero. Tool results do not contain `answer`, `wording`, Markdown narrative or UI routing hints.

Admission usage, timing, cache state and debug diagnostics travel in a private trace envelope, not the reader payload. Tool-call failures still consume applicable attempt limits. Cached results are reauthorized and version-checked before reuse.

## 4. Conversation state and context

Persist a versioned state with active topic, explicit filters, ordered presented record IDs, selected IDs, excluded IDs, pending clarification, answer artifact reference and provenance/source versions. State contains no inferred sensitive user profile. It has the same ownership/deletion lifecycle as the Conversation.

Only successfully delivered turns advance the presented list. Store the exact order shown. A merely retrieved candidate must not become “the second paper” if it was not displayed. A clarification can persist a pending choice without claiming task completion. Cancelled, failed and superseded attempts cannot mutate completed state.

One state revision advances per committed Turn. Concurrent submissions use a conversation revision check: the later run rebuilds from the newly committed state before its first model call, or returns a safe conflict outcome; it cannot silently apply stale references. Retry reuses the original request and expected context deliberately, not whichever topic happens to be newest.

Context assembly prioritizes the original request, explicit preferences, current selections, recent turns, a compact older-conversation summary and task-relevant evidence. Reserve context per selected paper/dimension. Summaries are lossy context and carry source dependencies. Revocation invalidates derived summaries, briefs and cached answer reuse; reconstruct from currently readable material. Audit and test the resolver, controller, synthesis and transcript paths, rather than only the research planner path.

## 5. Answer strategy and validation

The answer policy instructs the model to:

1. Answer the actual request first, at an appropriate depth.
2. Make reasonable research choices from the conversation instead of demanding exact titles unnecessarily.
3. Explain relevance and comparison choices using evidence. This is an explanation of the conclusion, not narration of tools.
4. Separate findings, interpretation and general background when their distinction matters.
5. Preserve uncertainty, missing data, disagreements and limits of comparability.
6. Ask one focused question only when ambiguity materially prevents progress; otherwise proceed with a stated reasonable interpretation.
7. Avoid internal workflow terminology, tool traces, process apologies and repetitive coverage boilerplate.

Use prose, bullets or tables according to the task. Two-paper comparisons may use a table; remove the old prompt rule requiring at least three things. A longer explanation should not be rejected because a global concise-answer instruction won over the user.

The model returns draft Markdown plus explicit source bindings and any typed computed/numeric claims. Validate citation identity, current access, source version, numeric fact bindings and unsupported completeness claims. Presentation numbers, equations and quoted explanatory phrases must not be treated indiscriminately as research counts or paper titles. Literal word/number membership is insufficient evidence of semantic correctness.

Allow one bounded revision after actionable validation feedback, using the same evidence or a remaining-budget targeted retrieval. Do not keep generating until a judge approves. If the revision cannot establish a claim, omit/qualify that claim where independently supported parts remain useful. Security/version failures fence affected content. This is a proposed change to the earlier whole-answer-withholding rule and must be explicitly reconciled before enablement. Until approved, legacy behavior stays in the legacy path.

First release: neutral progress streams, final validated answer delivered atomically. Do not stream unvalidated factual tokens and then pretend a later validation withheld them. Validated block streaming is a separate future optimization. If generation fails, return an honest unavailable state with safe source cards, not code-written “research findings.”

## 6. Reasoning and UI contract

### 6.1 Public presentation

During work, show one compact status row: `Waiting…`, `Thinking…`, or `Preparing your answer…`, driven by actual lifecycle state. Show Stop and truthful elapsed duration where useful. These are not a per-tool sequence. Never show pretend completion percentages or a long blank answer bubble containing debug events.

After completion, show the final answer and citations. Optionally show a collapsed **Reasoning summary** above the answer; omit it when empty, unavailable or unnecessary. On expansion, provide a short analytical account of assumptions and evidence limitations, not an execution log. Example: “These papers address the same research problem, but their evaluation settings differ, so their reported performance should not be treated as a direct ranking.” Only show that statement if supported by the evidence and answer.

Disallowed everywhere in reader UI: `Answer approach`, `Why this approach?`, `Try instead: Passages/List papers`, raw tool identifiers/arguments, classifier probabilities, rejected-call events, routing justification and provider model traces. Suggested follow-ups, if any, express user goals such as “Explain the limitations,” never internal lanes.

### 6.2 Data separation

Define distinct internal fields: provider continuation artifacts, private diagnostics, approved display summary, and answer. Native provider summary availability is an adapter capability; arbitrary `reasoning` text or `<think>` content is not presumed display-safe. Never ask for hidden chain of thought to fill the summary panel.

For this release, build the display summary from approved analytical observations tied to the evidence/answer, preferably in the existing answer response with a separately validated field. A provider-supported summary may inform internal processing but is not forwarded verbatim if it contains tool narration or unsafe content. If a safe summary cannot be produced, omit it; no additional summarization call is required just to fill UI chrome.

Provider-required continuation artifacts/signatures remain opaque and correctly preserved by adapters within the allowed run; never convert them into user text. Capability tests cover summary supported, unsupported, redacted and reasoning-only response. A reasoning-only response is not a successful answer.

New public DTO/event fields are `activity` and optional `reasoning_summary`; internal `routing`, `agent_step`, raw `reasoning` and tool payloads are excluded by a server-side allowlist for the new conversation protocol. Merely hiding them with CSS is insufficient. Existing legacy protocol can remain for compatibility but the new reader client must not request or render diagnostic fields. Historical turns are projected through the same public serializer, omitting old raw reasoning/routing without destructive deletion.

Collapsed content is absent from the accessible tree until expanded. Keyboard activation, focus, `aria-expanded`, reduced motion, narrow Paper Chat and screen-reader announcements are tested. Copy answer excludes summary/debug text. Transcript export contains answer/source content and may include an explicitly chosen safe summary, never raw internals. Reconnect deduplicates activity and final events. Never display simultaneous route, research-steps and reasoning panels.

Official capability references: [OpenAI reasoning summaries](https://developers.openai.com/api/docs/guides/reasoning), [Claude thinking](https://platform.claude.com/docs/en/build-with-claude/thinking), [Gemini thought summaries](https://ai.google.dev/gemini-api/docs/thinking/). Provider/model support must be checked per adapter; these docs do not imply identical consumer-app behavior.

## 7. Budget, durability and security

Reuse AskRun, original submission deadlines, admission, fenced writes and ordered SSE journal. A controller step cannot reset a deadline or bypass global accounting. Reserve answer capacity before research calls. At budget exhaustion, stop admitting work and compose a supported partial answer if the reserved allowance permits, otherwise report unavailable with safe sources.

Initial fake-test profile: four controller rounds, six tool calls, two concurrent independent reads, one repair. These are test fixtures, not production throughput claims. Production caps, pricing, vendor approvals and context windows are explicit configuration decisions; unset admission limits remain fail-closed. Deep reading must have a declared run budget before starting, rather than upgrade itself after exhaustion.

Charge every physical attempt, including retries, fallbacks, summary work and web adapters. Unknown usage retains conservative reservations. Cancellation fences new calls and state writes; account for already admitted remote work. Worker retry reauthorizes cached outputs and respects source versions. A duplicate-call/no-new-evidence detector terminates useless loops without requiring an LLM judge.

Read source content as untrusted data. Tools are read-only and closed-schema. Prompt injection must not widen scope, introduce tools, change identity, disclose protected state or exfiltrate via public queries. Log private trace IDs, failure codes and timings; raw content is not routine telemetry. Permissions apply to source cards and summaries as well as final prose.

## 8. Optional public research

Add `search_public` and `read_public` only in a later disabled capability bundle. User/deployment enablement is checked by code. Public-query construction must exclude restricted titles/passages and derived confidential material; broad opt-in is not permission to disclose them.

Fetching checks every redirect and resolved destination, blocks local/private networks, limits size/time/content types, and carries no user cookies or ambient credentials. Cite fetched sources rather than only snippets. Keep external provenance, retrieval time and identity separate from institutional Records. Public discovery cannot assert comprehensive literature coverage. Test injection, URL redirects, private-address resolution, confidential query leakage and source attribution before enablement.

## 9. Evaluation and acceptance scenarios

Use existing HTTP/SSE/Conversation test boundaries with deterministic fakes for contract correctness, real shared-store/worker tests for races, and human-reviewed model runs only after funding/data approval. No production readiness claim follows from fake tests.

| ID | Scenario | Required result |
|---|---|---|
| A01 | MeshKV → suggest two papers → compare → simplify | Retains topic and pair; discovers rather than demands names; preserves citations |
| A02 | “Compare the first and third” | Uses actual last-presented order and source versions |
| A03 | “Find another, excluding these” | Respects exclusions and reports insufficient results honestly |
| A04 | Ambiguous alias, clear named title, unknown reference | Resolves the clear one; asks focused ambiguity question; leaks no hidden identities |
| A05 | Long paper, requested late section | Reads/resumes the relevant section; not trapped at first token-cap prefix |
| A06 | Exact metadata count vs semantic topic count | Correct distinct-Record count vs explicit classified-subset basis |
| A07 | Two-paper metrics with different datasets | Explains non-comparability; no unsupported winner |
| A08 | User requests more detail or simpler wording | Adapts depth without unnecessary retrieval or lost context |
| A09 | Missing field, weak retrieval, provider outage | Distinguishes missing evidence, no found match and unavailable service |
| A10 | Numbered prose, equations, quoted phrase, invalid factual number | Harmless formatting passes; unsupported fact fails/repairs |
| A11 | Revocation mid-run, stale brief, cross-user handle, Paper Chat widening | Denies/leaks nothing; no stale-source answer or summary |
| A12 | Cancel, redelivery, reconnect, concurrent questions | No duplicate final Turn, new paid call after cancel or stale state overwrite |
| A13 | Live/reopened/copied/mobile/exported response | No tool/routing narration; optional safe collapsed summary; accessible controls |
| A14 | Unsupported summary capability or reasoning-only output | No fabricated summary; reasoning-only is unavailable |
| A15 | Malicious document and optional public query | No expanded permissions, invented tools or confidential egress |

Create a development/held-out multi-turn set with human labels for task success, pair usefulness, claim support, citations and unnecessary clarification. Start with at least 100 conversations across the families, reporting per-family sample counts and uncertainty; this alone does not prove institutional reliability. Hold out topics/papers where practical. Current system, improved fixed synthesis and new controller use equal data/model/budget in the architecture comparison. Model comparisons are a separate axis.

Proposed owner-review targets: >=90% completion on unambiguous supported tasks; >=95% reviewed factual-claim and citation/page support; zero observed access/disclosure breaches in the adversarial suite; blind human preference over baseline. Report each denominator and failure, not a blended score. Record human reviewer identity; independent review precedes institutional claims. Preserve existing load goals as goals and measure queue-inclusive latency/cost per successful task, cold/warm separately. If the approved budget cannot fit the test, report capacity unverified.

## 10. Implementation sequence and file ownership

Each ticket owns a bounded slice; later tickets adapt earlier contracts rather than implement a second stack.

1. **T01 decisions and baseline:** reconcile authority/ADR changes, public/private protocol, answer/summary policy, fixtures and acceptance mapping.
2. **T02 common tool contracts:** registry/results/ledger adapters; evidence envelopes, scoped handles, coverage, compatibility wrappers.
3. **T03 generalized research operations:** resolver, search/read/aggregate/extract implementations over current functions, briefs and comparison helpers.
4. **T04 conversation state:** Conversation/Turn migrations, context assembly, provenance, revision/ordering and revocation.
5. **T05 adaptive controller:** orchestrator composition, PLAN contract, tool loop, answer reservation, stop/repair signals and legacy flag.
6. **T06 synthesis and assurance:** answer policy, source bindings, typed facts, bounded repair, common answer DTO and summary validation.
7. **T07 provider and public event separation:** summary capability/opaque continuation, activity events, public serializers and legacy replay projection.
8. **T08 reader UI:** replace routing/steps/raw-reasoning surfaces in shared chat/Paper Chat; copy/export/accessibility and goal-based follow-ups.
9. **T09 runtime/security integration:** durable workers, admission, cache authorization, race/failure tests and operational controls.
10. **T10 quality/pilot report:** extend harness, controlled comparisons, review results, capacity/cost and rollback recommendation.
11. **T11 optional public adapters:** implement only after institutional contracts stabilize and separate policy gates are satisfied; does not block institutional release.

Relevant existing paths: `backend/apps/ai/{orchestrator.py,composition.py,resolution.py,history.py,memory.py,durable.py,inference/,providers/,research/,comparison/,briefs/,models/,views/,evaluation/}`. Frontend: `frontend/src/features/ai/`, shared conversation client, types and Paper Chat consumers. Do not duplicate active UI tickets IR-562, IR-571 or IR-584: coordinate public protocol adoption and reuse their shared-client/continuity work. No task in this pack implements those tickets' unrelated UI scope.

Stage code behind a new default-off controller setting. New runs pin controller/protocol/prompt versions. Rollback changes new runs only; running jobs finish or cancel under their pinned version. Old transcripts remain readable through a safe projection. Retire lane dispatch from the new path after parity/invariant tests; retain domain helpers. No schema deletion in the rollout migration.

## 11. Policy reconciliation and completion

T01 records amendments for ADR-038 fixed lanes/planning ceremony, ADR-034/035 direct answer policy, ADR-036 inference/summary capabilities, ADR-019 reasoning storage/public presentation, and relevant durable/admission contracts. It also records the supplied AGENTS hierarchy versus CLAUDE's frozen-SRS rule. Do not silently overwrite accepted decisions, sign an ADR as AI, or use Jira to override requirements authority.

Proposed tickets carry `not-ready`, remain unassigned, and do not imply deployment approval. Definition of Ready requires resolved decision dependencies; Definition of Done remains the repository's human-review/CI/merge contract. No automatic Done transition, no paid evaluation, no external corpus transmission or deployment from this specification alone.

## 12. Source evidence

The diagnosis and source links are retained in the [architecture investigation](2026-10-15-askiris-conversational-agent-proposal.md). In particular: `routing/lanes.py` currently publishes listing wording and parses comparison titles; `research/tools/__init__.py` exposes six existing tools; `research/tools/sections.py` reads a capped prefix; `ResearchSteps.tsx`, `RoutingDecisionPanel.tsx` and `ReasoningPanel.tsx` expose current process/working details. This proposal replaces those product contracts, while preserving the useful retrieval and evidence machinery underneath.
