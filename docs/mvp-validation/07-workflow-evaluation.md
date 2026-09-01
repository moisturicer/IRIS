# 07 — Workflow Evaluation

The controlled comparison that tests the thesis contribution. **This is the only element of the design that can produce a negative result**, and it is therefore the element that makes the claim evidence rather than assertion.

---

## Why a controlled comparison at all

The original plan measured the contribution by counting **preserved clearances** per resubmission.

That does not work. Given a log of which office declined, the preserved count is *deterministically computable*: (offices engaged) − (declining office). There is no variance, no uncertainty, and no possible outcome in which IRIS performs badly. It compares IRIS against a hypothetical worse version of IRIS that the authors defined. A panel will call it an arithmetic identity presented as a result, and they will be right.

Two further problems:

- **Preserved reviews ≠ preserved effort.** A repeat review of an already-cleared document plausibly costs a fraction of a first review. Counting reviews overstates the benefit unless duration is measured.
- **Sample.** A two-week pilot may produce single-digit resubmissions.

Only two comparisons are available:

| Comparison | Verdict |
|---|---|
| IRIS vs CIT-U's manual process | **Confounded.** Measures digitisation — any software beats paper. Retained as *context* only |
| **IRIS clearance-aware vs IRIS restart-all** | **Clean.** Same system, same users, same scenarios, one variable changed |

`W-02` makes the second possible for ~0.5 dev-days, because `W-01`'s transition table parameterises resubmission policy ([ADR-004](../adr/004-restart-all-comparison-mode.md)).

---

## Design

**Within-subjects, counterbalanced, matched scenarios.**

| | |
|---|---|
| **Independent variable** | Resubmission policy — `CLEARANCE_AWARE` / `RESTART_ALL` |
| **Design** | Within-subjects (each participant experiences both) |
| **Counterbalancing** | Participants alternately assigned AB / BA order |
| **Scenarios** | **Matched pairs — equivalent, not identical** |
| **Blinding** | Conditions presented as "Policy A" and "Policy B", never "ours" / "baseline" |
| **Environment** | A **separate evaluation instance**, never the customer's |
| **Population** | Census of accessible CIT-U reviewing-office staff |

### Why within-subjects

Each participant is their own control, which removes between-person variance — decisive when N is 6–12. It also halves the participants needed.

### Why matched, not identical, scenarios

**This is the most important design decision here.** Running the *same* scenario twice guarantees the second run is faster because the participant has already read the document — a learning effect that would be indistinguishable from a policy effect, and would inflate the result in the proposed model's favour if ordering were not perfectly balanced.

Matched pairs are equivalent in structure — same record type, same number of offices, same declining stage, comparable document length and complexity — but different in content. Combined with counterbalancing, this controls the threat rather than hoping it cancels.

**Matching must be documented and, ideally, checked** — ask a pilot participant whether the two scenarios in a pair felt comparable in difficulty. Record the answer.

### Why a separate instance

`RESTART_ALL` resets live clearance rows. Running it on the customer's production instance during the Weeks 11–12 pilot would corrupt real workflow state. Instance-per-tenant ([ADR-005](../adr/005-instance-per-tenant.md)) makes the second instance ~1 hour of provisioning. This is a hard operational rule.

---

## Scenarios

**8–10 matched pairs**, constructed from RDCO's real decline patterns (**NEEDS RDCO DATA** — see [09](09-baseline-data.md)). Each pair covers one cell:

| # | Record type | Declining stage | Offices engaged | Rationale |
|---|---|---|---|---|
| 1 | Thesis/Research | IERC (clearance) | IERC + KTTO | Core case — one office declines, one has cleared |
| 2 | Thesis/Research | KTTO (clearance) | IERC + KTTO | Symmetry check |
| 3 | Project | ITSO (sequential gate) | ITSO + KTTO | Sequential-gate decline |
| 4 | Project | IERC (clearance, post-ITSO) | ITSO + IERC + KTTO | **Maximum preservation** — two offices already cleared |
| 5 | Project | KTTO (clearance) | ITSO + IERC + KTTO | Three-office case, different decliner |
| 6 | Thesis/Research | RDCO intake (sequential) | none yet | **Control** — no clearances exist, so both policies must behave identically |
| 7 | Proposal | Adviser | none | **Control** — no clearance stage at all |
| 8 | Thesis/Research | IERC, then KTTO on re-review | IERC + KTTO | Two successive declines |

**Scenarios 6 and 7 are deliberate controls.** Where no clearance state exists, the two policies are structurally identical, so any measured difference is noise or learning effect. They calibrate the measurement and are a check on the protocol itself — a difference there means something is wrong with the design.

Scenario 4 is where the contribution should show its largest effect. If it does not show there, it does not show anywhere.

---

## Measures

Per participant, per condition, per scenario. Defined in [05](05-gqm.md).

| Measure | Metric | Captured by |
|---|---|---|
| Offices re-reviewed | M1 | `W-04` + observation |
| Offices preserved | M2 | `W-04` |
| Proportion preserved | M3 | Computed |
| Time-on-task per office review | M4 | `W-04` timestamps + stopwatch |
| Total reviewer time per scenario | M5 | Σ M4 |
| Repeat-review vs first-review time | **M6** | M4 by ordinality |
| Total workflow turnaround | M7 | `W-04` |
| Task success | M9 | Observation sheet |
| Errors and recoveries | M10 | Observation sheet |
| **Clearance-state comprehension** | **M17** | Comprehension check, asked early |

**M6 carries the practical claim.** M1–M3 count reviews; M6 is what tells you whether a preserved review saved twenty minutes or two. Without it the contribution is measured in units nobody cares about.

**M17 is the construct-validity gate.** If a participant cannot correctly state which offices cleared, their qualitative judgements about preservation are not about the phenomenon. A failed comprehension check invalidates that session's qualitative G1 data, and that must be reported rather than quietly dropped.

---

## Session protocol

**Duration:** ~90 minutes per participant.

| Step | Minutes | Content |
|---|---|---|
| 1 | 5 | Consent, recording permission, right to withdraw |
| 2 | 10 | Orientation: the system, the task, what is and is not in scope |
| 3 | 5 | **Comprehension check (M17)** — shown a record mid-clearance, participant states which offices cleared and which remain |
| 4 | 25 | **Condition 1** — 3–4 scenarios under the assigned policy |
| 5 | 5 | Break — reduces carry-over |
| 6 | 25 | **Condition 2** — matched scenarios under the other policy |
| 7 | 15 | Semi-structured interview: which felt better, why, **when would you prefer full re-review** (M20) |
| 8 | 5 | SUS (if not already administered) |

**Facilitator script rules.** Conditions are "Policy A" and "Policy B" throughout. The facilitator never indicates which is proposed. No leading language — not *"notice how much work that saved"*. Participants are told explicitly that either policy may prove better and that a finding of "no difference" is a useful result. Deviations are logged.

---

## Sample size — justification, not a number pulled from air

**The population is bounded, not chosen.** IRIS's clearance workflow involves four CIT-U offices. If each has 1–3 staff who perform clearance reviews, the total eligible population is roughly **4–12 people**.

This is therefore a **census of the accessible population**, not a sample. The correct methodological framing is:

- No power calculation is meaningful — you cannot recruit beyond the population
- No inferential generalisation is claimed
- Analysis is **descriptive statistics with effect sizes**, reported per participant ([11](11-analysis-plan.md))
- The unit of analysis is the **scenario-condition pair**, not the participant, which yields more observations: 8 scenarios × 2 conditions × N participants

At N=6 participants that is 96 scenario-condition observations — enough for descriptive comparison and effect size, not enough for a defensible inferential claim. **Report it that way.**

**Exact population size: NEEDS RDCO DATA** ([09](09-baseline-data.md), item 6).

---

## If organic pilot volume is sufficient

If RDCO data shows enough real submissions and declines during Weeks 11–12, report organic observations **alongside** the scenario results:

- Organic data has ecological validity the scenarios lack
- But organic data cannot be counterfactual — you cannot run the same real submission under both policies
- So organic data supports M1, M2, M3, M4, M7, M8 descriptively, and the **comparison** still rests on the scenario sessions

This is a complement, not a substitute. Plan the scenario sessions regardless of what RDCO volume turns out to be.

---

## Threats and controls

| Threat | Control |
|---|---|
| **Learning effect** | Matched-not-identical scenarios · counterbalanced order · break between conditions · order recorded and inspected in analysis |
| **Order effects** | AB/BA alternation; if N is odd, the imbalance is reported |
| **Demand characteristics** | Neutral labelling; scripted prompts; explicit statement that either result is useful |
| **Experimenter bias** | Metrics pre-registered here before data collection; fixed scenarios; deviations logged |
| **Fatigue** | 90-minute cap; break; SUS last |
| **Construct invalidity** | **M17 comprehension check** — and `W-07` must ship, or the contribution is invisible |
| **Scenario artificiality** | Built from RDCO's real decline patterns; controls (6, 7) calibrate |
| **Small N** | Census framing; descriptive analysis; no inferential claim |

---

## Possible outcomes, all reportable

The protocol is written so that each of these is a publishable finding:

1. **Clearance-aware materially reduces repeated review and reviewer time.** The expected result; report effect sizes and SME reasoning.
2. **It reduces repeated *reviews* but not much reviewer *time*** — because repeat reviews are cheap (low M6). A more interesting finding than (1): it qualifies the practical value and identifies where the model matters most.
3. **No meaningful difference.** Valid. Likely explanations to investigate: too few offices engaged per record; repeat reviews already cheap; the effect needs longer workflows to appear.
4. **SMEs prefer restart-all in identifiable cases** (M20). The most interesting outcome — a genuine boundary condition, and grounds for keeping the policy configurable in the product.
5. **Comprehension fails (low M17).** The contribution is real but unusable as presented. A design finding, and an argument that `W-07` needed to go further.

**Outcome 3 is not a failure of the thesis.** A negative or null result, honestly obtained and reported with its limitations, is a legitimate contribution — and defensible in a way that an arithmetic identity is not.

---

## Dependencies

| Requirement | Task | Deadline |
|---|---|---|
| Restart-all policy configurable | `W-02` | Week 7 |
| Transition table | `W-01` | Week 7 |
| **Clearance state visible** | **`W-07`** | **Before any session** |
| Instrumentation live | `W-04` | **Week 10 — hard** |
| Evaluation instance | `SA-02` provisioning | Week 10 |
| Scenarios built | This document + RDCO patterns | Week 10 |
| Participants scheduled | [10](10-respondent-plan.md) | Week 10 |
| Ethics/consent approved | **NEEDS ADVISER CONFIRMATION** | Week 3 |
