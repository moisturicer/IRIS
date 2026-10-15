# Final proposal: conversational Ask IRIS over general research tools

**Final proposal for review; architecture and implementation remain PROPOSED.** 15 October 2026. Jira parent: [IR-588](https://citiris.atlassian.net/browse/IR-588); implementation subtasks: IR-589–IR-599.

The detailed [proposed specification](2026-10-15-askiris-general-tools-spec.md) is the implementation contract for this proposal. [IR-588](https://citiris.atlassian.net/browse/IR-588) holds the child tickets and dependency order. This proposal records the product choice for this effort without rewriting accepted ADRs or completed work; the specification's source-evidence section points to the implementation it proposes changing.

## Outcome

Ask IRIS should understand the research task and carry it forward naturally. It should find a useful comparison pair when the reader asks for one, remember the papers it showed, read the evidence it needs, explain findings clearly, and recognize when it cannot support an answer.

Use institutional papers first. Public research is optional and separately enabled. Quality should be assessed against the useful behaviors of Claude, ChatGPT and Gemini, rather than a promise to reproduce their private internals or branding.

## Architectural decision

Replace exclusive answer lanes with **one conversational controller and a small set of composable, read-only research tools**. Keep the existing Django runtime and domain controls.

The controller interprets the original request with conversation state, chooses tools, adjusts after results, and asks the answer model to produce a coherent reply. It may answer a conversational transformation without a new search. It may discover papers before comparing them. It need not run every request through a fixed planning ceremony.

The application still owns authorization, disclosure, source identities, typed counts, scope, cost admission, cancellation and persistence. Models choose research actions and write prose; they do not authorize data access or calculate authoritative catalogue totals.

## Generalize, do not rename the lanes

The new tool surface comprises paper resolution, search, bounded reading, aggregation and evidence extraction. Existing screening and full-paper briefs become reusable options inside those capabilities. A separate model-visible `compare_papers` workflow is unnecessary: comparison is search/read/extract followed by synthesis over a set of evidence. Existing comparison code is retained as a helper for typed metrics, page verification and comparability checks.

Each tool returns structured data, source references, coverage and recoverable status. It never returns a finished answer such as “Screened 20 candidates…” for the UI to publish verbatim. Code-generated text remains appropriate for operational states such as cancellation or an unavailable provider, not ordinary research explanations.

## Reader experience

The final answer contains the answer, appropriate citations and material limitations. It contains **no** “Answer approach,” “Why this approach?”, route override buttons, tool calls, arguments, or tool-selection narration. The same rule applies to reopened chats, copied answers, Paper Chat and exported transcripts.

While work runs, show a compact neutral status such as “Thinking…” or “Preparing your answer…” and elapsed time when useful. Provide Stop. On completion, an optional collapsed **Reasoning summary** can explain the analytical basis at a high level—for example, that two papers address the same problem but use different evaluation settings. It must not become a disguised tool trace. It is not required on short answers and is never fabricated when unavailable.

Do not display raw provider reasoning or historic raw reasoning. New reasoning summaries have explicit provenance and are separated from answer text and citation parsing. Hide legacy raw reasoning in the new reader surface without deleting stored history as a side effect. Any retention change is a separate approved migration.

This is a product design inspired by provider capabilities, not a claim that all three apps use the same UI. Official documentation describes summaries separately from raw/internal reasoning: [OpenAI](https://developers.openai.com/api/docs/guides/reasoning), [Anthropic](https://platform.claude.com/docs/en/build-with-claude/thinking), and [Google](https://ai.google.dev/gemini-api/docs/thinking/).

## What the example becomes

“Give me papers about MeshKV” returns actual matches with a useful explanation of relevance. “Give me two papers that I can compare” uses that topic, discovers a suitable partner, and explains the comparison axis. “Compare their methods and limitations” reads the selected papers and provides a supported comparison. “Make it simpler” rewrites the explanation without losing its evidence.

If no suitable second institutional paper is found, say that the search did not find one and offer public research. Do not invent a partner or demand exact titles for a recommendation request.

## Reuse and cost

Reuse scoped retrieval, pgvector, Voyage, Docling, evidence ledger, citations, provider profiles, full-paper briefs, exact aggregation, screening, durable runs and shared admission. Borrow the small typed loop and context lifecycle ideas found in sibling repositories, rather than introduce another agent framework, database or service.

Compared with only improving prompts, this costs more controller, state and evaluation work, but addresses compound requests and follow-ups. Compared with a multi-agent replacement, it preserves existing operational controls and reduces integration work. Model quality remains a separate measured variable; a new loop cannot compensate for poor extraction or an incapable model.

## Delivery

Publish one proposed parent Story under IR-146 with independently reviewable subtasks. Start with policy reconciliation and fixtures, then general tool contracts and conversation state, controller and synthesis, summary/UI behavior, durability/security, and evaluation. Keep optional web work disabled and separate from the institutional release gate.

No runtime code or production setting changes are part of this documentation task. Proposed tickets remain unassigned and not-ready until the recorded decisions and dependencies are satisfied. Do not reopen or rewrite completed IR-551 work; this effort reuses its delivered capabilities and changes their orchestration.
