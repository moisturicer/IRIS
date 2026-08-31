# 02 — Backend

Nine tasks. Two are boot blockers — nothing in this repository can be verified until they land.

---

# B-01 · Fix six undefined names — restore application boot

## Objective
Make the Django URLconf loadable so the API responds at all.

## Problem
`apps/records/views.py` uses six names it never imports. One is evaluated in a `class` statement, so the module raises `NameError` at **import** time. `config/urls.py` includes it, so the entire URLconf fails and every endpoint returns 500.

## Evidence
`pyflakes 3.4.0` over all backend `.py` files:
```
apps/records/views.py:535:32: undefined name 'timezone'
apps/records/views.py:541:21: undefined name 'make_download_token'
apps/records/views.py:546:39: undefined name 'settings'
apps/records/views.py:550:26: undefined name 'APIView'
apps/records/views.py:563:22: undefined name 'verify_download_token'
apps/records/views.py:579:20: undefined name 'file_response_for_record'
```
Line 550 is `class DownloadRedeemView(APIView):`. Import chain: `config/urls.py:11` → `apps.records.urls` → `apps.records.views:3`. `records/download_tokens.py` and `records/download_service.py` define four of the six and are imported by nothing.

## Current State
The application does not start.

## Proposed State
All six imported; `manage.py check` passes; every route resolves.

## Scope
Add the six imports. Verify with `manage.py check` and a URLconf resolver walk.

## Out of Scope
The misplaced methods (`B-02`) and the authorization gaps on the same endpoints (`S-02`).

## Technical Approach
`from django.utils import timezone` · `from django.conf import settings` · `from rest_framework.views import APIView` · `from .download_tokens import make_download_token, verify_download_token` · `from .download_service import file_response_for_record`.

## Dependencies
None. **Blocks everything.**

## Risks
Low to apply. These endpoints have **never executed**, so first correct execution may surface further defects — budget for that rather than assuming green.

## Security Impact
Neutral directly; brings the download-redeem path into service, making `S-02` and `S-03` urgent rather than theoretical.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
Prerequisite for demonstrating anything.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Week 1

## Complexity
XS

## Acceptance Criteria
- [ ] `python manage.py check` exits 0.
- [ ] `python -c "import config.urls"` succeeds.
- [ ] `pyflakes apps/records/views.py` reports zero undefined names.
- [ ] `GET /api/v1/records/` returns 200 for an authenticated user.

## Testing Requirements
`T-01`'s import-smoke test, added in the same PR.

## Documentation Requirements
None.

## Definition of Done
Merged with the smoke test; CI runs `manage.py check`.

---

# B-02 · Relocate four methods indented into the wrong class

## Objective
Restore the download-request approve/decline endpoints, which resolve to a class that does not define them.

## Problem
`get_permissions`, `perform_create`, `approve` and `decline` sit inside `DownloadRedeemView(APIView)` instead of `DownloadRequestViewSet`. Three routed endpoints raise `AttributeError`; `DownloadRedeemView.get_permissions` reads `self.action`, which `APIView` lacks, so the redeem endpoint 500s too.

## Evidence
`records/views.py`: `class DownloadRedeemView` at :550, `class DeleteRequestViewSet` at :632, with `get_permissions` (:588), `perform_create` (:593), `approve` (:598), `decline` (:615) between them. `records/urls.py:15-16` routes to `DownloadRequestViewSet.as_view({"post": "approve"})`. `notify_download_request` and `notify_download_reviewed` are consequently unreachable.

## Current State
Three endpoints the frontend calls are broken.

## Proposed State
The four methods live on `DownloadRequestViewSet`; `DownloadRedeemView` keeps only `permission_classes` and `get`.

## Scope
Re-indent; delete the `get_permissions` override from `DownloadRedeemView`; reconcile the duplicate `partial_update` that overlaps `approve`/`decline`.

## Out of Scope
Redesigning the download flow. Watermarking (deferred, [ADR-001](../adr/001-mvp-scope-boundary.md)).

## Technical Approach
Pure code motion, then verify each of the three routes.

## Dependencies
`B-01`.

## Risks
Low. These endpoints have never run — treat first execution as new code.

## Security Impact
`DownloadRedeemView` regains its intended `AllowAny` + signed-token behaviour. The token design itself is sound.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
None — download requests are deferred from MVP scope, but the module must import.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Week 1

## Complexity
S

## Acceptance Criteria
- [ ] `POST /records/download-requests/<id>/approve/` returns 200 for staff and sets status `approved`.
- [ ] `POST .../decline/` returns 200 and sets `declined`.
- [ ] `GET /records/download/?token=<valid>` streams the file; an expired token returns 403.
- [ ] No `AttributeError` in logs for any of the three routes.

## Testing Requirements
One integration test per route.

## Documentation Requirements
None.

## Definition of Done
Merged with tests; duplicate `partial_update` logic reconciled.

---

# B-03 · Celery task routing

## Objective
Make background jobs execute.

## Problem
Workers are started against named queues that no task publishes to, so every enqueued task waits forever.

## Evidence
Compose runs `-Q default`, `-Q extraction`, `-Q embedding`, plus `beat`. `grep -rn "task_routes\|beat_schedule\|queue" backend/config/ backend/apps/*/tasks.py` returns **no matches**. Every `@shared_task` publishes to Celery's built-in `celery` queue, which no worker consumes. `celery-beat` runs with no schedule.

## Current State
PDF extraction is enqueued and never runs.

## Proposed State
Explicit `CELERY_TASK_ROUTES`; one worker consuming the routed queues; beat removed until a periodic task exists.

## Scope
`CELERY_TASK_ROUTES` in `settings/base.py`; `CELERY_TASK_DEFAULT_QUEUE` set explicitly; Compose worker flags reconciled ([ADR-010](../adr/010-deployment-topology.md)).

## Out of Scope
Worker topology (`D-01`).

## Technical Approach
Route by module path. One worker for the MVP; the SRS's `celery-worker` / `celery-worker-rag` split is the documented scale path.

## Dependencies
`D-01`. **Blocks `R-01`** — extraction cannot run without it.

## Risks
Low. Verify with `celery -A config inspect active_queues`.

## Security Impact
None.

## Performance Impact
Restores asynchronous processing; without it NFR-P4 is unmeasurable.

## SaaS Impact
Per-instance worker under [ADR-005](../adr/005-instance-per-tenant.md).

## Research/Thesis Impact
Indirect — document processing must work for the pilot.

## MVP Classification
MVP BLOCKER

## Priority
P1 — Week 4

## Complexity
S

## Acceptance Criteria
- [ ] `celery -A config inspect active_queues` shows every queue any task routes to.
- [ ] Uploading a PDF moves `PdfExtraction.status` off `queued` within 60 s.
- [ ] A test asserts `extract_pdf_text` runs under `CELERY_TASK_ALWAYS_EAGER`.
- [ ] No task publishes to a queue with no consumer.
- [ ] `celery-beat` has a schedule or is removed.

## Testing Requirements
Eager-mode task test in CI.

## Documentation Requirements
Queue topology noted in the deployment runbook.

## Definition of Done
Merged; extraction demonstrated end-to-end on a real upload.

---

# B-04 · Un-shadow `apps/ai` and generate migrations

## Objective
Make the real `apps/ai` modules importable and create the missing migrations.

## Problem
`apps/ai` contains both `models.py` and `models/`, and both `views.py` and `views/`. Python resolves the package first, so **both real modules are unreachable**. The app is in `INSTALLED_APPS` with **no `migrations/` package**, so none of its tables exist.

## Evidence
`apps/ai/` = `__init__.py`, `apps.py`, `models/`, `models.py`, `services/`, `tasks.py`, `urls.py`, `views/`, `views.py`. No `migrations/`. `models/` exports five field-less stubs; `models.py` defines the real `RecordEmbedding` and `EmbeddingJob`. `apps/ai/tasks.py:35` does `from apps.ai.models import EmbeddingJob, RecordEmbedding` → resolves to the package → `ImportError`. `apps/ai/serializers.py`, imported by `views.py`, does not exist.

The shadowed `views.py` implements **FR-M8-03** (`EmbedAllView`, `EmbeddingJobListView`) and FR-M4-01/02 — so the app must not be deleted wholesale.

## Current State
The AI app cannot import and has no tables.

## Proposed State
Stub packages removed; real modules importable; migrations generated; `apps.ai.urls` routed.

## Scope
Delete `apps/ai/models/`, `apps/ai/views/` and the eight `pass` service classes; generate `apps/ai/migrations/`; add `apps/ai/serializers.py`; route `apps.ai.urls` in `config/urls.py`.

## Out of Scope
RAG behaviour (`06-rag.md`). `Conversation`/`ChatMessage` — deferred with conversational RAG ([ADR-006](../adr/006-minimum-rag-pipeline.md)); drop the stubs rather than making them real.

## Technical Approach
Delete stubs, run `makemigrations ai`, **inspect the generated migration by hand** before committing.

## Dependencies
`B-01`. Feeds `R-03`.

## Risks
Medium — `makemigrations` on a previously unmigrated installed app must be reviewed manually. Confirm no other app's migration references `ai` (none does).

## Security Impact
`apps/ai/views.py` ships `pickle.loads` over database rows. **Do not route these views until `R-03` replaces that** ([ADR-007](../adr/007-pgvector-vector-store.md)).

## Performance Impact
None directly.

## SaaS Impact
Per-instance tables under [ADR-005](../adr/005-instance-per-tenant.md).

## Research/Thesis Impact
None — RAG is supporting.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
M

## Acceptance Criteria
- [ ] `from apps.ai.models import RecordEmbedding, EmbeddingJob` succeeds.
- [ ] `makemigrations --check --dry-run` reports no missing migrations.
- [ ] `apps/ai/migrations/0001_initial.py` committed.
- [ ] No directory in `apps/ai/` shadows a same-named module.
- [ ] `apps/ai/services/` contains no class whose body is `pass`.

## Testing Requirements
Import-smoke test covers this; `makemigrations --check` in CI.

## Documentation Requirements
FR-M8-03 traceability recorded in `DOC-06`.

## Definition of Done
Merged with migrations; CI enforces migration consistency.

---

# B-05 · `Record` queryset scopes

## Objective
Give "which records can this user see?" one implementation instead of six copies and one omission.

## Problem
The visibility rule is copy-pasted six times and forgotten once — the omission is an active data leak (`S-02`).

## Evidence
`("published", "approved", "completed")` × 6 · `Record.objects.filter(owners__user=…)` × 4 · `record.owners.filter(user=request.user).exists()` × 5. Sites: `records/views.py:54,84,267,483` · `views_dashboard.py:18-47` · `documents/views.py:227,303,337,379` · `reviews/views.py:184`.

## Current State
Six independently-drifting copies.

## Proposed State
`RecordQuerySet` with `.publicly_visible()`, `.owned_by(user)`, `.reviewable_by(user)`, `.visible_to(user)`.

## Scope
Add the queryset and manager; migrate all visibility and ownership sites.

## Out of Scope
The `retrieve` fix itself (`S-02`) — it should use this scope but ships first if this is not ready.

## Technical Approach
`RecordManager.from_queryset(RecordQuerySet)`, preserving the existing `is_deleted=False` filter in `get_queryset`.

## Dependencies
`F-02` preferred. Consumed by `S-02` and `R-04`.

## Risks
Low — but the existing manager filters soft-deletes; preserve that or deleted records reappear. Assert with a test.

## Security Impact
High and positive — the durable fix behind `S-02`, and the filter `R-04` must apply to RAG retrieval.

## Performance Impact
Neutral; a place to attach `select_related` once rather than per view.

## SaaS Impact
None under instance-per-tenant.

## Research/Thesis Impact
None directly.

## MVP Classification
MVP REQUIRED

## Priority
P1

## Complexity
M

## Acceptance Criteria
- [ ] `Record.objects.visible_to(user)` returns published/approved/completed plus owned plus reviewable, and nothing else.
- [ ] Soft-deleted records are excluded from every scope.
- [ ] `grep -c '"published", "approved", "completed"' backend/apps/` returns 1.

## Testing Requirements
Parametrised test over six roles against a fixed fixture set.

## Documentation Requirements
None.

## Definition of Done
Merged; all call sites migrated; scope tests in CI.

---

# B-06 · Log swallowed exceptions

## Objective
Make notification and audit failures observable without changing behaviour.

## Problem
Twelve bare `except Exception: pass` blocks discard every failure.

## Evidence
Ten in `notifications/services.py`, one in `audit/services.py:44-46`, one in `core/utils.py:52`. `_get_type` uses `.get()`, so a missing `NotificationType` raises and is swallowed. *(All eleven type names are currently seeded — verified — so this is latent, not firing.)*

## Current State
Silent failure. No `LOGGING` configuration exists.

## Proposed State
Every handler logs via `logger.exception(...)` with context; behaviour otherwise identical.

## Scope
Replace all twelve; add `LOGGING` to `settings/base.py`.

## Out of Scope
A domain-event bus — deliberately not built ([ADR-001](../adr/001-mvp-scope-boundary.md)).

## Technical Approach
Keep swallowing — the rule that notifications must not break the caller is correct. Only stop discarding the evidence.

## Dependencies
Pairs with `D-05`.

## Risks
None functionally. Expect noise on first deploy — that noise is pre-existing failures becoming visible.

## Security Impact
Positive: audit-write failures currently vanish, undermining NFR-S5.

## Performance Impact
Negligible.

## SaaS Impact
Per-instance logs.

## Research/Thesis Impact
Supports `W-04` — instrumentation failures must not be silent.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
XS

## Acceptance Criteria
- [ ] No bare `except Exception: pass` remains in `backend/`.
- [ ] `LOGGING` configured.
- [ ] A test forces `_get_type` to raise and asserts the failure is logged while the caller still returns 200.

## Testing Requirements
`caplog` assertion in CI.

## Documentation Requirements
Log destinations noted in the runbook.

## Definition of Done
Merged; logging configured; test in CI.

---

# B-07 · Fix the `.username` fallback

## Objective
Remove a latent `AttributeError` in document serialization.

## Problem
`documents/serializers.py:42` falls back to `obj.uploaded_by.username`; `User` sets `USERNAME_FIELD = "email"` and has no `username` field.

## Evidence
`accounts/models.py:57-84`. The correct version exists 34 lines below at `:76`.

## Current State
Reached only when both names are blank — latent.

## Proposed State
Falls back to `.email`, matching its sibling.

## Scope
One line.

## Out of Scope
Broader serializer work.

## Technical Approach
Match `:76`.

## Dependencies
None.

## Risks
None.

## Security Impact
None.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
None.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
XS

## Acceptance Criteria
- [ ] A user with blank first and last name serializes to their email, not an exception.

## Testing Requirements
One serializer test.

## Documentation Requirements
None.

## Definition of Done
Merged with test.

---

# B-08 · Fix two N+1 queries and the FTS signal

## Objective
Remove three known inefficiencies on hot paths.

## Problem
Two review endpoints issue one query per row; every `Record.save()` triggers a second UPDATE regardless of what changed.

## Evidence
`reviews/views.py:206-208` and `:218-220` build `Review.objects.filter(...)` without `select_related("record")`, then evaluate `[r.record for r in reviews]` — the class's own `get_queryset` *does* use `select_related`; these bypass it. `records/signals.py:6` rebuilds the FTS vector on every save, including `increment_access` and every `update_fields=["pipeline_status"]`.

## Current State
N+1 on reviewer dashboards; a redundant UPDATE per record write.

## Proposed State
`select_related` on both; the signal fires only when `title` or `abstract` changed.

## Scope
Three edits plus `assertNumQueries` tests.

## Out of Scope
Caching.

## Technical Approach
Compare against `update_fields` when present; keep a full rebuild on create.

## Dependencies
None.

## Risks
Low — ensure the signal still fires on create and on title/abstract edits, or search silently staleness.

## Security Impact
None.

## Performance Impact
Direct: removes N queries per dashboard load and one UPDATE per write. Supports NFR-P2.

## SaaS Impact
None.

## Research/Thesis Impact
Per-stage turnaround measurement (`W-04`) is on the same write path.

## MVP Classification
MVP RECOMMENDED

## Priority
P3

## Complexity
XS

## Acceptance Criteria
- [ ] `assertNumQueries` bounds `/reviews/approved/` and `/reviews/declined/` independent of row count.
- [ ] `search_vector` is rebuilt on create and on title change.
- [ ] `increment_access` does not trigger an FTS rebuild.

## Testing Requirements
Query-count tests in CI.

## Documentation Requirements
None.

## Definition of Done
Merged with tests.

---

# B-09 · Remove dead backend code

## Objective
Delete unreachable backend code so later work operates on less surface.

## Problem
Dead code is indistinguishable from live code during review.

## Evidence

| What | Where | Why safe |
|---|---|---|
| `MyRecordsViewSet` | `records/views.py:474-483` | Not routed; duplicates `RecordViewSet.mine` |
| `build_zip_for_record` | `documents/services.py:54-61` | Zero callers; contains undefined `BytesIO` |
| 5 permission classes | `core/permissions.py` | `IsStudent`, `IsAdviser`, `IsKTTO`, `IsITSO`, `IsIERC` — zero references |
| `LegacyFolder` | `storage/models.py:62-71` | Removed with `SC-01` |
| Commented-out view | `views_dashboard.py:55-82` | 28 lines of comment |
| Unused imports | `records/views.py:12`, `reviews/views.py:12`, `views_dashboard.py:5-6` | pyflakes-confirmed |

**Held back:** `ResearchLink`, `Publication`, `Conference`, `Budget`, `Collaboration` and five lookup tables have zero code references but map to SRS Module 2 fields. Dropping them is a destructive migration — resolve in `DOC-06` first.

## Current State
~700 unreachable backend lines.

## Proposed State
The six confirmed items removed; the ten domain models untouched pending `DOC-06`.

## Scope
Delete the six. Do **not** touch the domain models.

## Out of Scope
The ten unused domain models.

## Technical Approach
Grep for importers before each deletion. Note `core/exceptions.py`'s `NotRecordOwner` and `RecordNotFound` may be adopted by `S-03` — confirm before deleting.

## Dependencies
**After `T-01`** — deleting without an import-smoke test is how `B-01` happened.

## Risks
Low with grep verification; medium if done before tests exist.

## Security Impact
Neutral.

## Performance Impact
None.

## SaaS Impact
None.

## Research/Thesis Impact
None.

## MVP Classification
MVP RECOMMENDED

## Priority
P2

## Complexity
S

## Acceptance Criteria
- [ ] Each deletion has a documented zero-importer grep in the PR.
- [ ] `manage.py check` and the full suite pass afterwards.
- [ ] The ten domain models are untouched and a follow-up ticket exists.

## Testing Requirements
Existing suite must stay green.

## Documentation Requirements
Grep evidence in the PR description.

## Definition of Done
Merged after `T-01`.
