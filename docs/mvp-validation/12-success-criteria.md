# 12 — Success Criteria & Gates

What "good enough" means at each decision point, and what specific findings trigger which kind of change.

**Thresholds are judgement anchors, not statistical rules.** At N≈6–12 no threshold is statistically meaningful; these exist to make decisions consistent and to prevent post-hoc rationalisation of whatever was found.

---

## Gate 0 — before the MVP is exposed publicly (Week 1)

**Binary. Every item must pass. No exceptions, no "we'll fix it after the session."**

| # | Criterion | Task |
|---|---|---|
| 1 | `python manage.py check` exits 0; the URLconf imports | `B-01` |
| 2 | `docker compose config` exits 0 for both files; the stack starts | `D-01` |
| 3 | The frontend is reachable and serves the SPA | `D-02` |
| 4 | `GET /media/<known file>` does **not** return the file | `S-01` |
| 5 | A non-owner retrieving another user's draft record receives 404 | `S-02` |
| 6 | A non-owner calling `files/download-all/` receives 403 | `S-03` |
| 7 | `/api/v1/storage/*` returns 404 (app removed) | `SC-01` |
| 8 | No hardcoded credentials; `DEBUG=False`; `ALLOWED_HOSTS` set | `S-04` |
| 9 | HTTPS with a valid certificate; port 80 redirects 301 | `D-03` |
| 10 | Postgres and Redis are not reachable from the public internet | `D-03` |
| 11 | Only synthetic or already-published records are loaded | Data policy |
| 12 | **Per-office clearance state is visible in the UI** | **`W-07`** |

**If 1–11 cannot be met:** run demonstrations on a local instance via screen share. **Do not expose an unsafe build to meet a schedule.**

**If 12 cannot be met:** sessions may proceed, but the workflow-contribution portions produce **no valid qualitative data** — participants cannot assess what they cannot see. Record this and prioritise `W-07` for Week 3.

---

## Gate 1 — acceptable MVP validation feedback (end of Week 2)

Phase 1 has succeeded when:

| # | Criterion | Measure |
|---|---|---|
| 1 | **≥ 4 SMEs participated — at least one per office** | Session count |
| 2 | ≥ 3 students and ≥ 1 adviser participated | Session count |
| 3 | ≥ 1 decision-maker participated | Session count |
| 4 | Baseline request issued and a follow-up conversation held | [09](09-baseline-data.md) status |
| 5 | The instrument was piloted with ≥ 2 participants and revised | Change log |
| 6 | **≥ 75% of Phase 1 SMEs committed to Phase 3** | Retention tracker |
| 7 | Heuristic evaluation completed with a severity-rated defect list | HE sheets |
| 8 | Findings synthesised into the MVP validation report | Report exists |
| 9 | Gaps triaged into Week 3 refactor / Week 4–7 build / deferred | Triage table |

**Criterion 1 is the hard floor.** With fewer than four offices represented, Phase 1 has not validated the workflow model — an office's perspective is simply absent, and that office is also likely absent from Phase 3.

**Criterion 6 matters as much as any finding.** The SME population is bounded; losing them between phases cannot be recovered by recruiting harder.

---

## What triggers what

Applied to Phase 1 findings.

### Requirements change → Week 3 refactor (`F-03`)

| Trigger | Action |
|---|---|
| ≥ 2 SMEs describe routing that differs from the implementation | Amend SRS Module 5; update `W-01`'s table |
| An SME identifies a workflow state the model cannot express | Assess against the transition table; amend or record as a limitation |
| ≥ 2 SMEs name a mandatory re-review case (M20) | **Record as a boundary condition.** Do not remove the contribution — this strengthens the case for configurable policy |
| A decision-maker names a blocking adoption condition | Assess feasibility against the ~16-day Weeks 4–7 budget; scope decision |
| A required field or document type is missing | Amend SRS Module 2 |

### UI change → before Week 4, or into Weeks 4–7

| Trigger | Priority |
|---|---|
| **≥ 2 participants cannot read which offices cleared (low M17)** | **Highest** — this invalidates Phase 3's construct validity |
| ≥ 3 participants fail the same task | High |
| ≥ 3 participants need assistance at the same step | High |
| ≥ 2 severity-4 heuristic findings on a KEEP screen | High |
| Terminology mismatch reported by ≥ 2 SMEs | Medium — cheap to fix, affects comprehension |
| Cosmetic findings (severity 1–2) | Deferred to Phase 2 unless trivial |

### Workflow change

| Trigger | Action |
|---|---|
| The implemented routing contradicts documented institutional practice | **Change the implementation** — the model must reflect reality, or the contribution is about a workflow nobody uses |
| An office is engaged at the wrong stage | Correct the transition table |
| Resubmission routing sends records to the wrong office | Correct; add a regression test |

### Scope reduction

| Trigger | Action |
|---|---|
| A gap requires > ~2 dev-days | Scope decision — it competes with a 16-day window |
| Total identified work exceeds Weeks 4–7 capacity | Cut from `06-rag.md` and `03-frontend.md` first; **never** from `04-workflow.md` |
| RAG cannot be completed in its timebox | Pre-committed: ship search-only ([ADR-006](../adr/006-minimum-rag-pipeline.md)) |
| Fewer than 4 SMEs available for Phase 3 | Reframe the comparison as a multiple case study ([11](11-analysis-plan.md)); escalate |

---

## Gate 2 — before Week 4 implementation begins

| # | Criterion |
|---|---|
| 1 | MVP validation report complete, with gaps triaged |
| 2 | SRS/SDD amendments identified (`F-03`), amendment process confirmed |
| 3 | Instrument revised from the pilot |
| 4 | Baseline data received, **or** its absence documented with the fallback chosen |
| 5 | Phase 3 participants committed |
| 6 | Weeks 4–7 backlog fits the ~16 dev-day budget with slack reserved for RAG |
| 7 | Ethics/consent process confirmed |
| 8 | Framework combination approved |
| 9 | **`W-07` shipped or scheduled in Weeks 4–5** |

Items 7 and 8 are **NEEDS ADVISER CONFIRMATION** and should be raised in Week 1 — they have lead time and block instrument finalisation.

---

## Gate 3 — before the customer pilot (end of Week 10)

**The hardest gate. Real users, real data, no second chance.**

### Blocking — the pilot does not start without these

| # | Criterion | Task |
|---|---|---|
| 1 | **`W-04` instrumentation live and verified end to end on a seeded workflow** | `W-04` |
| 2 | `W-07` clearance visibility shipped | `W-07` |
| 3 | `W-01` transition table complete; all three routes traverse correctly | `W-01`, `V-09` |
| 4 | `W-02` restart-all policy configurable and tested | `W-02`, `T-03` |
| 5 | Authorization validation passed — NFR-S4 evidence produced | `V-07` |
| 6 | Backups running; **one restore drill performed** | `D-04`, `V-14` |
| 7 | Evaluation instance provisioned, separate from the customer's | `SA-02` |
| 8 | Written pilot commitment with named participants and dates | **NEEDS CIT-U CONFIRMATION** |
| 9 | Scenarios built, matched and pilot-tested with one participant | [07](07-workflow-evaluation.md) |
| 10 | Data policy confirmed — what the customer may load | **NEEDS CIT-U CONFIRMATION** |

**Criterion 1 is the one that cannot be recovered.** Instrumentation added after the pilot begins yields no data for the period it missed. If `W-04` slips, fall back to manual timing in Strand B sessions and report the loss of Strand A quantitative data.

### Non-blocking but expected

| # | Criterion |
|---|---|
| 11 | UAT passed against acceptance criteria (Weeks 8–9) |
| 12 | NFR validations `V-06`…`V-15` executed, results recorded |
| 13 | Health checks and logging in place (`D-05`) |
| 14 | Known defects triaged; none blocking core workflow |
| 15 | Support contact and escalation path agreed with the customer |

### System freeze

**From the start of Week 11, no deployments except defects that block usage.** A mid-pilot change invalidates comparability of timing data. Log any emergency change with timestamp and note the affected data.

---

## Gate 4 — before final defence

| # | Criterion |
|---|---|
| 1 | RQ1 answered with data, **including if the answer is "no meaningful difference"** |
| 2 | RQ2 answered; NFR-U1 and NFR-U2 reported against their thresholds |
| 3 | RQ3 answered with coded themes and supporting quotations |
| 4 | RQ4 answered, or generation documented as descoped with its reason |
| 5 | Threats to validity stated in the thesis |
| 6 | Limitations stated — census, single institution, small N, researcher-run |
| 7 | Deviations from the analysis plan disclosed |
| 8 | Disconfirming evidence reported |
| 9 | Traceability matrix complete: delivered / partial / Phase 2 per FR and NFR (`DOC-06`) |
| 10 | Every SRS deferral formally recorded (`F-03`) |
| 11 | Baseline reported, or its absence stated |
| 12 | Instrument development documented (Phase 1 → Phase 3 change log) |

**Criterion 1 does not require a favourable result.** A null result, honestly obtained and reported with its limitations, satisfies it. A favourable result obtained by an analysis that could not have failed does not.

---

## Explicitly not success criteria

| Not a criterion | Why |
|---|---|
| A specific SUS number beyond NFR-U1's 75 | The threshold is the requirement; exceeding it is not a research finding |
| Clearance-aware "winning" the comparison | The design permits either result. Requiring a win would make the evaluation dishonest |
| Statistical significance | N is a bounded population; significance is not achievable or claimed |
| 30 respondents as a raw count | Quality of feedback governs. **NEEDS ADVISER CONFIRMATION** on how the target is counted |
| All 31 FRs implemented | [ADR-001](../adr/001-mvp-scope-boundary.md) cuts scope deliberately; success is the *validated* MVP delivered and documented |
| Zero defects | Not achievable. Success is triaged defects with nothing blocking the core workflow |
