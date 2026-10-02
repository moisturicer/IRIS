# ADR-033: Hybrid retrieval and passage selection

## Status

**Accepted** — 2026-09-28 (IR-391, under the IR-390 spec *Hybrid retrieval, passage selection and measured RAG quality*).

**Amends [ADR-008](008-ai-degradation-to-fts.md)** — full-text search keeps its outage-fallback job and gains a second one, as a retrieval signal on the normal path. See that file's IR-391 amendment.

**Amends [ADR-023](023-retrieval-quality-evaluation.md)** (`023-retrieval-quality-evaluation.md`, not `023-migrate-on-container-boot.md`) — the harness's label format, its two measures, and how a run is conducted. See that file's IR-391 amendment.

**Extends [ADR-013](013-chunk-level-rag-pipeline.md)** (the chunk is the retrievable unit) and [ADR-015](015-voyage-embedding-and-reranking.md) (Voyage embedding and reranking, both stages). Neither is superseded.

**Applies [ADR-026](026-conversational-retrieval-and-memory.md) §3's evidence discipline** — a technique is adopted on a measurement, not on reputation.

**Note added — 2026-10-02 (IR-453): §5's gating rule cannot be satisfied for §3's cut-off, and §5 is deliberately unchanged.** See §Divergence — IR-453 below. §3 also acquires a dependant: [ADR-034](034-ungrounded-answers-as-a-distinct-state.md) makes an ungrounded answer reachable only when the cut-off returns nothing, so §3 is what makes that state detectable at all.

> **ADR references in this file are by filename.** `docs/adr/` currently holds two files claiming 021 and two claiming 023, so a bare number is ambiguous. The collision is tracked as IR-403 and is not resolved here.

## Context

Everything between a question arriving and a prompt being assembled is currently undecided in writing. The code makes choices — `apps/ai/retrieval/two_stage.py` retrieves by vector and `reranking.py` reorders the candidates, `degraded.py` searches chunks with PostgreSQL FTS only while the vendor is down — and no ADR says why retrieval is vector-only on the healthy path, what happens when nothing retrieved is actually relevant, or how the passages that survive reranking are chosen for the prompt.

Three concrete gaps forced this record:

- **Vector-only retrieval misses the queries a repository gets most.** An exact identifier, a surname, an instrument name or an uncommon acronym is precisely what a dense embedding blurs. FTS already searches chunks in this codebase — `FullTextRetriever` exists and is visibility-correct — but is reachable only through a failure path.
- **Nothing decides "no relevant sources".** Retrieval always returns its top *k*, so a question the corpus cannot answer produces confident prose over the least-bad passages. That is the failure mode a citation-grounded system exists to avoid.
- **Passages reach the prompt by truncation.** There is no per-paper cap, no joining of adjacent chunks, and no token budget, so one verbose paper can occupy the whole context and a passage split across a chunk boundary arrives halved.

`FullTextRetriever` also documents why chunks have no stored search vector: it builds one at query time because the path "runs only while the vendor is down". Putting FTS on the normal path invalidates that reasoning, which is the second half of this decision.

## Decision

### 1. Retrieval is hybrid: keyword and vector, merged by rank

Every question runs **two independent searches over the whole visible catalogue of passages** — dense vector search, and keyword search over the stored chunk keyword index — and their result lists are merged **by rank position** before reranking. The merged list is the reranker's candidate set; reranking and everything after it are unchanged.

Keyword search is **not** restricted to the vector candidates. A passage the vector search never surfaced is exactly the case hybrid retrieval exists to catch.

Visibility is applied inside each search, through the single `visible_to(user)` predicate, before anything is scored or merged. Hybrid retrieval adds a second source of candidates, never a second visibility rule.

### 2. The chunk keyword index is a stored column the database maintains

A `DocumentChunk` carries a stored, indexed search vector, populated and kept current **by the database** — a generated column or a trigger, with its own GIN index — not by application code on save.

### 3. The relevance cut-off is a setting, applied to reranker scores only

A minimum relevance score is configurable. Passages scoring below it are dropped, and when nothing survives the reader is told no relevant sources were found rather than given an answer.

- It is applied to **reranker scores only**. Vector distances and FTS ranks are not comparable across queries and carry no calibrated notion of "relevant".
- It is therefore **absent in degraded mode**: with the vendor unreachable there is no reranker and no score to threshold, and inventing one from FTS ranks would make the threshold mean something different depending on whether Voyage was up.
- The score is **never shown to a reader**. It is an engineering control, not a confidence figure, and displaying it invites exactly the over-reading it cannot support.

### 4. Passages are selected, not truncated

Between reranking and the prompt sits an explicit selection step:

- **A per-paper cap** on how many passages one Record may contribute, so a single verbose paper cannot crowd out the rest of the corpus. The cap is **ignored in Paper Chat**, where every passage legitimately comes from one paper.
- **Neighbour joining.** Adjacent chunks of the same document that both survive are joined into one passage. The joined passage **keeps every constituent chunk's regions** — they are what the PDF overlay highlights under `031-pdf-citation-overlay.md` — and **cites the first page** of the joined span.
- **A token budget** for the assembled passage set, measured with the same real tokenizer the chunker uses (`apps/ai/chunking/tokens.py`), so the budget is in the unit it claims to be in.

### 5. Every technique here ships off, and is switched on only once a harness run shows it helps

Fusion, the keyword index's participation in retrieval, the relevance cut-off, the per-paper cap, neighbour joining and the token budget each land behind a setting, **defaulting to the current behaviour**. A default is changed only when a run of the `023-retrieval-quality-evaluation.md` harness, one change at a time against a fixed baseline, shows the change helps.

This is [ADR-026](026-conversational-retrieval-and-memory.md) §3's discipline applied to a second batch of techniques: adopting them on the strength of their general reputation would be taste presented as evidence, and these are cheap to leave off.

## Divergence — 2026-10-02 (IR-453): the harness cannot measure the cut-off's benefit

**Recorded, not reconciled.** `CLAUDE.md`'s source-of-truth rule requires a
contradiction between an ADR and the code to be written down rather than quietly
resolved. This is one, found while scoping IR-396.

§5 says a default moves only when a harness run *"shows the change helps."* For
§1's fusion that worked exactly as intended: IR-395 measured +0.192 recall@10
with reranking and still shipped off, and IR-402 has a number to act on. **For
§3's relevance cut-off the same rule is unsatisfiable**, for a structural reason:

* Both harness measures are **recall** measures — recall@10 over what retrieval
  returned, and recall over the final set the model received
  (`023-retrieval-quality-evaluation.md` §Amendment).
* A relevance cut-off can only ever **remove** passages.
* Every question in both committed question sets —
  `apps/ai/evaluation/fixtures/synthetic_set.json` (2) and
  `docs/evaluation/proxy_starter.json` (52) — **is answerable**; not one has an
  empty expected-passage list. Verified 2026-10-02.

So any cut-off above zero scores at or below baseline on both numbers, by
construction. A run can report what the floor **costs** and can never report what
it **buys**, because "correctly refused a question the corpus cannot answer" is
not a question in the set and not a figure in the report. A floor's entire
purpose is invisible to the instrument meant to justify it.

**What is done about it.**

1. **§5 is unchanged, and the cut-off still ships off.** The rule's value is that
   it is absolute; carving out the one technique whose benefit cannot be measured
   would be the weakest possible exemption to grant. The default still moves only
   at IR-402.
2. **The provisional default comes from observation, not from a run** — the
   method `026-conversational-retrieval-and-memory.md` §3 permits when a number
   cannot be had honestly, and the one IR-446 already chose for the parallel
   cut-off on conversational memory: print reranker scores for questions a human
   agrees are relevant against ones that are not, pick a value separating them,
   and record the observed numbers in the PR. If they do not separate cleanly,
   say so and ship a deliberately loose default rather than a confident one.
3. **The instrument is extended as its own ticket — IR-454**, not folded into IR-396:
   unanswerable questions with empty expected sets, and a correct-refusal measure
   alongside the two recall measures, so §5's rule becomes satisfiable for §3 and
   for §4's selection. Until then the gap above is the honest state of the
   evidence.

**Why not simply tune the floor by taste in the meantime.** Because that is the
failure `026` §3 named, and a cut-off set too high is this ADR's own recorded
risk — *"a silent, reader-invisible regression, since the score is never
displayed."* Observation with the numbers written down is weaker than a run and
stronger than taste, and it is labelled as the middle thing it is.

## Alternatives Considered

**Keyword search restricted to the vector candidates** — run the vector search, then keyword-match within its top *n*. Rejected. It cannot surface a passage the vector search missed, which is the entire failure hybrid retrieval addresses. It buys a smaller keyword query in exchange for the only benefit on offer.

**Score normalisation instead of rank merging** — scale vector distances and FTS ranks onto a common range and add them. Rejected. The two scores have different distributions, and both shift with the query, so any normalisation constant is fitted to the queries it was chosen on. Merging by rank position needs no such constant, and the reranker — a model trained for exactly this — does the real relevance judgement afterwards, so precision lost in the merge is recoverable.

**An application-maintained keyword column** — populate the chunk search vector in a `save()` override or a signal, as `records/signals.py` does for `Record.search_vector`. Rejected. Chunks are written in bulk by the ingestion pipeline and swapped wholesale by `apps/ai/repositories.py`; a hook on instance save is silently skipped by exactly those paths, and the index would be stale on the only writes that matter. The database maintaining it makes staleness impossible rather than unlikely.

**A hardcoded cut-off.** Rejected. The right value depends on the reranker model and the corpus, neither of which is fixed, and the value has to be tuned by harness runs — which means it has to be changeable without a code change.

**A query-time reference-list filter** — detect bibliography passages when answering and drop them. Rejected here, twice over: it pays the cost on every question for a problem that belongs to ingestion (front matter and reference sections are a chunking-policy question under `013-chunk-level-rag-pipeline.md`), and a heuristic that guesses "this looks like a reference list" will also discard a genuine related-work discussion, which is a legitimate answer to a legitimate question.

**Leave retrieval vector-only and rely on reranking.** Rejected. Reranking reorders candidates; it cannot recover a passage retrieval never returned. An exact-token query that the dense embedding blurs never reaches the reranker at all.

## Decision Rationale

The two halves reinforce each other. Hybrid retrieval widens what reaches the reranker; the cut-off and selection narrow what leaves it. Widening without narrowing produces longer, worse prompts, and narrowing without widening cuts from a candidate set that was missing the right passage to begin with.

Everything shipping off is what makes this affordable to be wrong about. The expensive mistake in RAG work is a stack of plausible techniques switched on together, where no one can say which one helped and removing any of them is a gamble. One setting per technique, one harness run per change, and the default only moves on a number.

FTS earning a second job is the cheapest of the changes: the retriever, the visibility predicate and the tests already exist, and the only new asset is a stored column the database keeps current.

## Consequences

- **Positive.** Exact-term queries work. A question the corpus cannot answer is answerable with "nothing relevant" instead of a guess. One paper cannot monopolise the prompt. A passage split across a chunk boundary arrives whole, still highlightable, citing a page a reader can open.
- **Negative.** More moving parts on the hot path, and six settings whose defaults are only justified once a harness run exists. Until then the system behaves as it does today — which is the point of the off-by-default rule, not a workaround for it.
- A chunk migration and a database-maintained index are added; `apps/ai/retrieval/degraded.py`'s query-time `SearchVector` becomes redundant on both paths and its docstring's reasoning is superseded by §2.
- **Risk.** A cut-off set too high turns answerable questions into "nothing relevant" — a silent, reader-invisible regression, since the score is never displayed. The harness's recall-over-the-final-set measure (`023-retrieval-quality-evaluation.md` §Amendment, IR-391) exists to catch exactly this, and is the reason that second measure is mandatory rather than nice to have.
- **Risk.** Neighbour joining changes what a citation points at. It keeps every region and cites the first page precisely so the overlay contract in `031-pdf-citation-overlay.md` still holds.

## MVP Impact

No scope change. It refines a path that already exists and is already MVP. Every technique is inert until switched on, so an unfinished item here degrades to today's behaviour rather than to a broken one.

## SaaS Impact

Per-instance under `005-instance-per-tenant.md`. The settings are per-deployment, and a cut-off tuned on one institution's corpus does not transfer to another's — the same non-transferability `023-retrieval-quality-evaluation.md` §SaaS Impact already records for recall.

## Security Impact

**Neutral by construction, and the one thing that must not slip.** Both searches filter by `visible_to(user)` inside retrieval, before scoring or merging, so a fused candidate list cannot contain a passage the asker may not read. Hybrid retrieval adds a second candidate source and **no** second visibility predicate — the rule `CLAUDE.md` states and IR-285 enforced by deleting the alternative. A joined passage spans chunks of one document, so joining cannot merge across visibility boundaries.

No new outbound data: the keyword search is local, and the reranker already receives the candidate passages under `015-voyage-embedding-and-reranking.md`'s disclosure gate.

## Deployment Impact

One migration (the stored chunk keyword column and its index). No new service, no new vendor, no new credential.

## Research Impact

Thesis-critical under `013-chunk-level-rag-pipeline.md` §Research Impact (amended 2026-09-04). §5 is the part that matters for the write-up: each technique is a measured switch with a before and an after on a fixed baseline, so the RAG chapter can report which techniques helped on this corpus and which did not. A technique that did not help is a finding and is reported as one, not quietly deleted.

Results from the proxy corpus decide engineering switches and are **never** cited as findings about CIT-U research — `023-retrieval-quality-evaluation.md`'s two tiers, restated there by the IR-391 amendment.

## Related Requirements

FR-M3-02 (semantic indexing) · FR-M4-01 (RAG chatbot) · NFR-R2 (graceful degradation) — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-390 (parent spec) · IR-391 (this ADR) · IR-393 (chunk keyword index) · IR-394 (harness measures what the model received) · IR-396 (nothing-relevant answer) · IR-397 (passage selection) · IR-402 (moves the defaults) · IR-454 (makes §5's rule satisfiable for §3 and §4 — see the divergence note) · IR-453 / [ADR-034](034-ungrounded-answers-as-a-distinct-state.md) (the ungrounded state §3 makes detectable, and the divergence note above).
