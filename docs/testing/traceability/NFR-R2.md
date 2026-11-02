# NFR-R2

[Back to the matrix](../TRACEABILITY.md)

## NFR-R2

**Requirement:** Graceful degradation

**Implementation:** **IR-132** added the fallback itself: `apps/ai/retrieval/degraded.py` catches an open circuit or a spent rate-limit budget and searches chunks with PostgreSQL FTS through the *same* `visible_to` predicate as the vector path (ADR-008).

**IR-279** makes the other half of ADR-008's promise real — that a reader is *told* when the answer came from the fallback. The flag rode on a `list` subclass, chosen so callers could iterate unchanged; `RerankingRetriever` built an ordinary list from those results and the subclass went with it, so `GroundedAnswerService`'s `getattr(retrieved, "degraded", False)` was false whenever a decorator sat in the stack — which is always. The seam now returns a frozen `RetrievalResult` carrying passages, `degraded`, `mode` and `embedding_space_id`; a decorator calls `with_passages()`, so carrying everything forward is the default and dropping it is effortful. Neither mistake can pass silently now: a decorator returning a bare list gives the next reader an `AttributeError` on `.degraded`, and a caller treating a result as a list gets a `TypeError` — a failure at the seam rather than a `False` in the UI.

**Evidence:** `apps/ai/retrieval/tests/test_degradation_crosses_the_seam.py` — a `CircuitOpen` injected beneath the **full** chain (reranking over degradation, the real `FullTextRetriever`, real rows) is still marked degraded at the top, a healthy vendor is not, and `mode`/`embedding_space_id` survive too. Its second half enumerates every decorator in the package and asserts each carries the flag, with a guard test that fails when a new `Retriever` subclass is neither classified as a decorator nor as a source — so a future decorator cannot join the stack untested — and `SOURCES` membership is itself checked, by constructor signature, so filing a decorator there cannot silence the guard. Its stated limits: it sees `Retriever` subclasses under `apps/ai/retrieval/` only, so a decorator defined in another package or duck-typing the port is invisible. Four existing test suites had assertions rewritten from the list shape to `.passages` — deliberately, no assertion weakened; `test_the_degraded_result_needs_no_special_case_from_a_caller` was rewritten outright and renamed, since what it asserted (`isinstance(results, list)`) was the defect. Full backend suite green (1086 passed, 2 skipped, 1 xfailed, 2026-09-19).

**Status:** **IMPLEMENTED** — **IR-283 closed the last hop**: `degraded` is a field on the `/ai/ask/` and `/ai/search/` responses, asserted through the HTTP layer with a `CircuitOpen` injected beneath the full stack (`test_ask_http.py::DegradationTests`), and `RAGChatPage` says so to the reader. Not VERIFIED: the fallback has never run against a real vendor outage, only an injected one
