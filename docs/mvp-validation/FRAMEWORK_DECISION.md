# Framework Decision

**Status:** Proposed — **NEEDS ADVISER CONFIRMATION**
**Date:** 2026-09-01
**Supersedes:** the informal framework stack proposed during the architecture design interview

---

## Selected framework

**ISO 9241-11:2018 — Usability: definitions and concepts.**

Usability as **effectiveness**, **efficiency** and **satisfaction** within a **specified context of use**.

One framework, not a stack. Everything else below is either a method for deriving metrics, an instrument for collecting one dimension, or an experimental design that tests the research contribution — none is a competing framework.

---

## Supporting methods

| Element | Role | Justification |
|---|---|---|
| **GQM** | Derivation method, methodology section | Answers *"why these metrics?"* Presented as method, not as a second framework |
| **SUS** | Satisfaction instrument | **Already mandatory** — `NFR-U1` requires mean SUS ≥ 75 across ≥3 role groups, questionnaire in SRS Appendix B |
| **Task success rate** | ISO effectiveness measure | Standard operationalisation |
| **Time-on-task** | ISO efficiency measure | Converts "reviews preserved" into "effort preserved" |
| **Domain workflow metrics** | ISO effectiveness and efficiency, **context-specific** | Preserved clearances, offices re-reviewed, per-stage and total turnaround |
| **Within-subjects controlled comparison** | Experimental design testing the contribution | The only element that can yield a negative result |
| **Semi-structured SME interviews** | Qualitative strand | Primary evidence at small N; explains the quantitative results |
| **Heuristic Evaluation** | Phase 1 formative only | Costs no respondent time |
| **UAT** | Engineering activity, **not research** | Required Semester 2 deliverable; kept explicitly separate |

---

## Why this combination

**1 · ISO 9241-11's "context of use" is what makes the domain metrics legitimate.** Preserved clearances and offices re-reviewed are not extra measures bolted onto a usability framework — they are effectiveness measures specific to this context. One spine, no orphans, no second methodology to defend.

**2 · SUS is not an addition.** It is a requirement (`NFR-U1`) the design must satisfy regardless. Selecting it costs nothing and satisfies an NFR with a defined validation method.

**3 · The controlled comparison closes the gap the framework cannot.** ISO 9241-11 measures whether IRIS is usable software. It cannot measure whether *clearance-aware resubmission is better than restart-all* — a restart-all system could score SUS 85. Without the comparison, the thesis would carry a thorough usability study and an unevaluated contribution.

**4 · Everything competes for the same 6–12 people.** The evaluable population is the staff of four CIT-U offices. A second questionnaire on the same participants is not free rigour; it is fatigue that degrades both instruments. Each element earns its respondent-minutes.

**5 · The design permits failure.** If clearance-aware shows little or no advantage, that is a reportable finding about the model's boundary conditions. An evaluation that cannot fail is not evidence.

---

## Alternatives rejected

| Rejected | Why |
|---|---|
| **TAM** | A second multi-item questionnaire on the same 6–12 people. Its value comes from correlational modelling across a sample large enough to fit one, which is unavailable. **Replaced by** adoption-intent questions in the decision-maker interview guide. Reconsider if the adviser requires a formal acceptance model or the pool exceeds ~30 across institutions |
| **UEQ** | 26 items overlapping SUS on pragmatic dimensions, adding hedonic scales (novelty, stimulation) irrelevant to institutional compliance software. Nothing breaks if dropped |
| **NPS** | Arithmetically unstable at N≈10 — one detractor moves it by tens of points. Compresses a rich judgement into a number supporting no analysis. May appear in the commercial deck, labelled indicative and reported with N; **must not** appear as research evidence |
| **Cognitive Walkthrough** | Good theoretical fit for a multi-step workflow, but redundant with Heuristic Evaluation. HE gives more breadth per hour, and breadth is what Weeks 1–2 need. Reconsider as a focused method if Phase 1 shows the submission wizard specifically is where users fail |
| **Preserved-clearance counting as primary evidence** | Given which office declined, the count is deterministically computable — no variance, no possible negative result. An arithmetic identity, not a finding. Retained as a *supporting* descriptive measure only |
| **Manual-process comparison as primary evidence** | Confounded by digitisation — any software beats paper, so it measures the wrong variable. Retained as **context** for the problem statement |

---

## What this measures

- Whether reviewers can complete workflow tasks successfully (**effectiveness**)
- How long tasks and workflow stages take (**efficiency**)
- How satisfied users are with the system (**satisfaction**, SUS, NFR-U1)
- **Whether clearance-aware resubmission reduces redundant office review relative to restart-all** — the contribution
- How many office reviews are preserved, and how much reviewer time that represents
- Whether SMEs judge the model an improvement over current practice, **and why**
- Whether the supporting RAG capability is relevant, grounded, correctly cited and acceptably fast

---

## What this does **not** measure

Stated here so it is not claimed later.

- **Generalisability beyond CIT-U.** Single institution, census of an accessible population. Generality is *argued* from the configurability of the model, not demonstrated
- **Whether IRIS outperforms the current manual process.** The manual baseline is contextual and confounded by digitisation
- **Long-term adoption or sustained use.** A two-week pilot cannot evidence this
- **Commercial viability.** Adoption intent is gathered qualitatively; it is not a market study
- **Statistical significance in any conventional sense.** At N≈6–12 the analysis is descriptive with effect sizes; no inferential claim is made
- **Learnability over time, accessibility conformance beyond NFR-U3, or security posture** — those are covered by separate NFR validations, not by this framework

---

## Required adviser approval

**None of the following is assumed.**

| # | Item | Why it matters |
|---|---|---|
| 1 | **The framework combination itself** | Everything downstream depends on it |
| 2 | **Whether "SBCVM" is required** | I could not reliably identify this acronym and did not guess. If it is a mandatory programme framework it becomes primary and the design adapts around it |
| 3 | **SUS wording and administration** | NFR-U1 cites SRS Appendix B; confirm that instrument is the one to use |
| 4 | **Ethics and consent process** | Human participants, recorded sessions, timing data. RA 10173 applies |
| 5 | **Acceptability of a census rather than a sample** | N is bounded by the population, not by choice |
| 6 | **Acceptability of descriptive statistics with effect sizes** | No inferential testing is proposed |
| 7 | **Whether a null result is acceptable** | The design permits one; confirm the programme does |
| 8 | **NFR-P3 amendment** | 3 s p95 complete chatbot response is not achievable against a 3–10 s LLM round-trip |
| 9 | **Separation of UAT from research evaluation** | Confirm both are expected and are distinct deliverables |
| 10 | **Whether TAM or NPS is expected regardless** | Both rejected on methodological grounds; a programme requirement overrides |

---

## Required institutional data

**No value below has been invented.** Every one is a blank to be filled by RDCO — see [09-baseline-data.md](09-baseline-data.md).

| # | Data | Blocks |
|---|---|---|
| 1 | Submissions processed per fortnight | Whether Phase 3 can be organic or must be scenario-based |
| 2 | Decline / resubmission rate | Expected number of observable resubmissions |
| 3 | Typical turnaround per stage and overall | The efficiency baseline |
| 4 | Frequency and duration of **redundant re-review** under current practice | The effort approximation — the number that turns reviews into hours |
| 5 | Which stages most commonly cause resubmission | Scenario realism |
| 6 | Number of staff per office available to participate | The achievable N |
| 7 | Anonymised historical process records, if any | Strengthens the baseline beyond recall |
| 8 | Written commitment to the Weeks 11–12 pilot, with named participants and dates | **The single highest risk to Semester 2** |

---

## Consequences if this decision stands

**Positive.** One coherent methodology, defensible and small. An NFR satisfied rather than duplicated. A contribution claim that can fail. Respondent time spent on depth rather than instrument count.

**Negative.** No formal acceptance model, so adoption evidence is qualitative. No inferential statistics, so no generalisation claim. The evaluation depends on RDCO participation, which is an external dependency with no substitute.

**Revisit if:** the adviser requires SBCVM or TAM · the respondent pool grows beyond ~30 across multiple institutions · RDCO data shows organic pilot volume is sufficient for inferential analysis · the pilot commitment falls through, in which case the scenario-based design in [07](07-workflow-evaluation.md) becomes the primary rather than the contingency.
