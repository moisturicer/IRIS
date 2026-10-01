# IR-145 — Workflow and reviewer routing evidence (FR-M5-01)

What this shows: each record type routes correctly end to end, parallel offices clear independently and in either order, and a reviewer who is not eligible at a stage is refused. Every claim below names a test and points at the recorded run, [`IR-145-reviews-pytest-output.txt`](IR-145-reviews-pytest-output.txt).

## The run

| | |
|---|---|
| Date | 2026-10-02 |
| Base | `origin/main` at `eedef63` |
| Command | `python -m pytest apps/reviews -vv -rsx -p no:cacheprovider -W ignore` (from `backend/`) |
| Environment | Windows 11, Python 3.13.7, Django 5.1.15, local PostgreSQL |
| Result | **263 passed, 2 skipped, 1 xfailed** in 32.30 s |

Two results are not passes, and neither touches routing:

- **2 skipped** — `test_workflow_characterisation.py:655`, the legacy-import tests, need `pyexcel`, which was not installed in this environment. CI installs it. They are not in the table below.
- **1 xfailed** — `test_resubmission_after_a_metadata_revision_resets_only_the_requesting_office`, the known defect **IR-233**: a metadata-only revision is refused where ADR-021 §11 accepts one. It is marked `strict`, so it fails the build the day it unexpectedly passes. It concerns what counts as a revision, not which route a record takes.

This is a local run, not a CI run; no CI link is claimed.

## Acceptance criteria

Where a test appears under both resubmission policies it runs as `ClearanceAwareMatrixTests` and `RestartAllMatrixTests` (ADR-004's two arms); both are green in the output file.

### 1. All three routes, end to end

| Record type | Route walked | Test (`apps/reviews/test_workflow_characterisation.py`) |
|---|---|---|
| Proposal | Draft to Completed, through its Adviser | `ProposalRouteEndToEndTests::test_a_proposal_walks_draft_to_completed` |
| Thesis / Research | Draft to Published | `ProposalRouteEndToEndTests::test_a_thesis_walks_draft_to_published` |
| Project | Draft to Published, through ITSO | `ProposalRouteEndToEndTests::test_a_project_walks_draft_to_published_through_itso` |

Each type also enters its own first stage on submission: `SubmissionRoutingTests::test_each_record_type_enters_its_own_first_stage`. Beyond the three walks, `test_workflow_matrix.py` drives every declared review edge for every type:

- `test_every_matrix_cell_lands_where_it_should`
- `test_every_record_type_is_exercised` — fails if a type is missing from the grid
- `test_a_full_route_is_identical_under_both_arms`

### 2. Parallel offices, independently and in either order

| Claim | Test (`apps/reviews/test_workflow_matrix.py`, `test_workflow_characterisation.py`) |
|---|---|
| One office clearing leaves the record where it is and the others pending | `test_one_office_clearing_leaves_the_record_where_it_is`; `ClearanceRoutingTests::test_one_office_clearing_leaves_the_others_pending` |
| The last office clearing advances to final review | `test_the_last_office_clearing_advances_to_final_review` |
| **Either order, same end state** | `test_the_offices_may_clear_in_either_order` — IERC then KTTO, and KTTO then IERC, both ending in RDCO review with both cleared |
| Out of order across stages | `test_ktto_may_clear_before_itso_at_the_itso_stage` |
| Each clearance is recorded against its own office only | `test_a_clearance_is_recorded_against_its_own_office_only` |

### 3. An ineligible reviewer is refused

| Who is refused | Test |
|---|---|
| Any role, at a status that is not a review gate | `test_no_role_can_review_at_a_status_that_is_not_a_gate` |
| An office, at a stage its group excludes | `test_an_office_cannot_clear_at_a_stage_its_group_excludes` |
| An office, at a sequential gate | `test_an_office_cannot_act_at_a_sequential_gate` |
| An Adviser, at an RDCO gate | `test_an_adviser_cannot_act_at_an_rdco_gate` |
| An Adviser who is not assigned to the proposal | `test_only_the_assigned_adviser_may_review_a_proposal`; `test_reject_authority.py::RejectAuthorityTests::test_an_adviser_not_assigned_to_the_proposal_cannot_reject_it` |
| An office rejecting its own pending clearance | `RejectAuthorityTests::test_an_office_cannot_reject_its_pending_clearance` |
| Resubmission from any status but Declined | `test_resubmission_is_refused_from_every_status_but_declined` |
| What the refusal says | `test_the_refusal_says_what_was_wrong` |

These are the authorisation cases, kept separate from the routing ones above because the two are easy to conflate.

### 4. The route comes from configuration, not hardcoded branches

`test_the_matrix_covers_every_declared_review_edge` builds its expected set from `lifecycle.load_table()`, the declarative transition table (ADR-002), and asserts the suite's cases equal the table's edges in both directions. A new stage, event or office in the table fails the test until a case exists for it; a case for an edge the table does not declare fails it too. The suite therefore tracks the table instead of restating it.

## What this does not include

**A recorded manual walkthrough.** The ticket's acceptance criterion is "test output or recording", and the test output above meets it. A screen recording of the UI is a human step, was not made, and is not claimed. If the thesis wants to show a reader the workflow directly, record it separately and link it here.

## Traceability

[`TRACEABILITY.md`](../TRACEABILITY.md), FR-M5-01, links this file. The row was already **VERIFIED** from IR-140 (2026-09-10) with one open defect, IR-233; this adds the end-to-end, either-order and refusal evidence IR-145 asked for.
