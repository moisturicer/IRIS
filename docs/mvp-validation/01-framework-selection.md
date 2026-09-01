# 01 — Framework Selection

Twelve candidates evaluated against nine criteria. **Five are selected, six rejected, one cannot be evaluated without clarification.**

The governing principle: *do not use multiple frameworks to make research appear rigorous.* Every framework in the final set must answer a question the others cannot, and must survive the question *"what breaks if we drop it?"*

---

## Evaluation criteria

Each candidate is assessed on: fit with research objectives · fit with target users · fit with software type · fit with measurable outcomes · instrument complexity · statistical burden · qualitative value · thesis defensibility · adviser review burden.

**Context that constrains all of it:** the evaluable population is the staff of four CIT-U offices — plausibly 6–12 people. Every instrument competes for the same scarce respondent time. A second questionnaire administered to the same eight people is not free rigour; it is respondent fatigue that degrades both instruments.

---

## The candidates

### ✅ ISO 9241-11 — **SELECTED as the primary framework**

Defines usability as effectiveness, efficiency and satisfaction **within a specified context of use**.

| Criterion | Assessment |
|---|---|
| Research objectives | Strong. The contribution is a workflow that reviewers *use*; effectiveness and efficiency are the natural measures |
| Target users | Strong. Institutional reviewers performing defined tasks |
| Software type | Strong. Task-oriented workflow software is exactly its domain |
| Measurable outcomes | Strong. Task success, time-on-task and satisfaction are directly operationalisable |
| Instrument complexity | **Low** — it is a definition, not a questionnaire |
| Statistical burden | Low. Descriptive statistics suffice |
| Qualitative value | Neutral; accommodates qualitative data through context of use |
| Defensibility | **High.** An ISO standard, widely used, uncontroversial |
| Adviser burden | Low |

**Why it wins:** the "context of use" clause is what lets the domain-specific workflow metrics — preserved clearances, offices re-reviewed, per-stage turnaround — live *inside* the framework as context-specific effectiveness and efficiency measures, rather than being bolted alongside as a second methodology. One spine, no orphans.

**What it does not measure:** adoption intention, commercial viability, or whether the *model* is better than an alternative model. That last gap is why the controlled comparison exists.

---

### ✅ GQM — **SELECTED, but demoted to a method**

Goal–Question–Metric: a derivation technique linking research goals to measurements.

**Selected because** it answers *"why these metrics and not others?"* — the question a panel asks when domain metrics appear. Without it, preserved-clearance counting looks arbitrary.

**Demoted because** presenting GQM as a co-equal framework alongside ISO 9241-11 invites *"why do you need two frameworks?"* for no analytical gain. It belongs in the methodology chapter as the derivation, with its output — the metric set in [05-gqm.md](05-gqm.md) — presented under ISO 9241-11's three dimensions.

**Cost:** zero instrument burden. It is documentation of reasoning.

---

### ✅ SUS — **SELECTED as the satisfaction instrument**

Ten-item questionnaire producing a 0–100 score.

**Selected because it is already mandatory.** `NFR-U1` requires *"a minimum mean SUS score of 75 … measured by a representative survey of CIT-U IRIS users across at least three role groups,"* with the questionnaire in SRS Appendix B. It is not an addition to the design; it is a requirement the design must satisfy.

It also fills ISO 9241-11's satisfaction dimension with a validated, benchmarked instrument, which is stronger than an ad-hoc satisfaction question.

**Caveat, to be stated:** SUS means are unstable below roughly 12–15 respondents. At N≈10 report the mean **with a confidence interval** and treat it as indicative. Do not report a single decimal place as though precise.

**What it does not measure:** anything about the workflow model. A restart-all system could score 85. This is the category error [ADR-011](../adr/011-evaluation-framework.md) warns about, and the reason SUS alone cannot evidence the contribution.

---

### ✅ Task Success Rate — **SELECTED (it is ISO's effectiveness measure)**

Not a separate framework. The standard operationalisation of ISO 9241-11 effectiveness. Binary or graded completion per task, per participant.

**Cost:** an observation checklist. No extra respondent time.

---

### ✅ Time-on-Task — **SELECTED (it is ISO's efficiency measure)**

Not a separate framework. Elapsed time per task.

**Critical to the contribution**, because it converts "reviews preserved" into "effort preserved." Re-reviewing an already-cleared document plausibly costs a fraction of the original review; counting *reviews* overstates the benefit unless duration is measured. Captured both by observation (scenario sessions) and by instrumentation (`W-04`: office queue-entry timestamp → decision timestamp).

---

### ✅ Heuristic Evaluation — **SELECTED for Phase 1 only**

Nielsen's ten heuristics, applied by 3–5 evaluators without users.

**Selected because it costs no respondent time.** In Weeks 1–2 the scarce resource is stakeholder availability, and HE lets the team find interface problems *before* spending an SME's hour on them. Finding a broken form through heuristic inspection is free; finding it during an SME session costs a slot you cannot recover.

Nielsen's finding that ~5 evaluators surface ~75–85% of usability problems gives a defensible basis for using the four team members plus, if available, one outside evaluator.

**Phase 1 only.** It is a formative discount method, not summative evidence. It does not appear in the final evaluation.

---

### ❌ TAM — **REJECTED for the research evaluation; deferred to interviews**

Technology Acceptance Model: perceived usefulness and perceived ease of use predicting behavioural intention.

**Genuine appeal.** The commercial defence asks *"will institutions adopt this?"* and TAM measures exactly that construct with validated scales.

**Rejected because** it is a second multi-item questionnaire administered to the same 6–12 people who are already completing SUS and participating in a two-arm scenario session. At that N, a TAM score carries no more evidential weight than a direct interview question — and TAM's value comes from correlational analysis across a sample large enough to fit a model, which is not available here.

**Replaced by:** targeted adoption-intent questions in the decision-maker interview guide ([06](06-validation-instruments.md)). Qualitative adoption evidence from the people who would actually authorise purchase is stronger at this scale than a TAM mean at N=10.

**Reconsider if:** the adviser requires a formal acceptance model, or the respondent pool exceeds ~30 across multiple institutions. **NEEDS ADVISER CONFIRMATION.**

---

### ❌ UEQ — **REJECTED (redundant)**

User Experience Questionnaire: 26 items, six scales including novelty, stimulation and attractiveness.

**Rejected because** it overlaps SUS on the pragmatic dimensions and adds hedonic ones — novelty, stimulation — that are close to meaningless for institutional compliance software. Nobody adopts an IP clearance workflow because it is stimulating. It would cost 26 additional items per respondent to measure constructs the research questions do not ask about.

**What breaks if dropped:** nothing. SUS covers satisfaction; interviews cover experience qualitatively.

---

### ❌ NPS — **REJECTED as a research metric**

Single item: likelihood to recommend, 0–10, reported as a net score.

**Rejected because** NPS is arithmetically unstable at small N — a single detractor can move the score by tens of points at N=10 — and it compresses a rich judgement into one number that supports no analysis. It is a business-tracking metric designed for continuous large-sample measurement.

**Possible non-research use:** as one line in the commercial defence deck, clearly labelled as indicative and reported with N. It must not appear in the evaluation chapter as evidence. **Optional; adviser's call.**

---

### ❌ Cognitive Walkthrough — **REJECTED in favour of Heuristic Evaluation**

Expert task-based inspection asking, at each step, whether the user would know what to do and notice progress.

**Genuinely good fit** for a multi-step submission and review workflow — arguably a better theoretical fit than HE for this system.

**Rejected on marginal value.** Running both is redundant; the choice between them is close. HE wins here on breadth per hour: it surfaces layout, feedback, error-handling and consistency problems across the whole interface, whereas CW goes deep on a single task path. In Weeks 1–2 the team needs breadth — the pages have never been used by anyone outside the team.

**Reconsider if:** Phase 1 shows the submission wizard specifically is where users fail. A focused CW on that flow in Week 3 would then be well targeted.

---

### ⚠️ UAT — **SELECTED, but as engineering, not research**

User Acceptance Testing: stakeholder verification that the system meets agreed acceptance criteria.

**This is a required Semester 2 deliverable** and it is *not* a research framework. The distinction matters and should be explicit in the thesis:

| | UAT | Research evaluation |
|---|---|---|
| Question | Does it meet the agreed requirements? | Does the proposed model work, and how well? |
| Output | Pass / fail per criterion | Measurements and findings |
| Can it fail usefully? | Failure = defect to fix | A null result is a valid finding |
| Audience | Customer | Panel and readers |

Both are planned. UAT runs in Weeks 8–9 against the acceptance criteria in `docs/architecture-tasks/`; the research evaluation runs in Weeks 11–12. Conflating them — reporting UAT passes as research findings — is a defensibility failure.

---

### ❌ SBCVM — **REJECTED for the research evaluation; sense (3) belongs to the commercial track**

Three candidate meanings were supplied. **None is a software-quality or usability evaluation framework**, so none competes with ISO 9241-11 for the primary role.

| Sense | What it is | Fit with this evaluation |
|---|---|---|
| **Structured-Byte Code Real-Time Virtual Machine** (SBC-RVM) | A runtime / virtual-machine technology | **None.** An implementation technology, not an evaluation method. Nothing in IRIS uses or resembles it |
| **Structure-Behavior Coalescence** (SBC) | A systems-architecture description approach | **None for evaluation.** Conceivably relevant to *describing* architecture in the SDD, but it does not measure effectiveness, efficiency, satisfaction or the contribution |
| **Startup Business Company Validation Methodology** | Business / market validation, tool-supported | **None for research validation** — but genuinely relevant to the **commercial** track |

**The third sense exposes a real gap**, and it is worth stating plainly rather than burying.

Semester 2 contains **two distinct validation questions**, and they require different methods:

| | **Research validation** | **Commercial validation** |
|---|---|---|
| Question | Does the workflow contribution work? | Is this a viable business? |
| Framework | ISO 9241-11 + controlled comparison | Customer discovery, willingness to pay, Lean Canvas, BMC |
| Evidence | Effect sizes, SUS, SME themes | Paying customer, transaction evidence, market analysis |
| Deliverable | Evaluation chapter | Commercial defence, pitch deck |
| Weeks | 11–12 | 11–15 |
| Covered here | **Thoroughly** | **Thinly** — adoption intent (M21) and the decision-maker guide only |

**Conclusion.** SBCVM does not enter the research evaluation design in any of its three senses. If the programme intends sense (3), it belongs in the commercialisation track alongside Lean Canvas and the Business Model Canvas — and that track needs more structure than this document set currently gives it.

**Still open:** which sense the programme intends, and whether it is *required*. The definitions above are general; they are not a statement of what this programme means by the acronym. **NEEDS ADVISER CONFIRMATION** ([14](14-adviser-review.md) A3).

**If it turns out to be a required *research* framework** under a definition not listed above, this analysis is void and the design must be revisited — which is why the question is still tracked rather than closed.

---

## Summary

| Framework | Verdict | Role | Cost |
|---|---|---|---|
| **ISO 9241-11** | ✅ Selected | Primary spine | None (definition) |
| **GQM** | ✅ Selected | Derivation method, methodology section | None |
| **SUS** | ✅ Selected | Satisfaction; already NFR-U1 | 10 items |
| **Task success** | ✅ Selected | ISO effectiveness | Observation |
| **Time-on-task** | ✅ Selected | ISO efficiency; converts reviews → effort | Observation + `W-04` |
| **Heuristic Evaluation** | ✅ Selected | Phase 1 only, no respondent cost | ~4 hours |
| **UAT** | ✅ Selected | Engineering activity, **not research** | Weeks 8–9 |
| TAM | ❌ Rejected | Replaced by interview questions | — |
| UEQ | ❌ Rejected | Redundant with SUS | — |
| NPS | ❌ Rejected | Unstable at this N | — |
| Cognitive Walkthrough | ❌ Rejected | HE gives more breadth per hour | — |
| SBCVM | ❌ Rejected | Not an evaluation framework in any supplied sense; the startup-validation sense belongs to the **commercial** track | — |

**Plus, and separately from any of the above:** the **within-subjects controlled comparison** of clearance-aware against restart-all resubmission ([07](07-workflow-evaluation.md)). This is not a framework — it is the experimental design that tests the contribution, and it is the only element that can produce a negative result.

---

## Challenge to the team's proposed structure

The proposal was:

> PRIMARY: ISO 9241-11 · STRUCTURING: GQM · SUPPORTING: Task Success, Time-on-Task, SUS · DOMAIN-SPECIFIC: workflow metrics · QUALITATIVE: SME interviews

**Substantially correct, with three changes.**

1. **It is smaller than it looks and should be presented that way.** Task success, time-on-task and SUS are not "supporting frameworks" — they are ISO 9241-11's own three dimensions operationalised. Presenting five things where there is one framework and three measures invites a question with no good answer. Present one framework with three dimensions.

2. **The domain metrics belong *inside* ISO, not beside it.** "Context of use" explicitly permits domain-specific effectiveness measures. Preserved clearances and offices re-reviewed are effectiveness; per-stage turnaround is efficiency. Listing them as a separate category makes them look unjustified.

3. **The structure has a gap it does not close: nothing in it can produce a negative result.** ISO 9241-11 with SUS measures *whether IRIS is usable software*. It does not measure *whether clearance-aware resubmission is better than the alternative*. The controlled comparison is the missing element, and it must be named as a distinct component of the design rather than folded into "workflow metrics."

**Net: one framework, one method, one instrument, two observational measures, one experiment, one qualitative strand.** That is the smallest defensible combination, and every element answers something the others cannot.
