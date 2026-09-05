# Jira Reconciliation Plan v2 — capacity-validated

**Supersedes [`00-reconciliation-plan.md`](00-reconciliation-plan.md).** Nothing has been written to Jira.

**Site:** `citiris.atlassian.net` · **Project:** IR · **Legacy backlog:** 51 issues
**Capacity model:** 4 developers × ~8 effective hrs/person/week × 15 weeks = **60 dev-days**

---

## 1 · What changed from v1

| v1 | v2 |
|---|---|
| Reorganised the 51 existing issues into the new backlog | **The 51 are frozen as legacy.** New Kanban built fresh; old issues linked, not reused |
| 56 cards, no effort estimates | **48 cards, every one estimated**, summed against capacity |
| Commercialization deferred pending confirmation | **Committed workstream** — 6 cards, W11–W15 |
| No capacity check | **Full capacity validation. The plan does not fit — see §5** |

---

## 2 · Legacy backlog — freeze, classify, link

The 51 issues are **not** the foundation of Semester 2. They are Semester 1 history: no labels, one priority, several describing rejected technology, two asserting completion that is false.

**They are preserved. Nothing is deleted.** Each is relabelled `legacy-s1` plus one classification, and where a new card replaces it, the old issue is **linked** (`is superseded by`) to the new one.

| Classification | Count | Issues |
|---|---|---|
| **SUPERSEDED** — replaced by a new card, link created | 14 | IR-2, IR-3, IR-4, IR-6, IR-7, IR-9, IR-11, IR-12, IR-15, IR-22, IR-35, IR-41, IR-42, IR-46 |
| **DUPLICATE** — the capability already exists in the codebase | 2 | IR-39 (`DataTable.tsx` exists with pagination), IR-40 (covered by `B-05`/`W-07`) |
| **MERGED** — folded into another legacy issue or a new card | 3 | IR-14 → RAG card · IR-45 → consent logging · IR-47 → audit immutability |
| **DEFERRED** — legitimate, unfunded this semester | 19 | IR-10, IR-16, IR-17, IR-18, IR-19, IR-20, IR-21, IR-25, IR-33, IR-34, IR-36, IR-37, IR-38, IR-48, IR-49 + epics IR-28, IR-29, IR-32 |
| **CLOSED** — delivered | 2 | IR-50, IR-51 |
| **HISTORICAL** — Semester 1 context, no action | 11 | IR-1, IR-5, IR-8, IR-13, IR-23, IR-24, IR-43, IR-44 + epics IR-26, IR-27, IR-30, IR-31 |

**No status corrections are applied to legacy issues.** Reopening `IR-3` to say "actually not done" adds nothing once the issue is marked `legacy-s1` and superseded — the new card carries the real state. This removes 5 edits from v1 that were pure bookkeeping.

**Epics IR-26…IR-32 are retained read-only** as the Semester 1 structure. Semester 2 gets its own epics (§4).

---

## 3 · Determination — payment evidence

**Finding:** the SRS contains **zero** occurrences of *payment*, *billing*, *invoice* or *subscription* across all 31 functional requirements. [ADR-001](../adr/001-mvp-scope-boundary.md) explicitly lists billing as out of scope. `mvp-validation/14-adviser-review.md` §C3 estimates minimal billing at **8–15 dev-days**, plus a payment provider and PCI considerations.

**Determination:** the requirements do **not** establish an in-app payment module, so **out-of-band institutional payment evidence is the proportionate approach** — a signed service agreement or MOA, an invoice, and a receipt or bank confirmation, captured as commercial-defence artefacts.

**No payment processing is built.** Card `C-01` collects the evidence; it does not implement a transaction system.

> This is a determination against the requirements, not adviser sign-off. `mvp-validation/14-adviser-review.md` C3 remains the item to confirm. If the programme requires payment *inside* IRIS, that is 8–15 dev-days against a budget that is already over — and it would displace the entire thesis-critical workflow track. Confirm before Week 11.

---

## 4 · New Semester 2 Active Kanban — 48 cards

> **Card count corrected.** Earlier revisions of this document said "41 cards".
> The tables below have always contained **48**, and the 61.5 dev-day total is
> the correct sum of those 48 rows — only the label was wrong.
>
> **Two cards were added after this plan was written** and are *not* in the 61.5
> total: **IR-105** (Jira/Git traceability convention) and **IR-106** (resolve the
> AI gateway architecture contradiction). The active board therefore holds **50
> cards**. Both are documentation-only and were absorbed within the W1-W2
> allocation; neither changes the 102% finding, which was already over capacity.

Five new epics. Legacy epics stay untouched.

| Epic | Cards |
|---|---|
| **S2 Epic A: Platform Stability & Security** | P0-01…P0-07 |
| **S2 Epic B: Workflow & Thesis Contribution** | P1-02…P1-10, P1-13 |
| **S2 Epic C: Engineering Practice & Delivery** | P1-01, P1-14…P1-20, P2-01…P2-05 |
| **S2 Epic D: MVP Validation & Research Evaluation** | P0-08…P0-12, P1-11, P1-12, P2-06…P2-10 |
| **S2 Epic E: Commercialization & Sustainability** | C-01…C-06 |

### P0 — Blockers (15.0 dev-days)

| ID | Title | Area | Phase | Est | Dependencies | Thesis |
|---|---|---|---|---|---|---|
| P0-01 | Restore application boot (`B-01`+`B-02`) | Backend | W1-W2 | **1.5** | none | — |
| P0-02 | Make the Docker stack build and serve (`D-01`+`D-02`) | Deployment | W1-W2 | **1.5** | none | — |
| P0-03 | Remove the unauthenticated `/media/` route (`S-01`) | Security | W1-W2 | **0.5** | **must precede P0-02 going public** | — |
| P0-04 | Object-level authorization on records and documents (`S-02`+`S-03`+`B-05`) | Security | W1-W2 | **2.0** | P0-01 | — |
| P0-05 | Production configuration, secrets and CORS (`S-04`) | Security | W1-W2 | **1.0** | none | — |
| P0-06 | Remove `apps/storage` (`SC-01`) | Security | W1-W2 | **0.5** | none | — |
| P0-07 | Deploy to the interim VPS behind the security gate (`D-03`) | Deployment | W1-W2 | **1.0** | **P0-01…P0-06 all done** | — |
| P0-08 | Design the MVP validation instrument (`V-02`) | MVP Validation | W1-W2 | **1.0** | none | — |
| P0-09 | Recruit stakeholders and secure written pilot commitment | MVP Validation | W1-W2 | **1.0** | none | — |
| P0-10 | Conduct initial stakeholder validation and record feedback (`V-01`) | MVP Validation | W2-W3 | **1.5** | P0-07, P0-08, P0-09 | — |
| P0-11 | Collect the manual-process baseline (`V-03`) | Research | W2-W3 | **1.5** | P0-09 | **YES** |
| P0-12 | Week 3 SRS/SDD refactor (`F-03`+`DOC-03`) | Documentation | W3 | **2.0** | P0-10 | — |

> **P0-09 is the highest single risk in Semester 2.** Usage evidence, payment evidence, the organic evaluation strand and the entire commercial track depend on a written pilot commitment. It has no substitute beyond scenario-based evaluation (`P1-11`).

### P1 — Thesis-critical (16.75 dev-days)

| ID | Title | Area | Phase | Est | Dependencies | Thesis |
|---|---|---|---|---|---|---|
| P1-01 | `core/enums.py` — one `TextChoices` per concept | Backend | W4 | **0.5** | P0-01 | — |
| P1-02 | Declarative transition table (`W-01`) | Workflow | W4-W7 | **3.0** | P1-01 | **YES** |
| P1-03 | Configurable restart-all resubmission policy (`W-02`) | Workflow | W4-W7 | **0.5** | P1-02 | **YES** |
| P1-04 | Transaction boundaries on transitions (`W-03`) | Workflow | W4-W7 | **0.5** | P1-02 | **YES** |
| P1-05 | **Serialize clearance state — `clearances[]`, `route[]`, `resubmission{}`** | Backend | W4-W7 | **1.0** | P1-02 | **YES** |
| P1-06 | Workflow transition tests across both policies (`T-03`) | Testing | W4-W7 | **1.0** | P1-02, P1-03, P1-14 | **YES** |
| P1-07 | `ClearanceTrack`, `ClearanceStatus`, `PreservationNotice` | UI/UX | W4-W7 | **1.0** | P1-05, P1-19 | **YES** |
| P1-08 | Record detail with the Clearance Track | UI/UX | W4-W7 | **0.75** | P1-07 | **YES** |
| P1-09 | Merge review queues and make the decision screen self-sufficient | UI/UX | W8 | **1.5** | P1-07 | **YES** |
| P1-10 | **Audit workflow events and instrument time-on-task (`W-04`)** | Workflow | **W10 — hard** | **2.0** | P1-04 | **YES** |
| P1-11 | Scenario-based evaluation design (`V-04`) | Research | W10 | **1.0** | P1-03, P0-11 | **YES** |
| P1-12 | Final evaluation execution (`V-05`) | Research | W11-W12 | **3.0** | P1-10, P1-11 | **YES** |
| P1-13 | Workflow and reviewer routing evidence (`V-09`) | Research | W8-W10 | **1.0** | P1-02 | **YES** |

> **P1-10 is the only unrecoverable item.** `AuditEvent` has 14 types, all authentication, file or account — **zero workflow events.** No `SUBMITTED`, no `RESUBMITTED`, no `CLEARANCE_PRESERVED`. The evaluation metrics have no source. Events not written during the Weeks 11–12 pilot cannot be reconstructed and there is no second pilot.

### P1 — Supporting (7.75 dev-days)

| ID | Title | Area | Phase | Est | Dependencies |
|---|---|---|---|---|---|
| P1-14 | CI pipeline, backend test harness, dependency and secret scanning | Testing | W4 | **1.5** | P0-01 |
| P1-15 | Restore the AI app and the Celery pipeline (`B-03`+`B-04`) | Backend | W4-W7 | **2.0** | P0-01 |
| P1-16 | Remove the `is_staff` bypass and add the authorization regression suite | Security | W4-W7 | **2.0** | P0-04, P1-14 |
| P1-17 | Consolidate token storage and fix the refresh path (`FE-01`) | Frontend | W4-W7 | **0.5** | none |
| P1-18 | Reduce the pilot surface to 16 screens (`FE-02`) | Frontend | W4 | **0.5** | none |
| P1-19 | Design-system and accessibility primitive fixes (`UX-01`) | UI/UX | W4 | **0.25** | none |
| P1-20 | Submission wizard — type first, route preview, explicit submit | UI/UX | W4-W7 | **1.0** | P1-19 |

> **P1-19 is 2 hours and must come first.** `Input` gains `aria-invalid`/`aria-describedby`; `Modal` gains a focus trap. Every screen built afterwards inherits correct primitives instead of needing a retrofit.

### P2 — MVP supporting (12.5 dev-days)

| ID | Title | Area | Phase | Est | Dependencies |
|---|---|---|---|---|---|
| P2-01 | RAG — extraction, embedding, pgvector retrieval, FTS fallback | RAG | W5-W7 | **3.0** | P1-15 · **ADR-006 timebox, ends Week 6** |
| P2-02 | Search screen with degraded mode | UI/UX | W8 | **1.0** | P2-01, P1-19 |
| P2-03 | Audit log immutability (`S-07`) | Security | W8-W10 | **0.5** | P1-10 |
| P2-04 | Backups and a rehearsed restore (`D-04`) | Deployment | W10 | **1.0** | P0-07 |
| P2-05 | Health checks and error reporting | Deployment | W8-W10 | **0.5** | P0-07 |
| P2-06 | NFR evidence — security, performance, reliability | MVP Validation | W8-W10 | **2.0** | P1-16, P0-07 |
| P2-07 | NFR evidence — usability, accessibility, responsiveness | MVP Validation | W8-W10 | **2.0** | P1-20, P1-09 |
| P2-08 | Institutional configuration boundaries (`SA-01`) | SaaS | W8-W10 | **0.5** | P1-02 |
| P2-09 | Requirements traceability matrix | Documentation | W13-W15 | **1.0** | P0-12 |
| P2-10 | `TEST_PLAN.md` and `SECURITY.md` with the risk register | Documentation | W13-W15 | **1.0** | P1-14 |

### Commercialization — committed workstream (9.5 dev-days)

| ID | Title | Area | Phase | Est | Dependencies |
|---|---|---|---|---|---|
| C-01 | Customer onboarding, usage monitoring and **payment evidence** | Commercialization | W11-W12 | **2.0** | P0-09, P0-07 · §3 — evidence, not a payment system |
| C-02 | Customer discovery and problem validation | Commercialization | W11-W12 | **1.5** | P0-09 |
| C-03 | Willingness-to-pay and pricing validation | Commercialization | W13-W15 | **1.5** | C-02 |
| C-04 | Lean Canvas and Business Model Canvas | Commercialization | W15 | **1.5** | C-02, C-03 |
| C-05 | Market and competitor analysis | Commercialization | W15 | **1.5** | none |
| C-06 | Pitch deck and commercial defence preparation | Commercialization | W15-W16 | **1.5** | C-03, C-04, C-05 |

**Usage monitoring for `C-01` comes from `P1-10`'s audit export** — no separate analytics build, and no KPI dashboard. That reuse is why `C-01` is 2 days and not 5.

---

## 5 · Capacity validation — **the plan does not fit**

### Available

| | |
|---|---|
| 4 developers × 8 effective hrs/person/week | 32 hrs/week = **4 dev-days/week** |
| Weeks 1–15 | **60 dev-days** |
| Weeks 16–17 | Defence. No new work assumed |

### Required

| Category | Dev-days |
|---|---|
| P0 — Blockers | 15.0 |
| P1 — Thesis-critical | 16.75 |
| P1 — Supporting | 7.75 |
| P2 — MVP supporting | 12.5 |
| Commercialization | 9.5 |
| **Total** | **61.5** |

### Verdict

| | |
|---|---|
| **Total work vs capacity** | **61.5 / 60 = 102%** ❌ |
| Development-only work | 34.0 / 60 = **57%** ✅ |
| Research + validation + documentation | 18.0 |
| Commercialization | 9.5 |

**This is already the cut-down plan.** Removing R-04 grounded generation, code hygiene, session expiry, `ReviewPolicy` consolidation, SaaS provisioning and offboarding, the home/audit/history screens, dead-code removal and the frontend test harness saved ~20 dev-days before this table was written. There is no further fat.

### Per-phase pressure

| Phase | Capacity | Planned | Utilisation | |
|---|---|---|---|---|
| W1-W2 | 8.0 | 10.0 | **125%** | ❌ |
| W3 | 4.0 | 5.0 | **125%** | ❌ |
| W4-W7 | 16.0 | 19.0 | **119%** | ❌ |
| W8-W10 | 12.0 | 13.0 | **108%** | ❌ |
| W11-W12 | 8.0 | 6.5 | 81% | ✅ |
| W13-W15 | 12.0 | 8.0 | 67% | ✅ |

**The plan is front-loaded, not uniformly over.** The first four phases are over by 11 dev-days while the last two have **5.5 dev-days spare**. Part of the gap is a sequencing problem rather than a scope problem.

**Resequencing fix — free, no scope loss.** Move `P2-06` and `P2-07` (NFR evidence, 4.0 dev-days) from W8–W10 to W13–W15. The defence is W16–17, so the evidence does not need to exist before the pilot — only before the write-up.

| Phase | Capacity | After resequencing | |
|---|---|---|---|
| W1-W2 | 8.0 | 10.0 · **125%** | ❌ |
| W3 | 4.0 | 5.0 · **125%** | ❌ |
| W4-W7 | 16.0 | 19.0 · **119%** | ❌ |
| W8-W10 | 12.0 | 9.0 · 75% | ✅ |
| W11-W12 | 8.0 | 6.5 · 81% | ✅ |
| W13-W15 | 12.0 | 12.0 · 100% | ⚠️ |

**Weeks 1–3 and 4–7 remain the problem, and they cannot be resequenced.** W1–W2 carries 8 dev-days of P0 coding plus 2 of validation against 8 available, and the deployment is gated behind all six security cards, so it cannot be parallelised away. W4–W7 is the only window the thesis contribution can be built in.

### The structural question

**Is "8 effective development hours" a development budget or a total budget?**

| Reading | Consequence |
|---|---|
| **Development budget** (recommended) | Research, validation, documentation and commercial work draw on separate hours: 27.5 dev-days ≈ **3.7 hrs/person/week** on top of the 8. Total ≈ 12 hrs/person/week. **The plan fits at 57% development utilisation** |
| **Total budget** | The plan is 102% committed with zero buffer. **Something must be cut — see below** |

This is the single most important thing to settle, and it is your call, not mine. Interviewing a stakeholder or drafting a Lean Canvas does not consume the same hours as writing a transition table, but if the team's 8 hours is genuinely all the time available, the arithmetic is unforgiving.

### If it is a total budget — the cut list, in order

| Order | Cut | Saves | Cost |
|---|---|---|---|
| 1 | **`P2-01` RAG down to FTS-only** — no embeddings, no pgvector, no LLM | **2.0** | FR-M4-01 becomes Phase 2. Defensible via [ADR-008](../adr/008-ai-degradation-to-fts.md), which already pre-commits to this. `search_vector` already exists and works |
| 2 | **`P1-15` Celery/AI app restore** — only needed for RAG | **1.5** | Falls out automatically with cut 1 |
| 3 | `P2-02` search screen reduces to a keyword box | **0.5** | Cosmetic |
| 4 | `P2-06`/`P2-07` NFR evidence reduced to defence-sufficient sampling | **1.0** | Weaker NFR claims; state the sampling honestly |
| 5 | `P2-05` health checks, `P2-08` SaaS config boundaries | **1.0** | Operational and SaaS-story loss |
| | **Total available** | **6.0** | → **55.5 / 60 = 92%.** Still no real buffer |

**Even the full cut list does not produce a comfortable plan.** That is the honest finding. Cutting RAG entirely is the only lever large enough to matter, and it is the one [ADR-006](../adr/006-minimum-rag-pipeline.md) already anticipated with a pre-committed fallback.

**Cuts 1–3 all fall in W4–W7**, which is where the pressure is: they take that phase from 19.0 to 15.0 against 16.0 capacity. Combined with the resequencing above, the only phases still over are **W1–W2 and W3**, and those are over by 3 dev-days that no cut can reach — the system has to boot, be secured, be deployed, and be shown to stakeholders in the same fortnight.

**The realistic options for Weeks 1–3 are:** accept a ~1-week slip on the deployment date, raise capacity for those three weeks only, or run the initial stakeholder validation against a locally-demonstrated system rather than the deployed one. The last is cheapest and costs the least — a demo does not need a public URL.

**Never cut:** `P0-01`…`P0-07` (the system must run and be safe) · `P1-02`…`P1-12` (the contribution and its measurement) · `P1-10` (unrecoverable) · `C-01`…`C-06` (programme-mandated).

---

## 6 · Board structure

```
LEGACY / HISTORICAL  ──  51 issues, label legacy-s1
        │                SUPERSEDED · DUPLICATE · MERGED
        │                DEFERRED · CLOSED · HISTORICAL
        │                linked "is superseded by" ──┐
        ▼                                            │
SEMESTER 2 ACTIVE KANBAN  ◄──────────────────────────┘
   P0 Blockers          12 cards   15.0 d
   P1 Thesis-Critical   13 cards   16.75 d
   P1 Supporting         7 cards    7.75 d
   P2 MVP Supporting    10 cards   12.5 d
   Commercialization     6 cards    9.5 d
                        ─────────────────
                        48 cards   61.5 d
   P3 Post-MVP          no cards — docs/architecture-tasks/12-scope-cuts.md
```

### Labels

| Group | Values |
|---|---|
| Lifecycle | `legacy-s1` `s2-active` |
| Legacy class | `superseded` `duplicate` `merged` `deferred` `historical` |
| MVP | `mvp-blocker` `mvp-required` `mvp-recommended` `post-mvp` `do-not-build` |
| Phase | `phase-w1-w2` `phase-w3` `phase-w4-w7` `phase-w8-w10` `phase-w11-w12` `phase-w13-w15` `post-semester` |
| Area | `area-backend` `area-frontend` `area-workflow` `area-security` `area-rag` `area-saas` `area-deployment` `area-testing` `area-mvp-validation` `area-uiux` `area-research` `area-documentation` `area-commercialization` |
| Thesis | `thesis-critical` |
| Flow | `blocked` `ready-to-pull` |

Priority: P0 → `Highest`, P1 → `High`, P2 → `Medium`. **No assignees — the team pulls.**

---

## 7 · Decisions required before applying

| # | Question | Blocks | Why it matters |
|---|---|---|---|
| 1 | **Is 8 hrs/person/week a development budget or a total budget?** | The whole plan | Development-only → fits at 57%. Total → 102% and RAG must go |
| 2 | **Is external AI data transmission permitted?** | `P2-01`, `P1-15` | **UNCONFIRMED.** If refused, RAG is cut anyway and 3.5 dev-days return |
| 3 | **Is out-of-band payment evidence acceptable?** (§3) | `C-01` | If payment must be *inside* IRIS: 8–15 dev-days that do not exist |
| 4 | **Will the SRS amendment for Docling-serve deferral be accepted?** | `P0-12` | SRS-specified in four places |
| 5 | **Is CIT-U infrastructure confirmed, or is the interim VPS final?** | `P0-07` | Migration stays documented, not built |
| 6 | **Jira issue-type scheme** | All 48 cards | Proposed as Story under Epic; will map to Task/Subtask if the scheme requires |

---

## 8 · What gets applied on approval

| Action | Count |
|---|---|
| Create S2 epics | 5 |
| Create active cards | 41 |
| Label legacy issues `legacy-s1` + classification | 51 |
| Create `is superseded by` links | 14 |
| Close as delivered | 2 |
| **Jira writes total** | **~113** |

No legacy issue is deleted. No legacy status is edited. No assignees are set.
