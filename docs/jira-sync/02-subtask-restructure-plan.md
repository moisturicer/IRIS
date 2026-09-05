# Jira subtask restructure plan

**Site:** `citiris.atlassian.net` · **Project:** IR
**Status: all of §2–§5 are executed, dated 2026-09-05.** Epics D and E (§6) remain deliberately unrestructured — see that section for why. Per the existing convention ([`00-reconciliation-plan.md`](00-reconciliation-plan.md), [`01-revised-capacity-validated-plan.md`](01-revised-capacity-validated-plan.md) — both in git history, deleted from the working tree but not superseded in substance), a section was written up before any ticket in it was touched.

**A mechanical limitation discovered during execution, relevant to every remaining section:** Jira's edit endpoint refuses to change an issue's type across hierarchy levels (Story → Subtask) even with `parent` supplied in the same call — confirmed by testing directly, not assumed. There is no exposed "move issue" operation either. **"Convert in place" is therefore not achievable as originally worded.** What was actually done for Epic B, and what §3–§4 should expect: a fresh Subtask is created under the new parent with the old ticket's scope (narrowed per any partial-delivery comments); the old ticket is left at its current status (this workflow has no "Won't Do" — transitioning to Done would misrepresent redirected work as reviewer-approved, which the Definition of Done forbids), gets a `superseded` label, a `Relates` link to its replacement, and a comment pointing to it. History, comments and prior PR references stay fully intact on the old ticket; only the key changes.

## 0 · Why this exists

The v2 Semester 2 backlog (41 cards, five new epics) was built by mapping one Jira Story onto one-or-several [`docs/architecture-tasks/`](../architecture-tasks/00-index.md) spec IDs (e.g. `P1-02` = `W-01`, `P0-04` = `S-02`+`S-03`+`B-05`). That predates IR-89 and IR-108, which were built later by someone actually running a spec → tracer-bullet-subtasks pass against ADR-013/015: one parent Story, lettered subtasks (A, B, C…), each with its own acceptance criteria and an explicit `Blocked by` edge to the subtask(s) it needs. That shape is what makes IR-89/108 easy to pick up cold — a flat P1-xx ticket gives no such entry point.

This plan regroups the flat backlog into that shape **where the underlying work is actually one capability**. It does not force the shape everywhere — see §6, where it explicitly isn't a good fit.

## 1 · Current state

| Epic | Key | Children | Shape today |
|---|---|---|---|
| S2 Epic A: Platform Stability and Security | IR-52 | 7 flat Stories (P0-01…P0-07) + IR-89 | Flat |
| S2 Epic B: Workflow and Thesis Contribution | IR-53 | 11 flat Stories (P1-01…P1-13) + IR-106 (Done, unrelated) | Flat |
| S2 Epic C: Engineering Practice and Delivery | IR-54 | 12 flat Stories (P1-14…P2-08) + IR-105, IR-107, IR-108 | Flat, plus two RAG tickets that don't belong thematically |
| S2 Epic D: MVP Validation and Research Evaluation | IR-55 | 11 flat Stories (P0-08…P2-10) | Flat |
| S2 Epic E: Commercialization and Sustainability | IR-56 | 6 flat Stories (C-01…C-06) | Flat |
| — | IR-89, IR-107, IR-108 | — | **Already subtask-shaped** (IR-89 has 8 subtasks IR-109–116; IR-108 has 7, IR-127–133) but scattered across three different epics |
| — (no epic) | IR-117–126 | 10 Stories/Bugs | Flat, but **not from this pattern at all** — created later, ad hoc (see §7) |

**45 tickets are candidates for regrouping. 10 are not** (§7). RAG's own three tickets need re-parenting more than restructuring (§5).

## 2 · Epic B — Workflow and Thesis Contribution (IR-53): executed 2026-09-05

**One parent Story, `IR-134`** ("Declarative workflow engine and clearance-aware resubmission (ADR-002/ADR-003)"), **11 lettered subtasks**:

| Subtask | New key | Supersedes | Spec | Note |
|---|---|---|---|---|
| A | `IR-135` | `IR-73` | `F-02` | core/enums.py |
| B | `IR-136` | `IR-69` | `W-01` | Declarative transition table |
| C | `IR-137` | `IR-70` | `W-02` | Restart-all resubmission policy |
| D | `IR-138` | `IR-71` | `W-03` | Transaction boundaries |
| E | `IR-139` | `IR-72` | `W-07` | Serialize clearance state — narrowed scope, PR #22 partial delivery preserved on old ticket |
| F | `IR-140` | `IR-74` | `T-03` | Transition tests, both policies |
| G | `IR-141` | `IR-75` | — | ClearanceTrack/ClearanceStatus/PreservationNotice — narrowed scope, PR #22 partial delivery preserved on old ticket |
| H | `IR-142` | `IR-76` | — | Record detail with Clearance Track — narrowed scope, PR #22 partial delivery preserved on old ticket |
| I | `IR-143` | `IR-77` | — | Merge review queues |
| J | `IR-144` | `IR-78` | `W-04` | Audit workflow events — Week 10 hard deadline carried forward |
| K | `IR-145` | `IR-81` | `V-09` | Workflow and reviewer routing evidence |

Old tickets superseded, each `Relates`-linked, `superseded`-labelled and commented: `IR-73`→A, `IR-69`→B, `IR-70`→C, `IR-71`→D, `IR-72`→E, `IR-74`→F, `IR-75`→G, `IR-76`→H, `IR-77`→I, `IR-78`→J, `IR-81`→K.

**Content completeness, updated 2026-09-05:** each of the 11 new subtasks now carries its old ticket's full body verbatim (Objective through Definition of Done, every original acceptance criterion) beneath the condensed "What to build" section, plus — for E, G, H — the full PR #22 delivery-history comment, with already-shipped items marked `[x]` rather than dropped. This was done specifically so the eleven old tickets (`IR-69`–`IR-78`, `IR-81` — **not** `IR-79`/`IR-80`, which are unrelated Epic D tickets and were never touched) can be safely bulk-deleted later without losing content. Two known-stale fragments were carried forward flagged rather than silently fixed or silently repeated: `IR-69`'s "cut RAG first" line (superseded by the 2026-09-04 ADR-013 amendment) and `IR-70`'s `PRESERVE`/`RESTART_ALL` naming (superseded by `CLEARANCE_AWARE`/`RESTART_ALL` in `docs/architecture-tasks/04-workflow.md`).

**Deletion itself is not something these tools can execute** — no delete-issue operation exists in this Jira MCP's catalog (confirmed by search, twice). If the eleven are deleted, it will be a manual bulk-delete in the Jira UI, and Jira deletion has no undo.

Blocking edges wired as native Jira `Blocks` links, not just prose: A→B→{C,D,E}→F(+external `IR-82`), E→G(+external `IR-87`)→{H,I}, D→I, D→J, {B,F}→K, external `IR-57`→A, J→{external `IR-80`, external `IR-99`}.

IR-106 (Done, "Resolve the AI gateway architecture contradiction") is parented under `IR-53` but is unrelated content — left alone, not part of this restructure.

## 3 · Epic A — Platform Stability and Security (IR-52): executed 2026-09-05

Not one capability — seven distinct fixes sharing only a Week 1–2 deadline. Two parent Stories.

**A1 — `IR-147`, "Security gate before the app is public"** (3 subtasks):
| Subtask | New key | Supersedes | Spec |
|---|---|---|---|
| A | `IR-152` | `IR-59` | `S-01` |
| B | `IR-153` | `IR-60` | `S-02`+`S-03`+`B-05` |
| C | `IR-154` | `IR-61` | `S-04` |

**A2 — `IR-148`, "Boot and deploy the stack"** (3 subtasks):
| Subtask | New key | Supersedes | Spec | Note |
|---|---|---|---|---|
| A | `IR-155` | `IR-57` | `B-01`+`B-02` | Full delivery history (PR #17, then PR #22 commit `5f05d27`) preserved; `pyflakes` verification genuinely still open |
| B | `IR-156` | `IR-58` | `D-01`+`D-02` | The ticket's own "Corrected 2026-09-04" banner, and the pre-correction comment it contradicts, both preserved verbatim |
| C | `IR-157` | `IR-63` | `D-03` | Hard-gated on all of A1 + A2-A/B + `IR-62` |

**Left flat, not restructured:** `IR-62` (P0-06, remove `apps/storage`) — one dead-code removal.

## 4 · Epic C — Engineering Practice and Delivery (IR-54): executed 2026-09-05

Spans frontend, backend, CI, deployment ops and SaaS config, bundled only by "not a blocker, not validation." Three parent Stories.

**C1 — `IR-149`, "Frontend foundation and pilot surface"** (5 subtasks):
| Subtask | New key | Supersedes | Spec | Note |
|---|---|---|---|---|
| A | `IR-158` | `IR-87` | `UX-01` | Must land first, per original note |
| B | `IR-159` | `IR-85` | `FE-01` | |
| C | `IR-160` | `IR-86` | `FE-02` | **Open human decision preserved, not resolved**: is the 16-screen target still 16, or is `docs/ui-ux/15-mvp-ui-scope.md` §9 amended? |
| D | `IR-161` | `IR-88` | — | Extensive redesign history preserved; flags an apparent ADR numbering collision (a cited "ADR-016 — conditional parallel office routing" vs. the real `docs/adr/016-docling-structured-extraction.md`), not resolved here |
| E | `IR-162` | `IR-90` | — | **Open human decision preserved**: does the shipped "Ask IRIS" chat satisfy this card, or is a plain Search screen still needed? |

**C2 — `IR-150`, "Backend and CI hardening"** (3 subtasks):
| Subtask | New key | Supersedes | Spec | Note |
|---|---|---|---|---|
| A | `IR-163` | `IR-82` | `F-01`+`T-01`+`T-05` | Nearly fully delivered — most AC checked off |
| B | `IR-164` | `IR-83` | `B-03`+`B-04` | **Rescoped against the live tree, not copied unexamined** — see below |
| C | `IR-165` | `IR-84` | `S-05`+`T-02` | |

> **`IR-83`/`IR-164` rescope, verified directly against the code on 2026-09-05, not assumed:** `documents/tasks.py`'s undeclared extraction imports are gone (`IR-107` fixed that half). `apps/ai/models/` is split — `chunk.py`/`embedding.py`/`embedding_space.py`/`ingestion_job.py` are real (`IR-89`); `conversation.py`/`summary.py` remain field-less stubs, no longer "shadowing" anything since chat/summarization was simply never built. **The Celery queue-routing defect is confirmed still live**: no `CELERY_TASK_ROUTES` or `CELERY_TASK_DEFAULT_QUEUE` exists anywhere, three workers consume `default`/`extraction`/`embedding`, no task declares a queue — every dispatched task, including `ai.tasks.chunk_record_document`, lands on Celery's unconsumed default queue. **This contradicts `CLAUDE.md`'s claim that ingestion runs "in a worker... with no manual step."** Not fixed by this restructure — surfaced for separate follow-up.

**C3 — `IR-151`, "Production hardening"** (3 subtasks):
| Subtask | New key | Supersedes | Spec |
|---|---|---|---|
| A | `IR-166` | `IR-91` | `S-06`+`S-07` |
| B | `IR-167` | `IR-92` | `D-04` |
| C | `IR-168` | `IR-93` | `D-05` (reduced) |

**Left flat:** `IR-94` (P2-08, SaaS config boundaries), `IR-105` (traceability convention, In Review, undisturbed).

**Re-parented, not restructured:** `IR-107`, `IR-108` — see §5.

**Content completeness, all of §3–§4:** every subtask above carries its old ticket's full body verbatim beneath its condensed "What to build," plus full delivery-history comments where they existed, following the same rule established in §2. All 17 old tickets (`IR-59`, `IR-60`, `IR-61`, `IR-57`, `IR-58`, `IR-63`, `IR-87`, `IR-85`, `IR-86`, `IR-88`, `IR-90`, `IR-82`, `IR-83`, `IR-84`, `IR-91`, `IR-92`, `IR-93`) are `superseded`-labelled, `Relates`-linked and commented, left at their real status — none forced to Done.

## 5 · The RAG cluster — consolidated 2026-09-05

Option (a) taken: **`IR-146`, "S2 Epic F: RAG / AI Pipeline,"** created; `IR-89`, `IR-107`, `IR-108` re-parented onto it from `IR-52`/`IR-54`. Their own subtask structures (`IR-109`–116 under `IR-89`; `IR-127`–133 under `IR-108`) are untouched — this was pure re-parenting, no content change, and IR-108's subtasks were not individually re-labelled (a possible future nit, not done here).

While touching these tickets, a stale line was also found and corrected in both `IR-89` and `IR-108`'s bodies: both still read "RAG is not the thesis contribution... first thing to cut," left over from before this session's ADR-013/016 and `CLAUDE.md` amendments earlier the same day. Both now carry a dated amendment note instead, and both gained the `thesis-critical` label (previously only added to `IR-89`'s own subtasks, missed on `IR-89`, `IR-107`, `IR-108` themselves).

## 6 · Epics D and E: restructuring adds little or nothing

**Epic D (IR-55, MVP Validation)** is a research protocol, not a build — a sequential chain (design instrument → recruit → validate → baseline → …) already expressed as plain dependency notes in the v2 plan. It *could* take three parent Stories (validation protocol / final evaluation / NFR + docs evidence), but this is Weeks 8–15 work, far out, and none of it is blocked or confusing today the way the workflow tickets are. **Recommend deferring this epic's restructuring** rather than doing it now alongside B/A/C.

**Epic E (IR-56, Commercialization)** — each `C-0x` (customer discovery, pricing validation, Lean Canvas, market analysis, pitch deck) is already one atomic, single-owner deliverable. There is no internal capability to split into subtasks here. **Recommend leaving Epic E flat, permanently** — this is the concrete case of "the pattern doesn't fit everywhere."

## 7 · IR-117–126: a different, newer problem — leave alone

These ten tickets (Stories: 117, 118, 119, 120, 124, 125; Bugs: 122, 123, 126; plus IR-121, itself a small standalone epic "Calls and Conferences") were created after the architecture-tasks reconciliation, have no epic parent from that sync, and aren't bundled specs — they're individual bug reports and scope-drift dispositions (e.g. IR-122 "any user could change their own email," IR-117 "reader-side surfaces built ahead of scope, needs a disposition"). They don't exhibit the flat-bundling problem this plan exists to fix; each is already a single, scoped unit of work. **Out of scope for this restructure.**

## 8 · In-progress tickets — actual outcome

The confirmed rule was **convert in place**. Execution found this is not achievable through the Jira API available here (§0): a Story→Subtask hierarchy-level change is rejected by the edit endpoint even with `parent` supplied, and no "move issue" operation exists. What actually happened for every ticket below — in-progress or not — is the supersede-and-preserve mechanism in §0: a new Subtask carries the full original content forward, the old ticket keeps its status, comments and history, gets `superseded`-labelled and linked.

| Ticket | Was | Became |
|---|---|---|
| IR-57 | P0-01, In Review | A2 subtask A (`IR-155`) |
| IR-72 | P1-05, In Progress | Workflow subtask E (`IR-139`) |
| IR-75 | P1-07, In Progress | Workflow subtask G (`IR-141`) |
| IR-76 | P1-08, In Progress | Workflow subtask H (`IR-142`) |
| IR-82 | P1-14, In Progress | C2 subtask A (`IR-163`) |
| IR-86 | P1-18, In Progress | C1 subtask C (`IR-160`) |
| IR-88 | P1-20, In Progress | C1 subtask D (`IR-161`) |

No in-progress tickets sat in Epic D or E, so §6's deferral cost nothing there.

## 9 · Execution order — all complete

1. ~~**Epic B (Workflow)**~~ — **done 2026-09-05**, §2.
2. ~~**§5 RAG consolidation**~~ — **done 2026-09-05**, §5.
3. ~~**Epic C's three groupings**~~ — **done 2026-09-05**, §4, including the IR-83 rescope.
4. ~~**Epic A's two groupings**~~ — **done 2026-09-05**, §3.
5. **Epic D, E** — deferred per §6 unless priorities change. The only remaining open item in this plan.
