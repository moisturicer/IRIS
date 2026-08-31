# 05 — Security Tasks

Nine tasks. **Five are MVP Blockers.** Four of the defects are exploitable by any account that completes signup and receives the Student role.

Per the review brief, security defects outrank cosmetic refactoring: everything here precedes every item in `02-backend-tasks.md` and `03-frontend-tasks.md` except the boot blockers.

**Scope note.** This is a design and code review, not a penetration test. Nothing was exploited — the system does not currently run. Every finding cites a file and line.

---

## Priority order

| # | Task | Severity | Exploitable by | Effort |
|---|---|---|---|---|
| 1 | `SEC-01` unauthenticated `/media/` | **Critical** | anyone with a URL | XS |
| 2 | `SEC-02` any record readable by id | **Critical** | any student | S |
| 3 | `SEC-03` six document endpoints unchecked | **Critical** | any student | S |
| 4 | `SEC-04` storage endpoints unchecked | **Critical** | any student | S |
| 5 | `SEC-05` `is_staff` bypass | **High** | ITSO / IERC | S |
| 6 | `SEC-06` PIN enforces nothing | High | any user | M |
| 7 | `SEC-07` audit log mutable | Medium | superuser | S |
| 8 | `SEC-08` session never expires on inactivity | Medium | — | S |
| 9 | `SEC-09` prod config and secrets | Medium | deployment | S |

---

# SEC-01 · Remove the unauthenticated `/media/` route

## Objective
Stop serving every uploaded thesis PDF as a public static file.

## Problem
nginx serves the media volume directly, bypassing every permission check in `documents/views.py`.

## Current State
`frontend/nginx.conf:52-56`:

```nginx
location /media/ {
    alias /usr/share/nginx/html/media/;
    expires 30d;
    add_header Cache-Control "public, no-transform";
}
```

`docker-compose.prod.yml:210` mounts `media_files:/usr/share/nginx/html/media:ro`.

Every uploaded document is therefore reachable at `https://host/media/documents/<filename>` **with no authentication**. `RecordUpload.file` uses `upload_to="documents/"`, deriving filenames from the uploaded name, so they are guessable for predictably-named documents.

This is currently masked only by `DEP-02`'s port mismatch (nginx listens on 8080, Compose maps `80:80`), which makes the production frontend unreachable. **Fixing the port without fixing this exposes every document.**

Directly violates **NFR-S4** and the SRS's RA 10173 confidentiality commitments.

## Proposed State
No public media route. Uploads are served only through authenticated Django endpoints.

## Scope
- Delete the `/media/` location from `frontend/nginx.conf`
- Verify nothing in the frontend links `/media/` directly
- Optionally implement `X-Accel-Redirect` so Django authorizes and nginx streams

## Out of Scope
Moving media to S3 (post-MVP).

## Technical Approach
`RecordUploadDownloadView` and `RecordFileDownloadView` already exist and check permissions — route all access through them. If streaming performance matters later, add `X-Accel-Redirect` with Django doing the authorization.

## Dependencies
None. **Must land before or with `DEP-02`.**

## Risks
Low, but check for direct `/media/` references in the frontend first — removing the route breaks any that exist.

## Security Impact
Closes unauthenticated access to every uploaded document. Highest-severity finding in the review.

## Performance Impact
Downloads go through Django rather than nginx. Acceptable at this scale; `X-Accel-Redirect` restores nginx streaming if needed.

## Deployment Impact
nginx config change; redeploy the frontend image.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `GET /media/<known uploaded filename>` returns 403 or 404, never the file.
- [ ] `grep -rn '"/media/\|/media/' frontend/src/` returns no direct asset links.
- [ ] An authenticated owner can still download via `/api/v1/documents/uploads/<id>/download/`.
- [ ] A non-owner receives 403 from that endpoint.
- [ ] A deployment smoke test asserts the `/media/` case.

## Definition of Done
Merged; smoke test added; verified against a running prod-profile stack.

## Complexity
XS

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`security`, `critical`, `nginx`, `mvp-blocker`, `nfr-s4`

---

# SEC-02 · Enforce record visibility on `retrieve`, not only `list`

## Objective
Stop any authenticated user reading any record by primary key.

## Problem
The visibility filter is applied only to the `list` action. Every other action, including `retrieve`, runs against the unfiltered queryset with bare `IsAuthenticated`.

## Current State
`apps/records/views.py:50-58`:

```python
def get_queryset(self):
    if self.action == "list":
        return Record.objects.filter(
            pipeline_status__in=("published", "approved", "completed")
        ).select_related(...)
    return Record.objects.select_related(...)      # every other action: unfiltered
```

`apps/records/views.py:67-72`:

```python
def get_permissions(self):
    if self.action in ("update", "partial_update", "destroy"):
        return [IsAuthenticated(), IsOwnerOrStaff()]
    if self.action == "complete":
        return [IsAuthenticated(), IsRDCO()]
    return [IsAuthenticated()]                      # retrieve lands here
```

`GET /api/v1/records/<id>/` therefore returns **any record**: another student's unsubmitted draft, a thesis under IERC ethics review, a rejected submission with reviewer comments, an unpublished commercialisable invention. `RecordDetailSerializer` includes the abstract and related detail. Ids are sequential integers.

For a system whose purpose is managing **confidential pre-publication IP disclosures**, this is the most serious application-layer finding.

Violates **NFR-S4**.

## Proposed State
`get_queryset()` returns `Record.objects.visible_to(self.request.user)` for **all** actions, so `retrieve` 404s on a record the user may not see.

## Scope
- Apply the visibility scope to every action
- Add `IsOwnerOrStaff` to `retrieve` as defence in depth
- Audit `MyRecordsViewSet` and the dashboard views for the same pattern

## Out of Scope
Building the reusable scope — that is `BE-06`. This can ship with an inline filter if `BE-06` is not ready, but should adopt the scope when it lands.

## Technical Approach
404 rather than 403 for records the user cannot see, so existence is not confirmed.

## Dependencies
`BE-01` (module must import). `BE-06` provides the clean form.

## Risks
Low. Narrows access, so failures are visible 404s rather than silent leaks. Verify reviewers can still open records at their stage — that path runs through `reviewable_by`.

## Security Impact
Closes the broadest data leak in the API.

## Performance Impact
Neutral.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] A student requesting another student's `draft` record by id receives 404.
- [ ] A student requesting a record in `parallel_review` that they do not own receives 404.
- [ ] An owner can retrieve their own record at any status.
- [ ] A reviewer can retrieve a record at a stage they review.
- [ ] Any authenticated user can retrieve a `published` record.
- [ ] A parametrised regression test covers all six roles × the twelve pipeline statuses.

## Definition of Done
Merged; the role×status matrix test in CI; `NFR-S4` traceability recorded.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`security`, `critical`, `backend`, `idor`, `mvp-blocker`, `nfr-s4`

---

# SEC-03 · Add object-level authorization to six `documents` endpoints

## Objective
Stop any authenticated user reading, enumerating and writing documents on records they do not own.

## Problem
Six endpoints in `apps/documents/views.py` omit the ownership check their siblings perform. One has no check at all.

## Current State

| Endpoint | Line | Missing check | Effect |
|---|---|---|---|
| `RecordFileDownloadAllView` | 399 | **none at all** | Any user ZIPs **every file** on any record |
| `SubmitDocumentView` | 14 | none | Upload a PDF into any record |
| `RecordUploadCreateView` | 180 | none | Add a version to any record; `Record.objects.get(pk=…)` also unguarded |
| `RecordUploadListView` | 122 | none | Enumerate any record's upload history |
| `RecordFileListView` | 242 | none | Enumerate any record's attachments |
| `RecordSlotListView` | 103 | none | Read any record's slot structure |

`RecordFileDownloadAllView` is the worst: `RecordFile.objects.filter(record_id=record_id)` → `build_zip(files)` → returned. No `is_owner`, no `is_staff_user`, no 403 branch — while `RecordFileDownloadView` 40 lines above checks both.

**The write cases matter beyond confidentiality.** `resubmit_record` (`reviews/services.py:352-365`) requires *"at least one document uploaded after the last decline"* before a record may re-enter the pipeline. A third party can therefore satisfy another user's resubmission gate — a workflow-integrity defect.

Meanwhile the same four-line check is hand-written at `documents/views.py:226, 302, 336, 378` and in a fifth spelling at `reviews/views.py:183-192`.

**Relates to Jira `IR-7`**, which is marked *In Review* and claims to "decorate all sensitive backend API views." Six are undecorated. See `12-jira-ready-tasks.md`.

## Proposed State
All six endpoints enforce owner-or-staff via `core.permissions.IsOwnerOrStaff`; the five hand-written copies are replaced by the same class.

## Scope
- Add checks to the six endpoints
- Replace the five hand-written copies with `IsOwnerOrStaff`
- Filter the two list endpoints by records visible to the caller

## Out of Scope
The `is_staff` bypass inside those checks — that is `SEC-05`.

## Technical Approach
`IsOwnerOrStaff` already exists and implements `has_object_permission`. For the `APIView`-based endpoints, call `check_object_permissions` explicitly after fetching the record.

## Dependencies
`BE-01`. `BE-06` for the list filtering.

## Risks
Low. Confirm staff review workflows still function — reviewers legitimately need access to records they do not own, which `STAFF_ROLES` covers.

## Security Impact
Closes bulk document download, upload injection and enumeration.

## Performance Impact
One ownership query per request; negligible.

## Deployment Impact
None.

## Framework Impact
None — uses an existing class.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] `GET /api/v1/documents/files/download-all/?record=<not mine>` returns 403.
- [ ] `POST /api/v1/documents/submit/` with another user's record id returns 403.
- [ ] `POST /api/v1/documents/uploads/create/` with another user's record id returns 403.
- [ ] The three list endpoints return only records visible to the caller.
- [ ] `grep -c "is_staff_user = get_role_name" backend/apps/documents/views.py` returns 0.
- [ ] A reviewer at the correct stage can still access documents on records they do not own.

## Definition of Done
Merged; a parametrised non-owner test covering all six endpoints in CI; `IR-7` updated.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`security`, `critical`, `backend`, `idor`, `documents`, `mvp-blocker`, `nfr-s4`

---

# SEC-04 · Add ownership enforcement to `apps/storage`

## Objective
Stop any authenticated user reading, renaming, downloading and deleting any other user's folders and files.

## Problem
All six storage endpoints are bare `IsAuthenticated` with unfiltered querysets. Two are destructive.

## Current State

| View | Line | Queryset | Check |
|---|---|---|---|
| `StorageListView` | 11 | `filter(parent=parent)` — no owner filter | none |
| `StorageFolderListView` | 46 | `filter(parent_id=…)` | none |
| `StorageFolderDetailView` | 60 | **`StorageFolder.objects.all()`** | none |
| `StorageFileListView` | 67 | `filter(folder_id=…)` | none |
| `StorageFileDetailView` | 81 | **`StorageFile.objects.all()`** | none |
| `StorageFileDownloadView` | 88 | `.get(pk=pk)` | none |

`StorageFolderDetailView` is `RetrieveUpdateDestroyAPIView`; `StorageFileDetailView` is `RetrieveDestroyAPIView`. `StorageFolder.parent` is `on_delete=CASCADE`, so deleting a root folder destroys the whole subtree. There is **no soft delete** on these models and **no audit event** on these paths — the deletion is silent and unrecoverable.

`StorageFile.uploaded_by` and `StorageFolder.created_by` exist and are never consulted.

## Proposed State
Every queryset filtered by owner (or the model chosen in `ARCH-03`); detail views enforce object permission; deletions emit audit events.

## Scope
- Filter all six endpoints per the `ARCH-03` decision
- Add `IsOwnerOrStaff` to the detail views
- Emit `DELETE` audit events on folder and file deletion
- Consider soft delete for folders given the cascade

## Out of Scope
The personal-vs-institutional decision — that is `ARCH-03` and **blocks this task**.

## Technical Approach
Depends on `ARCH-03`: personal → filter by owner; institutional → reads open, writes/deletes staff-only; both → a `scope` field.

## Dependencies
**`ARCH-03` must be decided first.** Without it this gets guessed.

## Risks
Medium: if storage is currently used as a shared drive, filtering by owner will hide existing files from colleagues. Check for existing data before applying.

## Security Impact
Closes destructive IDOR on every stored file and folder.

## Performance Impact
Negligible.

## Deployment Impact
None.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] A user cannot retrieve, rename or delete a folder created by another user (403 or 404).
- [ ] A user cannot download a file uploaded by another user.
- [ ] `StorageListView` returns only entries the caller may see.
- [ ] No storage view uses an unfiltered `Model.objects.all()`.
- [ ] Folder and file deletions write an audit event.
- [ ] Behaviour matches the `ARCH-03` decision, cited in the PR.

## Definition of Done
Merged; six-endpoint non-owner test in CI; `ARCH-03` ADR linked.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`security`, `critical`, `backend`, `idor`, `storage`, `mvp-blocker`

---

# SEC-05 · Remove the `is_staff` authorization bypass

## Objective
Restore separation of duties between the four reviewing offices, as NFR-S4 and SRS Module 5 require.

## Problem
A migration and a helper together make ITSO and IERC de-facto administrators, and let any office approve at any workflow stage.

## Current State
Three parts compose the defect:

**(a)** `accounts/migrations/0005_set_is_staff_for_staff_roles.py` sets `is_staff=True` for `{RDCO, KTTO, ITSO, IERC}`.

**(b)** `core/permissions.py:23-25` — `is_django_staff()` returns `is_superuser or is_staff`.

**(c)** `IsAdmin` evaluates `is_django_staff(user) or role in ADMIN_ROLES` where `ADMIN_ROLES = {KTTO, RDCO}`. Because (a) gives ITSO/IERC `is_staff`, **`ADMIN_ROLES` never constrains anyone**.

**Privilege escalation.** ITSO/IERC gain every `IsAdmin` endpoint: `PATCH /users/<id>/role/` (assign any role, including RDCO — self-escalation to full control), `PATCH /users/<id>/lock/`, `POST /users/<id>/unlock/`, `GET /users/sessions/` (all sessions with emails), `DELETE /users/sessions/<jti>/`, `GET /users/`, `PATCH /settings/<key>/`.

**Workflow bypass.** `reviews/services.py:76-79`:

```python
def _can_review(user, record):
    from core.permissions import is_django_staff
    if is_django_staff(user):
        return True          # ← ITSO and IERC reach this
```

`_can_submit_clearance` likewise grants staff a pending-clearance fallback plus a final `if staff: return True, office`. An ITSO user can therefore perform **RDCO's final approval** and publish a record IERC never cleared.

**Compounding:** `is_staff=True` also grants Django admin login; `admin/` is mounted at `config/urls.py:7` and proxied by nginx.

Directly violates **NFR-S4**.

## Proposed State
Per the `ARCH-04` decision: `IsAdmin` means `ADMIN_ROLES or is_superuser`; the workflow predicates drop `is_django_staff` entirely.

## Scope
- Remove `is_django_staff` from `IsAdmin`
- Remove it from `_can_review` and `_can_submit_clearance`
- Per `ARCH-04`, add a migration reversing `is_staff` for ITSO/IERC
- Gate `admin/` behind superuser
- Replace the five hand-written `or request.user.is_staff` clauses (with `SEC-03`)

## Out of Scope
The decision itself (`ARCH-04`).

## Technical Approach
If a break-glass path is genuinely needed, gate it on `is_superuser` only, make it an explicit `force=True` parameter, and emit a distinct audit event when used.

## Dependencies
**`ARCH-04` must be decided first.** Pairs with `WF-02`.

## Risks
**Medium — the highest coordination risk in this backlog.** This removes capabilities ITSO/IERC accounts may be using daily. Confirm with the team before applying, and communicate the change.

## Security Impact
Closes privilege escalation and restores the four-office model that is the system's reason for existing.

## Performance Impact
None.

## Deployment Impact
Data migration on existing accounts.

## Framework Impact
None.

## MVP Classification
**MVP Blocker**

## Acceptance Criteria
- [ ] An ITSO user calling `PATCH /users/<id>/role/` receives 403.
- [ ] An IERC user calling `DELETE /users/sessions/<jti>/` receives 403.
- [ ] An ITSO user calling `approve` on a record at `rdco_review` receives 400/403 and the record does not advance.
- [ ] A KTTO user cannot act as the adviser on a Proposal at `adviser_review`.
- [ ] RDCO retains every capability it currently has.
- [ ] A `(role, stage, action) → allowed` table test covers all six roles × six stages.
- [ ] Django `admin/` is reachable only by superusers.

## Definition of Done
Merged; the role×stage matrix test in CI; `ARCH-04` ADR linked; team notified of removed access.

## Complexity
S

## Suggested Jira Type
Bug

## Suggested Priority
Critical

## Suggested Labels
`security`, `critical`, `rbac`, `privilege-escalation`, `mvp-blocker`, `nfr-s4`

---

# SEC-06 · Make the record access PIN enforce something

## Objective
Either make the PIN a real access control or stop presenting it as one.

## Problem
The mechanism issues and verifies PINs correctly and enforces nothing. It is relied upon by the UI while gating no server-side resource.

## Current State
`reviews/views.py:234-326`.

`generate` has `permission_classes = [IsAuthenticated]` and looks up the record by id with **no check** that the record is PIN-gated or that the caller has any relationship to it. Any authenticated user can therefore make IRIS email a PIN to their own address for any record id — also an existence oracle (404 vs 201) and an email-sending primitive.

`verify` sets `is_used = True` and returns `{"verified": true, "record_id": …}`. **Nothing is persisted that any later request consults.** `grep -rn "RecordAuthPin" backend/` returns only the model, its serializer, this view and its migrations.

The frontend presents the modal and, on `{"verified": true}`, renders the record — but the record and document endpoints never ask whether a PIN was verified.

## Proposed State
Per the `ARCH-05` decision: a real server-side grant that endpoints require, or an honest downgrade to confirmation-of-intent.

## Scope
- Restrict `generate` to records the caller may already see
- If option A: persist a grant (row or short-lived scoped token bound to user+record) and enforce it on record/document retrieval
- If option B/C: remove the access-control framing and schedule an SDD correction

## Out of Scope
The decision (`ARCH-05`).

## Technical Approach
For option A, a `RecordAccessGrant` row with an expiry, checked by the same permission layer as `SEC-02`/`SEC-03`.

## Dependencies
`ARCH-05`. Interacts with `SEC-02` — once visibility is enforced, the PIN may be redundant.

## Risks
Low.

## Security Impact
Removes assurance the control does not deliver, and closes the email/enumeration primitive.

## Performance Impact
One extra check per gated retrieval.

## Deployment Impact
Possible new table.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `POST /reviews/pin/generate/` for a record the caller cannot see returns 403, not a PIN email.
- [ ] Requesting a PIN for a non-existent record returns the same response as for a forbidden one (no existence oracle).
- [ ] If option A: accessing a gated record without a verified grant returns 403; with one, 200.
- [ ] If option A: the grant expires and is single-use.
- [ ] If option B/C: no UI or documentation describes the PIN as access control.

## Definition of Done
Merged per the ADR; tests for the chosen option; SDD 3.5.2 correction ticketed if needed.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`security`, `backend`, `mvp-required`, `pin`

---

# SEC-07 · Make the audit log immutable and cover review decisions

## Objective
Satisfy NFR-S5 (12-month retention, immutable) and FR-M8-02 (read-only audit log), and record the decisions that matter.

## Problem
Two gaps: the audit log is an ordinary mutable Django model, and it does not record any review or clearance decision.

## Current State
`apps/audit/models.py::AuditEvent` is a normal model with 14 event types. A superuser can edit or delete rows through the Django admin. **NFR-S5** requires: *"no user role, including System Administrators, shall be able to edit or delete log entries through any exposed interface,"* validated by attempting a DELETE via both the REST API and the admin panel.

`AuditEventListView` uses `IsAdminUser` (Django `is_staff`) — so, per `SEC-05`, all four office roles can currently read the whole log, including `FAILED_LOGIN` events whose metadata contains attempted email addresses (`accounts/views.py:50`).

**Coverage gap:** `grep -rn "create_audit_event" backend/apps/reviews/` returns two matches, both `PIN_GENERATED`/`PIN_VERIFIED`. There is **no event type for approve, decline, reject or clear** — the workflow actions with the highest integrity value are unaudited. `Review` and `RecordClearance` rows record them, but those are domain records, not an audit trail: `resubmit_record` (`reviews/services.py:381`) *deletes* clearance rows on a sequential-decline resubmission.

Also `ACCESS` is overloaded — `records/views.py:223` logs a tag edit as `ACCESS`.

Jira `IR-24` and `IR-47` cover immutability.

## Proposed State
Insert-only at the database layer; admin registration read-only; `REVIEW_DECISION`, `CLEARANCE_DECISION` and `TAG_CHANGE` event types emitted.

## Scope
- Revoke UPDATE/DELETE on the audit table at the database role level, or enforce via a DB trigger
- Register `AuditEvent` in the admin with `has_change_permission`/`has_delete_permission` returning False
- Add the three event types and emit them from `reviews/services.py` and `records/views.py`
- Narrow read access to `ADMIN_ROLES` once `SEC-05` lands

## Out of Scope
Log shipping and 12-month retention automation (`DEP-04`).

## Technical Approach
Application-level guards alone do not satisfy NFR-S5's "at the data layer" validation — a database trigger or a restricted DB role is required. Emit the new events inside `WF-05`'s transaction so they cannot diverge from the decision.

## Dependencies
`SEC-05` (read narrowing), `WF-03` (decision events), `WF-05` (transaction).

## Risks
Low. A DB-level restriction can complicate legitimate maintenance — document the break-glass procedure.

## Security Impact
Directly satisfies NFR-S5 and FR-M8-02.

## Performance Impact
Negligible.

## Deployment Impact
Database role or trigger migration.

## Framework Impact
None.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] `DELETE` on an audit event via the REST API is rejected.
- [ ] Deleting an audit event in the Django admin as a superuser is rejected **at the data layer** (NFR-S5 validation method).
- [ ] Editing an audit event is likewise rejected.
- [ ] Every approve/decline/reject/clear writes a `REVIEW_DECISION` or `CLEARANCE_DECISION` event including stage, decision and resulting status.
- [ ] Tag edits emit `TAG_CHANGE`, not `ACCESS`.
- [ ] Only `ADMIN_ROLES` or superusers can read the audit log.

## Definition of Done
Merged with the DB-level guard; the NFR-S5 validation performed and recorded for `VAL-02`; `IR-24`/`IR-47` linked.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`security`, `audit`, `compliance`, `nfr-s5`, `fr-m8-02`, `mvp-required`

---

# SEC-08 · Enforce session expiry after 30 minutes of inactivity

## Objective
Satisfy NFR-S2, which the current token design does not meet.

## Problem
**A conflict not covered in `docs/architecture-review/`.** NFR-S2 requires sessions to expire after 30 consecutive minutes of *inactivity*. The implementation expires *access tokens* after 30 minutes but issues a 7-day refresh token that the client silently rotates — so an idle session never expires.

## Current State
`settings/base.py:132-141`:

```python
"ACCESS_TOKEN_LIFETIME":  timedelta(minutes=30),
"REFRESH_TOKEN_LIFETIME": timedelta(days=7),
"ROTATE_REFRESH_TOKENS":  True,
"BLACKLIST_AFTER_ROTATION": True,
```

`src/api/client.ts` refreshes automatically on any 401, and `store/auth.store.ts::hydrateAuth` refreshes on page load from a `sessionStorage` refresh token.

NFR-S2's validation is explicit: *"authenticate, wait 31 minutes, attempt a protected API call, and verify an HTTP 401 response is returned and the token rejected on all subsequent requests."* Today the client refreshes and the call succeeds — **the test fails**.

Mitigating factor: the refresh token lives in `sessionStorage`, so closing the tab ends the session. That is not the same as inactivity expiry.

## Proposed State
Server-side inactivity tracking: refresh is refused when the last activity exceeds 30 minutes.

## Scope
- Track last-activity per refresh token (or per user session)
- Refuse refresh beyond the inactivity window and blacklist the token
- Frontend handles the resulting 401 by redirecting to login with a clear reason
- Reconcile `REFRESH_TOKEN_LIFETIME` with NFR-S2

## Out of Scope
Moving to httpOnly cookies.

## Technical Approach
A custom `TokenRefreshView` subclass consulting a last-seen timestamp updated by an authentication middleware or DRF authentication class. `OutstandingToken` already tracks issuance and is queried by `ActiveSessionsView`.

## Dependencies
`FE-01` (the refresh path must be sane first).

## Risks
Medium on usability — an aggressive implementation logs users out mid-form. "Activity" should mean any authenticated API call, not only navigation.

## Security Impact
Satisfies NFR-S2; reduces the window for a stolen refresh token.

## Performance Impact
One timestamp write per authenticated request — use a cheap store (Redis) rather than a DB write per call.

## Deployment Impact
Requires Redis (already deployed).

## Framework Impact
None.

## MVP Classification
**MVP Required** (it is an explicit NFR with a defined validation)

## Acceptance Criteria
- [ ] Authenticate, idle 31 minutes, call a protected endpoint → 401.
- [ ] The refresh token is rejected on all subsequent requests.
- [ ] A user active every 10 minutes is never logged out.
- [ ] The frontend redirects to login with a "session expired" reason.
- [ ] Activity is defined as any authenticated API call, documented.

## Definition of Done
Merged; the NFR-S2 validation test automated (with a mockable clock) and recorded for `VAL-01`.

## Complexity
M

## Suggested Jira Type
Story

## Suggested Priority
High

## Suggested Labels
`security`, `auth`, `jwt`, `nfr-s2`, `mvp-required`

---

# SEC-09 · Production configuration, secrets and CORS

## Objective
Close the deployment-time security gaps and finish the four `TODO`s in production settings.

## Problem
Production settings are 13 lines, four of which are TODOs; credentials are hardcoded; dev CORS allows any origin with credentials.

## Current State

| Item | State |
|---|---|
| `ALLOWED_HOSTS` | `# TODO: set ALLOWED_HOSTS to real domain`; `base.py:8` defaults to `"localhost"` |
| S3 media | `# TODO: configure S3 for MEDIA_ROOT via django-storages` — installed, unconfigured |
| Sentry | `# TODO: configure Sentry DSN` — `sentry-sdk` in `production.txt`, never initialised |
| `SECRET_KEY` | No default (good — fails loudly), but `.env.example` ships `change-me-in-production` |
| DB credentials | `base.py:79-82` defaults to `iris_user`/`iris_password`; **both Compose files hardcode the same values** |
| Dev CORS | `development.py:11` `CORS_ALLOW_ALL_ORIGINS = True` with `base.py:150` `CORS_ALLOW_CREDENTIALS = True` |
| Download tokens | Signed with `SECRET_KEY`, the same key as JWT |

CORS: because IRIS uses bearer tokens rather than cookies, practical exposure is limited today — but the combination becomes critical if auth ever moves to cookies, and dev settings reach staging easily.

CSRF: `CsrfViewMiddleware` is enabled and correct for the Django admin; DRF with `JWTAuthentication` is not session-authenticated, so it is not load-bearing for the API. No action needed — noted because it is *because* tokens travel in a header.

## Proposed State
Explicit `ALLOWED_HOSTS`, real generated secrets, restricted dev CORS, Sentry initialised or removed.

## Scope
- `ALLOWED_HOSTS` from environment, failing startup if unset in production
- Replace `CORS_ALLOW_ALL_ORIGINS` with an explicit localhost list
- Move DB credentials out of both Compose files into `.env`
- Initialise Sentry or remove the dependency
- Consider a separate signing key for download tokens

## Out of Scope
S3 configuration (post-MVP). TLS termination (`DEP-02`).

## Technical Approach
Keep `python-decouple`. Add a startup assertion for production-only settings.

## Dependencies
`DEP-05` overlaps on secrets — do them together.

## Risks
Low. A too-strict `ALLOWED_HOSTS` breaks deployment — test on staging first.

## Security Impact
Removes a credentialed-CORS hazard, default credentials, and unbounded host headers.

## Performance Impact
None.

## Deployment Impact
Requires real secrets at deploy time.

## Framework Impact
Possibly drops `sentry-sdk`.

## MVP Classification
**MVP Required**

## Acceptance Criteria
- [ ] Starting with production settings and no `ALLOWED_HOSTS` fails with a clear error.
- [ ] `grep -rn "iris_password" docker-compose*.yml` returns no matches.
- [ ] `CORS_ALLOW_ALL_ORIGINS` appears nowhere; dev uses an explicit origin list.
- [ ] `.env.example` contains no value usable as a real secret.
- [ ] Sentry is initialised **or** `sentry-sdk` is removed from requirements.
- [ ] `DEBUG` is False in every deployed profile (asserted by a smoke test).

## Definition of Done
Merged; verified on a staging deploy; secrets rotated; documented in `docs/DEVELOPMENT_GUIDE.md`.

## Complexity
S

## Suggested Jira Type
Task

## Suggested Priority
High

## Suggested Labels
`security`, `configuration`, `deployment`, `secrets`, `mvp-required`
