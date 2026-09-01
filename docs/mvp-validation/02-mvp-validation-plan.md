# 02 — MVP Validation Plan (Phase 1, Weeks 1–2)

**Formative, not summative.** The purpose is to validate needs, find gaps, refine scope and **refine the instrument** — not to produce statistical findings. Nothing gathered here is reported as a research result.

---

## Preconditions — the system must be safe to show

Weeks 1–2 requires a deployed, accessible MVP. The inherited system does not start, and exposing it as-is would publish every uploaded document.

**Nine tasks gate any shared URL.** From `docs/architecture-tasks/`:

| Gate | Task | Days |
|---|---|---|
| Application boots | `B-01`, `B-02` | 1.5 |
| Compose builds and serves | `D-01`, `D-02` | 2 |
| `/media/` closed | `S-01` | 0.5 |
| Record + document authorization | `S-02`, `S-03` | 2 |
| `apps/storage` removed | `SC-01` | 0.5 |
| Secrets, CORS, `ALLOWED_HOSTS` | `S-04` | 1 |
| Deployed to interim VPS | `D-03` | 1 |
| **Clearance state visible** | **`W-07`** | **1** |

**`W-07` is new and not in the current backlog.** Without it, `RecordClearance` is never serialized and the word "clearance" appears nowhere in the frontend — so the thesis contribution is invisible, and a validation session cannot show it. Add it.

**Data:** synthetic and already-published records only. No real unpublished IP until the governance question is resolved (**NEEDS CIT-U CONFIRMATION**).

**If the gate cannot be cleared in time:** run demonstrations and interviews **without live access** — a screen-shared walkthrough on a local instance. Do **not** expose an unsafe build to meet a deadline. That trade is never worth it, and a controlled demo yields better feedback than an unsupervised broken system.

---

## What can be validated

| Area | Validatable in Weeks 1–2 | Notes |
|---|---|---|
| Registration, login, role request | **Yes** | Complete |
| Record submission + PDF upload | **Yes** | Upload works; text extraction does not (Week 4) |
| Type-differentiated routing | **Yes** | All three routes |
| Parallel multi-office clearance | **Yes** | |
| **Clearance-aware resubmission** | **Yes, with `W-07`** | **The contribution** |
| Reviewer queues and decisions | **Yes** | |
| Notifications | **Yes** | |
| Full-text search | **Yes** | Only working index path |
| Audit trail | Partial | Review decisions not yet recorded (`W-04`, Week 10) |
| PDF text extraction | **No** | Libraries absent until `R-01` |
| Semantic search / chatbot | **No** | Does not exist until Week 6 |
| Summarization, chat history, dashboards | **No** | Deferred to Phase 2 |

**Set expectations explicitly in every session.** Participants told "this is the AI system" will evaluate an absence. Tell them what is in scope before they touch it — the script in [06](06-validation-instruments.md) does this.

---

## Objectives

1. Validate that the workflow model matches how the offices actually work
2. Identify gaps between the implemented workflow and real institutional practice
3. Identify usability problems before Week 4 implementation begins
4. **Pilot and refine the evaluation instrument** for Phase 3
5. Establish relationships with respondents who will return for the final evaluation
6. Gather the manual-process baseline ([09](09-baseline-data.md)) — **only possible now**
7. Produce an honest MVP validation report, including that the Semester 1 system did not start

Objectives 4, 5 and 6 are the ones that cannot be recovered later. Objective 6 in particular closes permanently once IRIS is in use.

---

## Methods

Sequenced so the cheapest filtering happens first.

### 1 · Heuristic evaluation — before any participant

**Who:** the four team members, plus one outside evaluator if available.
**When:** Week 1, before external sessions.
**How:** Nielsen's ten heuristics against the 16 KEEP screens; each evaluator works alone, then findings are merged and severity-rated 0–4.
**Why first:** it costs no respondent time. Finding a broken form here is free; finding it in an SME's one-hour slot costs a session you cannot get back.
**Output:** a severity-rated defect list feeding the Week 3 refactor.

### 2 · Guided demonstration + think-aloud

**Who:** SMEs (office staff), end users (students, advisers).
**Duration:** 45–60 minutes.
**How:** the facilitator walks a prepared scenario; the participant narrates expectations and reactions. For SMEs the scenario includes a decline and resubmission so clearance preservation is *seen*, not described.
**Captured:** observation sheet — points of confusion, incorrect expectations, missing information, comprehension of clearance state (**M17**).

### 3 · Hands-on task attempt

**Who:** a subset of end users who can attempt tasks unaided.
**Duration:** 20–30 minutes.
**How:** two or three scripted tasks — submit a record, respond to a decline, review a submission — attempted without guidance.
**Captured:** completion, assistance events, time. **Indicative only.** Phase 1 timings are not reported as results; they exist to calibrate Phase 3 task design and expected durations.

### 4 · Semi-structured interview

**Who:** all participant types, weighted toward SMEs and decision-makers.
**Duration:** 30–45 minutes.
**How:** the Phase 1 guide in [06](06-validation-instruments.md). Covers current practice, pain points, reaction to the model, and — for SMEs — **when full re-review would be preferable** (M20).
**Captured:** recorded with consent; transcribed; thematically coded.

### 5 · Instrument pilot

**Who:** two or three participants at the end of their session.
**How:** administer the draft SUS and one draft scenario; ask which items were ambiguous, whether terminology matched their vocabulary, and how long it took.
**Output:** the revised instrument for Phase 3. **This is one of the two highest-value activities of Phase 1** — a Phase 3 instrument that has never been piloted is a risk taken for no reason.

### 6 · Baseline data request

**Who:** RDCO, plus each office.
**How:** the checklist in [09](09-baseline-data.md), issued in writing in Week 1 and followed up in a scheduled conversation.
**Why now:** once IRIS is in use, the manual process is no longer observable. **This window does not reopen.**

---

## Participants

Detail in [10](10-respondent-plan.md). Phase 1 targets **quality over quota**.

| Type | Target | Method |
|---|---|---|
| SMEs — RDCO, IERC, KTTO, ITSO staff | ≥ 1 per office, **4 minimum** | Demonstration + interview |
| End users — students | 3–5 | Demonstration + hands-on |
| End users — advisers | 1–2 | Demonstration + interview |
| Decision-makers | 1–2 | Demonstration + interview |
| **Phase 1 total** | **9–13** | |

The school's 30-respondent target is a **programme-level figure across both phases**, not a Phase 1 quota. Phase 1 deliberately favours depth: thirteen people interviewed properly produce more actionable refinement than thirty questionnaires on a system nobody was walked through. **NEEDS ADVISER CONFIRMATION** that a phased distribution toward the 30 total is acceptable.

**Retention matters more than count.** Participants recruited here should carry into Phase 3 — particularly the four office SMEs, who are the population for the controlled comparison. Ask for that commitment at first contact, not in Week 10.

---

## Schedule

| Week | Activity |
|---|---|
| **1, days 1–3** | Clear the deployment gate: `B-01`, `B-02`, `D-01`, `D-02`, `S-01`, `SC-01` |
| **1, days 1–3** *(parallel, non-coding)* | Issue the RDCO data request · secure the written pilot commitment · draft instruments · recruit participants |
| **1, days 4–5** | `S-02`, `S-03`, `S-04`, `W-07`; deploy to interim VPS; **heuristic evaluation** |
| **2, days 1–3** | SME demonstrations and interviews (4 offices) · baseline follow-up conversation |
| **2, days 3–4** | Student and adviser sessions · hands-on tasks · instrument pilot |
| **2, day 5** | Decision-maker sessions · synthesis · **MVP validation report** |

Two team members on the gate, two on validation logistics. The activities are genuinely parallel — recruitment and instrument drafting are not coding work.

---

## Outputs

1. **MVP validation report** — findings, gaps, usability defects, stakeholder needs, and an honest statement of the inherited system's state
2. **Severity-rated defect list** from heuristic evaluation and sessions
3. **Refined scope** feeding the Week 3 requirements refactor (`F-03`)
4. **Refined instrument** for Phase 3
5. **Baseline data** or a documented record of what RDCO could not provide
6. **Confirmed Phase 3 participants**, with dates

---

## What triggers what

Thresholds are judgement anchors, not statistical rules. Full gate definitions in [12](12-success-criteria.md).

| Finding | Trigger |
|---|---|
| ≥ 2 SMEs describe a routing rule that differs from the implementation | **Requirements change** — into `F-03` Week 3 |
| ≥ 2 participants cannot correctly read which offices cleared (**low M17**) | **UI change**, high priority — this invalidates Phase 3's construct |
| ≥ 3 participants fail the same task, or need assistance at the same step | **UI change** before Week 4 |
| An SME identifies a workflow state the model cannot express | **Workflow change** — assess against `W-01`'s table |
| A gap requires more than ~2 dev-days to close | **Scope decision** — it competes with the ~16-day Weeks 4–7 budget |
| A decision-maker names a blocking adoption condition | **Scope decision**, and record it for the commercial defence |
| Instrument items are ambiguous to ≥ 2 participants | **Instrument revision** before Phase 3 |
| RDCO cannot supply baseline data | **Escalate.** Scenario-based evaluation becomes primary ([07](07-workflow-evaluation.md)) |

---

## Boundaries

Phase 1 does **not**:

- report statistical results
- administer the final instrument as though it were final
- evaluate features that do not exist (RAG, summarization, dashboards)
- test the clearance-aware vs restart-all comparison — that is Phase 3, needs `W-02`, and running it on an unrefined instrument would waste the only population available
- involve real unpublished IP disclosures
