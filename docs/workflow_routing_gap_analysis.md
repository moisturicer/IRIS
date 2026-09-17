# Workflow routing — repository gap analysis (input to `/to-spec` and `/to-tickets`)

**Status:** findings only. This is not a specification and not a ticket plan. The workflow is
final (ADR-021, ADR-022). This file adds the repository facts **not already recorded** in
[`workflow_routing_architecture.md`](workflow_routing_architecture.md):

- §3 there lists the conflicts, with file and line.
- §4 there gives the symbol-by-symbol mapping.
- §10 there covers test impact.

Read those first; this file only fills the gaps.

Read-only inspection of `docs/IR-254-reviewer-directed-routing` @ `7770d5e`, 2026-09-15.

---

## 1. Ask IRIS visibility

| Surface | Current behaviour | File | Change required |
|---|---|---|---|
| `POST /ai/ask/`, `POST /ai/search/` | Both call `search_records()`, which filters on `Record.objects.publicly_visible()`. Approved and completed Proposals are therefore retrievable and citable | `ai/services/retrieval.py:95,109`; `ai/views/chatbot.py:74` | None of its own. Narrowing `PUBLICLY_VISIBLE_STATUSES` to `(PUBLISHED,)` fixes both, because they share the one predicate |
| `GET /ai/status/` | `indexed_records` counts `publicly_visible()` | `ai/views/chatbot.py:97` | The count drops automatically with the tuple; note the change in the PR |
| `POST /ai/embed/all/`, `POST /ai/embed/<pk>/` | Embeds **every** record without `RecordEmbedding`, whatever its status: drafts, in-review records, Proposals. Staff-only | `ai/views/embedding.py:9–45` | **No exposure today**: Ask IRIS retrieval is FTS and does not read `RecordEmbedding`. **This is a latent leak.** Any future vector retriever over `RecordEmbedding` must filter through the visibility predicate |
| `chunk_record_document` | Chunks every uploaded document's record, whatever its status | `ai/tasks.py:24` | Same latent condition as the embeddings row, for any future chunk retriever |

## 2. Discover, frontend

| Current behaviour | File | Change required |
|---|---|---|
| Treats a Proposal with `pipeline_status === "approved"` as public "ongoing" research, citing the frozen SRS ("approves → approved (visible as ongoing)") | `frontend/src/features/discover/discoverUtils.ts:136, 162–168` | Must change in the same slice as the backend tuple. Otherwise Discover keeps rendering a state the API no longer returns to other users |

## 3. Permissions

| Current behaviour | File | Change required |
|---|---|---|
| `complete` is gated by `IsRDCO` alone | `records/views.py:121–122` | An Adviser may complete only a Proposal **they are assigned to** (`record.adviser_id == user.pk`). That is an object-level condition; a role check is not enough. Covers ADR-021 §7 |
| `complete` only accepts `approved` Proposals | `records/views.py:345–369` | Record-type and state checks stay; the actor check widens |
| `submit` allows owner or staff | `records/views.py:119` | Unchanged. It opens the entry assignment (IR-257/IR-260) |

## 4. Reviewer history endpoints

The architecture doc does not cover these.

| Endpoint | Current behaviour | File | Change required |
|---|---|---|---|
| `GET /reviews/approved/` | This reviewer's `Review.status="approved"` rows, shaped with `ROLE_TO_OFFICE` | `reviews/views.py:201–212` | Rebuild on `ROLE_TO_PARTIES` / assignments. `approved` now covers clears and decisions |
| `GET /reviews/declined/` | This reviewer's `status__in=["declined","rejected"]` rows | `reviews/views.py:214–229` | `declined` now means *resubmission requested*. Offices and Intake no longer write `rejected`. `NEGATIVE_FINDING` is new, so decide whether it appears here |
| `GET /reviews/analytics/` | Returns 501; stub is keyed on `Review.stage` | `reviews/views.py:98–110` | No behaviour change. The `rdco_intake` → `intake` rename changes the stage value it would group by |

## 5. Test tooling

- **The frontend has only Vitest** (`frontend/package.json:11–12`). There is no Playwright or
  Cypress.
- End-to-end verification therefore means backend API integration tests, plus manual browser
  verification against `seed_demo`.
- Adding an e2e runner is an infrastructure decision for the team. Do not add one inside a
  workflow ticket.

## 6. Audit

`apps/audit/models.py` has account event types only (for example `ACCOUNT_UNLOCKED`) and no
workflow events. Workflow auditing stays with IR-144 and IR-216. `RoutingEvent`,
`ResubmissionRequest` and `DocumentRequest` are what those tickets will serialise.

## 7. Jira facts

- **IR-254 and IR-255 are both `Story` issues under Epic IR-53.** Jira's hierarchy does not let
  a Story parent another Story, so IR-254 cannot be the parent of implementation tickets. The
  epic in use is **IR-53**. IR-254 and IR-255 are currently **not linked**.
- **IR-256 to IR-264 are `Subtask`s of IR-255, with no dependency links.** Their order exists
  only as prose in the descriptions.
- **IR-233** (Bug, To Do, no parent) is linked *relates to* IR-140 and IR-224.
- **IR-224** is *blocked by* IR-219.
- **IR-144** is a Subtask of IR-134 and is *blocked by* IR-138.
- **IR-216** is a Task under IR-215.

## 8. Slicing constraints the code imposes

These are **facts about what can ship separately, not a proposed ticket structure.**

**Can land on the current pipeline, before the contract migration, without structural change:**

- Specialist offices and intake lose terminal rejection: `lifecycle.py:285, 316, 328`;
  `reviews/services.py:submit_clearance`; `EvaluationPage.tsx:39–45`.
- ITSO becomes reachable for Thesis/Research: the gate at `lifecycle.py:519`. `itso_review`
  already admits ITSO.
- The assigned Adviser can complete an approved Proposal: `records/views.py:121, 345`.
- Proposals leave Discover and Ask IRIS: `core/enums.py:72`, plus the delete decoupling at
  `records/views.py:148` and `lifecycle.py:375`, plus `discoverUtils.ts:162–168`.
- Document requests. These need only the shadow assignments that dual-write provides, and never
  change `pipeline_status`.

**Must be delivered together with the contract migration**, because the single-value pipeline
cannot represent them:

- anything that creates concurrent assignments across parties (`route()`);
- resubmission driven by `ResubmissionRequest`;
- removing the stage values and `declined`.

IR-260 as currently written bundles both kinds. At 5–6 d it is the largest card.

## 9. Open items to carry into `/to-spec`

1. **PR #81 is OPEN, not merged.** ADR-021, ADR-022 and the architecture doc exist only on
   branch `docs/IR-254-reviewer-directed-routing`. Run `/to-spec` from that branch, or after the
   PR merges.
2. **Reading of "approve/complete" for a Proposal.** ADR-021 §3 (accepted) records two acts, each
   performed by the assigned Adviser or RDCO: approve (→ `approved`, research ongoing), then
   complete (→ `completed`). The latest instruction says "approve/complete" and "reject/complete".
   If that means approval should go straight to `completed` with no `approved` state, it is a
   one-row change to ADR-021 §3. It also affects My Workspace's *Research Ongoing* stage and
   `discoverUtils.ts:162`. The accepted ADR is followed unless a person rules otherwise.
