# 10 — MVP Validation

Fifteen tasks across the three phases in [ADR-011](../adr/011-evaluation-framework.md). Where the SRS defines a threshold and a validation method, these tasks use the SRS's own numbers.

| Phase | Weeks | Purpose |
|---|---|---|
| **1 — Initial MVP validation** | 1–2 | Deploy, gather feedback, identify gaps, **refine the instrument**, build respondent relationships. *Not* the final study |
| **2 — Build** | 3–10 | Refactor, implement, deploy, test |
| **3 — Final evaluation** | 11–12+ | Actual usage, the [ADR-004](../adr/004-restart-all-comparison-mode.md) comparison, quantitative and qualitative evidence |

**Common fields.** Applying to every task here unless overridden: **Out of Scope** — fixing what the validation finds; failures become tickets. **SaaS Impact** — none unless stated. **Testing Requirements** — the procedure *is* the test. **Documentation Requirements** — evidence attached to the ticket and carried into the research paper. **Definition of Done** — procedure executed, evidence attached, PASS/FAIL recorded, failures ticketed.

---

## Phase 1 — Weeks 1–2

# V-01 · Initial MVP validation

**Objective.** Deploy an accessible MVP, gather meaningful stakeholder feedback, identify gaps, and refine both scope and instrument.

**Problem.** Weeks 1–2 require a deployed MVP and meaningful feedback. The inherited system does not start, so there is nothing to validate until `B-01`, `D-01` and the security gate clear.

**Evidence.** Boot and Compose blockers in `02-backend.md` and `08-deployment.md`.

**Current State.** No deployment; no validation instrument; no respondents recruited.

**Proposed State.** A running instance with synthetic data, exercised by real stakeholders, with findings recorded.

**Scope.** Demonstrations · interviews · open-ended questions · observation · instrument pilot-testing · gap documentation. Respondents span **customers, end users, SMEs and decision-makers**.

**Technical Approach.** Quality of feedback over form count. Participants recruited here should carry into Phase 3.

**Dependencies.** `D-03` and its full security gate.

**Risks.** Validating a broken system produces worthless data. If the gate is not clear, run demonstrations and interviews without live access rather than exposing an unsafe build.

**Security Impact.** Synthetic and already-published data only.

**Performance Impact.** None.

**Research/Thesis Impact.** Phase 1 of [ADR-011](../adr/011-evaluation-framework.md). Establishes respondent relationships and refines the instrument used in Phase 3.

**MVP Classification.** MVP REQUIRED · **Priority** P0 · **Complexity** M

**Pass/fail criteria**
- [ ] **PASS** if an accessible MVP is reachable by external participants for at least one full working week.
- [ ] **PASS** if feedback is gathered from at least one respondent in each of the four types.
- [ ] **PASS** if identified gaps are documented and fed into the Week 3 refactor (`F-03`).
- [ ] **PASS** if the validation instrument is pilot-tested and revised.
- [ ] **PASS** if the report states honestly that the Semester 1 system did not start, and what was fixed to enable validation.

---

# V-02 · Validation instrument design

**Objective.** Produce the instrument that Phase 1 pilots and Phase 3 uses, aligned to [ADR-011](../adr/011-evaluation-framework.md).

**Problem.** Metrics must be defined before instrumentation is built, or `W-04` captures the wrong things.

**Evidence.** No instrument exists. `docs/README.md` promises a `TEST_PLAN.md` that does not exist.

**Current State.** Undefined.

**Proposed State.** An ISO 9241-11-structured instrument: effectiveness (task success, offices re-reviewed, preserved clearances) · efficiency (time-on-task, per-stage and total turnaround) · satisfaction (SUS, NFR-U1) · qualitative SME protocol.

**Scope.** GQM derivation from research goal to metric; the SUS questionnaire (SRS Appendix B); task scripts; interview guide; consent forms under RA 10173.

**Out of Scope.** Executing it.

**Technical Approach.** Every metric must map to something `W-04` can capture, or to an observation protocol.

**Dependencies.** **Blocked on adviser approval of the framework** (external blocker #6). Feeds `W-04`.

**Risks.** An instrument designed after instrumentation yields metrics the system cannot produce. Design first.

**Security Impact.** Participant data under RA 10173; anonymise in the paper.

**Research/Thesis Impact.** Defining — this is the evaluation chapter's method section.

**MVP Classification.** MVP REQUIRED · **Priority** P0 · **Complexity** M

**Pass/fail criteria**
- [ ] **PASS** if every metric traces to a GQM chain from the research goal.
- [ ] **PASS** if every quantitative metric maps to a specific `W-04` capture point.
- [ ] **PASS** if the instrument is pilot-tested in Phase 1 and revised.
- [ ] **PASS** if adviser approval of the framework is obtained and recorded.

---

# V-03 · Manual-process baseline collection

**Objective.** Capture how CIT-U's current process behaves, as the real-world comparator.

**Problem.** Without a baseline, the contribution has only a self-referential comparison. **Weeks 1–3 is the only window** — once IRIS is in use, the manual process is no longer observable.

**Evidence.** [ADR-004](../adr/004-restart-all-comparison-mode.md) — preserved-clearance counting alone is arithmetic, not evidence.

**Current State.** No baseline data.

**Proposed State.** Documented current-process metrics from RDCO and the three offices.

**Scope.** Typical fortnightly submission volume · decline/resubmission rate · typical turnaround per stage and overall · **how often an office today re-reviews something it already cleared, and how long that takes** · which stages most commonly cause resubmission · whether anonymised historical data can be provided.

**Technical Approach.** Structured interviews plus historical records if available. This doubles as external blocker #7, which determines whether Phase 3 is organic or scenario-based (`V-04`).

**Dependencies.** RDCO cooperation.

**Risks.** **Highest-urgency task in this document.** The window closes when IRIS goes live. If not done in Weeks 1–3 it cannot be done at all.

**Security Impact.** Institutional process data — treat as confidential.

**Research/Thesis Impact.** **Thesis-critical.** Establishes that the problem is real, and supplies the effort approximation that turns "reviews preserved" into "hours preserved."

**MVP Classification.** MVP REQUIRED — thesis-critical · **Priority** P0 — Weeks 1–3 · **Complexity** M

**Pass/fail criteria**
- [ ] **PASS** if fortnightly submission volume and decline rate are documented with a stated source.
- [ ] **PASS** if typical per-stage and total turnaround are documented.
- [ ] **PASS** if the frequency and duration of redundant re-review under the current process is estimated, with method stated.
- [ ] **PASS** if the data is sufficient to size Phase 3 as organic or scenario-based.

---

## Phase 3 — Weeks 11–12+

# V-04 · Scenario-based evaluation design

**Objective.** Design a controlled evaluation that works even if organic pilot volume is too small.

**Problem.** A two-week pilot may produce single-digit resubmissions. At N=3 there is no quantitative claim.

**Evidence.** External blocker #7 unresolved; `V-03` will determine the real number.

**Current State.** No evaluation design beyond the intent to compare policies.

**Proposed State.** 8–10 pre-constructed realistic submission cases, walked by real SMEs from the four offices, under both resubmission policies, with counterbalanced ordering.

**Scope.** Case construction covering all three record types and declines at different stages · participant scheduling across four offices · counterbalancing · time-on-task observation protocol · the [ADR-004](../adr/004-restart-all-comparison-mode.md) within-subjects comparison.

**Technical Approach.** Controlled N; covers branches organic usage would never reach. **Runs on the separate evaluation instance**, never the customer's.

**Dependencies.** `V-02`, `V-03`, `W-02`, `W-04`. A second instance per [ADR-005](../adr/005-instance-per-tenant.md).

**Risks.** Doubles participant time — each scenario is walked twice. Size the case count accordingly and secure participant commitment early.

**Security Impact.** Synthetic cases only; no real IP.

**Research/Thesis Impact.** **Thesis-critical.** This is the design that makes the contribution evaluable at realistic sample sizes.

**MVP Classification.** MVP REQUIRED — thesis-critical · **Priority** P1 · **Complexity** M

**Pass/fail criteria**
- [ ] **PASS** if 8–10 cases exist covering all three record types and declines at adviser, RDCO-intake and clearance stages.
- [ ] **PASS** if each case is executable under both policies with counterbalanced ordering.
- [ ] **PASS** if SME participants from all four offices are scheduled and confirmed.
- [ ] **PASS** if the protocol defines exactly what is timed and observed.

---

# V-05 · Final evaluation execution

**Objective.** Run the evaluation and produce the thesis evidence.

**Problem.** This is the only opportunity to gather it.

**Evidence.** [ADR-011](../adr/011-evaluation-framework.md).

**Current State.** Not started.

**Proposed State.** Executed evaluation with quantitative and qualitative data analysed.

**Scope.** Organic pilot usage (Weeks 11–12) · the scenario-based comparison · SUS administration · SME interviews · data extraction from `W-04`'s instrumentation.

**Technical Approach.** **Either result is a valid finding.** If clearance-aware shows a small advantage, report it — that is a publishable result about the model's boundary conditions.

**Dependencies.** `V-02`, `V-03`, `V-04`, `W-02`, `W-04`, `D-04`.

**Risks.** **Highest risk in the project: it depends on CIT-U's cooperation** (external blocker #1) with no fallback beyond scenario-based evaluation. Secure the written commitment in Weeks 1–2.

**Security Impact.** Real usage data under RA 10173; anonymise in the paper.

**Research/Thesis Impact.** Defining.

**MVP Classification.** MVP REQUIRED — thesis-critical · **Priority** P1 · **Complexity** L

**Pass/fail criteria**
- [ ] **PASS** if the comparison is executed under both policies with the planned participants.
- [ ] **PASS** if task success, time-on-task, offices re-reviewed, preserved clearances and turnaround are captured for every case.
- [ ] **PASS** if SUS is administered across at least three role groups.
- [ ] **PASS** if qualitative SME feedback is recorded and analysed.
- [ ] **PASS** if the result is reported honestly, including a null or small effect.

---

## NFR validation

# V-06 · Authentication (NFR-S2, NFR-S6)

**Objective.** Prove login, lockout and session expiry behave as specified.
**Problem.** Never tested end to end; `S-06` identifies NFR-S2 as unmet by the current design.
**Evidence.** `AXES_FAILURE_LIMIT=3`, `AXES_COOLOFF_TIME=10min`; 30-minute access tokens with a 7-day rotating refresh and silent client refresh.
**Current State.** NFR-S2 expected to FAIL until `S-06` lands — run early to confirm the gap.
**Proposed State.** Both NFRs pass on the deployed instance.
**Scope.** Registration → verification → login → lockout → unlock → inactivity expiry.
**Dependencies.** `S-06`, `FE-01`, `D-03`.
**Risks.** The 31-minute wait needs one real confirmation, not only a mocked clock.
**Security Impact.** Primary evidence for two security NFRs.
**MVP Classification.** MVP REQUIRED · **Priority** P2 · **Complexity** S

- [ ] **PASS** if 6 consecutive failed logins return **HTTP 403** on the 6th, the account shows locked in the admin, and a lock event exists in the audit log (NFR-S6 validation, verbatim).
- [ ] **PASS** if authenticating, idling **31 minutes**, then calling a protected endpoint returns **401**, and the token is rejected thereafter (NFR-S2 validation, verbatim).
- [ ] **PASS** if an unverified account cannot log in.
- [ ] **PASS** if a locked account cannot log in with correct credentials.
- [ ] **PASS** if an administrator can unlock and the user can then log in.

---

# V-07 · Authorization (NFR-S4, NFR-S5)

**Objective.** Prove NFR-S4 using the SRS's own validation method; this is the acceptance gate for `S-01`…`S-05`.
**Problem.** Twelve endpoints currently lack object-level authorization.
**Evidence.** `05-security.md`.
**Current State.** Expected to FAIL before the `S-0x` fixes — run first as a baseline.
**Proposed State.** All criteria pass; the run output is the NFR-S4 evidence artefact.
**Scope.** All record and document endpoints × six roles, plus the audit-immutability check.
**Dependencies.** `S-01`…`S-05`, `S-07`, `T-02`.
**Security Impact.** The most important validation in this document.
**MVP Classification.** MVP REQUIRED · **Priority** P1 · **Complexity** M

- [ ] **PASS** if a Student-role account calling every RDCO-restricted endpoint receives **403 with no restricted data in any response body** (NFR-S4, verbatim).
- [ ] **PASS** if `GET /records/<id>/` returns 404 for every non-owner, non-reviewer role on an unpublished record.
- [ ] **PASS** if `GET /documents/files/download-all/?record=<not mine>` returns 403.
- [ ] **PASS** if `GET /media/<known file>` does not return the file.
- [ ] **PASS** if an ITSO account can neither change a user's role nor approve at `rdco_review`.
- [ ] **PASS** if deleting an audit event via the REST API **and** via the Django admin as superuser are both rejected at the data layer (NFR-S5).

---

# V-08 · Document upload and processing (NFR-P4, NFR-P5)

**Objective.** Prove upload limits and that indexing completes within 30 seconds.
**Problem.** Extraction currently always fails (`R-01`); embedding never runs (`R-03`).
**Evidence.** `MAX_PDF_SIZE_BYTES = 50MB`; the view returns **400** on exceed while **NFR-P5 requires 413** — a discrepancy to resolve in `F-03` or with an nginx `client_max_body_size`.
**Current State.** FR-M3-01 unmet.
**Proposed State.** Both NFRs pass.
**Scope.** Format validation · size limit and status code · ownership · versioning · extraction → FTS → embedding timing.
**Dependencies.** `R-01`, `R-03`, `B-03`, `S-03`.
**Performance Impact.** The subject of the task.
**MVP Classification.** MVP REQUIRED · **Priority** P1 · **Complexity** M

- [ ] **PASS** if uploading a 51 MB PDF returns **HTTP 413** (NFR-P5, verbatim).
- [ ] **PASS** if a 49 MB PDF uploads successfully.
- [ ] **PASS** if a `.docx` renamed to `.pdf` is rejected.
- [ ] **PASS** if uploading to a record the user does not own returns 403.
- [ ] **PASS** if all 5 sample ~10 MB / 10-page papers complete extraction, FTS indexing and embedding **within 30 seconds each** of upload confirmation (NFR-P4, verbatim).
- [ ] **PASS** if a corrupt PDF is marked `failed` with a clear error and does not block the queue.

---

# V-09 · Workflow and reviewer routing (FR-M5-01)

**Objective.** Prove all three routes traverse correctly and each role sees exactly what it should review.
**Problem.** The workflow is the core contribution and has never been executed end to end.
**Evidence.** `04-workflow.md`; `W-05` notes the queue and authorization are encoded independently and can disagree.
**Current State.** Untested.
**Proposed State.** All three routes complete; queue and authorization agree for every role.
**Scope.** The three type routes · decline, reject, resubmit · clearance-smart resubmission · per-role pending queues · notification delivery.
**Dependencies.** `W-01`, `W-03`, `W-05`, `T-03`.
**Research/Thesis Impact.** Demonstrates the contribution end to end.
**MVP Classification.** MVP REQUIRED — thesis-critical · **Priority** P1 · **Complexity** M

- [ ] **PASS** if a Proposal goes `draft → adviser_review → approved`, and RDCO can mark it `completed`.
- [ ] **PASS** if a Thesis/Research goes `draft → rdco_intake → parallel_review → rdco_review → published`.
- [ ] **PASS** if a Project goes `draft → rdco_intake → itso_review → parallel_review → rdco_review → published`.
- [ ] **PASS** if a record leaves `parallel_review` **only** after every clearance is `cleared`.
- [ ] **PASS** if an IERC decline then resubmit resets **only** IERC, preserving KTTO's clearance.
- [ ] **PASS** if a `rejected` record cannot be resubmitted, and resubmission without a new document is refused.
- [ ] **PASS** if **every record in a role's queue is actionable by that role**, and every record absent from it is refused.

---

# V-10 · AI retrieval, groundedness, citations and latency (NFR-P3)

**Objective.** Prove retrieval is relevant and permission-safe, answers are grounded, citations resolve, and latency is measured against an achievable target.

**Problem.** **NFR-P3 requires a 3-second p95 for a complete response; a synchronous LLM round-trip is 3–10 s.** The requirement is likely unachievable as written — `F-03` amends it.

**Evidence.** NFR-P3 validation: *"20 consecutive representative natural language queries … measuring the 95th percentile."*

**Current State.** No AI endpoint runs.

**Proposed State.** Retrieval, groundedness, citations and latency all measured; degradation demonstrated.

**Scope.** 20 judged relevance queries · a negative visibility test · 20 questions in three classes (answerable / plausible-but-absent / adversarial) · citation resolution · per-phase latency breakdown · the `R-05` degradation demonstration.

**Dependencies.** `R-03`, `R-04`, `R-05`, `B-05`, `F-03`.

**Risks.** **Expected to FAIL against the literal 3-second target.** Run early — the result is the evidence `F-03` needs.

**Security Impact.** A retrieval leak bypasses `S-02` entirely. Hard fail on any.

**MVP Classification.** MVP REQUIRED · **Priority** P1 · **Complexity** M

- [ ] **PASS** if, for ≥80% of 20 judged queries, the expected document appears in the top 5.
- [ ] **PASS** if **a Student's query never returns a chunk or citation from a record they cannot see** — zero leaks (hard fail on any).
- [ ] **PASS** if ≥90% of answerable questions produce answers judged supported by a retrieved record.
- [ ] **PASS** if **100%** of absent and adversarial questions produce an explicit "not found" rather than a fabricated answer (hard fail on any fabrication).
- [ ] **PASS** if **100%** of citations resolve to existing records the asker may see.
- [ ] **PASS** if p95 over 20 consecutive queries meets the amended NFR-P3 target, with per-phase timings recorded.
- [ ] **PASS** if, with the provider unreachable, search returns FTS results with a visible unavailable state and the workflow is unaffected.

---

# V-11 · Usability (NFR-U1, NFR-U2)

**Objective.** Meet SUS ≥ 75 and the 10-minute submission target.
**Problem.** No usability testing has been done; both NFRs specify human studies with defined thresholds.
**Evidence.** NFR-U1 and NFR-U2 validation methods.
**Current State.** Untested.
**Proposed State.** Both measured with real participants.
**Scope.** SUS across ≥3 role groups; a timed submission task with ≥5 first-time students after a 1-hour onboarding.
**Dependencies.** `V-09` must pass first — you cannot usability-test a broken workflow.
**Risks.** **Longest lead time of any task here** — participant recruitment and ethics clearance. Start scheduling in Weeks 1–2.
**MVP Classification.** MVP REQUIRED · **Priority** P1 · **Complexity** L

- [ ] **PASS** if mean SUS across all respondents is **≥ 75** (NFR-U1).
- [ ] **PASS** if respondents span **at least three role groups**.
- [ ] **PASS** if **all 5** first-time participants complete a full submission including PDF upload and consent within **10 minutes** unassisted (NFR-U2).
- [ ] **PASS** if no participant requires external assistance.
- [ ] Qualitative friction points recorded and ticketed regardless of outcome.

---

# V-12 · Accessibility and responsiveness (NFR-U3)

**Objective.** All core workflows usable at 360 px with no horizontal scrolling.
**Problem.** Wide data tables have no horizontal-scroll container; icon-only buttons have no accessible name.
**Evidence.** 52 `aria-*` attributes across 128 files; `DataTable` pagination buttons are icon-only and unlabelled; `<th>` elements lack `scope`.
**Current State.** Untested.
**Proposed State.** NFR-U3 met on the four named workflows.
**Scope.** Login · IP disclosure submission · RAG chatbot query · workflow status view.
**Technical Approach.** NFR-U3 verbatim: DevTools emulation at 360 px **plus a physical 360 px Android device**.
**Dependencies.** `FE-02`.
**MVP Classification.** MVP REQUIRED · **Priority** P2 · **Complexity** M

- [ ] **PASS** if all four core workflows complete at 360 px with **no horizontal scrolling, no overlapping elements, no broken components** (NFR-U3, verbatim).
- [ ] **PASS** if verified on both emulation **and** a physical device.
- [ ] **PASS** if `axe-core` reports zero critical violations on the four screens.
- [ ] **PASS** if every interactive control has an accessible name.

---

# V-13 · Concurrency, load and deployment (NFR-P1, NFR-P2, NFR-R3, NFR-S1, NFR-S3)

**Objective.** Meet the load, integrity and deployment-security NFRs.
**Problem.** No load testing has been done, and `W-03` identifies a concurrency defect that can advance a record past an office that never cleared it.
**Evidence.** `gunicorn --workers 4` (sync). No transaction boundaries before `W-03`.
**Current State.** Untested.
**Proposed State.** All five NFRs measured.
**Scope.** JMeter MVP-baseline load; response-time percentiles; concurrent-write integrity; clean-clone deployment; HTTPS and redirect; encryption at rest.
**Dependencies.** `W-03`, `B-08`, `D-01`, `D-02`, `D-03`.
**Risks.** Four sync workers may not sustain 100 concurrent sessions; if it fails, `--worker-class gthread --threads 8` is the first remedy, not more hardware.
**MVP Classification.** MVP REQUIRED · **Priority** P2 · **Complexity** L

- [ ] **PASS** if 100 virtual users over 30 minutes with 5-minute ramp-up produce **zero crashes and sub-2-second average response** (NFR-P1, verbatim).
- [ ] **PASS** if the **95th percentile** is ≤ 2 s across student portal, role dashboards, upload interface (NFR-P2).
- [ ] **PASS** if 50 simultaneous PDF submissions produce a record count **exactly matching** successful responses, no duplicates, no missing fields (NFR-R3, verbatim).
- [ ] **PASS** if concurrent clearance submissions by two offices produce exactly two rows and correct advancement.
- [ ] **PASS** if a clean clone deploys with documented steps only.
- [ ] **PASS** if HTTPS serves a valid certificate and port 80 redirects with **301** (NFR-S3, verbatim).
- [ ] **PASS** if storage volumes are confirmed encrypted (NFR-S1).

---

# V-14 · Failure recovery and backups (NFR-R2, NFR-R4)

**Objective.** Meet the 5-minute recovery and 24-hour RPO requirements.
**Problem.** No backups exist and no recovery has been attempted.
**Evidence.** No backup configuration; `backend`, `frontend` and Celery services have no health checks, so a wedged worker never restarts.
**Current State.** Untested.
**Proposed State.** Both NFRs demonstrated by drill.
**Scope.** Forced restart under load; committed-data integrity; backup schedule; restore drill.
**Dependencies.** `D-04`, `D-05`.
**Risks.** **A backup that has never been restored is not a backup.**
**Research/Thesis Impact.** Losing `W-04`'s instrumentation would be unrecoverable.
**MVP Classification.** MVP REQUIRED · **Priority** P2 · **Complexity** M

- [ ] **PASS** if, after a forced restart under active load, the system serves a successful authenticated request **within 5 minutes** (NFR-R2).
- [ ] **PASS** if **all** pre-restart committed records remain intact with zero loss.
- [ ] **PASS** if a `pg_dump` runs daily, evidenced by timestamped files.
- [ ] **PASS** if a **restoration drill on a staging instance** recovers all records and files intact (NFR-R4, verbatim).
- [ ] **PASS** if measured RPO ≤ 24 hours.
- [ ] **PASS** if killing the Celery worker causes an automatic restart within 60 s.

---

# V-15 · Operating cost

**Objective.** Establish what IRIS costs to run monthly and confirm it is sustainable.
**Problem.** No cost model exists. AI usage is unmetered and uncapped — a real risk when a student's card may back the API key.
**Evidence.** No token accounting, no spend cap. DRF's global `1000/day` throttle is not a spend control. No caching, so re-indexing an unchanged document re-charges it.
**Current State.** Unknown and unbounded.
**Proposed State.** A measured monthly cost with a hard ceiling in place.
**Scope.** Hosting · AI API (embedding + generation) · storage growth · backup storage.
**Technical Approach.** Instrument token counts into `AuditEvent.metadata`; measure a representative week and extrapolate.
**Dependencies.** `R-02`, `R-04`, `D-03`.
**Risks.** **The cap must be in place before the first live key**, not after this measurement.
**Research/Thesis Impact.** Commercial defence evidence; feeds pricing.
**MVP Classification.** MVP REQUIRED · **Priority** P2 · **Complexity** M

- [ ] **PASS** if projected monthly cost is documented with a per-component breakdown.
- [ ] **PASS** if a **per-user daily cap** on AI endpoints is enforced and demonstrated (a request beyond it returns 429).
- [ ] **PASS** if token counts per request are recorded in the audit log.
- [ ] **PASS** if re-indexing an unchanged document makes **zero** provider calls.
- [ ] **PASS** if projected cost is within the budget recorded in the hosting decision.
- [ ] **PASS** if a documented ceiling exists beyond which AI degrades gracefully rather than billing without limit.
