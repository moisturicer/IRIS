# 00 — Validation Strategy

The spine connecting research objectives to final evidence, for IRIS Semester 2.

```
Research Objectives → SMART Goals → Framework → Research Questions
    → GQM → Instruments → Metrics → Data Collection → Analysis → Evidence
```

**Source note.** `docs/architecture-grill/` does not exist and was never created — by agreement, the design-interview conclusions were recorded as ADRs instead. The governing sources are `docs/adr/` (11 records), `docs/architecture-tasks/` (70 tasks), `docs/SRS.md` and `docs/SDD.md`, plus direct inspection of the working tree on `refactor/docker-service` @ `1ecb908`.

---

## 1 · The finding that shapes everything below

**The thesis contribution is currently invisible in the product.**

`RecordClearance` — the model holding per-office clearance state — is used in exactly one place outside its own app: filtering the reviewer's pending queue (`reviews/views.py:84`). It is **never serialized into any API response**. `grep -rn "clearance" frontend/src` returns nothing outside a code comment.

So no user — not the submitting student, not the reviewing office, not an SME evaluator — can see:

- which offices have cleared a record and which are still pending
- that a resubmission preserved IERC's and KTTO's completed work
- that only the declining office needs to review again

**You cannot evaluate a benefit your participants cannot perceive.** A qualitative session asking *"does clearance-aware resubmission reduce your workload?"* against a UI that shows only `pipeline_status: declined` is asking SMEs to assess something they have no evidence of. Their answers would measure the interviewer's framing, not the system.

This adds one task that is genuinely thesis-critical and is not in the current backlog:

> **`W-07` · Expose per-office clearance state (API + UI).** `RecordDetailSerializer` gains a `clearances` field; the record detail page renders per-office status; the resubmission confirmation states which offices were preserved. **~1 dev-day. Must land before any workflow evaluation session.**

Everything in this strategy assumes `W-07` exists. Without it, the workflow evaluation reduces to log analysis, which [ADR-004](../adr/004-restart-all-comparison-mode.md) already established is insufficient on its own.

---

## 2 · What the MVP can actually demonstrate

Verified against the working tree, not assumed.

| Capability | State today | After P0 fixes (Weeks 1–3) | Validatable in Weeks 1–2? |
|---|---|---|---|
| Authentication, registration, roles | Code complete | Working | **Yes** |
| Record submission + PDF upload | Code complete | Working | **Yes** |
| Type-differentiated routing | Code complete (`reviews/services.py`) | Working | **Yes** |
| Parallel multi-office clearance | Code complete | Working | **Yes** |
| **Clearance-aware resubmission** | Code complete (`resubmit_record:348-407`) | Working | **Yes — but invisible without `W-07`** |
| Reviewer queues + decisions | API + UI complete | Working | **Yes** |
| Per-office clearance *visibility* | **Absent** | Needs `W-07` | **No, until `W-07`** |
| Notifications (in-app + email) | Code complete | Working | Yes |
| Audit log | Model works; **no review decisions recorded** | Partial | Partially |
| Full-text search | Working (`records/signals.py`) | Working | **Yes** |
| PDF text extraction | **Always fails** — libraries absent | Working after `R-01` | Week 4+ |
| Semantic search / RAG | **Does not exist** | Week 6, timeboxed | **No** |
| Summarization, chat history, KPI dashboard | Deferred to Phase 2 | Deferred | No |

**The consequential conclusion: the entire thesis contribution is demonstrable in Weeks 1–2**, once the boot blockers and `W-07` are cleared. The workflow is the most complete part of IRIS, not the least.

That is unusual and valuable. It means MVP validation can genuinely probe the research contribution rather than gathering generic usability impressions — provided the P0 work lands first.

---

## 3 · Three phases, deliberately distinct

Per [ADR-011](../adr/011-evaluation-framework.md) and the Semester 2 guidance.

| | **Phase 1 — Initial MVP Validation** | **Phase 2 — Build** | **Phase 3 — Final Evaluation** |
|---|---|---|---|
| **Weeks** | 1–2 | 3–10 | 11–12+ |
| **Purpose** | Validate needs, find gaps, **refine the instrument**, build respondent relationships | Refactor, implement, deploy, test | Measure the contribution; produce thesis evidence |
| **Not** | A statistical study | — | Exploratory |
| **Methods** | Demonstration · interview · observation · heuristic evaluation · instrument pilot | UAT against acceptance criteria | Controlled comparison · SUS · task metrics · SME interviews |
| **Output** | MVP validation report · refined scope · refined instrument | Working system · test evidence | Quantitative + qualitative evidence |
| **Sample** | Purposive, small, high-quality | — | Census of accessible SMEs |

**Phase 1 is formative. Phase 3 is summative.** Conflating them is the most common way a capstone evaluation loses defensibility — findings from an exploratory session get reported as results. Instruments, participants and analysis are kept separate throughout, even where the same people appear in both.

---

## 4 · Framework, in one line

**ISO 9241-11 as the single spine** — effectiveness, efficiency, satisfaction — with GQM as the derivation method, SUS as the satisfaction instrument, task success and time-on-task as ISO's own effectiveness and efficiency measures, and the workflow metrics folded inside effectiveness as context-specific measures.

**The contribution is tested by a within-subjects controlled comparison** of clearance-aware against restart-all resubmission.

Full evaluation of all twelve candidate frameworks, including the five rejected, is in [01-framework-selection.md](01-framework-selection.md) and [FRAMEWORK_DECISION.md](FRAMEWORK_DECISION.md).

---

## 5 · The alignment chain

| Layer | Content | Document |
|---|---|---|
| **Research objective** | Propose and evaluate a type-differentiated institutional IP workflow with parallel multi-office clearance and clearance-aware resubmission | [ADR-003](../adr/003-clearance-aware-resubmission.md) |
| **SMART goals** | Three, each with a measure, a target and a date | [04](04-research-questions.md) |
| **Framework** | ISO 9241-11 + GQM + SUS + controlled comparison | [01](01-framework-selection.md), [FRAMEWORK_DECISION.md](FRAMEWORK_DECISION.md) |
| **Research questions** | RQ1–RQ4 | [04](04-research-questions.md) |
| **GQM** | 3 goals → 9 questions → 21 metrics | [05](05-gqm.md) |
| **Instruments** | MVP set and Final set, kept separate | [06](06-validation-instruments.md) |
| **Contribution test** | Within-subjects, counterbalanced, matched scenarios | [07](07-workflow-evaluation.md) |
| **Supporting test** | Lightweight RAG evaluation | [08](08-rag-evaluation.md) |
| **Baseline** | RDCO data request checklist | [09](09-baseline-data.md) |
| **Respondents** | Four types, retention plan | [10](10-respondent-plan.md) |
| **Analysis** | Non-parametric, effect sizes, thematic | [11](11-analysis-plan.md) |
| **Gates** | Before Week 4, before pilot, before defence | [12](12-success-criteria.md) |
| **Logistics** | Schedule, ethics, instrumentation, storage | [13](13-data-collection-plan.md) |
| **Approvals** | What the adviser must confirm | [14](14-adviser-review.md) |

---

## 6 · Honest statement of limitations

To be stated in the thesis, not discovered by the panel.

1. **Small N.** The evaluable population is the staff of four CIT-U offices — plausibly 6–12 people. This is a **census of the accessible population**, not a sample, and it does not support inferential generalisation. Analysis is descriptive with effect sizes ([11](11-analysis-plan.md)).
2. **Single institution.** All findings are from CIT-U. Generality is argued from the configurability of the model ([ADR-002](../adr/002-workflow-transition-table.md)), not demonstrated across institutions.
3. **The comparison is within-system.** Clearance-aware versus restart-all isolates the mechanism, but both arms are IRIS. It does not establish that IRIS beats the current manual process — the manual baseline ([09](09-baseline-data.md)) provides context for that, and is confounded by digitisation.
4. **Researcher-built system, researcher-run evaluation.** Mitigated by pre-registered metrics, fixed scenarios and a protocol that permits a negative result — not eliminated.
5. **Pilot volume is unknown.** If organic resubmissions are too few, the contribution is evaluated by scenario-based session instead ([07](07-workflow-evaluation.md)). This is planned, not a fallback improvised in Week 12.

---

## 7 · Critical path

| Week | Must be true |
|---|---|
| **1** | Boot blockers cleared; security gate passed; MVP deployed to interim VPS with synthetic data |
| **1–2** | **`W-07` clearance visibility shipped** · baseline data requested from RDCO · respondents recruited · MVP instrument piloted |
| **2** | MVP validation report; gaps feed the Week 3 refactor |
| **3** | Instrument revised; scenarios drafted; adviser approvals sought |
| **10** | **`W-04` instrumentation live** — no second chance to collect pilot data |
| **10** | Evaluation instance provisioned; scenarios finalised; participants scheduled |
| **11–12** | Pilot + controlled comparison executed |
| **13–15** | Analysis and write-up |

**Two hard deadlines.** `W-04` must be live before Week 11 or there is no quantitative research data. Baseline collection must happen in Weeks 1–3 or never — once IRIS is in use, the manual process is no longer observable.

---

## 8 · Open items

Nothing below is assumed. Each is marked and tracked.

| Item | Status |
|---|---|
| Framework combination approval | **NEEDS ADVISER CONFIRMATION** |
| SUS use and instrument wording | **NEEDS ADVISER CONFIRMATION** |
| Ethics / consent process for human participants | **NEEDS ADVISER CONFIRMATION** |
| NFR-P3 amendment (3 s p95 chatbot) | **NEEDS ADVISER CONFIRMATION** |
| Whether "SBCVM" refers to a specific required model | **NEEDS ADVISER CONFIRMATION** — see [01](01-framework-selection.md) |
| RDCO submission volume, decline rate, turnaround | **NEEDS RDCO DATA** |
| Written pilot commitment, named participants | **NEEDS CIT-U CONFIRMATION** |
| External AI transmission approval | **NEEDS CIT-U CONFIRMATION** |
| CIT-U hardware for final deployment | **NEEDS CIT-U CONFIRMATION** |
| Payment-evidence acceptability | **NEEDS ADVISER CONFIRMATION** |

**No institutional process data appears anywhere in these documents.** Every value that would come from RDCO is a blank to be filled ([09](09-baseline-data.md)).
