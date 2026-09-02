# 04 — Research Questions & SMART Goals

Research objective → SMART goals → research questions. Each RQ must be answerable with data the design actually collects.

---

## Research objective

> To propose and evaluate a **type-differentiated institutional IP workflow** in which parallel multi-office clearance maintains per-office clearance state, such that resubmission after a decline resets only the declining office and preserves the completed work of unaffected offices.

Recorded as [ADR-003](../adr/003-clearance-aware-resubmission.md). RAG is a supporting capability, not part of the claim.

---

## SMART goals

Each is Specific, Measurable, Achievable, Relevant and Time-bound. Targets marked **NEEDS RDCO DATA** cannot be set until baseline collection completes — setting them now would be inventing values.

### SG-1 · Demonstrate the workflow model

> By **end of Week 7**, IRIS shall execute all three type-differentiated routes end to end — Proposal, Thesis/Research and Project — including parallel multi-office clearance and clearance-aware resubmission, with **per-office clearance state visible in the user interface**, verified by an automated transition test suite covering every legal edge and by a walkthrough of each route.

- **Specific:** three routes, parallel clearance, clearance-aware resubmission, visible state
- **Measurable:** `T-03` test suite passes; `V-09` walkthrough completes; `W-07` shipped
- **Achievable:** the workflow is the most complete part of IRIS; `W-01`, `W-02`, `W-07` total ~4.5 dev-days
- **Relevant:** without this there is nothing to evaluate
- **Time-bound:** Week 7

### SG-2 · Evaluate the contribution

> By **end of Week 12**, the difference between clearance-aware and restart-all resubmission shall be measured under a counterbalanced within-subjects design with the accessible population of CIT-U reviewing-office staff, reporting offices re-reviewed, time-on-task, task success and total workflow turnaround for both conditions, **with the result reported whether or not it favours the proposed model**.

- **Specific:** two conditions, four measures, named population
- **Measurable:** paired measurements per participant per condition
- **Achievable:** scenario-based design bounds it to a scheduled session ([07](07-workflow-evaluation.md))
- **Relevant:** this is the contribution's evidence
- **Time-bound:** Week 12

### SG-3 · Establish usability and acceptance

> By **end of Week 12**, IRIS shall achieve a mean SUS score of **≥ 75** across respondents spanning **at least three role groups** (`NFR-U1`), and **all five** first-time student participants shall complete a full IP disclosure submission including PDF upload and consent within **10 minutes** unassisted after a one-hour onboarding (`NFR-U2`).

- Targets and validation methods taken verbatim from the SRS, not invented
- **Time-bound:** Week 12

### SG-4 · Establish the supporting AI capability *(conditional)*

> By **end of Week 12**, the RAG capability shall return the expected document in the top 5 for **≥ 80%** of a fixed 20-query relevance set, produce **zero** citations to records the querying user may not access, produce **zero** fabricated answers on questions with no supporting record, and degrade to full-text search with a visible indicator when AI services are unavailable.

**Conditional on `R-04` completing within its 3-day timebox** ([ADR-006](../adr/006-minimum-rag-pipeline.md)). If it does not, this goal reduces to semantic search only and generation is reported as Phase 2. The 80% threshold is a design target for a fixed internal query set, not a benchmark claim.

---

## Research questions

### RQ1 — The contribution *(primary)*

> **Does clearance-aware resubmission reduce redundant office review, relative to restart-all resubmission, in a type-differentiated parallel multi-office clearance workflow?**

**Sub-questions**

- **RQ1.1** — How many office reviews are repeated under each condition?
- **RQ1.2** — How much reviewer time does the difference represent? *(reviews → effort)*
- **RQ1.3** — Does total workflow turnaround differ between conditions?
- **RQ1.4** — Does task success differ between conditions?

**Answered by:** the within-subjects controlled comparison ([07](07-workflow-evaluation.md)), plus `W-04` instrumentation.
**Possible answers include:** *"no meaningful difference"* and *"a difference smaller than expected."* Both are valid findings and the protocol is designed to surface them.

### RQ2 — Usability of the model

> **Is the type-differentiated parallel clearance workflow effective, efficient and satisfying for institutional reviewers and submitters?**

**Sub-questions**

- **RQ2.1** — Can reviewers complete their stage tasks successfully? *(effectiveness)*
- **RQ2.2** — How long do stage tasks and full workflow traversals take? *(efficiency)*
- **RQ2.3** — How do users rate overall usability? *(satisfaction, SUS, NFR-U1)*
- **RQ2.4** — Can a first-time submitter complete a disclosure within 10 minutes after onboarding? *(NFR-U2)*

**Answered by:** ISO 9241-11 measures across Phase 1 and Phase 3.

### RQ3 — Expert judgement

> **Do subject-matter experts from the reviewing offices judge clearance-aware resubmission an improvement over current practice, and what reasons do they give?**

**Sub-questions**

- **RQ3.1** — What problems does current practice cause, in the offices' own terms?
- **RQ3.2** — Which aspects of the model do SMEs identify as beneficial or problematic?
- **RQ3.3** — Under what circumstances would an office *prefer* full re-review?
- **RQ3.4** — Would decision-makers adopt the system, and what would they require first?

**Answered by:** semi-structured interviews ([06](06-validation-instruments.md)).
**Why it carries weight:** at N≈6–12, expert reasoning is stronger evidence than a mean. RQ3.3 is deliberately adversarial — it invites SMEs to argue *against* the contribution, which is where a genuine boundary condition would surface.

### RQ4 — Supporting capability

> **Does the RAG capability return relevant, grounded, correctly-cited answers within acceptable latency, and fail safely when unavailable?**

**Sub-questions:** retrieval relevance · answer groundedness · citation correctness and **permission-safety** · latency against the amended NFR-P3 · behaviour under provider failure.

**Answered by:** the lightweight evaluation in [08](08-rag-evaluation.md). Conditional on `R-04`.

---

## Traceability

| RQ | SMART goal | GQM goal | Instrument | NFR / FR | Phase |
|---|---|---|---|---|---|
| RQ1 | SG-2 | G1 | Scenario protocol, observation sheet, `W-04` export | FR-M5-01 | 3 |
| RQ2 | SG-1, SG-3 | G2 | Task observation, SUS, timed submission | NFR-U1, U2, P2 | 1 + 3 |
| RQ3 | SG-2 | G1, G3 | SME interview guide, decision-maker guide | FR-M5-01 | 1 + 3 |
| RQ4 | SG-4 | G4 | Query set, groundedness rubric, latency script | FR-M4-01, NFR-P3 | 3 |

---

## Questions deliberately **not** asked

Recorded so their absence is a decision rather than an oversight.

| Not asked | Why |
|---|---|
| *Does IRIS outperform CIT-U's manual process?* | Confounded by digitisation — it would measure the effect of software, not of the clearance model. The manual baseline provides **context** for the problem, not a treatment comparison |
| *Would other institutions adopt IRIS?* | Single-institution study. Generality is argued from configurability ([ADR-002](../adr/002-workflow-transition-table.md)), not claimed from data |
| *Is IRIS commercially viable?* | Not a market study. Adoption intent is gathered qualitatively for the commercial defence |
| *Does the model improve outcomes over months?* | A two-week pilot cannot answer a longitudinal question |
| *Is IRIS more usable than a named competitor?* | No comparator system is available, and a fair comparison would require equivalent configuration and training |

---

## Threats to validity

Stated in the thesis rather than left for the panel to find. Full treatment in [11](11-analysis-plan.md).

| Threat | Type | Mitigation |
|---|---|---|
| **Learning effect** — the second scenario run is faster regardless of condition | Internal | Counterbalanced order **and matched-but-not-identical scenarios**; order included in analysis |
| **Experimenter bias** — the researchers built the system and run the sessions | Internal | Pre-registered metrics and fixed scenarios; scripted prompts; a protocol permitting a null result |
| **Demand characteristics** — participants infer the hoped-for answer | Internal | Conditions presented neutrally as "Policy A / Policy B", never as "ours / the baseline" |
| **Small N** | Statistical conclusion | Census of the accessible population; descriptive statistics and effect sizes only; no inferential claim |
| **Single institution** | External | Explicitly scoped; generality argued from configurability |
| **Scenario artificiality** | Ecological | Scenarios built from RDCO's real decline patterns (**NEEDS RDCO DATA**); organic pilot data reported alongside where volume permits |
| **Invisible contribution** | Construct | **`W-07` must ship** — participants cannot assess a benefit the UI does not display |
