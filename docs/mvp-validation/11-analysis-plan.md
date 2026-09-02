# 11 — Analysis Plan

Written **before** data collection, so the analysis is pre-registered rather than chosen after seeing results. Deviations from this plan must be recorded and justified in the thesis.

---

## Governing constraint

**N is bounded by the population, not chosen.** The accessible SME population is roughly 4–12 people ([10](10-respondent-plan.md)). This is a census, not a sample.

Consequences, adopted deliberately:

1. **No inferential generalisation.** No claim that results extend beyond CIT-U.
2. **No null-hypothesis significance testing as the primary result.** At this N, a p-value would be uninterpretable and its absence of significance would be uninformative.
3. **Descriptive statistics and effect sizes are the primary quantitative output.**
4. **Qualitative data carries substantial evidential weight** — at small N, expert reasoning is stronger than a mean.

**This must be stated in the thesis, not left for the panel to raise.** A census reported honestly as a census is defensible. A census reported as though it were a sample is not.

---

## Unit of analysis

Choosing the unit carefully is what makes the quantitative analysis viable.

| Unit | Count | Used for |
|---|---|---|
| Participant | 4–12 | SUS, per-person summaries, retention |
| **Scenario-condition pair** | **8 scenarios × 2 conditions × N** | **The primary comparison** |
| Office review event | Many | Time-on-task distributions (M4, M6) |

At N=6 participants the scenario-condition unit yields 96 observations. That supports descriptive comparison and effect size; it does **not** convert a census into a sample, because the observations are clustered within six people. Report the clustering.

---

## Quantitative analysis

### Primary comparison — RQ1

For each participant, paired differences between conditions:

| Metric | Statistic reported |
|---|---|
| M1 Offices re-reviewed | Median and range per condition; per-participant difference |
| M2 Offices preserved | Median and range |
| M4 Time-on-task per office review | Median, IQR; distribution plot |
| M5 Total reviewer time per scenario | Median, IQR; per-participant difference |
| **M6 Repeat-review vs first-review time** | **Ratio, with distribution** |
| M7 Total workflow turnaround | Median, IQR |
| M9 Task success | Proportion per condition |

**Presentation.** A per-participant table showing both conditions side by side, plus a paired-difference plot. **Every participant's data is visible** — with N this small, individual values are more informative than aggregates and hiding them behind a mean would waste the data.

### Effect size

**Primary effect measure: matched-pairs rank-biserial correlation** (r), reported with a confidence interval where N permits.

Chosen over Cohen's d because the measures are unlikely to be normally distributed at this N and time-on-task is typically right-skewed.

**Interpretation stated in advance:** r ≈ 0.1 small · 0.3 medium · 0.5 large. **The interpretation bands are conventions, not thresholds for a claim.**

### Optional inferential test

**Wilcoxon signed-rank**, reported only if N ≥ 6 pairs, and reported as **supplementary** with an explicit statement that the study is not powered for it.

**Not used as the basis for any conclusion.** If it is reported at all, exact p-values are given, no threshold language ("significant") is used, and the reason for including it is stated.

### Controls

**Scenarios 6 and 7 are structural controls** — no clearance state exists, so both policies should behave identically ([07](07-workflow-evaluation.md)).

- If the controls show a difference, that difference is the measurement noise floor plus any residual learning effect
- **Report the control result before the treatment result.** A treatment effect smaller than the control difference is not evidence
- If controls differ substantially, investigate the protocol before interpreting anything else

### Order effects

Order (AB / BA) is recorded per participant and inspected:

- Compare condition-1 timings against condition-2 timings irrespective of policy
- If a systematic order effect appears, report it and interpret the policy comparison with that caveat
- With odd N the counterbalancing is imperfect; state the imbalance

### SUS

- Standard scoring, 0–100
- **Mean with 95% confidence interval**, N stated
- By role group where N ≥ 3 per group
- **At N < 12, report as indicative** and note that SUS means are unstable below roughly 12–15 respondents
- Compare against the `NFR-U1` threshold of 75 and against the published ~68 average, with the sample-size caveat attached to both

### NFR validation metrics

Pass/fail against SRS-defined thresholds, reported as a compliance table, not as research findings. Sourced from `V-06`…`V-15`.

---

## Qualitative analysis

### Method

**Thematic analysis**, hybrid deductive-inductive:

- **Deductive codes** derived from RQ3 sub-questions: current-practice pain points · perceived benefit · perceived problems · **boundary conditions favouring restart-all (M20)** · adoption blockers (M21)
- **Inductive codes** for themes that emerge and do not fit the above

### Procedure

1. Transcribe recordings (or work from detailed notes where recording was declined)
2. First-pass coding by one team member
3. **Second coder on ≥ 25% of transcripts**; disagreements discussed and the codebook revised
4. Themes assembled with supporting quotations
5. Frequency reported as *"3 of 6 SMEs"* — never as a percentage, which implies a precision N does not support

**Inter-rater reliability.** With few transcripts, formal κ is unstable. Report the **proportion of coding agreements** and describe how disagreements were resolved. Do not report a κ that the data cannot support.

### Disconfirming evidence

**Actively sought and reported.** Specifically:

- Any SME who preferred restart-all, and their reasoning (M20)
- Any participant who did not perceive a difference between conditions
- Any case where quantitative and qualitative results disagree

> **Where a measured advantage was not perceived by participants — or a perceived advantage does not appear in the measurements — report the disagreement prominently.** It is among the more informative outcomes available, and concealing it would be the clearest failure of integrity in this study.

---

## Integration

**Sequential explanatory:** quantitative results first, then qualitative explanation.

| Quantitative | Qualitative role |
|---|---|
| Difference favours clearance-aware | Why? What did SMEs notice? Does M6 explain the magnitude? |
| No meaningful difference | Why not? Too few offices per record? Repeat reviews already cheap? Did participants perceive any difference at all? |
| Difference favours restart-all | Why? Confusion about preserved state? A genuine workflow property? |

**A joint display** — findings table with quantitative result, qualitative theme and convergence/divergence per research question — is the primary integration artefact.

---

## Handling the possible outcomes

All five are anticipated; none requires an unplanned analysis.

| Outcome | Analysis |
|---|---|
| Clear advantage | Report effect size, CI, supporting themes. State limitations |
| Reviews reduced, time not (low M6) | **Report both.** The contribution reduces review *count* but repeat reviews are cheap. More interesting than a simple win — it identifies where the model matters |
| **No meaningful difference** | Report descriptively with effect size near zero. Examine: offices engaged per record, M6, whether participants perceived the manipulation (B3 Q1). **Do not re-analyse until something reaches significance** |
| SMEs prefer restart-all in cases | Report as a boundary condition. Strong support for keeping the policy configurable ([ADR-004](../adr/004-restart-all-comparison-mode.md)) |
| Comprehension failure (low M17) | Exclude affected sessions' G1 qualitative data, **report the exclusion**, and report the comprehension failure as a design finding in its own right |

**Explicitly prohibited:** dropping participants because their data is inconvenient · adding scenarios after seeing results · switching the primary metric post hoc · reporting only the favourable subset. Any deviation from this plan is disclosed with its reason.

---

## Missing data

| Situation | Handling |
|---|---|
| Participant completes one condition only | Report; exclude from paired analysis; include in descriptive |
| A timing is not captured | Report as missing; do not impute |
| A recording fails | Use facilitator notes; flag as lower-fidelity |
| An office does not participate | **Report the gap prominently** — it is a coverage limitation, not a footnote |

**No imputation.** At this N, imputing a value would fabricate a substantial share of the dataset.

---

## Reporting checklist

- [ ] N stated everywhere, including per subgroup
- [ ] Census framing stated explicitly
- [ ] Per-participant data shown, not only aggregates
- [ ] Effect sizes with CIs where computable
- [ ] Control scenarios reported before treatment
- [ ] Order effects inspected and reported
- [ ] SUS reported with CI and the small-N caveat
- [ ] Disconfirming evidence reported
- [ ] Quant/qual disagreements reported
- [ ] Threats to validity stated ([04](04-research-questions.md))
- [ ] Deviations from this plan disclosed
- [ ] Null results reported as findings, not omissions
