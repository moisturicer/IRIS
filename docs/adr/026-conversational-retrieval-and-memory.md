# ADR-026: Conversational retrieval — question rewriting, and memory by retrieval rather than summary

## Status

**Accepted** — 2026-09-17.

**Implements and amends [ADR-019](019-persisted-unified-conversation-history.md).** ADR-019 decided *that* conversation history is persisted and unified across Ask IRIS and Paper Chat, and that decision stands unchanged. It deliberately left *how* history reaches retrieval unspecified, and its citation-storage mechanics have been overtaken by work completed since. This ADR settles the first and amends the second.

**Depends on [ADR-023](023-retrieval-quality-evaluation.md)** for why one technique here is adopted and two are deferred.

**Amended — 2026-09-28 (IR-392), under [ADR-013](013-chunk-level-rag-pipeline.md)'s thesis-critical RAG scope.** Four additions, all reader-facing: §12 Retry, §13 what the model is allowed to see of a Conversation's own failures, §14 where the multi-part flag of §2 comes from — which **closes the open question §2 left**, explicitly rather than by quiet insertion — and §15 feedback privacy as an addition to §11. The vocabulary for **Retry**, **Reader feedback** and a **Listing question** is `CONTEXT.md`; the listing routing outcome those questions reach is in [ADR-027](027-corpus-level-questions.md) §9.

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

### 7. Only questions are embedded, and their vectors cost nothing extra

**A turn is indexed by its question and returned whole.** Answer recall is preserved without embedding answers, because a question and its answer are a pair.

The cost property that makes this free: **the memory vector and the search vector are the same vector.** Every question is already embedded to search the corpus; that result is stored on the turn instead of discarded. Remembering a user's questions indefinitely costs zero additional vendor calls.

Embedding answers would be a genuine extra call on every turn, for recall that indexing questions already provides.

### 8. A turn adds no cost unless it actually needs rewriting

The rewrite is the only new per-turn cost, and it is avoided wherever it does nothing:

- **Skipped on the first turn** — there is no history to resolve against.
- **Skipped when the question carries no back-reference**, decided by a cheap word check rather than a model call. The failure is soft: a missed back-reference retrieves on the raw question, exactly as today.
- **Performed by a small model**, configured separately from the answering model. Rewriting is an easy task and does not need the model that writes answers.
- **Cached**, keyed like query embeddings already are — same question and same history yield the same rewrite.

Most turns therefore cost what they cost today.

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


## Alternatives Considered

**Retrieve on the raw question and give history only to the answering model.** Cheapest, and it does not fix the problem the feature exists for: retrieval still sees "what about its limitations?" and finds nothing useful, so the model writes a fluent answer from bad sources. Rejected.

**Retrieve on the question plus the last few turns concatenated.** A bounded version of today's approach. Rejected — it is the same idea currently failing, mixing a question with commentary.

**Rolling summary of older turns.** Rejected: lossy in exactly the way that hurts, since the detail a summary drops is the kind a reader later asks about.

**Fixed window of recent turns only.** The original recommendation, rejected on review as too shallow — a fact established in turn 2 is gone by turn 12, and the purpose of persisting history is defeated.

**Entity-extraction or graph-based agentic memory.** Rejected as disproportionate. Those systems target months-long personal-assistant histories; an IRIS conversation is research Q&A on a bounded topic. Current research reports the graph-free variant matching the elaborate ones anyway.

**Embedding questions and answers both.** Rejected on cost once it was clear that indexing the question and returning the whole turn preserves answer recall for free.

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

## Decision Rationale

The through-line is that **the expensive, elaborate options are not the good ones here**. Rewriting is mandatory and cheap. Memory-by-retrieval is stronger than summarisation *and* simpler. The memory vector is free because it already exists. Multi-query is the one genuinely promising technique being held back, and it is held back for the reason ADR-023 was written to enforce — there is no measurement yet, and a small corpus plus an existing reranker makes its benefit here genuinely uncertain.

## Consequences

- The 2,000-character question limit stops being load-bearing and is retained as a plain abuse guard. The conversations it currently breaks past ~five turns are fixed as a side effect; this should be reported as a fix, not left silent.
- A second, smaller model must be configurable for rewriting. Only one inference model is configured today.
- Turns carry a vector, under the active Embedding Space, with the same cross-space hazards — a vector stored under a retired space must never be compared against a current one.
- A new object-level permission surface, as ADR-019 anticipated, now with an explicit staff exclusion.
- Frontend chat storage is retired; the local conversation shape and its question-concatenation helper go with it.
- Each enhancement technique must be independently switchable, or ADR-023's comparison cannot be run.

## MVP Impact

Not MVP-required; ADR-001's Semester 2 boundary stands. This is current-phase RAG work, thesis-critical per ADR-013's amendment.

## SaaS Impact

Conversation data is per-instance under [ADR-005](005-instance-per-tenant.md). Memory vectors live in the same Embedding Space as the corpus, so a space migration must re-embed turns or drop their vectors — a conversation whose vectors are dropped degrades to recent-turns-only, which is acceptable and must not be silent.

## Security Impact

Three positions, deliberately recorded:

**A transcript is sensitive in itself.** Owner-only, staff excluded, no automatic expiry, user-initiated delete.

**Stored citations are pointers, never text.** ADR-019's guarantee, re-expressed against the predicate IRIS actually uses.

**Embedding turns adds no new exposure class, but does increase footprint.** A question is already sent to the vendor on every search, and an answer contains only passages that already passed the disclosure gate to be generated. What changes is that these vectors are now *stored* rather than computed and dropped. That is a conscious trade and is named here rather than buried in a ticket.

## Deployment Impact

None. No new services. One additional model configuration.

## Research Impact

Substantial, and this is the part worth defending. A system that answers follow-up questions correctly demonstrates the RAG contribution more strongly than one answering only isolated questions. More importantly, putting each enhancement technique behind its own switch makes **retrieval quality with and without each technique measurable** under ADR-023 — which is the difference between a defensible finding and a list of features.

The deferral of multi-query is itself a recorded research position: a technique with published gains was not adopted because the conditions that produce those gains are absent here and no local measurement exists yet.

## Related Requirements

Conversational memory and history, as named in ADR-019 — unlabeled by an FR- id, per the frozen-SRS rule.

## Related Tasks

IR-283, IR-284 (citation objects and the visibility predicate this depends on), IR-278 and ADR-023 (the corpus and measurement that gate multi-query), IR-243 (same deferral discipline). **IR-392** adds §12-§15 and closes §2's open question; **IR-398** (Retry), **IR-399** (multi-part questions) and **IR-401** (reader feedback) build them, all under IR-390.
