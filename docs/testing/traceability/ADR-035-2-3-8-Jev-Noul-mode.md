# ADR-035-2-3-8-Jev-Noul-mode

[Back to the matrix](../TRACEABILITY.md)

## ADR-035 §2 · §3 · §8 (Jev Noul mode)

**Requirement:** **The Evidence route can be asked as a probability** — no FR- id; [ADR-035](../../adr/035-ask-iris-decides-whether-it-needs-evidence.md), [ADR-036](../../adr/036-openai-compatible-inference-provider.md) §Amendment 2026-10-08. IR-482 under IR-480

**Design:** §2/§3 every failure, timeout, rate limit or malformed response to search with its own code, the detector stays an independent floor in the union · §8 the state holds the question, the stored Resolved question (labelled untrusted), at most five prior reader questions and a versioned corpus description, and nothing retrieved

**Implementation:** `apps/ai/providers/decisions.py` (the `DecisionModel` port, `ScriptedDecisionModel`) and `openrouter_decisions.py` (adapter pinned to `typesafe/jev-1.13`, alias refused); `apps/ai/evidence/jev_noul.py` (`JevNoulDecision`, `build_state`, `jev_digest`); `ModelDecision.probability` and `malformed_response`; `ModelResult.curve` (missed searches over the evidence-required, over-searches over the rest, by category, union beside it, no operating point chosen); `eval_evidence --decision-mode jev-noul` (public proxy tier only, key lent by an Inference task already at OpenRouter, never builds the composition root)

**Test:** `providers/tests/test_openrouter_decisions.py`, `evidence/tests/test_jev_noul.py`, `evaluation/tests/test_evidence_threshold_curve.py`, `tests/test_eval_evidence_jev_command.py` — offline, no vendor account

**Evidence:** **Four live runs on the 113 public proxy questions, 2026-10-08** (`20261008-110112`, `-110304`, `-110450`, `-110632`; returned model `typesafe/jev-1.13-20260917`, prompt digest `836128e51bba`, 0 fallbacks in all four, no run pooled). Missed searches over the 83 evidence-required, over-searches over the 20 others (the 10 `ambiguous` questions tolerate a search): at 0.10 → 3 missed / 5-7 over; 0.20 → 4 / 0-1; 0.30 → 8-10 / 0; 0.50 → 16-17 / 0; 0.70 → 31-35 / 0. No operating point chosen. Stable misses (every run) 4 at 0.20, 15 at 0.50 (nine of them `mechanism`); flaky 0 at 0.20, 3 at 0.50; the probability moved at most 0.13 between runs. Latency mean 889-928 ms, p95 1011-1156 ms, against 2.2-2.8 s mean for the gpt-oss-20b route-label runs. Failure rate 0%. Stable/flaky was computed ad hoc from the run files, with no committed tool. Retention, training and rate-limit terms for the alpha endpoint remain unverified, and nothing reaches reader traffic

**Status:** Not Done
