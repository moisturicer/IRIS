# Evidence-decision pilot report (IR-467)

Two instruments, reported separately and never blended (ADR-035 §10). The pilot is complete when it has produced a trustworthy measurement, whatever that measurement says.

## 1. Curated evaluation (has ground truth)

Each lane's denominator is the annotated questions carrying that lane's text (the Resolved lane only those with a Resolved question). Each category's is its own annotated questions. The model section's is every annotated question put to the model.

### Run `20261008-024428-evidence-proxy-starter.json`

- commit `v0.1.0-619-gafe6976-dirty`; question set `proxy-starter` (sha256 `553696988bac8487d447985d30a8df55ef5144bd0981611637f9b586d902ca1b`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: False
- prompt digest: not recorded; generation: not recorded
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 10 of 62 questions annotated, 4 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 10 | 9 | 0 | 1 |
| resolved | 4 | 3 | 0 | 1 |
| combined | 10 | 10 | 0 | 0 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 4 |
| raw | institution_term | 1 | 0 | 3 |
| raw | document_reference | 2 | 0 | 2 |
| raw | sourcing_demand | 0 | 0 | 4 |
| raw | aggregate_shape | 1 | 0 | 3 |
| resolved | scope_record | 0 | 0 | 2 |
| resolved | institution_term | 0 | 0 | 2 |
| resolved | document_reference | 1 | 0 | 1 |
| resolved | sourcing_demand | 0 | 0 | 2 |
| resolved | aggregate_shape | 0 | 0 | 2 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 2 | 2 | INCONCLUSIVE (min 5) | n/a |
| follow-up-after-direct | 2 | 2 | INCONCLUSIVE (min 5) | n/a |
| follow-up-after-grounded | 2 | 2 | INCONCLUSIVE (min 5) | n/a |
| general-knowledge | 2 | 2 | INCONCLUSIVE (min 5) | n/a |
| off-corpus-research | 2 | 2 | INCONCLUSIVE (min 5) | n/a |

Institutional questions: 1 judged, 0 incorrect.

Model decision: **not run** in this file.

### Run `20261008-044833-evidence-proxy-starter.json`

- commit `v0.1.0-620-g3fba71f-dirty`; question set `proxy-starter` (sha256 `cafe5d976e0d1101a9d03ef13dcfeb932b82eb04c0c82cf401de87b0418dee93`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: False
- prompt digest: not recorded; generation: not recorded
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 113 of 113 questions annotated, 20 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 113 | 55 | 0 | 58 |
| resolved | 20 | 16 | 0 | 4 |
| combined | 113 | 56 | 0 | 57 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 83 |
| raw | institution_term | 5 | 0 | 78 |
| raw | document_reference | 10 | 0 | 73 |
| raw | sourcing_demand | 2 | 0 | 81 |
| raw | aggregate_shape | 15 | 0 | 68 |
| resolved | scope_record | 0 | 0 | 10 |
| resolved | institution_term | 0 | 0 | 10 |
| resolved | document_reference | 1 | 0 | 9 |
| resolved | sourcing_demand | 1 | 0 | 9 |
| resolved | aggregate_shape | 5 | 0 | 5 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| cross-paper | 10 | 1 | CONCLUSIVE (min 10) | 0.1 |
| exact-term | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| follow-up-after-direct | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| follow-up-after-grounded | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| general-knowledge | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| mechanism | 33 | 1 | CONCLUSIVE (min 10) | 0.0303 |
| near-duplicate | 10 | 4 | CONCLUSIVE (min 10) | 0.4 |
| off-corpus-research | 10 | 6 | CONCLUSIVE (min 10) | 0.6 |

Institutional questions: 5 judged, 0 incorrect.

Model decision: **not run** in this file.

### Run `20261008-051409-evidence-proxy-starter.json`

- commit `v0.1.0-621-g4418b1a`; question set `proxy-starter` (sha256 `cafe5d976e0d1101a9d03ef13dcfeb932b82eb04c0c82cf401de87b0418dee93`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: True; model(s) openai/gpt-oss-120b
- prompt digest: 1ffdd72ab6e91a532a825accb697ffa1990082cc4ba5a62b77a014e95a654754; generation: {'vendor': 'groq', 'model': 'openai/gpt-oss-120b', 'fallback_models': [], 'temperature': 0.5, 'reasoning_effort': 'medium'}
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 113 of 113 questions annotated, 20 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 113 | 55 | 0 | 58 |
| resolved | 20 | 16 | 0 | 4 |
| combined | 113 | 56 | 0 | 57 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 83 |
| raw | institution_term | 5 | 0 | 78 |
| raw | document_reference | 10 | 0 | 73 |
| raw | sourcing_demand | 2 | 0 | 81 |
| raw | aggregate_shape | 15 | 0 | 68 |
| resolved | scope_record | 0 | 0 | 10 |
| resolved | institution_term | 0 | 0 | 10 |
| resolved | document_reference | 1 | 0 | 9 |
| resolved | sourcing_demand | 1 | 0 | 9 |
| resolved | aggregate_shape | 5 | 0 | 5 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| cross-paper | 10 | 1 | CONCLUSIVE (min 10) | 0.1 |
| exact-term | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| follow-up-after-direct | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| follow-up-after-grounded | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| general-knowledge | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| mechanism | 33 | 1 | CONCLUSIVE (min 10) | 0.0303 |
| near-duplicate | 10 | 4 | CONCLUSIVE (min 10) | 0.4 |
| off-corpus-research | 10 | 6 | CONCLUSIVE (min 10) | 0.6 |

Institutional questions: 5 judged, 0 incorrect.

Model decision (openai/gpt-oss-120b): 113 calls, 0 fell back to evidence (failure rate 0.0).

| view | judged | correct | over-searches | missed searches |
|---|---|---|---|---|
| model alone | 113 | 95 | 7 | 11 |
| union (detector OR model) | 113 | 96 | 7 | 10 |

Model alone over calls where it ruled: 95/113.
Detector/model agreement: {'both_evidence': 25, 'both_direct': 33, 'detector_only_evidence': 1, 'model_only_evidence': 54, 'agreement': 0.5133}.
Reason codes: {'search_requested': 79, 'answered_directly': 34}. Decision latency: {'mean': 3467, 'p95': 7262}.

### Run `20261008-053345-evidence-proxy-starter.json`

- commit `v0.1.0-622-g455d3d7`; question set `proxy-starter` (sha256 `cafe5d976e0d1101a9d03ef13dcfeb932b82eb04c0c82cf401de87b0418dee93`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: True; model(s) openai/gpt-oss-120b
- prompt digest: 1ffdd72ab6e91a532a825accb697ffa1990082cc4ba5a62b77a014e95a654754; generation: {'vendor': 'groq', 'model': 'openai/gpt-oss-120b', 'fallback_models': [], 'temperature': 0.5, 'reasoning_effort': 'medium'}
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 113 of 113 questions annotated, 20 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 113 | 55 | 0 | 58 |
| resolved | 20 | 16 | 0 | 4 |
| combined | 113 | 56 | 0 | 57 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 83 |
| raw | institution_term | 5 | 0 | 78 |
| raw | document_reference | 10 | 0 | 73 |
| raw | sourcing_demand | 2 | 0 | 81 |
| raw | aggregate_shape | 15 | 0 | 68 |
| resolved | scope_record | 0 | 0 | 10 |
| resolved | institution_term | 0 | 0 | 10 |
| resolved | document_reference | 1 | 0 | 9 |
| resolved | sourcing_demand | 1 | 0 | 9 |
| resolved | aggregate_shape | 5 | 0 | 5 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| cross-paper | 10 | 1 | CONCLUSIVE (min 10) | 0.1 |
| exact-term | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| follow-up-after-direct | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| follow-up-after-grounded | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| general-knowledge | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| mechanism | 33 | 1 | CONCLUSIVE (min 10) | 0.0303 |
| near-duplicate | 10 | 4 | CONCLUSIVE (min 10) | 0.4 |
| off-corpus-research | 10 | 6 | CONCLUSIVE (min 10) | 0.6 |

Institutional questions: 5 judged, 0 incorrect.

Model decision (openai/gpt-oss-120b): 113 calls, 1 fell back to evidence (failure rate 0.0088).

| view | judged | correct | over-searches | missed searches |
|---|---|---|---|---|
| model alone | 113 | 96 | 7 | 10 |
| union (detector OR model) | 113 | 97 | 7 | 9 |

Model alone over calls where it ruled: 95/112.
Detector/model agreement: {'both_evidence': 25, 'both_direct': 32, 'detector_only_evidence': 1, 'model_only_evidence': 55, 'agreement': 0.5044}.
Reason codes: {'search_requested': 79, 'answered_directly': 33, 'rate_limited': 1}. Decision latency: {'mean': 3406, 'p95': 9528}.

### Run `20261008-054102-evidence-proxy-starter.json`

- commit `v0.1.0-622-g455d3d7`; question set `proxy-starter` (sha256 `cafe5d976e0d1101a9d03ef13dcfeb932b82eb04c0c82cf401de87b0418dee93`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: True; model(s) openai/gpt-oss-120b
- prompt digest: 1ffdd72ab6e91a532a825accb697ffa1990082cc4ba5a62b77a014e95a654754; generation: {'vendor': 'groq', 'model': 'openai/gpt-oss-120b', 'fallback_models': [], 'temperature': 0.5, 'reasoning_effort': 'medium'}
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 113 of 113 questions annotated, 20 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 113 | 55 | 0 | 58 |
| resolved | 20 | 16 | 0 | 4 |
| combined | 113 | 56 | 0 | 57 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 83 |
| raw | institution_term | 5 | 0 | 78 |
| raw | document_reference | 10 | 0 | 73 |
| raw | sourcing_demand | 2 | 0 | 81 |
| raw | aggregate_shape | 15 | 0 | 68 |
| resolved | scope_record | 0 | 0 | 10 |
| resolved | institution_term | 0 | 0 | 10 |
| resolved | document_reference | 1 | 0 | 9 |
| resolved | sourcing_demand | 1 | 0 | 9 |
| resolved | aggregate_shape | 5 | 0 | 5 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| cross-paper | 10 | 1 | CONCLUSIVE (min 10) | 0.1 |
| exact-term | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| follow-up-after-direct | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| follow-up-after-grounded | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| general-knowledge | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| mechanism | 33 | 1 | CONCLUSIVE (min 10) | 0.0303 |
| near-duplicate | 10 | 4 | CONCLUSIVE (min 10) | 0.4 |
| off-corpus-research | 10 | 6 | CONCLUSIVE (min 10) | 0.6 |

Institutional questions: 5 judged, 0 incorrect.

Model decision (openai/gpt-oss-120b): 113 calls, 0 fell back to evidence (failure rate 0.0).

| view | judged | correct | over-searches | missed searches |
|---|---|---|---|---|
| model alone | 113 | 94 | 9 | 10 |
| union (detector OR model) | 113 | 94 | 9 | 10 |

Model alone over calls where it ruled: 94/113.
Detector/model agreement: {'both_evidence': 26, 'both_direct': 31, 'detector_only_evidence': 0, 'model_only_evidence': 56, 'agreement': 0.5044}.
Reason codes: {'search_requested': 82, 'answered_directly': 31}. Decision latency: {'mean': 3827, 'p95': 9107}.

### Run `20261008-054438-evidence-proxy-starter.json`

- commit `v0.1.0-622-g455d3d7`; question set `proxy-starter` (sha256 `cafe5d976e0d1101a9d03ef13dcfeb932b82eb04c0c82cf401de87b0418dee93`)
- rule-set digest `cdbeb62020fd328f473aad61760fc415f96daa55c35a7d0ac86aef82bdf62c33`; `AI_EVIDENCE_DECISION=off`
- model run: True; model(s) openai/gpt-oss-120b
- prompt digest: 1ffdd72ab6e91a532a825accb697ffa1990082cc4ba5a62b77a014e95a654754; generation: {'vendor': 'groq', 'model': 'openai/gpt-oss-120b', 'fallback_models': [], 'temperature': 0.5, 'reasoning_effort': 'medium'}
- retrieval configuration: not applicable (no retrieval runs)
- coverage: 113 of 113 questions annotated, 20 with a Resolved form

Detector, per lane (own denominators):

| lane | judged | correct | over-fires | misses |
|---|---|---|---|---|
| raw | 113 | 55 | 0 | 58 |
| resolved | 20 | 16 | 0 | 4 |
| combined | 113 | 56 | 0 | 57 |

Per rule, raw and Resolved lanes separately (silent-on-required is not a detector miss):

| lane | rule | fired | over-fires | silent on required |
|---|---|---|---|---|
| raw | scope_record | 0 | 0 | 83 |
| raw | institution_term | 5 | 0 | 78 |
| raw | document_reference | 10 | 0 | 73 |
| raw | sourcing_demand | 2 | 0 | 81 |
| raw | aggregate_shape | 15 | 0 | 68 |
| resolved | scope_record | 0 | 0 | 10 |
| resolved | institution_term | 0 | 0 | 10 |
| resolved | document_reference | 1 | 0 | 9 |
| resolved | sourcing_demand | 1 | 0 | 9 |
| resolved | aggregate_shape | 5 | 0 | 5 |

Categories (combined lane; fewer examples than the minimum is inconclusive and its accuracy is withheld):

| category | judged | correct | status | accuracy |
|---|---|---|---|---|
| ambiguous | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| cross-paper | 10 | 1 | CONCLUSIVE (min 10) | 0.1 |
| exact-term | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| follow-up-after-direct | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| follow-up-after-grounded | 10 | 7 | CONCLUSIVE (min 10) | 0.7 |
| general-knowledge | 10 | 10 | CONCLUSIVE (min 10) | 1.0 |
| mechanism | 33 | 1 | CONCLUSIVE (min 10) | 0.0303 |
| near-duplicate | 10 | 4 | CONCLUSIVE (min 10) | 0.4 |
| off-corpus-research | 10 | 6 | CONCLUSIVE (min 10) | 0.6 |

Institutional questions: 5 judged, 0 incorrect.

Model decision (openai/gpt-oss-120b): 113 calls, 53 fell back to evidence (failure rate 0.469).

| view | judged | correct | over-searches | missed searches |
|---|---|---|---|---|
| model alone | 113 | 80 | 26 | 7 |
| union (detector OR model) | 113 | 80 | 26 | 7 |

Model alone over calls where it ruled: 51/60.
Detector/model agreement: {'both_evidence': 26, 'both_direct': 11, 'detector_only_evidence': 0, 'model_only_evidence': 76, 'agreement': 0.3274}.
Reason codes: {'search_requested': 49, 'answered_directly': 11, 'rate_limited': 5, 'provider_failure': 48}. Decision latency: {'mean': 1876, 'p95': 8979}.

Model runs: 4; most on one question set: 4. Runs are listed separately and never pooled.

## 2. Real-traffic shadow operations (NO ground truth)

**Real traffic carries no labels: no accuracy is computed from this section, and any accuracy figure drawn from it is a category error (ADR-035 §10).**

Coverage is over eligible questions. Latency is over completed rows that recorded it. Parity is over completed rows. Detector/model cells are over rows where the model ruled.

**No shadow rows in the reported window.**

## 3. Sample plan

- **exploratory**: not declared
- **confirmatory**: not declared
- reported stage: exploratory; window {'since': None, 'until': None}
- The figure of 200 decisions that circulated during design is an exploratory planning estimate with no demonstrated statistical basis. It certifies nothing and is not used here.

## 4. What this report cannot measure

- Answer quality and claim support. The hypothetical direct answer is discarded in process by design, so neither is observable. They become measurable only through a separately approved capture, which is out of scope.
- Reader-visible end-to-end latency for a direct answer. Shadow always retrieves afterwards, so no request ever takes the shape a production direct answer would. The latencies below are the decision call's and the task's, not a reader's.
- Page precision. There is no instrument: labels match on record identity plus normalised quote containment, and the page is reported and never scored. ADR-028's central objection can be neither confirmed nor refuted today.

## 5. Safety properties asserted by test, not observed

- no reader-visible change: `apps/ai/tests/test_evidence_shadow.py::test_shadow_changes_nothing_a_reader_receives`; `apps/ai/tests/test_shadow_off_snapshot.py`; `apps/ai/tests/test_evidence_shadow.py::test_a_failing_enqueue_never_reaches_the_reader`
- no shadow-attributable degradation of the answer path: `apps/ai/tests/test_evidence_shadow.py::test_the_reader_path_spends_against_no_bucket`; `apps/ai/tests/test_evidence_shadow.py::test_shadow_is_skipped_when_the_answer_breaker_is_open`; `apps/ai/tests/test_evidence_shadow.py::test_shadow_is_skipped_when_its_budget_is_spent`

## 6. Recommendation

- 5 categories are inconclusive: label more questions before any per-category claim.
- 20261008-051409-evidence-proxy-starter.json: the union missed 10 question(s) needing the corpus (q03, q06, q07, q12, q13, q16, q32, q36, q40, q43). That is the expensive direction (ADR-035 §3).
- 20261008-053345-evidence-proxy-starter.json: the union missed 9 question(s) needing the corpus (q04, q07, q12, q13, q16, q32, q40, q43, q106). That is the expensive direction (ADR-035 §3).
- 20261008-054102-evidence-proxy-starter.json: the union missed 10 question(s) needing the corpus (q04, q07, q12, q13, q16, q32, q35, q36, q40, q43). That is the expensive direction (ADR-035 §3).
- 20261008-054438-evidence-proxy-starter.json: the union missed 7 question(s) needing the corpus (q06, q07, q12, q13, q16, q32, q40). That is the expensive direction (ADR-035 §3).
- No shadow rows: the operational side of the pilot has not run on any traffic, so coverage, latency and contention are unmeasured. ADR-035 §11 keeps shadow off real reader questions until the vendor-retention check is recorded.
- The exploratory sample plan is not declared.
- The confirmatory sample plan is not declared.
- Recommendation: do not move toward production `on` on this evidence. The pilot is evidence for that decision, not authorization to make it, and none of the other gates below is satisfied by it.

Production `on` requires all of the following. The pilot informs them and satisfies none of them:

1. Routing thresholds met across repeated runs.
2. An offline review of hypothetical direct answers passed.
3. The landscape policy (ADR-035 §9) resolved with an accountable owner named by a person, never inferred.
4. The reader-facing 'search the papers instead' override built.
5. ADR-035 accepted (it is, as of 2026-10-06; that does not make the other four true).
