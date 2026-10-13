# ADR-026: Conversational retrieval — question rewriting, and memory by retrieval rather than summary

## Status

**Accepted** — 2026-09-17.

> **Amendment to §13 — [ADR-035](035-ask-iris-decides-whether-it-needs-evidence.md) (Accepted 2026-10-06, IR-461).** The evidence decision is a consumer §13's single predicate does not describe: it receives prior **reader questions only** — no prior assistant answer text, no recalled Turns, no Passage text — because a grounded answer is retrieval-derived and may echo text injected into a Passage. A `generated` Turn is admissible to the answering model and **not** to a routing decision, so state is the wrong axis there. Implemented by IR-465; the broader per-consumer refactor is IR-453's. See ADR-035 §8.

> **Amendment proposed — 2026-10-11 (IR-499). Not accepted.** [ADR-038](038-bounded-research-lane-for-ask-iris.md) continues the per-consumer split: the router sees prior reader questions only, and the research planner sees recent history **including prior answers** but not memory-recalled Turns. Drafted by an AI agent; awaiting a named approver. See §Amendment — 2026-10-11 below.

**Implements and amends [ADR-019](019-persisted-unified-conversation-history.md).** ADR-019 decided *that* conversation history is persisted and unified across Ask IRIS and Paper Chat, and that decision stands unchanged. It deliberately left *how* history reaches retrieval unspecified, and its citation-storage mechanics have been overtaken by work completed since. This ADR settles the first and amends the second.

**Depends on [ADR-023](023-retrieval-quality-evaluation.md)** for why one technique here is adopted and two are deferred.

**Amended — 2026-09-28 (IR-392), under [ADR-013](013-chunk-level-rag-pipeline.md)'s thesis-critical RAG scope.** Four additions, all reader-facing: §12 Retry, §13 what the model is allowed to see of a Conversation's own failures, §14 where the multi-part flag of §2 comes from — which **closes the open question §2 left**, explicitly rather than by quiet insertion — and §15 feedback privacy as an addition to §11. The vocabulary for **Retry**, **Reader feedback** and a **Listing question** is `CONTEXT.md`; the listing routing outcome those questions reach is in [ADR-027](027-corpus-level-questions.md) §9.

**Amended — 2026-10-02 (IR-444), under [ADR-013](013-chunk-level-rag-pipeline.md)'s thesis-critical RAG scope.** Two reversals, both traced to one observed failure: §8's back-reference word check is struck, so resolution runs on every follow-up, and §7's question-only embedding becomes question *and* answer, which is no longer free. §6 is unchanged. See §Amendment — 2026-10-02 below, and the [ADR-015](015-voyage-embedding-and-reranking.md) note it requires.

**Amended — 2026-10-06 (IR-355), §9 only, reader-facing, no backend change.** A Paper Chat conversation whose citation the reader followed to a *different* paper stays open, pinned, while that paper is shown. This stretches [ADR-019](019-persisted-unified-conversation-history.md)'s description of Paper Chat as "shown only while viewing one record's detail page, scoped to that record". Decided with the project lead 2026-09-24; **pending review by the AI-track owner** (ADR-019 and this ADR are AI-track decisions). See §Amendment — 2026-10-06 below.

## Context

ADR-019 states that the backend "loads and extends the real message history for both retrieval and LLM synthesis". That sentence admits two readings which behave completely differently, and nothing records which was meant.

The problem it has to solve: a reader asks "what does this paper conclude?", then "what about its limitations?". The second question has no subject. Searching the corpus for *limitations* returns every paper's future-work section.

### What exists today

Multi-turn is a frontend illusion built on string concatenation. `buildRagQuestion` glues the entire prior transcript into one string and sends it as the question, which goes straight into full-text search — so retrieval matches against the whole conversation and degrades with every turn.

**It is also actively broken past a handful of turns.** `ChatQueryView` rejects questions over 2,000 characters. Because the transcript *is* the question, a conversation of roughly five or six turns starts returning 400s. Moving history behind a conversation id fixes this as a side effect.

### Two things in ADR-019 that later work overtook

ADR-019 decided citations are stored as **record ids only**, re-checked against `Record.objects.publicly_visible()` on every read. Both halves have since moved:

- IR-283 replaces `publicly_visible()` with `visible_to(user)` on every retrieval path — the mechanism ADR-019's mitigation names is being removed.
- IR-284 makes a citation an object carrying Record, **page and Passage**. Under ADR-019's literal rule, reopening yesterday's conversation would show citations stripped of their quotes — strictly worse than asking the same question fresh.

ADR-019's *reasoning* remains correct and is preserved below. Only its mechanics are amended.

## Decision

### 1. A follow-up question is rewritten into a standalone question before retrieval

When a Conversation has history, an LLM call rewrites the incoming question into a self-contained one using that history — "what about its limitations?" becomes "what are the limitations of *[paper title]*?" — and **retrieval runs on the rewrite**, not on the raw question.

This is not an optimization. It is the mechanism that makes multi-turn retrieval work at all; without it, retrieval sees a question with no subject and the answering model then writes from bad sources.

Two guards:

- **The resolved question is stored and shown.** A wrong rewrite silently changes what was asked, so it must be inspectable rather than mysterious.
- **A failed rewrite falls back to the raw question.** Retrieval degrades for that turn; it does not error.

### 2. Sub-query decomposition runs only on questions flagged multi-part

Decomposition produces the largest recall gain of the available techniques, and it has a well-documented failure mode: an LLM asked to decompose will split a single-hop question into three redundant sub-queries, tripling retrieval cost for no gain, and the longer merged context can degrade the answer.

So it is **conditional, never default**. This matters because Paper Chat's "search all papers" control (below) directly invites comparison questions, which are genuinely multi-hop.

> **Open question closed, 2026-09-28 (IR-392).** This section made decomposition conditional on a question being flagged multi-part and never said what does the flagging. **§14 answers it:** the flag comes from the same classifier call that routes the question. The gap is named here rather than left for someone to rediscover in code.

### 3. Multi-query retrieval is deferred, and this is an evidence decision

Generating several rewrites and fusing their results does measurably outperform a single rewrite for conversational retrieval, at proportionally higher cost. It is deferred anyway, for two reasons specific to IRIS:

- Its value is reported to appear **at scale**, where different phrasings reach genuinely different regions of the vector space. IRIS's corpus is small and institutional.
- **IRIS already reranks.** Reranking recovers much of what multi-query buys, so the marginal gain here is unknown rather than merely unmeasured.

Adopting it now would be taste presented as evidence. [ADR-023](023-retrieval-quality-evaluation.md) exists precisely to settle questions of this shape, and its recall measurement is blocked on corpus acquisition. This is the same discipline IR-243 applied to the chunk token ceiling.

### 4. HyDE is rejected

Generating a hypothetical answer and embedding *that* to retrieve is a poor fit twice over. It pushes fabricated passage text into the retrieval path — text a model invented about a domain it may know nothing about — inside a system whose purpose is grounded citation into IP disclosures. And it doubles the LLM calls per turn for a technique general guidance already recommends against by default.

### 5. Query enhancement sits behind a seam, like reranking

Each technique is a transform applied to the question before retrieval, composed around the retriever rather than built into it — the shape reranking already uses.

This is what makes ADR-023's with-and-without comparison possible **per technique**, and what turns "we added some tricks" into a measurable contribution. Enabling multi-query later becomes a configuration change rather than a rewrite.

### 6. Memory is retrieval over the conversation's own turns, never a summary

Recent turns go into the prompt verbatim. Older turns are **retrievable**: the conversation's own history is searched for relevant past turns, which are included alongside.

**Nothing is summarised and nothing is discarded.** Lossy compression is the risky option for long-term memory precisely because a reader may refer back to a detail that looked minor at the time, and a summary drops exactly those. Retrieval keeps everything findable while keeping prompts short.

This needs no new infrastructure. A conversation's turns are a small corpus, and IRIS already has an embedding provider, a vector store, a reranker and a retriever. Current research also finds that dense retrieval with filtering — **without** knowledge graphs or agentic memory managers — matches far more elaborate systems while using shorter contexts, so the simple form is chosen deliberately rather than as a first step toward a graph.

### 7. ~~Only questions are embedded, and their vectors cost nothing extra~~ Questions and answers are both embedded; only the question's vector is free

> **Superseded 2026-10-02 (IR-444).** The answer is embedded too, and that is a real cost. The headline and the "answer recall for free" claim below no longer hold; see §Amendment — 2026-10-02, §7.

**A turn is indexed by its question and returned whole.** Answer recall is preserved without embedding answers, because a question and its answer are a pair.

The cost property that makes this free: **the memory vector and the search vector are the same vector.** Every question is already embedded to search the corpus; that result is stored on the turn instead of discarded. Remembering a user's questions indefinitely costs zero additional vendor calls.

Embedding answers would be a genuine extra call on every turn, for recall that indexing questions already provides.

### 8. ~~A turn adds no cost unless it actually needs rewriting~~ A follow-up always resolves; the cache and the small model bound the cost

The rewrite is the only new per-turn cost, and it is avoided wherever it does nothing:

- **Skipped on the first turn** — there is no history to resolve against.
- ~~**Skipped when the question carries no back-reference**, decided by a cheap word check rather than a model call. The failure is soft: a missed back-reference retrieves on the raw question, exactly as today.~~ **Struck 2026-10-02 (IR-444).** The failure is not soft; see §Amendment — 2026-10-02, §8.
- **Performed by a small model**, configured separately from the answering model. Rewriting is an easy task and does not need the model that writes answers.
- **Cached**, keyed like query embeddings already are — same question and same history yield the same rewrite.

~~Most turns therefore cost what they cost today.~~ No longer true as of 2026-10-02; see §Amendment — 2026-10-02, §8.

### 9. Paper Chat filters to its Record, with an explicit control to widen

A Conversation scoped to a Record retrieves **only that Record's passages** by default, which is ADR-019's "pre-filtered to this record" made operational. A visible control lets the reader search all papers.

Silent scope-widening is rejected outright: a reader asking about the paper in front of them must never receive an answer drawn mostly from a different one without having asked for it.

### 10. A stored citation keeps a pointer, never the text — amending ADR-019

A `ChatMessage` stores **record id, chunk id and page**. It never stores the Passage text. The quote is re-resolved at read time through the current visibility predicate.

This preserves ADR-019's intent exactly — a stored message must never hold enough of a citation to reconstruct content from a record that has *since* become restricted — while fixing mechanics it could not have anticipated. **A pointer is not content.** History reads at full fidelity while the reader may see the record, and reveals nothing once they may not.

Where re-chunking has removed the referenced chunk, the citation degrades to a record-level link rather than inventing a quote.

**The predicate is `visible_to(user)`**, not `publicly_visible()`. ADR-019's naming of the latter is superseded by IR-283.

### 11. A Conversation is private to its owner, kept until deleted

Only the owning User may read a Conversation. **This explicitly includes staff**, who read everything else in the workflow — recorded because "staff can see everything" is the default assumption in this system and here it is wrong.

A transcript is a record of what someone asked about confidential IP. "Has anyone patented a humidity-control method like this?" is sensitive regardless of which records it cited.

There is **no automatic expiry**. The user may delete a Conversation, and deleting a Record cascades to Conversations scoped to it. Automatic expiry would solve a storage problem IRIS does not have while creating a trust problem it does not want.

### 12. A Retry is a new Turn on the same Resolved question, recognised deterministically

A reader who is unhappy with an answer can ask the same question again — a **Retry** (`CONTEXT.md`). **A Retry is recognised from an explicit action** — a control on the answer — with a short, fixed phrase list ("try again", "retry", "regenerate") as the only fallback. Nothing else is guessed. Deterministic patterns first, then nothing: the shape [ADR-027](027-corpus-level-questions.md) §5 already uses for routing, for the same reason — on unambiguous phrasings a pattern can only be more accurate than a model, and on ambiguous ones a wrong guess silently discards what the reader actually typed.

**A Retry searches again**, with the previous Turn's **Resolved question** (§1) rather than the raw text, and it does **not** reuse the previous Turn's stored citations. Re-running re-applies `visible_to(user)` inside retrieval; reusing stored citations would skip exactly the check §10 exists to enforce, so a Record that stopped being readable between the two attempts could be quoted back. Re-running also costs a retrieval the reader explicitly asked for, which is the cheapest justification available.

**A Retry is a new Turn, appended.** The retried Turn stays in the Conversation, visible. Overwriting it would destroy the evidence that the first answer was poor — the only thing that makes retry rate, and §15's feedback, measurable under [ADR-023](023-retrieval-quality-evaluation.md). A reader can also compare the two answers, which is the point of asking again.

### 13. Failed and refused Turns stay visible to the reader and are kept out of the model's history

> **Amended 2026-10-02 (IR-453).** An **ungrounded** Turn joins the three states excluded here, so `MODEL_HISTORY_STATES` stays `{generated}`. Unlike the other three it holds genuine content, so the exclusion has a real cost — a follow-up to an ungrounded aside does not resolve against it — and that cost is accepted rather than hidden: an ungrounded answer left in the prompt is a demonstration of answering without sources, and the bias runs toward the one path that must not drift. See [ADR-034](034-ungrounded-answers-as-a-distinct-state.md) §5.

A Turn whose answer failed (no model reachable, per [ADR-008](008-ai-degradation-to-fts.md)) or whose answer was a refusal (no readable sources; [ADR-027](027-corpus-level-questions.md) §1b/§1d's refusals) **is excluded from the history handed to the answering model and to the rewriter of §1**. It stays in the transcript the reader sees, and it stays stored.

A refusal left in the prompt is a demonstration of refusing. The next attempt — very often a Retry of the same question under §12 — is then biased toward repeating it, and the rewriter is asked to resolve a follow-up against text that says nothing about the subject. Excluding these Turns costs nothing: they carry no answer content a later question could need.

This is not hiding a failure from the reader. The reader sees every Turn; only the model's view is filtered, and that asymmetry is deliberate.

### 14. The multi-part flag comes from the routing classifier, not from a second call

§2's conditional decomposition is gated on a flag, and **the flag is produced by the same small-model classifier call that routes the question** in [ADR-027](027-corpus-level-questions.md) §5. Both are the same question — *what kind of question is this?* — and answering them together costs one call.

This does **not** breach [ADR-027](027-corpus-level-questions.md) §5's refusal to fold routing into question *resolution*. That refusal is about resolution: rewriting a follow-up into a standalone question is a generative rewrite, and pairing it with a classification makes both worse. Classifying one question along two axes is one job, not two.

How a flagged question is then answered:

- **Each sub-question retrieves on its own**, through the ordinary retrieval stack, so `visible_to(user)` applies to each independently.
- **Results merge by rank position**, not by raw score. Scores from separate retrievals are not comparable; rank position is.
- **Every sub-question is guaranteed at least one passage in the final set.** Without that guarantee a merge can starve one part of a two-part question entirely, and the answer then looks complete while covering half of what was asked.
- **The sub-questions are shown to the reader**, for exactly the reason the Resolved question is (§1): a bad split changes what was asked, so it is never hidden.

### 15. Feedback stores a verdict, not a transcript — an addition to §11

§11 makes a Conversation private to its owner, staff included. **Reader feedback (`CONTEXT.md`) must not become the way around that.**

- By default, submitting feedback stores **the verdict and the cited Record ids, and nothing else** — no question text, no answer text.
- **Sharing the exchange is a separate, explicit choice.** Only then is question and answer text stored, and citations are still stored as pointers under §10 — a shared exchange is not a licence to keep Passage text.
- **Deleting a Conversation deletes its feedback**, shared exchanges included. A deletion the reader believes is complete must be complete.
- **Feedback is never a ranking input.** It changes no retrieval score and no ordering. It is evidence for [ADR-023](023-retrieval-quality-evaluation.md)'s measurement, read by people. Letting a handful of votes on a small institutional corpus steer ranking would make retrieval quality drift in a way no measurement could attribute, and would make gaming it trivial.


## Amendment — 2026-10-02 (IR-444): resolution runs on every follow-up, and a Turn's answer is embedded too

### Evidence

[ADR-023](023-retrieval-quality-evaluation.md)'s rule is that a change of this kind cites what was observed, so the observation comes first. It is quoted from IR-443, where it was traced. A reader asked a cosmology question and got a good grounded answer. They then typed **"give me a longer explanation"** and were told *"The supplied sources do not contain any information about the separate-universe approach."* In order:

1. `has_back_reference` (`apps/ai/resolution.py`) found no pronoun in "give me a longer explanation", so resolution was skipped with no model call. That is §8's word check doing exactly what it was written to do.
2. Retrieval therefore searched the literal string `give me a longer explanation`, which sits nowhere near a cosmology paper in embedding space, and returned arbitrary passages.
3. The answering model had the previous Turn in its `Conversation so far:` block but is grounded to the numbered `Sources:`, so it correctly refused.
4. That refusal became Turn 2 and entered every later prompt verbatim — the bias §13 exists to prevent. §13 was decided under IR-392 and implemented nowhere at the time this amendment was written; **IR-448 implements it as of 2026-10-02** — one predicate over `Turn.state`, applied to the verbatim window, the rewriter's history and memory recall alike, with the reader's transcript deliberately unfiltered. It was not part of this amendment and did not need to be: the rule above was already decided.

Steps 1 and 2 are what this amendment decides. The Turn 3 / Turn 20 example under §7 below is a **constructed illustration**, not an observation, and is labelled as one.

### §8 — the word check is struck; resolution runs on every follow-up

§8 said a missed back-reference is a soft failure that "retrieves on the raw question, exactly as today". **That was wrong, and the transcript above is the proof.** A missed back-reference does not leave retrieval working on a slightly worse question. It leaves retrieval working on text that was never meant to be a search query: "give me a longer explanation" has no topic in it at all, so the vector search returns arbitrary passages and the reader gets a confident-sounding refusal over unrelated sources. That is worse than a weak answer, because nothing about it looks like the retrieval's fault.

Widening the list does not fix this. The failing question contains no referring word to add, and any list is incomplete in exactly the cases a reader reaches for (see §Alternatives Considered).

What this changes:

- **Resolution runs on every follow-up.** The word check is deleted.
- **Unchanged:** it is still skipped on the first Turn, where there is no history to resolve against; the result is still cached under the key §8 describes; and a failed rewrite still falls back to the raw question (§1's guard).
- **Cost control moves entirely to the cache plus the small model.** §8's closing sentence — "Most turns therefore cost what they cost today" — is no longer true. Every follow-up that misses the cache now costs one small-model call. That is the price of the fix, stated here rather than discovered on an invoice, and it makes §Consequences' "a second, smaller model must be configurable" load-bearing rather than a nicety.

### §7 — question and answer are both embedded, and that is no longer free

§7 held that "a turn is indexed by its question and returned whole", and that answer recall is "preserved without embedding answers, because a question and its answer are a pair". That was an assumption and was never measured. It fails when an answer states a fact its question never names. *Illustration (constructed):* ask "what does the paper conclude?" at Turn 3 and "what was that figure for the Jordan frame bound?" at Turn 20. Recall cannot find Turn 3, because its **question** contains neither "Jordan" nor "bound".

1. **The answer is embedded as a second vector per Turn per Embedding Space.** The Turn is still returned whole; either vector can now reach it.
2. **This costs one embedding call per Turn and is no longer free.** §7's headline claim has to change, not only its scope. The *question* vector remains free, being the retrieval vector reused. The *answer* vector is a real vendor call on every Turn that has an answer.
3. **Both vectors are stored under `input_type="query"`.** `ConversationMemory.recall` is a single `ORDER BY distance`. Storing questions as `query` and answers as `document` would rank two non-comparable distance scales in one list, and would leave IR-446's distance cut-off impossible to set. `query` is the shared type because the question vector is the retrieval vector reused; moving questions to `document` would cost two paid calls per Turn instead of one.

**This choice is provisional.** It is a single-list shortcut, not a claim that answers are queries. If it measures badly under [ADR-023](023-retrieval-quality-evaluation.md)'s with-and-without discipline, the fallback is **two ranked lists** — questions embedded as `query`, answers as `document` — merged by rank position in the shape of IR-395's `fuse_by_rank` (not yet on `main`), which compares rank and never raw distance. That costs a second search per recall and is the reason it is not the starting point.

**Exposure, named as §Security Impact's practice requires.** Voyage now receives the text of generated answers, which it did not before. Those answers are derived only from passages that already passed the disclosure gate, and Voyage already holds the text of every chunk those passages came from, so this adds no new class of source material. It does add a new class of *input*, and §SaaS Impact's space-migration rule now covers two vectors per Turn, not one.

### §6 — unchanged, and no summary tier is authorised

**§6 stands as written.** Memory is retrieval over verbatim Turns, and its rejection of summarisation is untouched. Nothing in this amendment is an opening for a summary tier of any kind. Embedding the answer is what makes retrieval-over-Turns deliver what §6 claimed for it: before this, a Turn was findable only through the question that happened to open it.

### The verbatim window — no number here to change

§6 says only that "recent turns go into the prompt verbatim" and names no count. **This ADR contains no fixed Turn count for the window, so nothing in it changes.** The fixed count lives in code, and IR-449 replaces it with a token budget without needing an ADR amendment to do so. **IR-449 shipped on 2026-10-02** and that is what it did: `AI_HISTORY_TOKEN_BUDGET`, filled newest-first, the newest Turn always present and truncated rather than dropped, counted locally with the repository's own pinned tokenizer and no vendor call. Still nothing here changed.

### ADR-015 rule 3 — a note, not a change

[ADR-015](015-voyage-embedding-and-reranking.md) rule 3 (`embed_documents` and `embed_query` are separate methods, not a flag) is **unchanged**; this amendment adds no flag. A note under rule 3 now records that sending stored answer text through `embed_query` is deliberate, so a later reader does not "fix" it as a bug.


## Amendment — 2026-10-06 (IR-355): a followed citation keeps its Paper Chat conversation

### What was observed

With "All papers" on, a Paper Chat answer about paper X can cite paper Y. Following that citation used to replace the conversation: the paper view unmounted the panel while Y loaded, and remounted it scoped to Y. The answer the reader had just clicked disappeared, and the scope control reset to "This paper". Nothing was lost, since Back to X restored X's conversation, but the reader lost the argument they were following. This was traced from the code, not exercised live: it needs an answer citing a second indexed record, and none is indexed yet ([IR-250](https://citiris.atlassian.net/browse/IR-250)).

### §9 — the conversation owns its scope, and a citation it produced may pin it

§9's rule is unchanged: a Conversation scoped to a Record retrieves only that Record's passages unless the reader widens it, and nothing widens it silently. What this amendment adds is *which* Record a Paper Chat panel shows the conversation for.

1. **A citation followed from inside Paper Chat keeps that conversation open** while the cited paper is displayed. The panel says so ("Chatting about <X>") and offers one step back to the displayed paper's own conversation ("Chat about this paper instead"). While pinned, nothing calls X "this paper", because a reader looking at Y would take it to mean Y. The scope control names X (truncated on screen, whole in its accessible name), and so does the composer's accessible name ("Ask about <X>"). Decided with the project lead 2026-10-06.
2. **The scope belongs to the conversation, not the page.** A follow-up asked while pinned goes to X's Conversation with the widen setting it had before the click. Widening resets when the *conversation* changes, never because the page's paper changed. No question is ever answered from a scope the reader did not set.
3. **The pin holds only across navigation that originated from a citation inside the panel.** It is released, and the displayed paper's own conversation shown, on: "Chat about this paper instead"; closing and reopening the panel; reaching the paper any other way (Discover, a typed URL, an in-page link); and a reload, which leaves no panel to keep. Back to X re-aligns naturally.

   **Back and Forward restore the chat a history entry was left with** (decided with the project lead 2026-10-06). An entry reached by a Paper Chat citation carries the mark, and every other entry carries none. So Back to X re-aligns, Forward to Y re-pins X's conversation, and Back while hopping between one conversation's citations keeps that conversation. The accepted cost: a reader who chose "Chat about this paper instead" on Y, went Back and then Forward, gets X's pin again rather than Y's conversation. Rewriting history entries to remember that choice was rejected as machinery for an edge case. Releasing the pin on every Back or Forward was rejected because it drops the conversation in the middle of the citation-hopping this amendment exists to protect.

**Mechanism, for the record.** The citation link carries `origin: "paper-chat"` in router state, beside the citation it already carried for the highlight ([ADR-031](031-pdf-citation-overlay.md)). The panel holds its own subject record and moves it to the page's record on any arrival without that mark. No API, model or stored field changed: `aiApi.conversations.findOrCreateForRecord` and the existing `{ conversationId, widen }` ask path already supported asking into a conversation about another record.

### What this does not change

- **Visibility.** A pinned conversation's citations are the ones it already had, each re-resolved through `visible_to` on replay as before (§10). Pinning shows nothing the reader could not already open.
- **[ADR-019](019-persisted-unified-conversation-history.md)'s one-Conversation-per-Record model.** No Conversation is created, moved or re-scoped by a pin. The panel only chooses which existing one to show.

## Amendment — 2026-10-11 (IR-499): history per consumer, continued

**Status: Proposed, not accepted.** Drafted by an AI agent. The decision is in [ADR-038](038-bounded-research-lane-for-ask-iris.md) §7. Until a person accepts it, §13 and the 2026-10-02 and 2026-10-06 amendments stand.

| Consumer | Sees of a Conversation |
|---|---|
| Router (Jev and its `route` backup) | Prior reader questions only. No prior answer, no recalled Turn, no Passage text |
| Research planner | Recent history including prior answers. No memory-recalled Turns |
| Answering model | As §13 already allows |

* "Recent" follows the existing history window by token budget.
* A planner multi-search is subject to §3's evidence discipline: it is not a free pass to multi-query retrieval, and the aggregate context holds passages with handles, never a summary of the Conversation.
* **Prior answers are context, not evidence.** They are never cited.
* **Recorded, not solved:** prior answers are not re-gated if a cited record later becomes restricted, and the planner carries more of them. ADR-038 §12 keeps it open.
* §6 is unchanged: no summary tier is authorised.

## Alternatives Considered

**Retrieve on the raw question and give history only to the answering model.** Cheapest, and it does not fix the problem the feature exists for: retrieval still sees "what about its limitations?" and finds nothing useful, so the model writes a fluent answer from bad sources. Rejected.

**Retrieve on the question plus the last few turns concatenated.** A bounded version of today's approach. Rejected — it is the same idea currently failing, mixing a question with commentary.

**Rolling summary of older turns.** Rejected: lossy in exactly the way that hurts, since the detail a summary drops is the kind a reader later asks about.

**Fixed window of recent turns only.** The original recommendation, rejected on review as too shallow — a fact established in turn 2 is gone by turn 12, and the purpose of persisting history is defeated.

**Entity-extraction or graph-based agentic memory.** Rejected as disproportionate. Those systems target months-long personal-assistant histories; an IRIS conversation is research Q&A on a bounded topic. Current research reports the graph-free variant matching the elaborate ones anyway.

**Embedding questions and answers both.** Rejected on cost once it was clear that indexing the question and returning the whole turn preserves answer recall for free. **Reversed 2026-10-02 (IR-444):** the answer is embedded after all, because that recall was an unmeasured assumption; see §Amendment — 2026-10-02, §7.

**Storing the full Passage text in history.** Rejected — the precise leak ADR-019 exists to prevent.

**Storing record ids only, as ADR-019 literally says.** Rejected: old conversations would show citations with no quote and no page, worse than a fresh answer to the same question.

**Recognising a Retry by interpreting free text.** Rejected — asking a model, or a loose heuristic, whether a message means "do that again" turns a new question into a repeat of the old one whenever it guesses wrong, and what the reader actually typed is then never searched. An explicit control plus a short fixed phrase list fails in the harmless direction: an unrecognised retry is answered as an ordinary question.

**Reusing the retried Turn's stored citations instead of searching again.** Rejected on security, not cost. Stored citations are pointers precisely because visibility is re-checked on read (§10); serving them as a fresh answer skips the retrieval-time application of `visible_to(user)` and can quote a Record that has since become unreadable.

**Overwriting the retried Turn with the new answer.** Rejected — it destroys the record that the first answer was unsatisfactory, which is the signal retry rate and §15's feedback exist to capture, and it takes away the comparison the reader asked for.

**Leaving failed and refused Turns in the model's history.** Rejected: a refusal in the prompt biases the next attempt toward refusing again, and a failed Turn carries no content a later question could need. Cheaper to exclude than to mitigate.

**A separate classifier call for the multi-part flag.** Rejected — it doubles the per-question classification cost to answer a question the routing classifier is already being asked, and two independent calls can disagree about the same question.

**Feedback readable by staff, or by anyone but the owner.** Rejected outright. §11 excludes staff from a Conversation deliberately; a feedback table holding question and answer text would reinstate exactly the exposure §11 refuses, through a side door, and a reader clicking "this was bad" has consented to nothing of the kind.

**Feedback as a ranking input.** Rejected — a few votes over a small corpus would move ranking in ways no [ADR-023](023-retrieval-quality-evaluation.md) measurement could separate from a retrieval change, and it is trivially gameable.

**Migrating existing browser-local conversations.** Rejected. They are demo and testing conversations against a corpus of 4,910 stub files; migration code for data with no value is cost without benefit. The sidebar emptying is surfaced with a notice rather than left unexplained.

**Widening or replacing the back-reference word list (added 2026-10-02, IR-444).** Rejected. The observed failure contained no referring word at all, so no list reaches it, and every list is incomplete in the cases a reader actually reaches for. A cheaper check that fails *silently and into a refusal* is not cheaper than a cached small-model call that cannot miss.

**Overflow-triggered summarisation of older Turns (added 2026-10-02, IR-444).** Rejected, with the call count against the token size as the reasoning. A summary reduces tokens *per call* and adds a model call of its own, while the cost concern on this path is the *number* of calls. The history handed to the model is already hard-bounded at the source (a token budget in `apps/ai/history.py` since IR-449; `MAX_HISTORY_TURNS` when this was written), so an overflow trigger would never fire. It also fails §6's objection unchanged: the detail a summary drops is the detail a reader later asks about. The bounded-prompt benefit worth having comes from IR-449's token budget, which costs zero model calls.

## Decision Rationale

The through-line is that **the expensive, elaborate options are not the good ones here**. Rewriting is mandatory and cheap. Memory-by-retrieval is stronger than summarisation *and* simpler. The question's memory vector is free because it already exists (the answer's, added 2026-10-02, is not). Multi-query is the one genuinely promising technique being held back, and it is held back for the reason ADR-023 was written to enforce — there is no measurement yet, and a small corpus plus an existing reranker makes its benefit here genuinely uncertain.

## Consequences

- The 2,000-character question limit stops being load-bearing and is retained as a plain abuse guard. The conversations it currently breaks past ~five turns are fixed as a side effect; this should be reported as a fix, not left silent.
- A second, smaller model must be configurable for rewriting. Only one inference model is configured today.
- Turns carry two vectors since 2026-10-02 (question and answer), each under the active Embedding Space, with the same cross-space hazards — a vector stored under a retired space must never be compared against a current one.
- A new object-level permission surface, as ADR-019 anticipated, now with an explicit staff exclusion.
- Frontend chat storage is retired; the local conversation shape and its question-concatenation helper go with it.
- Each enhancement technique must be independently switchable, or ADR-023's comparison cannot be run.

## MVP Impact

Not MVP-required; ADR-001's Semester 2 boundary stands. This is current-phase RAG work, thesis-critical per ADR-013's amendment.

## SaaS Impact

Conversation data is per-instance under [ADR-005](005-instance-per-tenant.md). Memory vectors (two per Turn since 2026-10-02, question and answer) live in the same Embedding Space as the corpus, so a space migration must re-embed turns or drop their vectors — a conversation whose vectors are dropped degrades to recent-turns-only, which is acceptable and must not be silent.

## Security Impact

Three positions, deliberately recorded:

**A transcript is sensitive in itself.** Owner-only, staff excluded, no automatic expiry, user-initiated delete.

**Stored citations are pointers, never text.** ADR-019's guarantee, re-expressed against the predicate IRIS actually uses.

**Embedding turns adds no new exposure class, but does increase footprint.** A question is already sent to the vendor on every search, and an answer contains only passages that already passed the disclosure gate to be generated. What changes is that these vectors are now *stored* rather than computed and dropped. That is a conscious trade and is named here rather than buried in a ticket. **Amended 2026-10-02 (IR-444):** answer text is now also sent to Voyage for embedding — a new class of input, though derived only from gated passages; see §Amendment — 2026-10-02, §7.

## Deployment Impact

None. No new services. One additional model configuration.

## Research Impact

Substantial, and this is the part worth defending. A system that answers follow-up questions correctly demonstrates the RAG contribution more strongly than one answering only isolated questions. More importantly, putting each enhancement technique behind its own switch makes **retrieval quality with and without each technique measurable** under ADR-023 — which is the difference between a defensible finding and a list of features.

The deferral of multi-query is itself a recorded research position: a technique with published gains was not adopted because the conditions that produce those gains are absent here and no local measurement exists yet.

## Related Requirements

Conversational memory and history, as named in ADR-019 — unlabeled by an FR- id, per the frozen-SRS rule.

## Related Tasks

IR-283, IR-284 (citation objects and the visibility predicate this depends on), IR-278 and ADR-023 (the corpus and measurement that gate multi-query), IR-243 (same deferral discipline). **IR-392** adds §12-§15 and closes §2's open question; **IR-398** (Retry), **IR-399** (multi-part questions) and **IR-401** (reader feedback) build them, all under IR-390. **IR-444** amends §7 and §8 and notes ADR-015 rule 3; the code follows under IR-443 — **IR-445** (resolution on every follow-up), **IR-446** (recall distance cut-off), **IR-447** (answer vector), **IR-448** (failed and refused Turns leave history) and **IR-449** (token-budget window).
