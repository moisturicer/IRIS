# 03 — Final Evaluation Plan (Phase 3, Weeks 11–12+)

**Summative.** This is where research evidence is produced. Distinct from Phase 1 in purpose, instrument and analysis, even where the same people participate.

---

## Preconditions

Nothing here runs unless all of the following are true. Each has a hard deadline because none can be recovered afterwards.

| Precondition | Task | Deadline | If missed |
|---|---|---|---|
| **Instrumentation live** | `W-04` | **Week 10** | **No quantitative research data exists.** Unrecoverable |
| Clearance state visible | `W-07` | Week 7 | Contribution invisible; qualitative data invalid |
| Restart-all policy configurable | `W-02` | Week 7 | No controlled comparison possible |
| Transition table | `W-01` | Week 7 | `W-02` cannot exist |
| Evaluation instance provisioned | `SA-02` | Week 10 | Comparison would corrupt customer data |
| Scenarios built and matched | [07](07-workflow-evaluation.md) | Week 10 | Sessions cannot run |
| Instrument refined from Phase 1 | [06](06-validation-instruments.md) | Week 3 | Unpiloted instrument on the only available population |
| Participants scheduled | [10](10-respondent-plan.md) | Week 10 | Four offices cannot be assembled at short notice |
| Backups working, restore rehearsed | `D-04` | Week 10 | Losing pilot data would be unrecoverable |
| Ethics / consent approved | — | Week 3 | **NEEDS ADVISER CONFIRMATION** |
| Written pilot commitment | — | Weeks 1–2 | **NEEDS CIT-U CONFIRMATION** — highest single risk |

---

## Two strands

Phase 3 has an organic strand and a controlled strand. They answer different questions and neither substitutes for the other.

| | **Strand A — Organic pilot** | **Strand B — Controlled comparison** |
|---|---|---|
| **Weeks** | 11–12 | Week 12 (scheduled sessions) |
| **Question** | Does IRIS work in real institutional use? | Does clearance-aware beat restart-all? |
| **Data** | Real submissions, real reviews, real timings | Matched scenarios under both policies |
| **Validity** | Ecological | Internal |
| **Weakness** | Cannot be counterfactual — a real submission cannot be run twice | Artificial scenarios |
| **Feeds** | RQ2, RQ3, M4, M7, M8, M15 | **RQ1** — the contribution |

**Strand B is the evidence for the contribution.** Strand A cannot be, because you cannot run the same real submission under both policies. Strand A supplies ecological grounding, usability data and SUS.

**Strand B runs regardless of Strand A's volume.** If organic resubmissions are few — which RDCO data may well show — Strand B is unaffected because it does not depend on organic volume.

---

## Strand A — organic pilot, Weeks 11–12

**Data collected passively** via `W-04` instrumentation:

| Metric | What it gives |
|---|---|
| M4, M6, M8 | Real per-office review durations and per-stage turnaround |
| M7 | Real end-to-end workflow time |
| M1, M2, M3 | Real preserved-clearance counts *(descriptive only — see [07](07-workflow-evaluation.md) on why counting alone is insufficient)* |
| M11, M12 | Task completion and support requests, from usage and helpdesk contact |

**Data collected actively:**

- **SUS** at the end of the pilot, across ≥3 role groups (`NFR-U1`, M15/M16)
- **Timed first-submission task** with 5 first-time students after a one-hour onboarding (`NFR-U2`, M14)
- **Exit interviews** with pilot participants (M19, M21)

**Scope of data.** Phase 1 (synthetic/published) may extend to approved institutional data in Phase 3 **only if** the governance question is resolved. Real unpublished IP requires separate approval — **NEEDS CIT-U CONFIRMATION**. Default to non-sensitive records; the evaluation does not require confidential content.

**Operational discipline during the pilot:**

- **Freeze the system.** No deployments during Weeks 11–12 except for defects that block usage. A mid-pilot change invalidates comparability of timing data
- Daily check that instrumentation is recording
- Log every support contact — helpdesk volume is itself a usability measure (M12)
- Daily backup verified (`D-04`)

---

## Strand B — controlled comparison, Week 12

Design, scenarios, protocol, threats and sample-size justification are in [07](07-workflow-evaluation.md).

**Summary:** within-subjects, counterbalanced, 8 matched scenario pairs including 2 controls, ~90-minute sessions, census of accessible reviewing-office staff, run on a separate evaluation instance.

**Scheduling constraint.** This requires staff from four offices in scheduled sessions. Book in Week 10, confirm in Week 11. Four separate offices cannot be assembled on short notice, and there is no second window.

---

## Supporting evaluation

**RAG** — [08](08-rag-evaluation.md). Conditional on `R-04` completing within its timebox. Runs as a scripted evaluation, not a user session; it does not consume respondent time.

**NFR validations** — `V-06` through `V-15` in `docs/architecture-tasks/10-mvp-validation.md` run in Weeks 8–10, **before** the pilot. They are engineering verification, not research evidence, and are reported separately.

---

## Data collection summary

| Source | Metrics | Timing |
|---|---|---|
| `W-04` instrumentation | M1–M8 | Continuous, Weeks 11–12 |
| Observation sheets | M9–M13, M17 | Session-based |
| SUS | M15, M16 | End of pilot |
| Timed submission task | M14 | Week 11 |
| Interview transcripts | M19, M20, M21 | Session-based |
| Baseline (Phase 1) | M18 | Weeks 1–3 |
| RAG scripts | [08](08-rag-evaluation.md) | Week 12 |

---

## Analysis

Detail in [11](11-analysis-plan.md). In outline:

- **Quantitative:** descriptive statistics per condition; paired differences per participant; effect sizes with confidence intervals; **no inferential significance claims** at this N
- **Qualitative:** thematic analysis of transcripts; codes derived from RQ3 sub-questions plus emergent themes; quotations supporting each theme
- **Integration:** quantitative results reported first, then qualitative explanation. Where they disagree — for example a measured advantage that SMEs did not perceive — **report the disagreement**; it is one of the more informative outcomes available

---

## Outputs

1. **Evaluation results** — quantitative tables, effect sizes, qualitative themes
2. **Answers to RQ1–RQ4**, including null or negative results
3. **NFR evidence** for U1, U2, U3, P2, P3, P4, S2, S4, S5, R2, R3, R4
4. **Threats to validity**, stated rather than left to be found
5. **Boundary conditions** — where SMEs judged the model inappropriate (M20)
6. **Research paper draft** (Weeks 13–15)

---

## What Phase 3 will not produce

- Statistical significance in a conventional sense — N is a bounded population
- Generalisation beyond CIT-U — single institution
- Evidence that IRIS beats manual process — confounded by digitisation
- Longitudinal adoption evidence — two weeks
- A commercial market study — adoption intent is qualitative

**These are stated in the thesis, not discovered by the panel.**

---

## Contingencies

| If | Then |
|---|---|
| **Pilot commitment falls through** | Strand B becomes the sole evaluation. It is self-contained and does not need organic volume. Report the absence of ecological data as a limitation |
| **Organic volume yields no resubmissions** | Expected and planned for. Strand B is unaffected |
| **`W-04` slips past Week 10** | **Escalate immediately.** Fall back to manual timing during Strand B sessions — stopwatch and observation sheet — which preserves RQ1 at the cost of Strand A's quantitative data |
| **`R-04` misses its timebox** | RAG evaluation reduces to retrieval relevance and degradation only; generation reported as Phase 2 ([ADR-006](../adr/006-minimum-rag-pipeline.md)) |
| **Fewer than 4 SMEs available** | Report the achieved N explicitly. With N<4 the comparison becomes a multiple case study; reframe the analysis as such rather than presenting weak aggregates |
| **A participant fails the M17 comprehension check** | Their G1 qualitative data is excluded and the exclusion is reported. Quantitative measures still stand |
