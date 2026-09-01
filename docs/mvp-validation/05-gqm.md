# 05 — Goal–Question–Metric

GQM derives the metric set from the research goals, so every measurement has a stated reason. Presented here as **method**, not as a second framework — the output is reported under ISO 9241-11's three dimensions ([FRAMEWORK_DECISION.md](FRAMEWORK_DECISION.md)).

**Four goals → twelve questions → twenty-one metrics.**

Every metric names its **source** — the specific mechanism that produces it. A metric with no source is a metric that will not exist in Week 12.

---

## G1 · Evaluate clearance-aware resubmission

> **Analyse** the resubmission policy
> **for the purpose of** evaluating its effect
> **with respect to** redundant office review and reviewer effort
> **from the viewpoint of** institutional reviewing offices
> **in the context of** CIT-U's four-office IP clearance workflow.

| | Question | Metric | Source | Type |
|---|---|---|---|---|
| **Q1.1** | How many office reviews are repeated under each policy? | **M1** Offices re-reviewed per resubmission | `W-04` audit event; observation sheet | Ratio |
| | | **M2** Offices preserved per resubmission | `W-04`; computed at resubmission time | Ratio |
| | | **M3** Proportion of prior clearances preserved | M2 ÷ (M1 + M2) | Ratio |
| **Q1.2** | How much reviewer time does that represent? | **M4** Time-on-task per office review (s) | `W-04` queue-entry → decision timestamp; stopwatch in sessions | Ratio |
| | | **M5** Total reviewer time per scenario, all offices (s) | Σ M4 | Ratio |
| | | **M6** Time-on-task for a *repeat* review vs a *first* review | M4 split by review ordinality | Ratio |
| **Q1.3** | Does end-to-end turnaround differ? | **M7** Total workflow turnaround, submission → terminal state | `W-04` first and last event timestamps | Ratio |
| | | **M8** Per-stage turnaround | `W-04` per-stage timestamps | Ratio |
| **Q1.4** | Does task success differ? | **M9** Task success rate per scenario per condition | Observation sheet, binary + graded | Nominal / ordinal |
| | | **M10** Errors and recoveries per scenario | Observation sheet | Count |

**M6 is the metric that turns reviews into effort.** Without it, M1–M3 count reviews and silently assume a repeat review costs as much as a first one — which it almost certainly does not. If M6 shows a repeat review costs a small fraction of a first review, the practical value of the contribution is correspondingly smaller, and that must be reported.

---

## G2 · Evaluate usability of the workflow

> **Analyse** the IRIS workflow interface
> **for the purpose of** characterising usability
> **with respect to** effectiveness, efficiency and satisfaction
> **from the viewpoint of** submitters and reviewers
> **in the context of** routine institutional use.

| | Question | Metric | Source | Type |
|---|---|---|---|---|
| **Q2.1** | Can users complete their tasks? *(effectiveness)* | **M11** Task completion rate per role | Observation sheet | Ratio |
| | | **M12** Assistance events per task | Observation sheet | Count |
| **Q2.2** | How efficiently? *(efficiency)* | **M13** Time-on-task per scripted task | Stopwatch | Ratio |
| | | **M14** First-time submission completion time (NFR-U2) | Timed session, 5 students | Ratio |
| **Q2.3** | How satisfied are users? *(satisfaction)* | **M15** SUS score per respondent (NFR-U1) | SUS, SRS Appendix B | Interval |
| | | **M16** SUS mean with confidence interval, by role group | Aggregate of M15 | Interval |
| **Q2.4** | Is clearance state comprehensible? | **M17** Correct identification of which offices cleared / remain | Comprehension check in the observation sheet | Nominal |

**M17 exists because of the `W-07` finding.** It is the construct-validity check for the whole of G1: if participants cannot correctly read which offices cleared, their qualitative judgements about preservation are not about the thing being studied. Ask it early in each session; a low M17 invalidates that session's G1 qualitative data and must be reported.

---

## G3 · Characterise the current process and expert judgement

> **Analyse** current CIT-U practice and expert opinion
> **for the purpose of** contextualising the contribution
> **with respect to** redundant review and perceived improvement
> **from the viewpoint of** reviewing-office staff and decision-makers
> **in the context of** existing institutional workflow.

| | Question | Metric | Source | Type |
|---|---|---|---|---|
| **Q3.1** | What does current practice cost? | **M18** Baseline: submissions per fortnight, decline rate, turnaround, redundant-review frequency and duration | RDCO — **NEEDS RDCO DATA** | Mixed |
| **Q3.2** | Do SMEs judge the model an improvement? | **M19** Thematic coding of SME judgements, with supporting quotations | Interview transcripts | Qualitative |
| **Q3.3** | When would full re-review be preferred? | **M20** Documented boundary conditions where SMEs favour restart-all | Interview transcripts | Qualitative |
| **Q3.4** | Would decision-makers adopt it? | **M21** Adoption intent, stated conditions and blockers | Decision-maker interviews | Qualitative |

**M20 is deliberately adversarial.** A genuine boundary condition — an office that legitimately needs to re-review after any change elsewhere, for example on ethics grounds — would qualify the contribution and is a more interesting finding than uniform endorsement. If no SME can name such a case, that is itself worth reporting.

**M18 is entirely blank.** No value has been invented. See [09](09-baseline-data.md).

---

## G4 · Evaluate the supporting AI capability *(conditional)*

> **Analyse** the RAG capability
> **for the purpose of** establishing fitness as a supporting feature
> **with respect to** relevance, groundedness, citation correctness, latency and failure behaviour
> **from the viewpoint of** end users
> **in the context of** search over the institutional research corpus.

Conditional on `R-04` completing within its timebox. Metrics and thresholds are in [08](08-rag-evaluation.md); they are internal design targets on a fixed query set, not benchmark claims.

---

## Mapping to ISO 9241-11

How the metrics are **reported** — the presentational spine, distinct from the derivation above.

| ISO dimension | Metrics |
|---|---|
| **Effectiveness** | M1, M2, M3, M9, M10, M11, M12, M17 |
| **Efficiency** | M4, M5, M6, M7, M8, M13, M14 |
| **Satisfaction** | M15, M16 |
| **Context of use** | M18 (baseline), M19, M20, M21 (expert judgement) |

The domain metrics sit **inside** effectiveness and efficiency as context-specific measures, which ISO 9241-11's context-of-use clause permits. They are not a fourth category.

---

## Instrumentation dependencies

**Every metric must have a working source before Week 11. There is no second chance to collect Phase 3 data.**

| Metric | Depends on | Status | Deadline |
|---|---|---|---|
| M1, M2, M3 | `W-04` — preserved/reset offices recorded at resubmission, surviving clearance-row deletion | Not built | **Week 10** |
| M4, M6, M8 | `W-04` — per-office queue-entry and decision timestamps | Not built | **Week 10** |
| M5, M7 | `W-04` event timestamps | Not built | **Week 10** |
| M9–M14, M17 | Observation sheet + stopwatch | To draft | Week 3 |
| M15, M16 | SUS, SRS Appendix B | Exists | — |
| M17 | **`W-07` clearance visibility** | **Not built — not in the current backlog** | **Before any session** |
| M18 | RDCO cooperation | **NEEDS RDCO DATA** | **Weeks 1–3** |
| M19–M21 | Interview guides, consent, recording | To draft | Week 3 |

**Two items are unrecoverable if missed.** `W-04` cannot be retrofitted after the pilot — the data simply will not exist. M18 cannot be collected after IRIS goes live, because the manual process stops being observable.

---

## Metrics deliberately excluded

| Excluded | Why |
|---|---|
| Preserved-clearance count as *primary* evidence | Deterministically computable from which office declined — no variance, no possible negative result. Retained as descriptive support (M2, M3), never as the headline |
| Lines of code, velocity, defect density | Process metrics; irrelevant to the research questions |
| Page-level analytics, click paths | Would require analytics instrumentation that is not built and not justified |
| NPS | Unstable at N≈10 ([01](01-framework-selection.md)) |
| TAM constructs | Replaced by qualitative adoption intent (M21) |
