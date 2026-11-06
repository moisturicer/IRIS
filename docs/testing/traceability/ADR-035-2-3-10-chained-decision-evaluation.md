# ADR-035-2-3-10-chained-decision-evaluation

[Back to the matrix](../TRACEABILITY.md)

## ADR-035 §2 · §3 · §10 (chained decision evaluation)

**Requirement:** **The proposed decision chain can be scored offline** — no FR- id; ADR-035 as amended by IR-487 (pending approval). IR-486 under [IR-484](https://citiris.atlassian.net/browse/IR-484)

**Design:** IR-484 §Intended design (rules, detector, Jev bands, LLM confirmation of direct candidates, LLM alone on Jev failure) · ADR-035 §10 (curated instrument supplies accuracy; no operating point chosen)

**Implementation:** `apps/ai/evaluation/chain.py` (pure) and `eval_evidence --chain`: eight arms over stored or freshly collected decider runs; two band parameters (uncertain band searches); missed searches first, ambiguous apart, stable vs flaky misses, rescue and shared misses, calibration (reliability, Brier), failure/timeout/rate-limit/fallback rates, latency and cost per decision; a replicate over 5% fallbacks reported alone; Jev failure simulated by forcing it; raw-vs-Resolved ablations. `ModelDecision.cost_usd` records the vendor's usage cost when reported (omitted from `as_dict` when absent, so shadow rows are unchanged)

**Test:** `evaluation/tests/test_chain.py` (45 — the §5.1 decision table row by row, a model never turns a rule search direct, pooling, stable/flaky, calibration, an import-boundary test, and **re-scoring the stored IR-481/IR-482 runs reproduces proposal 12 §4's band and rescue tables**) · `tests/test_eval_evidence_chain_command.py` (14 + 1 DB-gated: stored replay, live fakes, ablation, refusals, no Conversation/Turn)

**Evidence:** `pytest apps/ai/evaluation apps/ai/evidence apps/ai/tests/test_eval_evidence_chain_command.py` passed 2026-10-10 (the DB-gated test skipped: no Postgres on this host). Recorded run: `docs/evaluation/runs/*-chain-proxy-starter.json`. **One discrepancy recorded, not smoothed:** proposal 12 §4.2 prints 'missed by all' = 4 at cutoff 0.5; the runs give 3 (q12, q16, q40) — 4 is the label model's own miss count

**Status:** **BUILT, offline, exploratory.** Nothing reaches the answer path, shadow rows or reader settings. Bands in the recorded file are the proposal's illustrations, not an operating point; the proxy set is arXiv, not CIT-U. Not Done: awaits review
