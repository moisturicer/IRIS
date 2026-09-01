# 06 — Validation Instruments

Two sets, kept separate. The **MVP set** (Phase 1) is a draft to be used and revised. The **Final set** (Phase 3) is the refined version.

**Instrument wording and administration: NEEDS ADVISER CONFIRMATION.** SUS is required by `NFR-U1` with the questionnaire in SRS Appendix B — confirm that is the instrument to use.

---

# Part A — MVP validation instruments (Phase 1)

## A1 · Session opening script

Read verbatim so every session starts the same way.

> *"Thank you for your time. IRIS is a system for managing research and IP disclosure submissions through institutional review. We are in early validation — this is a working prototype, not a finished product.*
>
> *Three things before we start. First, some features are not yet built: automatic PDF text extraction and the AI search assistant are not available today, so please don't judge those. What is working is the submission process, the routing between offices, the review and clearance steps, and the resubmission flow.*
>
> *Second, we are testing the system, not you. If something is confusing, that is information we need — please say so. There are no wrong answers.*
>
> *Third, I'd like to record audio so I don't have to take notes while we talk. It will be used only by our team and only for this project, and it will be anonymised in anything we write. You can ask me to stop at any point, and you can withdraw at any time with no consequence. Is that alright?"*

☐ Consent obtained ☐ Recording permitted ☐ Declined recording — notes only

---

## A2 · Observation checklist

One per participant per session.

**Participant:** ______ **Role:** ______ **Date:** ______ **Facilitator:** ______

### Comprehension check (M17) — ask before any task

Show a record mid-clearance with at least one office cleared and one pending.

> *"Looking at this screen — which offices have finished reviewing this record, and which are still to review it?"*

☐ Correct ☐ Partly correct ☐ Incorrect ☐ **Cannot tell from the screen**

Verbatim response: ________________________________________________

> **If "cannot tell from the screen" is recorded for ≥ 2 participants, `W-07` has not gone far enough. This is a blocking finding for Phase 3.**

### Task observation

| Task | Completed | Assisted | Time | Confusion points |
|---|---|---|---|---|
| Register / log in | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| Submit a record with PDF | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| Locate submission status | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| *(Reviewer)* Find pending queue | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| *(Reviewer)* Record a decision | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| *(Reviewer)* Identify cleared offices | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| *(Submitter)* Respond to a decline | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |
| *(Submitter)* Resubmit | ☐ Y ☐ N ☐ Partial | ☐ | ___ | |

**Assistance events:** ____ **Errors:** ____ **Recovered unaided:** ____

*Phase 1 timings are indicative only and are not reported as results. They exist to calibrate Phase 3 task design.*

### Free observation

Expectation violations: ________________________________________
Vocabulary mismatches (their words vs ours): ____________________
Missing information they looked for: ____________________________
Spontaneous positive reactions: _________________________________

---

## A3 · SME interview guide (offices)

30–45 minutes, semi-structured. Probe; do not read mechanically.

**Current practice — before showing IRIS**

1. Walk me through what happens when a submission reaches your office.
2. How do you know a submission is waiting for you?
3. Roughly how long does a typical review take you?
4. What happens when you decline something?
5. **When a submission comes back after revision, what do you do?** *(Probe: do you review the whole thing again, or only what changed? Does it matter whether another office had already cleared it?)*
6. Does it ever happen that you review something you had already approved? *(Probe: how often, how long does it take, how does it feel?)*
7. What is the most frustrating part of the current process?

*Questions 5 and 6 are the baseline for M18 and the problem statement. Ask them before showing the system, so the answers are not primed.*

**Reaction to the model — after the demonstration**

8. What did you understand about how a record moves between offices?
9. When you saw the resubmission, what happened to the other offices' work?
10. Does that match how you would want it to work?
11. **Can you think of a situation where you would want to review a record again even though nothing in your area changed?** *(M20 — probe hard: ethics changes, scope changes, time elapsed, regulatory obligation)*
12. What is missing that you would need before using this for real submissions?
13. What would you change about how the offices' progress is displayed?

*Question 11 is deliberately adversarial. A named boundary condition is a more interesting finding than uniform endorsement, and its absence is also worth reporting.*

**Close**

14. Anything I should have asked and didn't?
15. Would you be willing to take part again in a more structured session later in the semester? *(Phase 3 retention — ask everyone)*

---

## A4 · End-user interview guide (students, advisers)

20–30 minutes.

1. Have you submitted research or IP disclosures before? How?
2. *(After the task)* What did you expect to happen when you clicked submit?
3. Was it clear where your submission was in the process?
4. *(After seeing a decline)* What would you do next?
5. Did you understand which offices had looked at it?
6. What was the most confusing part?
7. What would make this obviously better than however you do it now?
8. Would you take part again later in the semester?

---

## A5 · Decision-maker interview guide

30 minutes. Adoption intent, replacing a TAM instrument ([01](01-framework-selection.md)).

1. What problem would you want a system like this to solve for the institution?
2. How do you currently know how many submissions are in progress, or where they are stuck?
3. *(After demonstration)* Does this address a real problem for your office?
4. **What would need to be true before you would authorise using this for actual submissions?** *(M21 — blockers)*
5. What would concern you about it? *(Probe: data confidentiality, audit, staff time, support)*
6. Who else would need to agree?
7. If it worked as demonstrated, would you want it used routinely? *(Probe the reasoning, not the yes/no)*
8. What would make this worth paying for?

---

## A6 · Heuristic evaluation sheet

One per evaluator, before external sessions.

**Evaluator:** ______ **Screens reviewed:** ______ **Date:** ______

For each of Nielsen's ten heuristics, record findings with location and severity.

| Heuristic | Finding | Screen / element | Severity |
|---|---|---|---|
| 1 Visibility of system status | | | 0–4 |
| 2 Match to the real world | | | |
| 3 User control and freedom | | | |
| 4 Consistency and standards | | | |
| 5 Error prevention | | | |
| 6 Recognition over recall | | | |
| 7 Flexibility and efficiency | | | |
| 8 Aesthetic and minimalist design | | | |
| 9 Error recovery | | | |
| 10 Help and documentation | | | |

**Severity:** 0 not a problem · 1 cosmetic · 2 minor · 3 major · 4 catastrophic.

Findings are merged across evaluators and rated by consensus before entering the Week 3 refactor.

---

## A7 · Instrument pilot questions

Ask 2–3 participants after their session.

1. Were any questions unclear or ambiguous?
2. Did we use words that don't match how your office talks about this?
3. Was anything important we didn't ask about?
4. How long did that feel? Too long?
5. *(After a draft SUS)* Did any statement not apply to your role?

---

# Part B — Final evaluation instruments (Phase 3)

Refined from Phase 1. **Do not finalise before the Phase 1 pilot** — an instrument that has never been used on the only available population is an avoidable risk.

## B1 · SUS

The standard ten-item instrument, `NFR-U1`, SRS Appendix B. Administered once per respondent at the end of the pilot, across ≥ 3 role groups.

**Administration rules:** after real use, not after a demo · same wording for everyone · no facilitator interpretation of items · record role group with each response.

**Reporting:** mean **with confidence interval**, N stated, and by role group where N permits. At N < 12 report as indicative and say so ([11](11-analysis-plan.md)).

## B2 · Scenario protocol sheet

One per participant. Session structure in [07](07-workflow-evaluation.md).

**Participant:** ____ **Office:** ____ **Order:** ☐ A→B ☐ B→A **Date:** ____

☐ Consent ☐ Recording ☐ **M17 comprehension check passed**

| Scenario | Condition | Offices re-reviewed | Offices preserved | Review time (per office) | Total time | Success | Errors |
|---|---|---|---|---|---|---|---|
| 1a | A | | | | | ☐Y ☐N ☐P | |
| 1b | B | | | | | ☐Y ☐N ☐P | |
| … | | | | | | | |

**Protocol deviations:** ______________________________________
**Facilitator notes:** _________________________________________

*Conditions are recorded as A and B throughout. The mapping to policy is held separately and applied at analysis.*

## B3 · Post-session comparison interview

15 minutes, immediately after both conditions.

1. Those two ways of handling resubmission worked differently. Describe the difference in your own words.
2. Which felt better to work with? Why?
3. Did one create work you thought was unnecessary? What kind?
4. **Was there a case where the second approach — full re-review — seemed more appropriate?** *(M20)*
5. If you handled twenty submissions a month, would the difference matter? How?
6. Anything that surprised you?

*Question 1 checks whether the participant perceived the manipulation at all. If they cannot describe the difference, their preference in Q2 is not evidence about the contribution — record that.*

## B4 · Exit interview — organic pilot

20 minutes with pilot participants at the end of Week 12.

1. How many submissions did you handle in IRIS?
2. What worked well?
3. What got in your way?
4. Did you ever have to go outside the system? What for?
5. Compared with your usual process, what was better and what was worse?
6. Would you keep using it? What would need to change first?
7. Did you notice anything about how resubmissions were handled? *(Unprompted recall of the contribution — do not lead)*

## B5 · Timed submission task — NFR-U2

Five first-time student participants, after a one-hour onboarding.

**Task:** complete a full IP disclosure submission including PDF upload and consent acknowledgment, unassisted.

**Pass criterion:** all five complete within **10 minutes** (NFR-U2, verbatim).

| Participant | Start | End | Duration | Completed | Assistance |
|---|---|---|---|---|---|
| 1–5 | | | | ☐Y ☐N | ☐Y ☐N |

*Any assistance given voids the unassisted criterion for that participant and must be recorded, not quietly excluded.*

---

## Instrument change log

Phase 1 → Phase 3 revisions are recorded here, so the thesis can state how the instrument was developed.

| Date | Instrument | Change | Reason |
|---|---|---|---|
| | | | |
