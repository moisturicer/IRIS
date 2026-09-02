# ADR-011: ISO 9241-11 as the evaluation spine

## Status

Accepted — 2026-09-01. **Subject to adviser approval of the framework combination.**

## Context

Semester 2 requires a validation framework aligned to SMART goals and measurable outcomes, covering usefulness, effectiveness, efficiency, usability, user experience, acceptance and project-specific outcomes. It must also evidence the research contribution (ADR-003).

A candidate stack was proposed: ISO 9241-11 + GQM + SUS + task success + time-on-task + workflow metrics + qualitative SME feedback. Reviewed, most of it collapses into one structure:

| Proposed item | What it actually is |
|---|---|
| ISO 9241-11 | The framework — effectiveness, efficiency, satisfaction, in a context of use |
| Task success rate | ISO's **effectiveness** measure |
| Time-on-task | ISO's **efficiency** measure |
| SUS | ISO's **satisfaction** instrument — already mandated by NFR-U1 (≥ 75, SRS Appendix B) |
| GQM | A derivation method, not a co-equal framework |
| Preserved clearances, turnaround | **Effectiveness in this specific context of use** |
| SME qualitative | Explanation of the above |

There is also a category error to avoid. ISO 9241-11 measures the **usability of a system**; the contribution is a **workflow model**. SUS ≥ 75 says the interface is pleasant — it says nothing about whether clearance-aware resubmission beats restart-all. A system could score 85 with a workflow that restarts everything. Left unaddressed, an elaborate usability evaluation would sit alongside an unevaluated thesis claim.

## Decision

**One framework: ISO 9241-11.** Effectiveness, efficiency and satisfaction, in a defined context of use.

- **Effectiveness** — task success rate; workflow completion; offices re-reviewed; preserved clearances
- **Efficiency** — time-on-task; per-stage turnaround; total workflow turnaround
- **Satisfaction** — SUS (NFR-U1, target ≥ 75)

**GQM is a methodology subsection**, describing how the research goal was decomposed into these metrics. It is not presented as a second framework.

**Domain metrics sit inside ISO's effectiveness and efficiency**, as context-specific measures — which ISO's "context of use" explicitly permits — rather than bolted alongside.

**The contribution is evaluated by within-subjects comparison** (ADR-004): the same SME participants, the same scenario set, run under `CLEARANCE_AWARE` and `RESTART_ALL`, with counterbalanced ordering. **Either result is a valid finding.**

**Qualitative SME data** — interviews, observation, open-ended feedback — is primary evidence, not decoration, given the expected sample size.

**Three phases stay distinct:**

| Phase | Weeks | Purpose |
|---|---|---|
| 1 — Initial MVP validation | 1–2 | Deploy, gather feedback, identify gaps, **refine the instrument**, build respondent relationships. *Not* the final study |
| 2 — Build | 3–10 | Refactor, implement, deploy, test |
| 3 — Final evaluation | 11–12+ | Actual usage, the ADR-004 comparison, quantitative and qualitative evidence |

Respondents span customers, end users, SMEs and decision-makers. Phase 1 participants may carry into Phase 3.

## Alternatives Considered

**Preserved-clearance counting as primary evidence.** Rejected — see ADR-004. Given which office declined, the count is deterministically computable: there is no variance and no possible negative result. It is an arithmetic identity presented as a finding.

**Present ISO 9241-11 and GQM as co-equal frameworks.** Rejected. It invites *"why do you need two?"* at defence for no analytical gain. Same content, one spine.

**Comparison against CIT-U's manual process as primary.** Rejected as primary, retained as supporting context. It is confounded by digitisation — any software beats paper, so it measures the wrong variable. Still worth gathering in Weeks 1–3 because it evidences the real-world problem.

**TAM or UTAUT for acceptance.** Rejected. A third model for an acceptance dimension that SUS and SME interviews already cover adequately at this scale.

**System metrics only, no expert evaluation.** Rejected. Expected pilot volume is unknown and may be single-digit; qualitative depth from four offices is defensible at small N where quantitative claims are not.

## Decision Rationale

Adopt one framework and fold everything into it. This is a presentation simplification with no loss of rigour, and it removes an avoidable line of questioning.

**Two things must be evaluated, and they are different questions.** (A) *Is IRIS usable, effective, efficient, acceptable software?* — ISO 9241-11 with SUS answers this well. (B) *Does clearance-aware resubmission improve on restart-all?* — only the ADR-004 within-subjects comparison answers this. Conflating them is how a thesis ends up with a thorough usability study and an unevaluated contribution.

The design must permit a negative result. If the difference proves small, that is a publishable finding about the boundary conditions of the model — and reporting it honestly is stronger than reaching for a favourable framing.

## Consequences

**Positive.** One coherent methodology. A contribution claim that can fail. Domain metrics justified by the framework rather than asserted.

**Negative.** The comparison doubles participant time — each scenario is walked twice. Scenario count must be sized for that, and ordering counterbalanced.

**Risk — the dominant one.** Organic pilot volume may be too small to exercise resubmission at all. Mitigation: **scenario-based evaluation** with pre-constructed realistic cases walked by real SMEs, including deliberate declines at different stages. This yields controlled N and covers branches organic usage would never reach. RDCO process-volume data (an open external question) determines whether this becomes the primary design.

**Dependency.** Time-on-task and preserved-clearance instrumentation must exist **before Week 11**. There is no second opportunity to collect it.

## MVP Impact

Instrumentation is **MVP Required, P1** (~2 dev-days, `W-04`). The framework itself costs no implementation.

## SaaS Impact

None directly. Per-stage turnaround becomes a product analytics capability later.

## Security Impact

Evaluation data includes participant identities and timings — handle under RA 10173, anonymise in the paper, and keep it out of the audit log's PII surface.

## Deployment Impact

Requires a separate evaluation instance for the ADR-004 comparison so live customer workflows are never reset. Free under ADR-005.

## Research Impact

Defining. This ADR is the evaluation chapter's structure.

## Related Requirements

NFR-U1 (SUS ≥ 75) · NFR-U2 (submission within 10 minutes) · NFR-U3 (360 px) · NFR-P2 · NFR-P3 · NFR-P4 · FR-M5-01.

**NFR-P3 conflict.** NFR-P3 requires a 3-second p95 for a *complete* chatbot response; a synchronous LLM round-trip is 3–10 s. The requirement is not achievable as written. It should be amended in the Week 3 refactor to **time-to-first-token ≤ 3 s with complete response ≤ 15 s p95**, or the metric restated. This requires adviser approval and is tracked as an external blocker.

## Related Tasks

`W-04` (instrumentation), `V-01`…`V-05`, `V-11`. See [`10-mvp-validation.md`](../architecture-tasks/10-mvp-validation.md).
