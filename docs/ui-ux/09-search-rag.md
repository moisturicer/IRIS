# 09 — Search & AI

**Verdict: REBUILD as one screen called "Search". REMOVE the chat interface.**

> **The product is not a chatbot.** The user's goal is finding a record. AI is one way that search works — not what the feature is.

---

## 1 · What exists

| File | Lines | State |
|---|---|---|
| `AIHubPage` | 83 | Routed at `/ai`. **Both modes render "Coming Soon" panels.** No search input exists |
| `RAGChatPage` | 239 | Full chat UI — **routed to nothing** |
| `ai/components/` ×7 | 509 | `ChatInput`, `ChatMessageBubble`, `ChatMessageList`, `ChatToolbar`, `ConversationSidebar`, `SourceContextPanel`, `AssistantMessageSkeleton` — all reachable only from `RAGChatPage` |

`api/ai.ts` declares six endpoints — `semanticSearch`, `ask`, `summarize`, `embedRecord`, `embedAll`, `embeddingJobs`. Per [ADR-006](../adr/006-minimum-rag-pipeline.md) the backing services are class bodies containing `pass`.

**So the honest position is:** 748 lines of chat interface that no route reaches, and the one screen that *is* routed says "Coming Soon" twice. There is no search box in the product.

Meanwhile `records/signals.py` maintains `Record.search_vector` with a GIN index and weighted title/abstract vectors. **Full-text search works today and nothing in the UI uses it.**

---

## 2 · The correction

Three decisions, in order of importance.

### It is called "Search"

Not "AI Research Hub". The user came to find a record. Naming the feature after its implementation makes the FTS fallback read as a downgrade — *"the AI is broken"* — when it is a designed mode ([ADR-008](../adr/008-ai-degradation-to-fts.md)). Under the name "Search", keyword results are simply results.

This is not cosmetic. [ADR-008](../adr/008-ai-degradation-to-fts.md) commits to degrading to FTS during a pilot that may be observed. A feature named "AI Hub" that silently stops being an AI hub is a defect narrative; a feature named "Search" that returns keyword matches is a working product.

### Search is one input, not two modes

The current mode toggle asks the user to classify their own intent before they have typed anything — and the distinction between "semantic search" and "ask a question" is an implementation detail they have no basis to reason about.

One input. The system decides how to answer it.

### The chat interface is removed

`RAGChatPage` and its seven components are deleted from the router, per [ADR-006](../adr/006-minimum-rag-pipeline.md)'s exclusion of conversational memory. `Conversation` and `ChatMessage` are field-less stubs; the UI is built against a backend that does not exist. Keeping it routed invites evaluation participants to use a feature with no data layer.

---

## 3 · The screen

```
Search

  ┌────────────────────────────────────────────────────┐
  │ 🔍  crop disease detection using deep learning     │
  └────────────────────────────────────────────────────┘
  [ All types ▾ ]  [ All years ▾ ]

  ─── ANSWER ──────────────────────────────────── AI ───
   Three records address crop disease detection with
   deep learning. Two use convolutional networks on
   leaf imagery [1][2]; one applies transfer learning
   to a Philippine rice dataset [3].

   Generated from the 3 records below. Verify against
   the source documents before citing.

  ─── RECORDS ─────────────────────────── 7 results ───
  [1] Machine learning for crop disease detection
      Reyes, Santos · 2025 · Thesis/Research
      "…a CNN trained on 4,200 annotated leaf images…"

  [2] Transfer learning for rice blast identification
      Cruz · 2024 · Project
```

### Degraded mode

Same screen. One banner, and the answer block is absent:

```
  ⓘ AI-assisted search is unavailable. Showing keyword
    results.                                    [ Retry ]

  ─── RECORDS ─────────────────────────── 5 results ───
```

**The results are still there.** The layout does not reflow into an error page; one block is missing and one banner is present. That is the whole degradation, visually.

| Rule | Reason |
|---|---|
| **Never fabricate an answer.** No AI → no answer block | [ADR-008](../adr/008-ai-degradation-to-fts.md). A stale or invented answer is worse than none |
| **Every claim carries a citation** to a record the viewer can open | FR-M4-01, and a groundedness requirement |
| **The answer is labelled `AI`** and visually distinct from records | The user must always know which text a machine wrote |
| **Results render before the answer resolves** | Retrieval is fast; generation is not. Never block records on an LLM call |
| **The answer is never the only content** | If the records list is empty, there is nothing to ground an answer in, so there is no answer |

---

## 4 · The visibility rule

**Search must never surface a record the viewer cannot open — including in a citation.**

`S-02` establishes that `GET /records/:id/` currently returns any record to any authenticated user, and `get_queryset` filters only on `list`. A retrieval layer that queries embeddings directly bypasses even that filter.

| Surface | Requirement |
|---|---|
| Result rows | Filtered by `visible_to(user)` server-side |
| **AI citations** | Filtered by the **same** predicate, before the prompt is built |
| Snippets | Drawn only from records that passed the filter |
| Result counts | Counted after filtering — *"7 results"* must mean seven openable records |

The count matters more than it looks. A count computed before filtering discloses the existence of records the viewer cannot see, which is the same leak in a smaller package.

> A citation to an unpublished record is a disclosure with a footnote. [ADR-006](../adr/006-minimum-rag-pipeline.md) states the rule; this screen is where it becomes visible or does not.

---

## 5 · Specification

**User.** All authenticated roles.

**Goal.** Find records relevant to a question or a keyword.

**Primary action.** Search.

**Secondary actions.** Open a record · filter by type or year · retry when degraded · clear the query.

**Required data.** `POST /ai/search/` → `{ answer?, sources[] }` · reference lists for the type and year filters · per result: id, title, authors, year, type, snippet.

**Permissions.** All authenticated roles may search. **Results and citations are visibility-filtered server-side** (`S-02`, `B-05`). No client-side filtering of results — a filtered-out result that reached the browser has already leaked.

**States.**

| State | Rendering |
|---|---|
| Idle, no query | Empty state with example queries and a corpus count |
| Searching | Skeleton result rows; the input stays editable |
| Results + answer | Answer block, then results |
| Results, answer pending | Results rendered; the answer block shows its own skeleton |
| **Degraded** | Banner + results, **no answer block** |
| No results | Empty state with suggestions |
| Query too short | Inline hint; no request fired |

**Errors.**

| Error | Handling |
|---|---|
| Embedding or vector search fails | **Fall back to FTS silently at the data layer**, show the degraded banner. Not an error screen |
| LLM fails or times out | Results stand; the answer block is replaced by *"An AI summary could not be generated for this search."* with retry |
| Timeout > 30 s | Bounded per [ADR-008](../adr/008-ai-degradation-to-fts.md); message names the timeout rather than blaming the query |
| Both FTS and vector search fail | A genuine error state with retry — this is infrastructure down, not degradation |
| Rate-limited | Degraded banner; the user-facing text does not mention credits or quotas |

**Empty states.** No query yet → *"Search published research records"* plus three example queries and a corpus size, which sets expectations about what is searchable. No results → *"No records match 'xyz'"* plus a suggestion to broaden terms and a link to browse all published records. **An empty corpus** → *"No records have been published yet"* — distinct, because it is not the user's query that failed.

**Loading states.** Skeleton rows sized to the final result card. The answer block loads independently and **later**; it must not delay results. The input is never disabled during a search — a user retyping should not be blocked by their previous query.

**Accessibility.**
- The search input is a labelled `<input type="search">` inside a `<form role="search">`; submission works by Enter without a mouse
- The result count is announced via `aria-live="polite"` — once per search, not per keystroke
- The answer block is `<section aria-label="AI-generated summary">`, so its provenance is announced, not only shown
- Citations are real links with accessible text — *"Reference 1: Machine learning for crop disease detection"*, not a bare `[1]`
- The degraded banner is `role="status"`, announced once
- Results are a `<ol>` of links; snippet emphasis uses `<mark>`, not colour alone
- Focus moves to the results heading after a search, not into the first result

**Responsive.** Single column at every width. The input is full-width; filters wrap below it and become a bottom sheet under 768 px. The answer block sits above results at all widths — it is never a sidebar, because at 360 px a sidebar becomes a footer nobody reads. Snippets clamp to three lines ([13](13-responsive.md)).

**MVP/Post-MVP.**

| | |
|---|---|
| **MVP** | One input · results · grounded answer with citations · degraded mode · type and year filters |
| **MVP if the timebox holds** | The answer block. Per [ADR-006](../adr/006-minimum-rag-pipeline.md), **if grounded generation is not working by end of Week 6, ship search only** — the screen is designed so that removing the answer block leaves a complete product |
| **Post-MVP** | Conversation history · summarization · saved searches · similar-record recommendations · chunk-level citation into a page |
| **Removed** | Chat interface · conversational memory · mode toggle |

**Backend/API dependencies.**

| Dependency | ADR / Task | Status |
|---|---|---|
| `POST /ai/search/` returning results **and** an optional answer | `R-01`…`R-04` | Service bodies are `pass` |
| Visibility filtering inside retrieval | `S-02`, [ADR-006](../adr/006-minimum-rag-pipeline.md) | **Not built — this is a disclosure risk, not a feature gap** |
| pgvector similarity | [ADR-007](../adr/007-pgvector-vector-store.md) | Not built |
| **FTS fallback path** | [ADR-008](../adr/008-ai-degradation-to-fts.md) | **`search_vector` exists and is maintained; nothing queries it** |
| Health signal so the UI knows it is degraded | [ADR-008](../adr/008-ai-degradation-to-fts.md) | Not built |

---

## 6 · What this buys

The screen is designed so that the AI is **subtractable**. Remove the answer block and the remaining product is a working search over published research — which is what most users wanted, and which runs on an index that already exists.

That property is the point. It means the RAG timebox in [ADR-006](../adr/006-minimum-rag-pipeline.md) can expire without leaving a hole in the interface, and it means an AI outage during the Week 11–12 pilot degrades one block rather than one screen.
