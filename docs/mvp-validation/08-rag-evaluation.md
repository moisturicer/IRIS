# 08 — RAG Evaluation

**Lightweight by design.** RAG is a supporting capability, not the thesis contribution ([ADR-003](../adr/003-clearance-aware-resubmission.md)). This is a fitness check, not an AI benchmark.

**Conditional.** `R-04` is timeboxed to 3 dev-days ending Week 6, with a pre-committed fallback to semantic-search-only ([ADR-006](../adr/006-minimum-rag-pipeline.md)). If generation does not ship, sections 3–5 below are reported as Phase 2 and only sections 1–2 and 6 run.

**Consumes no respondent time.** Everything here is scripted and run by the team, which is why it can be thorough without competing with the workflow evaluation for the scarce 6–12 participants.

---

## Why not a full benchmark

Rejected: RAGAS, TruLens, large golden-answer sets, LLM-as-judge pipelines. All are defensible for a system whose contribution *is* the RAG pipeline. Here they would cost days, need their own validation, and evidence a capability the thesis explicitly does not claim.

What is needed is enough evidence to state: *the supporting capability works, is permission-safe, does not fabricate, and fails visibly.* Six checks do that.

---

## 1 · Retrieval relevance

**Question:** does semantic search return the right documents?

**Method.** A fixed set of **20 queries** written against the actual indexed corpus before any results are seen. For each, a team member records the document(s) they expect in the top 5. Judgements are made **before** running the system, and are recorded — otherwise the evaluation drifts into confirming whatever the system returned.

| Query type | Count | Example shape |
|---|---|---|
| Topic | 8 | *"machine learning for crop disease detection"* |
| Author or group | 3 | *"research by the College of Engineering on solar"* |
| Method | 4 | *"studies using survey methodology"* |
| Application domain | 5 | *"blockchain in academic credentialing"* |

**Metric.** Proportion of queries where an expected document appears in the top 5.

**Target: ≥ 80%.** An internal design target on a fixed internal query set — **not** a benchmark claim and not comparable to published IR figures.

**Also record:** rank of the first expected document; queries returning nothing; queries where every result is irrelevant.

---

## 2 · Permission safety — **hard fail**

**Question:** can a user receive a result or citation for a record they are not permitted to see?

This is the most important check in this document. Retrieval that ignores visibility is a bypass around every access control in [ADR-009](../adr/009-authorization-model.md) — the vector index does not know about `Record.pipeline_status` or ownership unless it is told.

**Method.** Seed the corpus with a record that is (a) unpublished, (b) owned by user X, and (c) contains a distinctive phrase appearing nowhere else. Log in as user Y — a Student with no relationship to it — and query for that phrase directly.

Repeat for: a draft record · a record in `parallel_review` · a `rejected` record · a soft-deleted record.

**Metric.** Count of leaked results or citations.

**Target: exactly 0. Any leak is a hard fail** and blocks the RAG feature from the pilot until fixed, regardless of every other result here.

---

## 3 · Groundedness

**Question:** are answers supported by retrieved content, and does the system refuse when it has none?

**Method.** 20 questions in three classes, scored by a team member against a rubric:

| Class | Count | Expected behaviour |
|---|---|---|
| **A — Answerable** | 10 | Answer supported by at least one retrieved record |
| **B — Plausible but absent** | 5 | Explicit "not found in the repository" |
| **C — Adversarial** | 5 | Explicit refusal. *e.g. "Summarise the 2019 study on X"* where no such record exists |

**Rubric per answer:**

| Score | Meaning |
|---|---|
| 2 | Every factual claim traceable to a retrieved record |
| 1 | Mostly supported; one unsupported detail |
| 0 | Contains a claim absent from retrieved content, or fabricates a record |

**Targets.** Class A: ≥ 90% scoring 2 or 1. **Classes B and C: 100% explicit non-answer — any fabrication is a hard fail.**

A confident fabrication about a research record in a research-integrity system is worse than no answer at all. This is the one quality dimension with no tolerance.

---

## 4 · Citation correctness

**Question:** do citations resolve, are they relevant, and are they permitted?

Using the same 20 questions:

| Metric | Target |
|---|---|
| Citations resolving to an existing record | **100%** |
| Citations to records the asker may see | **100% — hard fail otherwise** |
| Citations judged relevant to the answer | ≥ 90% |
| Answers with a factual claim and no citation | 0 |

Citations are the reviewer-auditability mechanism the SRS promises. A dangling or impermissible citation is worse than none, because it invites trust.

---

## 5 · Latency

**Question:** is response time acceptable?

**Method.** `NFR-P3`'s own procedure — 20 consecutive representative queries against the deployed system, p95 computed.

**Break the measurement down** — query embedding, retrieval, generation — so the bottleneck is evidenced rather than assumed.

| Measure | Target |
|---|---|
| Retrieval only (p95) | < 200 ms |
| End-to-end, complete answer (p95) | **Amended NFR-P3 target** |
| Time to first token, if streaming | ≤ 3 s |

> **NFR-P3 as written requires a 3-second p95 for a *complete* response.** A single LLM round-trip is typically 3–10 s. **The requirement is not achievable as specified.** It should be amended to time-to-first-token ≤ 3 s with complete response ≤ 15 s p95, or restated. **NEEDS ADVISER CONFIRMATION** — tracked in [14](14-adviser-review.md).
>
> Run this measurement **early**, in Week 7 if possible. The result is the evidence the amendment needs.

---

## 6 · Graceful failure

**Question:** does the system degrade rather than break?

Per [ADR-008](../adr/008-ai-degradation-to-fts.md), each failure is induced deliberately and the behaviour recorded.

| Induced failure | How | Expected | Pass? |
|---|---|---|---|
| Embedding provider unreachable | Point config at a closed port | Falls back to FTS; visible banner | ☐ |
| LLM provider unreachable | Same | Retrieval still returns records; explicit "AI unavailable"; **no fabricated answer** | ☐ |
| Provider timeout | Introduce delay | Bounded ~30 s, then 503 | ☐ |
| pgvector retrieval error | Break the query path | Falls back to FTS | ☐ |
| Celery / Redis down | Stop the containers | **Submission and every workflow transition still succeed** | ☐ |
| Rate limit / credit exhausted | Simulate 429 | As unavailable, with a distinct operator log | ☐ |

**The Celery/Redis row is the important one.** It proves the thesis contribution has no AI dependency — the workflow must be completely unaffected by every AI component being down.

**Also record:** is the degraded state *visible*? A silent fallback is a fail. Users who believe semantic search is working while receiving keyword results would contaminate usability data.

**This is demonstrated deliberately during system testing**, and is a stronger defence answer than a feature that happened to work on the day.

---

## Reporting

One table in the evaluation chapter:

| Check | Metric | Target | Result | Verdict |
|---|---|---|---|---|
| Retrieval relevance | Expected doc in top 5 | ≥ 80% | | |
| **Permission safety** | Leaks | **0** | | |
| Groundedness A | Score ≥ 1 | ≥ 90% | | |
| **Groundedness B/C** | Explicit non-answer | **100%** | | |
| Citation resolution | Resolve | 100% | | |
| **Citation permission** | Permitted | **100%** | | |
| Citation relevance | Judged relevant | ≥ 90% | | |
| Latency | p95 | Amended NFR-P3 | | |
| Degradation | Modes passing | 6 / 6 | | |

**Stated limitations:** single evaluator per judgement, so no inter-rater reliability · a fixed 20-query set is not a benchmark · relevance and groundedness judged by the system's authors, which is a bias mitigated only by pre-registering expectations before running.

---

## Effort

Roughly **1 dev-day total** — query set and judgements (2 h), scripted runs (2 h), degradation induction (2 h), write-up (2 h). Reasonable for a supporting capability, and it consumes none of the workflow evaluation's participant budget.

---

## If `R-04` misses its timebox

Per [ADR-006](../adr/006-minimum-rag-pipeline.md), semantic search ships without generation. Then:

- **Run:** sections 1 (relevance), 2 (permission safety), 5 (retrieval latency), 6 (degradation)
- **Report as Phase 2:** sections 3 (groundedness) and 4 (citations)
- **State plainly** that generation was descoped, with the reason and the evidence — a timeboxed decision recorded in advance is a defensible engineering choice, not a failure
