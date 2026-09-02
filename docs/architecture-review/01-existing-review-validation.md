# 01 — Validation of the Existing Architecture Review

Every claim in `docs/backend_frontend_architecture_review.md` was treated as a **hypothesis** and re-verified against `refactor/docker-service` @ `ddcc54c`. Verdicts are one of:

**CONFIRMED** · **REJECTED** · **REVISED** · **ALREADY FIXED** · **NEEDS INVESTIGATION**

The prior document was written against branch `feat/rag-service`. Some divergence is expected and is noted where it matters.

---

## Summary

| Section | Confirmed | Revised | Rejected | Needs investigation |
|---|---|---|---|---|
| Defects 1–9 | 7 | 1 | 1 | 0 |
| Backend B1–B7 | 5 | 2 (one partial reject) | 0 | 0 |
| Frontend F1–F6 | 5 | 1 | 0 | 0 |
| Cross-cutting X1–X2 | 1 | 1 | 0 | 0 |
| Removals table | 10 rows | 1 row | 2 rows | 1 row |
| Hosting section | confirmed, with one material correction | | | |

**Overall: the document is trustworthy.** Its analysis method is sound and its line references were accurate wherever they had not drifted. Keep it. The corrections below are additive, not a repudiation.

**Its one serious blind spot:** it assumes the `ai/` gateway exists. It does not, and never has. See [Gap 1](#gap-1--the-ai-gateway-does-not-exist).

---

## Part 1 — The nine claimed defects

### Defect 1 · "Five undefined names in `records/views.py`" → **REVISED (understated)**

**Claim.** `timezone`, `make_download_token`, `settings`, `verify_download_token`, `file_response_for_record` are used but never imported; "guaranteed `NameError`".

**Verification.** Correct, but there are **six**, not five, and the sixth changes the severity category entirely. `pyflakes 3.4.0` output, verbatim:

```
./apps/records/views.py:535:32: undefined name 'timezone'
./apps/records/views.py:541:21: undefined name 'make_download_token'
./apps/records/views.py:546:39: undefined name 'settings'
./apps/records/views.py:550:26: undefined name 'APIView'
./apps/records/views.py:563:22: undefined name 'verify_download_token'
./apps/records/views.py:579:20: undefined name 'file_response_for_record'
```

**Why the sixth matters.** The five named in the prior review are all inside method bodies, so they fail *when the endpoint is called*. `APIView` at line 550 is in a **class statement**:

```python
class DownloadRedeemView(APIView):
```

Class statements execute at module import. `config/urls.py:11` includes `apps.records.urls`, which imports `.views` at line 3. So the failure is not "three endpoints are broken" — it is **the Django URLconf cannot load and every endpoint in the system returns 500**.

**Revised verdict.** Same defect, one severity band higher: from *feature-breaking* to **MVP BLOCKER — the application does not start**. This is finding **BLOCK-1** in [02](02-backend-architecture.md).

> Derived from static analysis and CPython import semantics; not executed (no dependencies installed in the review environment).

---

### Defect 2 · "`approve` and `decline` indented into the wrong class" → **CONFIRMED**

`records/views.py:588-630`. `get_permissions`, `perform_create`, `approve` and `decline` sit inside `DownloadRedeemView(APIView)` rather than `DownloadRequestViewSet`. Confirmed by structural grep — `class DownloadRedeemView` at 550, `class DeleteRequestViewSet` at 632, with all four methods between them.

Two consequences, both confirmed:

1. `records/urls.py:15-16` routes `<int:pk>/approve/` and `decline/` to `DownloadRequestViewSet.as_view({"post": "approve"})`. DRF's `ViewSetMixin.as_view` resolves the handler by `getattr` at request time, so these raise `AttributeError` → 500.
2. `DownloadRedeemView.get_permissions` reads `self.action`, which `APIView` does not define, so `GET /api/v1/records/download/` would 500 even after Defect 1 is fixed.

`notify_download_request` and `notify_download_reviewed` are consequently unreachable. Confirmed — the only other callers are inside the same misplaced methods.

---

### Defect 3 · "`apps/ai/views/` shadows `views.py`; same shape in `documents/`" → **REVISED (half confirmed, half rejected)**

**First half — CONFIRMED and extended.** `apps/ai/` contains both `views.py` and `views/`, and both `models.py` and `models/`. Python resolves a package before a same-named module, so **both `.py` files are unreachable**:

| Shadowed file | Size | Contains | Reachable? |
|---|---|---|---|
| `apps/ai/views.py` | 9,924 bytes (~250 lines) | `SemanticSearchView`, `AskView`, `SummarizeView`, `EmbedRecordView`, `EmbedAllView`, `EmbeddingJobListView` | **No** |
| `apps/ai/models.py` | 2,518 bytes | `RecordEmbedding`, `EmbeddingJob` | **No** |

The prior review says `views.py` is "54 lines"; it is roughly 250. It does not mention the `models.py` shadowing at all, which is the more damaging of the two — `apps/ai/tasks.py:35` does `from apps.ai.models import EmbeddingJob, RecordEmbedding`, which resolves to the **package**, which does not export those names. `embed_record` therefore raises `ImportError` on every invocation.

**Second half — REJECTED.** The claim that `documents/` has a `services/` directory without `__init__.py`, making `services/pdf_extractor.py` dead, is **false on this branch**. Directory listing:

```
apps/documents/: __init__.py  apps.py  migrations/  models.py
                 serializers.py  services.py  tasks.py  urls.py  views.py
```

There is no `documents/services/` directory and no `documents/services/pdf_extractor.py`. Either this was fixed between `feat/rag-service` and here, or it was misreported. The corresponding **removals-table row is also rejected** — you cannot delete a file that is not there. The `documents/tasks.py` three-tier chain it refers to *is* present and is a real problem, but for a different reason (see Defect 3-adjacent finding in [02](02-backend-architecture.md): the libraries are not in `requirements/base.txt`).

---

### Defect 4 · "`apps.ai` installed but never routed" → **CONFIRMED and escalated**

`config/urls.py` has ten `path(...)` entries; none includes `apps.ai.urls`. Confirmed.

**Escalation the prior review missed:** `apps/ai/` has **no `migrations/` package at all**:

```
apps/ai/: __init__.py  apps.py  models/  models.py
          services/  tasks.py  urls.py  views/  views.py
```

`apps.ai` is in `INSTALLED_APPS` (`settings/base.py:39`). With no migrations directory, `makemigrations` treats the app as unmigrated and `migrate` creates none of its tables. This directly contradicts the prior review's removals table, which asserts *"The five `pass` models were migrated into real empty tables."* **They were not.** No migration exists. That row is **REJECTED** as stated, though its conclusion — delete the app's dead scaffolding — still holds for a different reason.

Note also that `apps/ai/urls.py:2` imports six names from `.views`, which resolves to the stub package that exports none of them. Were it ever routed, it would `ImportError` immediately.

---

### Defect 5 · "`storage/views.py` has no ownership check" → **CONFIRMED and extended**

Confirmed on all six endpoints in `apps/storage/views.py`: every one is bare `IsAuthenticated`, and `StorageFolderDetailView` / `StorageFileDetailView` use unfiltered `queryset = Model.objects.all()`. Any authenticated user can read, rename or delete any other user's folders and files, and `StorageFileDownloadView` streams any file by primary key.

**Extension — the prior review scoped this to `storage/` only.** `apps/documents/` has the same class of hole on six further endpoints, and one of them is worse than anything in `storage/`:

| Endpoint | Check | Reality |
|---|---|---|
| `RecordFileDownloadAllView` (`views.py:399`) | **none at all** | any user ZIPs every file on any record |
| `RecordUploadListView` (`views.py:122`) | none | enumerate any record's uploads |
| `RecordFileListView` (`views.py:242`) | none | enumerate any record's files |
| `SubmitDocumentView` (`views.py:14`) | none | upload into any record |
| `RecordUploadCreateView` (`views.py:180`) | none | upload a new version into any record |
| `RecordSlotListView` (`views.py:103`) | none | read any record's slot structure |

Detailed in [05-security-architecture.md](05-security-architecture.md).

---

### Defect 6 · "Refresh interceptor writes to storage nothing reads" → **CONFIRMED and extended**

`api/client.ts:29-30` writes `localStorage["access_token"]` and `localStorage["refresh_token"]`; the request interceptor at line 12 reads `useAuthStore.getState().accessToken`; `lib/authStorage.ts` persists to `sessionStorage["iris_refresh_token"]`. The interceptor never calls `setTokens`, so the store keeps the stale token and only the retried request succeeds. All confirmed verbatim.

**Extension.** Two further problems in the same 15 lines:

1. **Rotation race.** `SIMPLE_JWT` sets `ROTATE_REFRESH_TOKENS: True` and `BLACKLIST_AFTER_ROTATION: True` (`settings/base.py:139-140`). The interceptor has no in-flight deduplication, so two concurrent 401s issue two refreshes; the second presents a token the first has already blacklisted, and the user is logged out mid-session.
2. **Logout leak.** `clearAuthSession()` removes `localStorage["refresh_token"]` but **not** `localStorage["access_token"]`, which the interceptor writes at line 29. A valid bearer token survives logout in browser storage.

---

### Defect 7 · "`npm run lint` cannot run" → **CONFIRMED**

`eslint ^9.6.0` in devDependencies; no `eslint.config.js`, no `.eslintrc*`, no `eslintConfig` key in `package.json`. ESLint 9 requires flat config. Scripts are `dev`, `build`, `preview`, `lint` — no `test`, no `typecheck`. Confirmed exactly as claimed.

---

### Defect 8 · "`get_uploaded_by_name` falls back to `.username`" → **CONFIRMED**

`documents/serializers.py:42`:

```python
return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.username
```

`accounts.User` sets `USERNAME_FIELD = "email"` and declares no `username` field. Reached only when both names are blank, so it is a latent `AttributeError`. The near-identical serializer at line 76 does it correctly. Confirmed.

---

### Defect 9 · "`build_zip` uses `f.file.path`" → **CONFIRMED**

`core/utils.py:21`. `django-storages[s3]` is in `requirements/base.txt:23`. `.path` raises `NotImplementedError` on any non-filesystem backend. Confirmed. Called from `documents/services.py:54` and `documents/views.py:404`.

> Note: `documents/services.py:54` has a *second*, separate defect pyflakes catches — `undefined name 'BytesIO'` in the return annotation context. The prior review lists this function under "dead code inside live files," which is correct; it is called by nothing.

---

## Part 2 — Backend candidates B1–B7

### B1 · Record lifecycle has no module → **CONFIRMED**

The count holds. `pipeline_status` is assigned in `reviews/services.py` (×8), `records/views.py` (×6: lines 76, 88, 137, 208, 254, 334, 690), `records/services.py:33`. The type-routing rule *"Proposal → adviser_review, else rdco_intake"* is genuinely written three times: `reviews/services.py:150-152` (`_first_status_for_type`), `records/views.py:135-138` (`submit`), and `records/views.py:689-694` (delete-request decline restoring `approved` vs `published`).

**Deletion test: passes.** Removing a `RecordLifecycle` module would scatter the transition table back across three modules and twelve call sites. Complexity concentrates, it does not relocate.

One addition the prior review does not make: **no transition is wrapped in `transaction.atomic()`**. `approve_record` creates a `Review` row, then saves the record, then notifies. A failure between steps one and two leaves a review recorded for a transition that did not happen. The lifecycle module is the natural place to put that transaction boundary, which strengthens the case.

**Verdict: CONFIRMED.** Classification: **MVP RECOMMENDED**, not blocker — the current split works, it is just unsafe to change.

---

### B2 · Access rules copy-pasted, `IsOwnerOrStaff` bypassed → **CONFIRMED, priority raised**

Confirmed. `core/permissions.py` declares eleven classes; `IsStudent`, `IsAdviser`, `IsKTTO`, `IsITSO`, `IsIERC` have zero references. The four-line inline owner-or-staff check is duplicated at `documents/views.py:226, 302, 336, 378` and in a fifth spelling at `reviews/views.py:183-192`. `core/exceptions.py` declares five exceptions; only `InvalidPipelineTransition` is used.

**Raised from "architecture" to "security."** The prior review classifies B2 as `Category: security` but sequences it after B1. Given that the same missing check is an *active IDOR* on twelve endpoints (Defect 5 above, extended), the permission work is P1, ahead of the lifecycle work. See [09](09-mvp-priorities.md).

**One addition.** The bypass is not only copy-paste; it is *wrong* in a specific way. Every hand-written copy reads:

```python
is_staff_user = get_role_name(request.user) in STAFF_ROLES or request.user.is_staff
```

Because migration `accounts/0005` sets `is_staff=True` for RDCO, KTTO, ITSO and IERC, the `or request.user.is_staff` clause is redundant for those roles — but it also silently admits any Django admin account. Combined with `is_django_staff()` inside `IsAdmin`, `_can_review()` and `_can_submit_clearance()`, this is a privilege-escalation path, not just duplication. See [05](05-security-architecture.md) finding SEC-4.

---

### B3 · Record visibility answered by copy-paste → **CONFIRMED and escalated to a security defect**

The counts hold: `("published", "approved", "completed")` appears six times, `Record.objects.filter(owners__user=…)` four times, `record.owners.filter(user=request.user).exists()` five times.

**Escalation.** The prior review frames the risk as *"miss one and the bug is a silent visibility leak."* That leak already exists and is not a copy-paste miss — it is a structural omission:

```python
def get_queryset(self):
    if self.action == "list":
        return Record.objects.filter(pipeline_status__in=("published","approved","completed"))...
    return Record.objects.select_related(...)          # ← no filter, any action
```
`records/views.py:50-58`, with `get_permissions` returning bare `IsAuthenticated` for `retrieve` (`:67-72`).

`GET /api/v1/records/<any id>/` therefore returns **any record in the system** — another student's draft, an in-review thesis, a rejected submission — to any authenticated account. A `visible_to(user)` queryset scope is the fix, which is exactly B3's recommendation; the classification changes from *refactor* to **MVP BLOCKER (security)**.

---

### B4 · `ApprovalRequest` abstraction → **REVISED — partially REJECTED**

**Confirmed as observation.** `DownloadRequest` and `DeleteRequest` do share six fields (`records/models.py:227-252`). `DownloadRequestSerializer` and `DeleteRequestSerializer` are near-identical (`records/serializers.py:132-169`) — same `get_requested_by_name` body verbatim. `RoleRequest` (`accounts/models.py:107-124`) declares the same status triple a third time.

**Rejected as prescribed.** The recommendation is an *abstract base model* carrying shared fields plus an `approve()`/`decline()` template method. Applying the deletion test to that specific abstraction:

> *If the `ApprovalRequest` base model were removed, would complexity increase or merely move?*

It would **merely move** — into two model definitions that are already flat, readable and independently migratable. The base class buys ~40 lines of field declarations and costs: a Django abstract-model inheritance hop when reading either model, a migration graph that must be reasoned about across two apps, and a template method whose two implementations already diverge (declining a `DeleteRequest` restores `previous_pipeline_status`; declining a `DownloadRequest` does nothing). `RoleRequest` cannot join the hierarchy at all — it lives in `accounts`, has no `record` FK, and its approval mutates `User.role`. A three-member hierarchy where one member does not fit is a two-member hierarchy with extra ceremony.

**What the duplication actually is.** The repeated thing is not the *fields*, it is the **guard-and-stamp block**, which appears five times in one file with identical bodies (`records/views.py:597-613, 615-630, 650-669, 671-694`, plus `520-536`):

```python
if dr.status != "pending":
    return Response({"detail": f"Request is already '{dr.status}'."}, status=400)
dr.status = ...; dr.reviewed_by = request.user; dr.reviewed_at = timezone.now()
dr.save(update_fields=["status", "reviewed_by", "reviewed_at"])
```

**Revised recommendation.** Extract *that* — one `ApprovalActionMixin` (or a plain `stamp_decision(request_obj, actor, decision)` function) plus one shared `ApprovalRequestSerializer` base. Leave the models alone. This captures the real repetition at a fraction of the risk.

- **Complexity:** Low (one function, one serializer base) vs Medium (model inheritance + migrations)
- **Migration risk:** **None** vs Medium — abstract-base refactors of existing concrete models require careful migration state handling
- **MVP classification:** **POST-MVP** for the mixin; **DO NOT IMPLEMENT** for the model base class

---

### B5 · Business logic in views → **CONFIRMED, scope narrowed**

Confirmed. `records/views.py` is 695 lines. `download_template` is 115 lines of openpyxl styling (`:358-472`); `import_excel` is 82 lines of per-row model writes that force `pipeline_status="published"`, bypassing the entire review pipeline (`:274-356`); `tags` is 68 lines of hand-rolled field whitelisting (`:160-228`).

**Narrowing.** Three of the four cited cases are worth extracting; one is better solved elsewhere:

| Case | Verdict |
|---|---|
| `download_template` → `records/reporting.py` | **Confirm.** 115 lines of spreadsheet styling has no business in a view; it is also the single easiest thing in this codebase to unit-test once moved. |
| `import_excel` → `records/importing.py` | **Confirm, and highest value** — because it is also a lifecycle bypass (B1) and an authorization question (staff-only import that force-publishes). |
| `tags` | **Revise.** The problem is not that it is in a view; it is that `VALID_IP_TYPES` at `:180` restates `Record.IP_TYPE_CHOICES`. Fix it with B7 (one enum) plus a serializer, not a service module. |
| `RecordAuthPinViewSet.generate` | **Confirm** — and it has a security dimension the prior review does not note: any authenticated user may generate a PIN for any record, and PIN verification gates nothing server-side. See [05](05-security-architecture.md) SEC-6. |

---

### B6 · Notification fan-out and swallowed failures → **REVISED**

**Confirmed as observation.** `notifications/services.py` is 736 lines. Twelve bare `except Exception: pass` blocks (ten in notifications, one in `audit/services.py:44`, one in `core/utils.py:52`). Calls originate from both views and services with no single dispatcher. A three-owner record advancing one stage does produce 2 broadcasts + 3 direct rows + 2 emails.

**One prior sub-claim REJECTED.** The review states *"a missing `NotificationType` row fails invisibly — and `_get_type` uses `.get()`, so a typo in a type name is undetectable."* The mechanism is right, but the implied instance is not: all eleven type names used by `_get_type` **are** seeded. Cross-check of `_get_type("...")` call sites against the four seed migrations shows an exact match on all eleven — `Record Approved`, `Record Declined`, `Record Advanced`, `Record Resubmission`, `New Record (Project)`, `New Record (Proposal / Thesis)`, and the four download/delete pairs. So the swallowing is a real *latent* hazard, not a currently-firing bug.

**Recommendation REVISED — the prescribed remedy is too big for this stage.** The proposal is a domain-event bus with notification and audit as subscribers. Deletion test on *that*:

> *If the event bus were removed, would complexity increase or merely move?*

At today's size it would **merely move** — from a bus plus subscriber registry plus event types back into eleven direct function calls that are perfectly legible. An event bus earns its keep when there are several independent subscribers or the publisher must not know its consumers. Here there is one consumer (notifications), one incidental one (audit), and the publisher is a single service module.

**Revised, two-step recommendation:**

1. **Now (MVP REQUIRED, ~1 hour):** replace all twelve `except Exception: pass` with `except Exception: logger.exception(...)`. This changes no behaviour and makes every silent failure observable. This is the entire safety benefit of B6 at 1% of the cost.
2. **Now (MVP RECOMMENDED, ~2 hours):** move the four `notify_*` calls that live in `records/views.py` (lines 144, 258, 668, 695) down into `records/services.py` / `reviews/services.py`, so notification dispatch has one layer, not two. No new abstraction.
3. **Later (POST-MVP):** revisit domain events *if and only if* a third subscriber appears (a webhook, a digest mailer, an analytics sink). One adapter is a hypothetical seam; two is a real one.

---

### B7 · Same three-element set spelled five ways → **CONFIRMED**

All five encodings verified: `RecordClearance.OFFICE_CHOICES` (`reviews/models.py:56`), `ROLE_TO_OFFICE` (`reviews/services.py:68`), `CLEARANCE_OFFICES` (`reviews/services.py:381`), `_OFFICE_TO_ROLE` (`notifications/services.py:416`), `_OFFICE_LABELS` (`notifications/services.py:264`). The adjacent claims also hold: `Record.IP_TYPE_CHOICES` vs `VALID_IP_TYPES` (`records/views.py:180`); the queued/running/done/failed triple duplicated on `PdfExtraction` and `EmbeddingJob`; "who reviews what" encoded independently at `reviews/views.py:61-67` and `reviews/services.py:89-93`.

**Verdict: CONFIRMED, and it is the best effort-to-value ratio in the backend.** One `TextChoices` enum per concept. Cheap, mechanical, low-risk, and it removes a failure mode that is currently silent because of B6's swallowing.

---

## Part 3 — Frontend candidates F1–F6

### F1 · Server state hand-rolled → **CONFIRMED; remedy confirmed after independent comparison**

Confirmed: `@tanstack/react-query` is **not** installed (only `@tanstack/react-table`). 35 `.tsx` files use `useEffect`; twelve fetch directly inside it. The specific bugs cited were spot-checked and hold. A full three-way comparison against simpler alternatives is in [03-frontend-architecture.md](03-frontend-architecture.md) — the short version is that TanStack Query wins, but for reasons that must be stated rather than assumed, and it is **MVP RECOMMENDED**, not a blocker.

---

### F2 · Four non-equivalent answers to "is this user staff?" → **CONFIRMED**

Verified: `hooks/useRole.ts:21` (canonical), `store/auth.store.ts:100-102` (dead duplicate export named `useRole`, colliding with the real hook), `components/auth/ProtectedRoute.tsx:24` (private local `isDjangoStaff`), plus the inline re-derivations in `Sidebar.tsx` and `DocumentsPage.tsx`. The name collision between `store/auth.store.ts`'s exported `useRole` and `hooks/useRole.ts`'s `useRole` is real and is the sharpest part of this finding — an import from the wrong module type-checks and silently behaves differently.

Also confirmed: `router/PrivateRoute.tsx` and `router/RoleRoute.tsx` are both superseded by `components/auth/ProtectedRoute.tsx`, which is the only guard `router/index.tsx` uses.

---

### F3 · Thirteen hand-rolled tables, `DataTable` used twice → **CONFIRMED**

`components/shared/DataTable.tsx` is 124 lines, wraps `@tanstack/react-table`, and already includes pagination controls at lines 96-118. `hooks/useDataTable.ts` (30 lines) has zero importers. Confirmed.

---

### F4 · Multiple form-validation stacks → **CONFIRMED, count corrected**

Import-count verification:

| Library | Files importing it |
|---|---|
| `react-hook-form` | 5 |
| `zod` | 3 |
| `formik` | 2 |
| `yup` | 1 |

Both stacks ship. The prior review's framing of "four stacks" counts *approaches* (Formik+Yup, RHF+Zod, RHF-no-resolver, hand-rolled), which is a fair reading; in *dependency* terms it is two stacks, five packages. Recommendation unchanged and confirmed: standardise on react-hook-form + Zod, drop `formik` and `yup`.

---

### F5 · Auth token in three places → **CONFIRMED** (see Defect 6 for the two additions)

---

### F6 · `DocumentsPage` is 793 lines → **CONFIRMED, priority lowered**

File sizes verified: `DocumentsPage` 793, `SignupPage` 457, `RecordDetailPage` 402, `DiscoverPage` 334, `PublishedRecordsPage` 304.

**Priority lowered to OPTIONAL / POST-MVP.** Every claim is true, but a long component is a readability cost, not a correctness or security one. Against twelve open IDOR endpoints and a system that does not boot, splitting a page file is the least valuable thing in this document. The prior review already rates it "Worth exploring" rather than "Strong"; this review agrees and defers it explicitly.

---

## Part 4 — Cross-cutting X1–X2

### X1 · Hand-retyped API contract → **REVISED (split into two decisions)**

**Confirmed as observation.** `PaginatedResponse<T>` is declared in four api modules. Four endpoints return bare arrays while the frontend types them as paginated (`records/views.py:262-272`, `reviews/views.py:90-92, 206-208, 218-220` — all four verified). The download-redeem route mismatch is confirmed: backend reads `request.query_params.get("token")` (`records/views.py:558`), and `records/urls.py:12` mounts it at `download/` with no path parameter.

**Revised.** The recommendation bundles two very different-cost changes:

| Step | Cost | Verdict |
|---|---|---|
| Add `drf-spectacular`, expose `/api/schema/` + Swagger UI | One dependency, ~10 lines of settings | **MVP RECOMMENDED.** Cheap, and it doubles as thesis-defence API documentation. |
| Generate the TypeScript client from the schema and wire it into the build | New codegen step, new CI dependency, regenerate-on-change discipline | **POST-MVP.** Real benefit, but it is a build-pipeline commitment, and there is no CI to hang it on yet. |
| Meanwhile: one shared `PaginatedResponse<T>`, paginate the four bare-array endpoints | Trivial | **MVP REQUIRED.** Do this regardless. |

---

### X2 · Nothing tested, lint cannot run → **CONFIRMED and escalated to MVP BLOCKER**

Verified: zero test files across both codebases; no ESLint config; no `test` or `typecheck` script; `requirements/development.txt:4` still reads `# TODO: add pytest-django and factory-boy when writing tests`.

**Escalated.** The prior review positions X2 as an enabler for the other candidates. This review positions it as a **blocker in its own right**, on direct evidence: of the five things that stop IRIS running today, **an import-smoke test would have caught three** (BLOCK-1 undefined names, BLOCK-5 missing `ai` migrations surfacing on `migrate --check`, and the `apps/ai` shadowing), and a `docker compose config` check in CI would have caught a fourth (BLOCK-2, the absent `ai/` directory). The prior review's own sentence — *"Five undefined names and a block of methods indented into the wrong class would each have been caught by importing the module once"* — is now demonstrated twice over on a later branch.

---

## Part 5 — Removals table

| Prior row | Verdict |
|---|---|
| Dead AI chat UI (~840 lines) | **CONFIRMED** — `RAGChatPage` + 7 components + `chatStorage` + `types/chat.ts`, unrouted; `AIHubPage` is what `router/index.tsx` mounts. |
| Unrouted feature pages | **CONFIRMED** — `AccessRequestsPage`, `FolderBrowserPage`. |
| Superseded router guards | **CONFIRMED** — `PrivateRoute`, `RoleRoute`, `ForbiddenPage`. |
| Other dead frontend modules | **CONFIRMED** — including the duplicate `features/discover/discoverUtils.ts` vs `lib/discoverUtils.ts`. |
| Dead API surface | **NEEDS INVESTIGATION** — the individual member counts were not re-verified call-site by call-site in this pass. The module-level claims (`api/dashboard.ts`, `api/storage.ts`) hold. |
| Orphaned Django AI app | **CONFIRMED as an action, REJECTED as stated** — the app should go, but *not* because "the five `pass` models were migrated into real empty tables." There is no `apps/ai/migrations/` package; nothing was migrated. |
| Duplicate PDF extraction (`documents/services/pdf_extractor.py`) | **REJECTED** — that file and directory do not exist on this branch. The `documents/tasks.py` chain is real and has a *different* problem: its three libraries are absent from `requirements/base.txt`. |
| Unused domain models | **CONFIRMED** — `ResearchLink`, `Publication`, `Conference`, `Budget`, `Collaboration` and the five lookup tables appear in no serializer, view or service. **Caveat:** several map to SRS fields (publication level, conference level, budget type) that Module 2 may still require. Confirm against the SRS before dropping the tables; dropping them is a destructive migration. |
| Unused core declarations | **CONFIRMED** — five permissions, four exceptions, zero references. |
| Dead code inside live files | **CONFIRMED** — `MyRecordsViewSet` (`records/views.py:474-483`) duplicates `RecordViewSet.mine` and is not routed; `documents/services.py:54-61` `build_zip_for_record` has no callers and an undefined `BytesIO`. |
| Two dependencies (`formik`, `yup`) | **CONFIRMED, and understated** — three more are installed with **zero** importers: `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone`. |
| Migration churn | **CONFIRMED** — `reviews/0002` adds `expires_at`, `0003` removes it, `0005` re-adds it. Low priority, as stated. |
| "Do not merge `storage` and `documents`" | **CONFIRMED, and endorsed.** Correct call. A personal file browser and per-record attachments are different concepts; merging them would concentrate complexity rather than reduce it. |

---

## Part 6 — Hosting section

**CONFIRMED with one material correction.**

The reasoning is sound and the recommendation — one box, Docker Compose, on campus, behind a Cloudflare Tunnel — is the right one for a thesis MVP with a low-budget path to production. The three cost levers it identifies (build the frontend instead of running `vite dev`; reconsider Docling's 4 GB; collapse the Celery workers) are all correct and all still open on this branch.

**The correction.** The memory table budgets 1 GB for `ai-gateway` and treats it as an existing component. It does not exist. Removing it and Docling takes the stack from a claimed ~8 GB to roughly **2 GB**, which materially widens the hosting options — and, more importantly, means the "does it fit on free tier?" question has a different answer than the one the table implies.

Full deployment analysis, including the five-service target and the fact that neither compose file can currently start, is in [07-deployment-architecture.md](07-deployment-architecture.md).

---

## Gaps — things the prior review does not cover

### Gap 1 · The `ai/` gateway does not exist

The most consequential omission. `docker-compose.yml:104` and `docker-compose.prod.yml:92` both declare:

```yaml
ai-gateway:
  build:
    context: ./ai
    dockerfile: Dockerfile
  env_file:
    - ./ai/.env
```

`ls ./ai` → no such directory. `git ls-files | grep '^ai/'` → no tracked files. **Both compose files fail at build.** The prior review's companion document `architecture_review_and_aws_roadmap.md`, described as covering "the `ai/` gateway," is also absent from `docs/`.

`docs/docker_compose_rag_services.md` compounds this by specifying the build context as `./ai-gateway` while the actual compose files use `./ai` — two different non-existent paths.

### Gap 2 · Celery cannot execute anything

Both compose files run workers with `-Q default`, `-Q extraction`, `-Q embedding`. `config/settings/base.py` defines no `CELERY_TASK_ROUTES` and no `task_default_queue`, so every `@shared_task` publishes to Celery's built-in default queue, named `celery`. **No worker consumes `celery`.** Every task is enqueued and never picked up. `celery-beat` likewise runs with no `CELERY_BEAT_SCHEDULE` defined, so the "nightly `embed_all_records`" that `rag_pipeline_service_map.md` documents is not scheduled anywhere.

### Gap 3 · The PDF extraction chain cannot import its libraries

`documents/tasks.py` imports `unstructured`, `fitz` (PyMuPDF), `pytesseract` and `PIL`. `requirements/base.txt` contains none of them — the comment block at lines 14-17 records their deliberate removal. All three extractors therefore raise `ImportError`, `_run_extraction_chain` raises `RuntimeError`, and the task retries three times and dies. **PDF text extraction, FR-M3-01, cannot succeed on any input.** The same applies to `sentence_transformers`, imported by `apps/ai/tasks.py:51` and absent from requirements.

### Gap 4 · Documentation references a different machine and non-existent files

`docs/README.md` links nine documents; **seven do not exist** (`SOFTWARE_ENGINEERING_PLAN.md`, `SDLC_PROCESS.md`, `SECURITY.md`, `SECURITY_RISK_REGISTER.md`, `TEST_PLAN.md`, `TRACEABILITY_MATRIX.md`, `DEVELOPMENT_GUIDE.md`). Both RAG documents link source files via absolute `file:///c:/Users/edlav/.antigravity/AntiProjects/IRIS/...` URLs — another contributor's local filesystem — and cite `docs/software-design/M04-RAG-AI-Services.md` and `docs/agile_and_scrum_notes.md`, neither of which is in the repository.

### Gap 5 · Storage/vector-DB configuration contradicts itself

`docker-compose.yml` uses `pgvector/pgvector:pg16`; `requirements/base.txt` lists `pgvector` twice (`>=0.3` at line 11 and `>=0.2.4` at line 21). But `pgvector` is **not** in `INSTALLED_APPS`, and `RecordEmbedding.embedding` is a `BinaryField` holding `pickle.dumps(...)` output (`apps/ai/models.py:26`, `apps/ai/tasks.py:57`). Vector search is `pickle.loads` in a Python loop over the full table (`apps/ai/views.py`). Unpickling database content is also an unsafe-deserialization pattern.

### Gap 6 · Authorization defects beyond `storage/`

Covered above under Defect 5 and B2/B3. Twelve endpoints total. See [05-security-architecture.md](05-security-architecture.md).

### Gap 7 · No transaction boundaries on workflow transitions

No `transaction.atomic()` anywhere in `reviews/services.py` or `records/views.py`. Multi-write operations — create `Review` + update `Record` + create `RecordClearance` rows — can partially apply.

### Gap 8 · `post_save` signal fires an extra UPDATE on every record write

`records/signals.py:6` rebuilds the FTS vector on **every** `Record.save()`, including `increment_access` and every `update_fields=["pipeline_status"]` call. Two statements where one would do, on the hottest write path. Minor, but free to fix by narrowing the signal to title/abstract changes.
