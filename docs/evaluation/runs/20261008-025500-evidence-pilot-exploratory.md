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

Model runs: 0; most on one question set: 0. Runs are listed separately and never pooled.

## 2. Real-traffic shadow operations (NO ground truth)

**Real traffic carries no labels: no accuracy is computed from this section, and any accuracy figure drawn from it is a category error (ADR-035 §10).**



**Shadow rows unavailable: database not readable: OperationalError.** Nothing is reported, and this is not a finding of zero traffic.

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

- No curated run included the model (--model-decision), so the model's route accuracy and detector/model agreement are unmeasured.
- 5 categories are inconclusive: label more questions before any per-category claim.
- The shadow rows could not be read (database not readable: OperationalError): the operational side is unmeasured, which is not the same as zero traffic.
- The exploratory sample plan is not declared.
- The confirmatory sample plan is not declared.
- Recommendation: do not move toward production `on` on this evidence. The pilot is evidence for that decision, not authorization to make it, and none of the other gates below is satisfied by it.

Production `on` requires all of the following. The pilot informs them and satisfies none of them:

1. Routing thresholds met across repeated runs.
2. An offline review of hypothetical direct answers passed.
3. The landscape policy (ADR-035 §9) resolved with an accountable owner named by a person, never inferred.
4. The reader-facing 'search the papers instead' override built.
5. ADR-035 accepted (it is, as of 2026-10-06; that does not make the other four true).
