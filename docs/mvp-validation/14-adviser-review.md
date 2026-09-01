# 14 — Adviser Review

Everything requiring approval or clarification before it can be treated as settled. **Nothing in these documents claims adviser approval.**

Grouped by urgency. Items in Group A block Phase 1 work that starts this week.

---

## Group A — needed in Week 1

### A1 · Ethics and consent process

**Question.** What is the required process for human-participant research in this programme? Is formal ethics review needed, or is a consent form sufficient?

**Why now.** Sessions begin in Week 2. Any approval with lead time must start immediately.

**Prepared:** consent script, recording permission, withdrawal rights, anonymisation, RA 10173 handling ([13](13-data-collection-plan.md)).

**Needed:** confirmation of the process · required consent wording · retention periods for recordings and transcripts.

**Status: NEEDS ADVISER CONFIRMATION**

---

### A2 · The framework combination

**Question.** Is the proposed structure acceptable?

> **ISO 9241-11** as the single framework · **GQM** as derivation method · **SUS** for satisfaction (already `NFR-U1`) · task success and time-on-task as ISO's own measures · domain workflow metrics inside effectiveness/efficiency · **within-subjects controlled comparison** to test the contribution · SME interviews as the qualitative strand · heuristic evaluation for Phase 1 only.

**Why now.** Everything downstream depends on it, and the instrument must be piloted in Week 2.

**Rejected, with reasons in [01](01-framework-selection.md):** TAM, UEQ, NPS, Cognitive Walkthrough.

**Status: NEEDS ADVISER CONFIRMATION**

---

### A3 · What is "SBCVM"?

**Question.** I could not reliably identify this acronym and **deliberately did not guess** — a wrong assumption would have propagated through the entire design.

**Needed:** the full name · its source · whether it is **required** by the programme or offered as an option.

**Consequence.** If it is mandatory it likely becomes the primary framework and the rest of the design adapts around it. That is a substantial change and is much cheaper now than in Week 10.

**Status: NEEDS ADVISER CONFIRMATION — blocking**

---

### A4 · Respondent count and distribution

**Question.** The programme references a 30-respondent target. Is that cumulative across Phases 1 and 3, or per phase? Is a phased distribution acceptable — 9–17 in Phase 1, 20–27 in Phase 3?

**Context.** The SME population is **bounded at roughly 4–12 people** — four offices with 1–3 reviewers each ([10](10-respondent-plan.md)). We cannot recruit a thirteenth ITSO reviewer if ITSO has two. Phase 1 deliberately favours depth: thirteen people interviewed properly yield more actionable refinement than thirty questionnaires from people never walked through the system.

**Status: NEEDS ADVISER CONFIRMATION**

---

### A5 · Baseline and pilot commitment from RDCO

**Question.** Can the adviser support or route the request to RDCO?

**Two things needed, both time-critical:**

1. **Baseline data** ([09](09-baseline-data.md)) — collectable **only in Weeks 1–3**. Once IRIS is in use the manual process stops being observable and recall becomes contaminated.
2. **Written pilot commitment** with named participants and dates — **the highest single risk to Semester 2.** Usage evidence, payment evidence, analytics and the organic evaluation strand all depend on it.

**Status: NEEDS CIT-U CONFIRMATION — highest risk**

---

## Group B — needed by Week 3

### B1 · Census rather than sample; descriptive rather than inferential

**Question.** Is it acceptable that the SME evaluation is a **census of the accessible population** rather than a sample, analysed with descriptive statistics and effect sizes, with **no inferential significance testing** as the primary result?

**Reasoning.** N is bounded by the population, not chosen. A power calculation is meaningless when you cannot recruit beyond the population. Reporting a census honestly as a census is defensible; reporting it as though it were a sample is not ([11](11-analysis-plan.md)).

**Status: NEEDS ADVISER CONFIRMATION**

---

### B2 · Is a null result acceptable?

**Question.** The design deliberately permits the finding that clearance-aware resubmission shows **little or no advantage** over restart-all. Is that an acceptable thesis outcome?

**Why it is asked directly.** The alternative — preserved-clearance counting — cannot produce a negative result, because the count is deterministically computable from which office declined. An evaluation that cannot fail is not evidence, and a panel will say so.

**If a positive result is effectively required**, that must be known now, because it changes the design — and the team should understand that the resulting evaluation would be substantially weaker.

**Status: NEEDS ADVISER CONFIRMATION**

---

### B3 · SUS instrument and administration

**Question.** `NFR-U1` requires mean SUS ≥ 75 across ≥ 3 role groups, citing SRS Appendix B. Confirm that is the instrument to use, and that administering it once at the end of the pilot (rather than after each session) satisfies the requirement.

**Note.** At N < 12 the mean will be reported **with a confidence interval and an explicit indicative caveat** — SUS means are unstable below roughly 12–15 respondents.

**Status: NEEDS ADVISER CONFIRMATION**

---

### B4 · NFR-P3 amendment

**Question.** `NFR-P3` requires a **3-second p95 for a complete chatbot response**. A single LLM round-trip is typically 3–10 seconds. **The requirement is not achievable as written.**

**Proposed amendment:** time-to-first-token ≤ 3 s, complete response ≤ 15 s p95.

**Alternatives:** keep 3 s and accept a documented failure at `V-10` · restate the metric another way · descope the chatbot.

**Evidence:** measure it in Week 7 and bring the number to the amendment discussion rather than arguing from first principles.

**Status: NEEDS ADVISER CONFIRMATION**

---

### B5 · SRS amendment procedure

**Question.** What is the procedure for Semester 2 SRS/SDD amendments — supervisor sign-off, panel approval, formal resubmission? What is the turnaround?

**Pending amendments:** NFR-P3 (B4) · the extraction hierarchy contradiction (§31 vs §481-489/§361) · Qdrant residue in §384 against §456/§624 · scope deferrals from [ADR-001](../adr/001-mvp-scope-boundary.md) · the SaaS and tenancy position.

**Why now.** The Week 3 refactor formalises every scope cut. A heavy process changes what is worth amending.

**Status: NEEDS ADVISER CONFIRMATION**

---

### B6 · UAT distinct from research evaluation

**Question.** Confirm both are expected as separate deliverables:

| | UAT (Weeks 8–9) | Research evaluation (Weeks 11–12) |
|---|---|---|
| Question | Does it meet agreed requirements? | Does the proposed model work? |
| Output | Pass/fail per criterion | Measurements and findings |
| Failure means | A defect to fix | A valid finding |

Conflating them — reporting UAT passes as research findings — would be a defensibility failure.

**Status: NEEDS ADVISER CONFIRMATION**

---

## Group C — needed by Week 10

### C1 · Data policy for the pilot

**Question.** May the customer load **real institutional records** during Weeks 11–12? At what sensitivity level?

**Default assumed:** synthetic and already-published records only. Real unpublished IP disclosures require separate approval.

**Note.** The evaluation does not require confidential content. Nothing in the design depends on real IP, so the safe default costs nothing.

**Status: NEEDS CIT-U CONFIRMATION**

---

### C2 · External AI transmission

**Question.** May extracted text or abstracts be sent to a third-party AI API?

**Context.** SRS §197 already commits to sending *"exclusively anonymized, extracted text chunks"* while §632 leaves the provider **"TBD"** — a data-handling guarantee without a named recipient.

**If not approved:** local embeddings, so abstracts never leave campus and only the user's query does. The provider protocol (`R-02`) makes this a one-module change.

**Status: NEEDS CIT-U CONFIRMATION**

---

### C3 · Payment evidence

**Question.** Does "payment/transaction evidence" require payment **inside** IRIS, or is an out-of-band arrangement — invoice, service agreement, receipt, bank confirmation — acceptable?

**Context.** The SRS contains **no payment capability** across all 31 FRs. Building even minimal billing is 8–15 dev-days that do not exist in the budget, plus a payment provider and PCI considerations.

**Status: NEEDS ADVISER CONFIRMATION**

---

### C4 · CIT-U hardware

**Question.** Does dedicated CIT-U server hardware exist for IRIS, with the 500 GB secondary backup drive SRS §384 specifies?

**Interim plan:** a small VPS for Weeks 1–2 validation, migrating later. Migration is `pg_dump` plus `docker compose up`.

**If unavailable:** NFR-S1 (encryption at rest), NFR-R1 (uptime), NFR-R4 (separate backup drive) and SRS §456's on-premise requirement must be amended rather than reported as satisfied.

**Status: NEEDS CIT-U CONFIRMATION**

---

## Summary

| # | Item | Group | Type | Blocks |
|---|---|---|---|---|
| A1 | Ethics and consent | A | Adviser | Week 2 sessions |
| A2 | Framework combination | A | Adviser | Everything downstream |
| A3 | **What is SBCVM?** | A | Adviser | Framework selection |
| A4 | Respondent count | A | Adviser | Recruitment |
| A5 | **Baseline + pilot commitment** | A | CIT-U | **Highest risk** |
| B1 | Census / descriptive analysis | B | Adviser | Analysis plan |
| B2 | **Is a null result acceptable?** | B | Adviser | Experimental design |
| B3 | SUS instrument | B | Adviser | Instrument |
| B4 | NFR-P3 amendment | B | Adviser | `V-10` |
| B5 | SRS amendment procedure | B | Adviser | Week 3 refactor |
| B6 | UAT vs research evaluation | B | Adviser | Deliverables |
| C1 | Pilot data policy | C | CIT-U | Week 11 |
| C2 | External AI transmission | C | CIT-U | `R-02` |
| C3 | Payment evidence | C | Adviser | Commercial defence |
| C4 | CIT-U hardware | C | CIT-U | Final deployment |

**Five items are in Group A and should be raised this week.** A3 and B2 are the two most likely to change the design if answered unexpectedly, and both are cheap to ask.

---

## Suggested agenda for the first adviser meeting

1. Where the system actually is — it did not start; here is what was fixed and what remains
2. Scope: the ~27 dev-day budget and the deferrals it forces ([ADR-001](../adr/001-mvp-scope-boundary.md))
3. **Framework proposal and the SBCVM question** (A2, A3)
4. **Whether a null result is acceptable** (B2)
5. Ethics process (A1)
6. Respondent count interpretation (A4)
7. Support for the RDCO baseline and pilot commitment (A5)
8. NFR-P3 and the SRS amendment procedure (B4, B5)
