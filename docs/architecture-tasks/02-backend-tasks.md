# 02 — Backend Tasks

Nine tasks. Two are blockers that stop the application starting.

---

# BE-01 · Restore application boot — fix six undefined names in `records/views.py`

## Objective
Make the Django URLconf loadable so the API responds at all.

## Problem
`apps/records/views.py` uses six names it never imports. One of them is evaluated in a `class` statement, so the module raises `NameError` at **import** time, not call time. `config/urls.py` includes this module, so the entire URLconf fails and every endpoint returns 500.

## Current State
`pyflakes 3.4.0` over all backend `.py` files:

```
./apps/records/views.py:535:32: undefined name 'timezone'
./apps/records/views.py:541:21: undefined name 'make_download_token'
./apps/records/views.py:546:39: undefined name 'settings'
./apps/records/views.py:550:26: undefined name 'APIView'
./apps/records/views.py:563:22: undefined name 'verify_download_token'
./apps/records/views.py:579:20: undefined name 'file_response_for_record'
```

Line 550 is `class DownloadRedeemView(APIView):`. `apps/records/download_tokens.py` and `apps/records/download_service.py` define four of the six names and are imported by nothing.

Import chain: `config/urls.py:11` → `apps.records.urls` → `apps.records.views:3`.

## Proposed State
All six names imported; `manage.py check` passes; every route resolves.

## Scope
Add the six imports to `apps/records/views.py`. Verify with `manage.py check` and `manage.py show_urls` (or an equivalent resolver walk).

## Out of Scope
The misplaced methods (`BE-02`) and the authorization gaps on these endpoints (`SEC-02`) — separate tasks, same file.

## Technical Approach
`from django.utils import timezone`, `from django.conf import settings`, `from rest_framework.views import APIView`, `from .download_tokens import make_download_token, verify_download_token`, `from .download_service import file_response_for_record`.

## Dependencies
None. **Blocks essentially everything else** — no backend task can be verified until this lands.

## Risks
Low to apply. Note these endpoints have **never executed**, so their first correct run may surface further defects; budget for that rather than assuming green.

## Security Impact
Neutral directly. Brings the download-redeem path into service, which makes `SEC-02` and `SEC-03` urgent rather than theoretical.

## Performance Impact
None.

## Deployment Impact
The backend container becomes able to serve requests.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `python manage.py check` exits 0 with no errors.
- [ ] `python -c "import config.urls"` succeeds.
- [ ] `pyflakes apps/records/views.py` reports zero `undefined name` findings.
- [ ] `GET /api/v1/records/` returns 200 for an authenticated user (not 500).
- [ ] An automated test importing the URLconf exists and passes (`TEST-01`).

## Definition of Done
Fix merged; `TEST-01`'s import-smoke test added in the same PR; CI (`ARCH-01`) runs `manage.py check`.

## Complexity
XS

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`bug`, `backend`, `mvp-blocker`, `boot`

---

# BE-02 · Relocate four methods indented into the wrong class

## Objective
Restore the download-request approve/decline endpoints, which currently resolve to a class that does not define them.

## Problem
`get_permissions`, `perform_create`, `approve` and `decline` sit inside `DownloadRedeemView(APIView)` instead of `DownloadRequestViewSet`. Three routed endpoints therefore raise `AttributeError` at request time, and `DownloadRedeemView` carries a `get_permissions` that reads `self.action` — an attribute `APIView` does not have — so the redeem endpoint 500s too.

## Current State
`apps/records/views.py`: `class DownloadRedeemView` at :550, `class DeleteRequestViewSet` at :632, with `get_permissions` (:588), `perform_create` (:593), `approve` (:598) and `decline` (:615) between them.

`apps/records/urls.py:15-16` routes `<int:pk>/approve/` and `<int:pk>/decline/` to `DownloadRequestViewSet.as_view({"post": "approve"})`. DRF resolves the handler by `getattr` at request time → `AttributeError` → 500.

Consequence: `notify_download_request` and `notify_download_reviewed` are unreachable — their only other callers are inside these same misplaced methods. The frontend calls these routes from `src/api/records.ts`.

## Proposed State
The four methods live on `DownloadRequestViewSet`; `DownloadRedeemView` keeps only `permission_classes = [AllowAny]` and `get`.

## Scope
Re-indent the four methods into `DownloadRequestViewSet`; delete the `get_permissions` override from `DownloadRedeemView`; confirm the router mapping.

## Out of Scope
Redesigning the download flow; watermarking (Jira `IR-18`).

## Technical Approach
Pure code motion. Note `DownloadRequestViewSet` already has a `partial_update` that duplicates part of `approve`/`decline`; reconcile the two rather than leaving both.

## Dependencies
`BE-01` must land first or the module still will not import.

## Risks
Low. These endpoints have never run — treat first execution as new code, not a regression fix.

## Security Impact
`DownloadRedeemView` regains its intended `AllowAny` + signed-token behaviour. The token design itself is sound (short-lived, typed, re-verified against the DB).

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `POST /api/v1/records/download-requests/<id>/approve/` returns 200 for a staff user and transitions status to `approved`.
- [ ] `POST /api/v1/records/download-requests/<id>/decline/` returns 200 and transitions to `declined`.
- [ ] `GET /api/v1/records/download/?token=<valid>` streams the file; an expired token returns 403.
- [ ] `notify_download_reviewed` is invoked on both paths (assert via log or notification row).
- [ ] No `AttributeError` in logs for any of the three routes.

## Definition of Done
Merged with an integration test per route; duplicate `partial_update` logic reconciled or removed.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`bug`, `backend`, `mvp-blocker`, `records`, `download`

---

# BE-03 · Route Celery tasks to the queues the workers consume

## Objective
Make background jobs execute.

## Problem
Workers are started against named queues. No task publishes to any of them, so every enqueued task waits forever.

## Current State
Compose starts `celery -A config worker -Q default`, `-Q extraction`, `-Q embedding`, plus `celery -A config beat`.

`grep -rn "task_routes\|TASK_ROUTES\|beat_schedule\|BEAT_SCHEDULE\|queue" backend/config/ backend/apps/*/tasks.py` returns **no matches**. Every task is a bare `@shared_task`, so it publishes to Celery's built-in default queue named `celery`, which no worker consumes. `celery-beat` runs with no `CELERY_BEAT_SCHEDULE`, so the "nightly `embed_all_records`" documented in `docs/rag_pipeline_service_map.md` is scheduled nowhere.

`config/celery.py` is 8 lines: `Celery("iris")`, `config_from_object`, `autodiscover_tasks`.

## Proposed State
Explicit `CELERY_TASK_ROUTES` mapping task modules to the queues the SRS names (`celery-worker`, `celery-worker-rag`), and a `CELERY_BEAT_SCHEDULE` for any periodic task actually required.

## Scope
- `CELERY_TASK_ROUTES` in `settings/base.py` for `apps.documents.tasks.*` and `apps.ai.tasks.*`
- `CELERY_TASK_DEFAULT_QUEUE` set explicitly
- `CELERY_BEAT_SCHEDULE` populated, or the beat service removed until a periodic task exists
- Compose worker `-Q` flags reconciled with the routes

## Out of Scope
Deciding the worker topology (`ARCH-02`, `FW-07`).

## Technical Approach
Route by module path. For the MVP, one worker consuming all queues is acceptable and simplest; the SRS's `celery-worker` / `celery-worker-rag` split is the target and should be introduced with the routes so both are consistent.

## Dependencies
`ARCH-02` (topology). `BLOCK` for `AI-01`/`AI-02` — extraction cannot run without this.

## Risks
Low. Verify with `celery -A config inspect active_queues` that declared and consumed queues match.

## Security Impact
None.

## Performance Impact
Restores asynchronous processing; without it, `NFR-P4` (30-second indexing) is unmeasurable because nothing runs.

## Deployment Impact
May reduce worker container count.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `celery -A config inspect active_queues` shows every queue that any task routes to.
- [ ] Uploading a PDF results in `PdfExtraction.status` leaving `queued` within 60 seconds.
- [ ] A test asserts `extract_pdf_text` executes under `CELERY_TASK_ALWAYS_EAGER`.
- [ ] No task publishes to a queue with no consumer (verified by inspecting declared routes against Compose `-Q` flags).
- [ ] `celery-beat` either has a populated schedule or is removed.

## Definition of Done
Routes merged; extraction demonstrated end-to-end on a real upload; Compose updated; documented in `docs/DEVELOPMENT_GUIDE.md`.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`bug`, `backend`, `celery`, `mvp-blocker`, `infrastructure`

---

# BE-04 · Un-shadow `apps/ai` and delete the stub packages

## Objective
Make the real `apps/ai` modules importable and generate the missing migrations, so FR-M8-03 and FR-M4-01/02 have a working home.

## Problem
`apps/ai` contains both `models.py` and `models/`, and both `views.py` and `views/`. Python resolves a package before a same-named module, so **both real modules are unreachable**. The app is also in `INSTALLED_APPS` with **no `migrations/` package**, so none of its tables exist.

> **Correction to `docs/architecture-review/` BLOCK-5,** which recommended deleting `apps.ai` outright. That is too broad: the shadowed `views.py` implements **FR-M8-03** (`EmbedAllView`, `EmbeddingJobListView` — embedding index administration) and FR-M4-01/02 (`SemanticSearchView`, `AskView`, `SummarizeView`). Delete the *stubs*, keep the real code.

## Current State
`apps/ai/` = `__init__.py`, `apps.py`, `models/`, `models.py`, `services/`, `tasks.py`, `urls.py`, `views/`, `views.py`. No `migrations/`.

- `models/` exports five field-less stubs (`class Conversation(models.Model): pass`, etc.)
- `models.py` defines the real `RecordEmbedding` and `EmbeddingJob`
- `views/` contains `chatbot.py` and `summarize.py`, four classes, all `pass`
- `views.py` contains six working view classes
- `services/` contains eight classes, every body `pass`
- `apps/ai/tasks.py:35` does `from apps.ai.models import EmbeddingJob, RecordEmbedding` → resolves to the package → `ImportError`
- `config/urls.py` never includes `apps.ai.urls`

## Proposed State
Stub packages removed; real modules importable; `migrations/0001_initial.py` generated; `apps.ai.urls` routed; the eight `pass` service classes either implemented (`AI-03`…`AI-08`) or deleted.

## Scope
- Delete `apps/ai/models/`, `apps/ai/views/`, and the eight `pass` classes in `apps/ai/services/`
- Preserve `Conversation` / `ChatMessage` as **real** models if FR-M4-01 conversation history is in MVP scope (see `AI-08`); otherwise drop them
- Generate and commit `apps/ai/migrations/`
- Add `path("api/v1/ai/", include("apps.ai.urls"))` to `config/urls.py`
- Add `apps/ai/serializers.py`, which `views.py` imports and which does not exist

## Out of Scope
Implementing RAG behaviour (`AI-03`…`AI-08`). Changing `RecordEmbedding` to `VectorField` (`AI-03`).

## Technical Approach
Delete stubs, run `makemigrations ai`, inspect the generated migration before committing, wire the URLconf, add the missing serializer module.

## Dependencies
`BE-01`. Feeds `AI-03`…`AI-08`. Conversation-model scope depends on `AI-08`.

## Risks
Medium — `makemigrations` on a previously unmigrated installed app must be reviewed by hand. Confirm no other app's migration references `ai` (none does).

## Security Impact
`apps/ai/views.py` currently ships `pickle.loads` over database rows (see `SEC-11`). Do not route these views until `AI-03` replaces that.

## Performance Impact
None directly.

## Deployment Impact
`migrate` becomes consistent; `makemigrations --check` can be enforced in CI.

## Framework Impact
Enables correct `pgvector` wiring (`AI-03`).

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `from apps.ai.models import RecordEmbedding, EmbeddingJob` succeeds.
- [ ] `python manage.py makemigrations --check --dry-run` reports no missing migrations.
- [ ] `apps/ai/migrations/0001_initial.py` exists and is committed.
- [ ] No directory in `apps/ai/` shadows a same-named `.py` module.
- [ ] `apps/ai/services/` contains no class whose entire body is `pass`.
- [ ] FR-M8-03 endpoints resolve (routing may remain gated behind `AI-03`).

## Definition of Done
Merged with migrations; `makemigrations --check` in CI; FR-M8-03 traceability recorded in `DOC-06`.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
Critical

## Suggested Labels
`backend`, `ai`, `mvp-required`, `technical-debt`, `fr-m8-03`

---

# BE-05 · Introduce `core/enums.py` — one `TextChoices` per concept

## Objective
Replace five independent encodings of the clearance offices, and the scattered status literals, with one source of truth per concept.

## Problem
Adding a fifth reviewing office today means finding and editing four of five dictionaries across three modules. Missing one fails **silently**, because every notification path swallows exceptions (`BE-07`).

## Current State
`{ITSO, IERC, KTTO}` is encoded five times:

| Encoding | Location |
|---|---|
| `RecordClearance.OFFICE_CHOICES` | `reviews/models.py:56` |
| `ROLE_TO_OFFICE` | `reviews/services.py:68` |
| `CLEARANCE_OFFICES` | `reviews/services.py:381` |
| `_OFFICE_TO_ROLE` | `notifications/services.py:416` |
| `_OFFICE_LABELS` | `notifications/services.py:264` |

Also: pipeline statuses appear as bare literals across eight files; `Record.IP_TYPE_CHOICES` is restated as `VALID_IP_TYPES` at `records/views.py:180`; the queued/running/done/failed quartet is declared identically on `PdfExtraction` and `EmbeddingJob`.

## Proposed State
`core/enums.py` with `PipelineStatus`, `ClearanceOffice`, `ReviewStage`, `IPType`, `JobStatus` as `models.TextChoices`. `ClearanceOffice` carries a `role_name` property so the role↔office mapping is a member attribute, not a fourth dict.

## Scope
Create the enums; replace all five office encodings, the IP-type duplication, and the job-status duplication; replace status literals in `reviews/services.py` and `records/views.py`.

## Out of Scope
The lifecycle transition table (`WF-01`) — this is its prerequisite.

## Technical Approach
Member **values must match the existing database strings exactly** so no data migration is required. Verify with a migration dry-run showing no schema change.

## Dependencies
None. **Prerequisite for `WF-01`.**

## Risks
Low, provided values match exactly. A mismatch is a silent data bug — assert equality in a test.

## Security Impact
Indirect: removes a class of silent authorization mis-mapping.

## Performance Impact
None.

## Deployment Impact
None if values match.

## Framework Impact
None — `TextChoices` is stdlib Django.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `core/enums.py` defines the five enums.
- [ ] `grep -rn '"itso"\|"ierc"\|"ktto"' backend/apps/` returns only `core/enums.py`.
- [ ] `makemigrations --check` reports no schema change.
- [ ] A test asserts every enum value equals the string previously stored in the database.
- [ ] `VALID_IP_TYPES` in `records/views.py` is gone, replaced by the enum.

## Definition of Done
Merged; all call sites migrated; equality test in CI.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`backend`, `refactor`, `technical-debt`, `mvp-recommended`

---

# BE-06 · Named queryset scopes on `Record`

## Objective
Give "which records can this user see?" one implementation instead of six copies and one omission.

## Problem
The visibility rule is copy-pasted six times and forgotten once — and the omission is an active data leak (`SEC-02`).

## Current State

| Expression | Copies |
|---|---|
| `("published", "approved", "completed")` | 6 |
| `Record.objects.filter(owners__user=…)` | 4 |
| `record.owners.filter(user=request.user).exists()` | 5 |

Sites: `records/views.py:54,84,267,483`, `records/views_dashboard.py:18-47`, `documents/views.py:227,303,337,379`, `reviews/views.py:184`. `views_dashboard.py:21` carries a seventh, different list for "in pipeline".

## Proposed State
`RecordQuerySet` exposing `.publicly_visible()`, `.owned_by(user)`, `.reviewable_by(user)` and `.visible_to(user)`; every consumer calls a scope.

## Scope
Add the queryset and manager; migrate all six visibility sites and the four ownership sites.

## Out of Scope
The `retrieve` authorization fix itself is `SEC-02` — it should *use* this scope, but ships first if this task is not ready.

## Technical Approach
`RecordQuerySet(models.QuerySet)` + `Record.objects = RecordManager.from_queryset(RecordQuerySet)()`, preserving the existing soft-delete filter in `get_queryset`.

## Dependencies
`BE-05` (status enum) preferred. Consumed by `SEC-02`.

## Risks
Low — but the existing `RecordManager` already filters `is_deleted=False`; preserve that or soft-deleted records reappear. Assert with a test.

## Security Impact
High and positive — this is the durable fix behind `SEC-02`.

## Performance Impact
Neutral; an opportunity to attach `select_related`/`prefetch_related` once instead of per view.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended** (the `SEC-02` subset is **MVP Blocker**)

## Acceptance Criteria
- [ ] `Record.objects.visible_to(user)` returns published/approved/completed plus records the user owns plus records they may review, and nothing else.
- [ ] Soft-deleted records are excluded from every scope (test).
- [ ] `grep -c '"published", "approved", "completed"' backend/apps/` returns 1.
- [ ] A parametrised test covers each of the six roles against a fixed fixture set.

## Definition of Done
Merged; all call sites migrated; scope tests in CI.

## Complexity
M

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`backend`, `refactor`, `security`, `orm`, `mvp-recommended`

---

# BE-07 · Log swallowed exceptions instead of discarding them

## Objective
Make notification and audit failures observable without changing behaviour.

## Problem
Twelve bare `except Exception: pass` blocks mean a failure in notification or audit is invisible. Nothing reports it, nothing alerts, and no test can assert it.

## Current State
Ten in `notifications/services.py`, one in `audit/services.py:44-46`, one in `core/utils.py:52`. `_get_type` uses `.get()`, so a missing `NotificationType` raises `DoesNotExist` and is swallowed.

> Verified: all eleven type names passed to `_get_type` **are** seeded across the four notification migrations. This is a latent hazard, not a currently-firing bug — it becomes live the moment a twelfth event type is added and its seed is forgotten.

## Proposed State
Every handler logs with `logger.exception(...)` and structured context; behaviour otherwise identical.

## Scope
Replace all twelve handlers; add a `LOGGING` configuration to `settings/base.py` (there is none, so Django defaults apply).

## Out of Scope
The domain-event bus — deliberately not implemented (see `docs/architecture-review/06-workflow-architecture.md` WF-5, deletion test fails at current size).

## Technical Approach
`logger = logging.getLogger(__name__)` per module; `except Exception: logger.exception("notify_x failed", extra={"record_id": ...})`. Keep swallowing — the design rule that notifications must not break the caller is correct.

## Dependencies
None. Pairs naturally with `DEP-04` (observability).

## Risks
None functionally. Expect noise on first deploy — that noise is pre-existing failures becoming visible.

## Security Impact
Positive: audit-write failures currently vanish, which undermines NFR-S5.

## Performance Impact
Negligible.

## Deployment Impact
Requires a logging destination (`DEP-04`).

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `grep -rn "except Exception:\s*$" -A1 backend/apps/ | grep -c "pass"` returns 0.
- [ ] `LOGGING` is configured in `settings/base.py`.
- [ ] A test forces `_get_type` to raise and asserts the failure is logged (via `caplog`) while the caller still returns 200.
- [ ] Audit-write failures appear in logs at ERROR.

## Definition of Done
Merged; logging config in place; `caplog` test in CI.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`backend`, `observability`, `mvp-required`, `technical-debt`

---

# BE-08 · Fix two N+1 queries and one redundant write

## Objective
Remove three known query inefficiencies on hot paths.

## Problem
Two review endpoints issue one query per row; every `Record.save()` triggers a second UPDATE regardless of what changed.

## Current State
1. `reviews/views.py:206-208` and `:218-220` build `Review.objects.filter(...)` without `select_related("record")`, then evaluate `[r.record for r in reviews]` — one query per review. The class's own `get_queryset` *does* use `select_related`; these two actions bypass it.
2. `records/signals.py:6` rebuilds the FTS vector on **every** `Record.save()`, including `increment_access` and every `update_fields=["pipeline_status"]` call.

## Proposed State
`select_related("record")` on both actions; the FTS signal fires only when `title` or `abstract` changed.

## Scope
Three small edits plus `assertNumQueries` tests.

## Out of Scope
Broader query optimisation; caching.

## Technical Approach
For the signal, compare against `update_fields` when present and skip when neither `title` nor `abstract` is included; keep a full rebuild on create.

## Dependencies
None. Related to `NFR-P2` (2 s p95).

## Risks
Low — ensure the signal still fires on create and on title/abstract edits, or search silently staleness. Test both.

## Security Impact
None.

## Performance Impact
Direct: removes N queries per reviewer dashboard load and one UPDATE per record write.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] `assertNumQueries` bounds `GET /reviews/approved/` and `/reviews/declined/` to a constant independent of row count.
- [ ] A test asserts `search_vector` is rebuilt on create and on a title change.
- [ ] A test asserts `increment_access` does **not** trigger an FTS rebuild.

## Definition of Done
Merged with query-count tests in CI.

## Complexity
XS

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`backend`, `performance`, `orm`, `nfr-p2`

---

# BE-09 · Remove unreachable backend code

## Objective
Delete roughly 700 unreachable backend lines so later refactors operate on less surface.

## Problem
Dead code is indistinguishable from live code during review, and one item is a conflicting duplicate.

## Current State

| What | Where | Why safe |
|---|---|---|
| `MyRecordsViewSet` | `records/views.py:474-483` | Not routed; duplicates `RecordViewSet.mine` |
| `build_zip_for_record` | `documents/services.py:54-61` | Zero callers; contains `undefined name 'BytesIO'` (pyflakes) |
| Five permission classes | `core/permissions.py` | `IsStudent`, `IsAdviser`, `IsKTTO`, `IsITSO`, `IsIERC` — zero references |
| Four exception classes | `core/exceptions.py` | Only `InvalidPipelineTransition` is used |
| `LegacyFolder` | `storage/models.py:62-71` | `managed = False`; docstring says "DO NOT use in new code" |
| Commented-out view | `records/views_dashboard.py:55-82` | 28 lines of comment |
| Unused imports | `records/views.py:12`, `reviews/views.py:12`, `views_dashboard.py:5-6` | pyflakes-confirmed |

**Held back pending `DOC-06`:** `ResearchLink`, `Publication`, `Conference`, `Budget`, `Collaboration` and five lookup tables have zero code references but map to SRS Module 2 fields. Dropping them is a destructive migration — confirm against the SRS first.

## Proposed State
The seven confirmed items removed; the ten models left in place pending confirmation.

## Scope
Delete the seven items above. Do **not** touch the domain models.

## Out of Scope
The ten unused domain models (needs `DOC-06` / SRS confirmation).

## Technical Approach
Grep for importers before each deletion. The five permission classes are named in Jira `IR-7` — note that `IsStudent`/`IsAdviser` may be wanted by `SEC-03`; confirm before deleting rather than deleting and re-adding.

## Dependencies
Do **after** `TEST-01` — deleting without an import-smoke test is how `BE-01` happened.

## Risks
Low with grep verification. Medium if done before tests exist.

## Security Impact
Neutral. Note `core/exceptions.py`'s `NotRecordOwner` and `RecordNotFound` may be adopted by `SEC-03` rather than deleted — confirm first.

## Performance Impact
None.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Recommended**

## Acceptance Criteria
- [ ] Each deleted symbol has a documented zero-importer grep in the PR.
- [ ] `manage.py check` and the full test suite pass after deletion.
- [ ] `pyflakes` reports zero unused imports in the three named files.
- [ ] The ten domain models are untouched and a follow-up ticket exists.

## Definition of Done
Merged after `TEST-01`; grep evidence in the PR description.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
Medium

## Suggested Labels
`backend`, `cleanup`, `technical-debt`
