# 13 — Data Collection Plan

Logistics: what is collected, by what mechanism, when, by whom, and how it is stored and protected.

---

## Data inventory

| # | Data | Mechanism | Phase | Owner |
|---|---|---|---|---|
| 1 | Workflow event log — decisions, stages, timestamps | `W-04` instrumentation | 3 | Backend dev |
| 2 | Per-office queue-entry and decision times | `W-04` | 3 | Backend dev |
| 3 | Offices reset / preserved per resubmission | `W-04`, computed at resubmission | 3 | Backend dev |
| 4 | Task success, assistance, errors | Observation sheet | 1 + 3 | Facilitator |
| 5 | Session task timings | Stopwatch | 1 + 3 | Facilitator |
| 6 | Clearance-state comprehension (M17) | Observation sheet | 1 + 3 | Facilitator |
| 7 | SUS responses | Questionnaire | 3 | Facilitator |
| 8 | NFR-U2 timed submission | Timed observation | 3 | Facilitator |
| 9 | Interview audio and transcripts | Recorder + transcription | 1 + 3 | Facilitator |
| 10 | Heuristic evaluation findings | HE sheet | 1 | Each evaluator |
| 11 | Baseline process data | RDCO request + interview | 1 | Team lead |
| 12 | RAG evaluation results | Scripts + rubric | 3 | AI dev |
| 13 | NFR validation results | Test execution | 2 | QA owner |
| 14 | Support contacts during pilot | Log | 3 | Team lead |

---

## Instrumentation: what `W-04` must capture

**The single highest-risk dependency in the plan.** If this is not live before Week 11, Strand A produces no quantitative data and there is no way to recover it.

Per event, in `AuditEvent.metadata`:

| Field | Purpose |
|---|---|
| `event_type` | `REVIEW_DECISION` / `CLEARANCE_DECISION` |
| `record_id`, `stage`, `office` | Identity |
| `decision` | approved / declined / rejected / cleared |
| `resulting_status` | Pipeline state after the transition |
| `queue_entered_at` | **When this office could first act** |
| `decided_at` | When the decision was recorded |
| `review_ordinality` | **1st, 2nd, 3rd review of this record by this office** — enables M6 |
| `offices_reset[]`, `offices_preserved[]` | On resubmission events |
| `resubmission_policy` | Which policy was active |
| `actor_role` | Who acted |

**Three details that are easy to miss and expensive to discover late:**

1. **`queue_entered_at`** — without it, time-on-task cannot be computed at all. It is not the same as the record's `updated_at`.
2. **`review_ordinality`** — without it, M6 (repeat vs first review) is impossible, and M6 is what converts reviews into effort.
3. **`offices_preserved` must be computed and stored at resubmission time**, because `resubmit_record` deletes clearance rows on sequential-decline resubmissions (`reviews/services.py:381`). Reconstructing it afterwards is impossible.

**Verification before Week 11:** run a seeded workflow end to end, export the events, and confirm every metric in [05](05-gqm.md) can be computed from the export. Do this in Week 10, not Week 11.

---

## Session logistics

**Roles.** Facilitator (runs the session, does not take notes) · Observer (completes the observation sheet, operates the stopwatch) · optional Technical support for the first sessions.

**Two people per session.** A facilitator who is also note-taking will miss things, and participants notice divided attention.

**Setup.** A prepared instance with seeded scenario data · participant accounts created in advance and tested · audio recorder tested before the participant arrives · consent forms printed or ready.

**Location.** The participant's own office where possible. It is more convenient for them, it improves attendance, and it is closer to their real working context.

**Timing.** Phase 1: 30–60 minutes. Phase 3 scenario sessions: 90 minutes with a mid-session break.

---

## Schedule

| Week | Collection |
|---|---|
| **1** | Heuristic evaluation · baseline request issued |
| **2** | Phase 1 sessions (9–17) · baseline follow-up · instrument pilot |
| **3** | Synthesis; instrument revision |
| **8–9** | NFR validations; UAT |
| **10** | **`W-04` verification** · scenario pilot with one participant · Phase 3 scheduling confirmed |
| **11–12** | Organic pilot (passive) · SUS · NFR-U2 task · scenario sessions · exit interviews |
| **12** | RAG evaluation |
| **13–15** | Analysis and write-up |

---

## Storage and protection

**RA 10173 applies.** Participant data, session recordings and timing records are personal data.

| Data | Storage | Retention |
|---|---|---|
| Recordings | Encrypted, team-access only | **Deleted after transcription and analysis** |
| Transcripts | Encrypted, **anonymised at transcription** | Retained for the thesis |
| Observation sheets | Digitised, pseudonymised | Retained |
| SUS responses | Pseudonymised, role group recorded | Retained |
| `W-04` export | Pseudonymised on export — actor id → role label | Retained |
| Consent forms | Separate from data, restricted access | Per institutional policy |
| Baseline data | As RDCO specifies; treat as confidential | Per agreement |

**Anonymisation rules.** Participants identified by role and office only — "IERC reviewer 1". No names, no email addresses, no employee identifiers in any analysis file or output. The mapping from pseudonym to person is held in one place, separately from the data.

**Exact retention periods and the required consent wording: NEEDS ADVISER CONFIRMATION.**

---

## Quality control

| Risk | Control |
|---|---|
| Facilitator drift between sessions | Scripted opening ([06](06-validation-instruments.md)); same facilitator for all Phase 3 SME sessions where possible |
| Inconsistent observation | Single observer for Phase 3; sheet completed during, not after |
| Timing inconsistency | Defined start and stop points per task, written on the sheet |
| Recording failure | Test before each session; observer notes as backup |
| Instrumentation gaps | Daily check during the pilot that events are being written |
| Lost data | Daily verified backup (`D-04`) |
| Protocol deviation | Logged on the session sheet and reported in the analysis |

---

## Contingencies

| If | Then |
|---|---|
| **`W-04` is not live by Week 10** | Manual timing in Strand B sessions — stopwatch and observation sheet. Preserves RQ1; loses Strand A quantitative data. **Report the loss** |
| A participant declines recording | Proceed with notes; mark the transcript lower-fidelity |
| A session is cut short | Record what was completed; do not compress the protocol to fit |
| Instrumentation is found to be wrong mid-pilot | Fix, note the affected window, and exclude that window from analysis |
| A participant withdraws | Delete their data on request; report the withdrawal and adjust N |
| The pilot instance fails during Weeks 11–12 | Restore from backup (`D-04`); note the outage; assess timing-data impact |

---

## Pre-collection checklist

**Phase 1** — ☐ Gate 0 passed ☐ instruments printed ☐ recorder tested ☐ consent forms ready ☐ accounts created and tested ☐ scenario data seeded ☐ facilitator and observer assigned ☐ sessions confirmed

**Phase 3** — ☐ Gate 3 passed ☐ `W-04` verified end to end ☐ export confirmed to produce every metric ☐ evaluation instance provisioned ☐ scenarios matched and pilot-tested ☐ order assignment prepared ☐ participants confirmed with dates ☐ ethics confirmed ☐ backups verified ☐ **system freeze in effect**
