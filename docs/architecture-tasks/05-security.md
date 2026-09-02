# 05 — Security

Seven tasks. **Four are P0 and gate the Weeks 1–2 public deployment.** Nothing goes to a public URL until `S-01`, `S-02`, `S-03`, `S-04` and `SC-01` are done.

Governed by [ADR-009](../adr/009-authorization-model.md). This is a design and code review, not a penetration test — nothing was exploited, since the system does not currently run. Every finding cites a file and line.

---

# S-01 · Remove the unauthenticated `/media/` route

## Objective
Stop serving every uploaded thesis PDF as a public static file.

## Problem
nginx serves the media volume directly, bypassing every permission check in `documents/views.py`.

## Evidence
`frontend/nginx.conf:52-56`:
```nginx
location /media/ {
    alias /usr/share/nginx/html/media/;
    expires 30d;
}
```
with `docker-compose.prod.yml:210` mounting `media_files:/usr/share/nginx/html/media:ro`. `RecordUpload.file` uses `upload_to="documents/"`, so filenames derive from the uploaded name and are guessable.

Currently masked only by `D-02`'s port mismatch. **Fixing the port without fixing this exposes every document.**

## Current State
Every uploaded document is reachable at `https://host/media/documents/<filename>` with no authentication.

## Proposed State
No public media route. Files served only through authenticated Django endpoints.

## Scope
Delete the `/media/` location; verify no frontend code links `/media/` directly.

## Out of Scope
`X-Accel-Redirect` — the right answer if streaming performance matters later; unnecessary at pilot scale.

## Technical Approach
`RecordUploadDownloadView` and `RecordFileDownloadView` already exist and check permissions.

## Dependencies
None. **Must land before or with `D-02`, and before any public URL.**

## Risks
Low, but grep for direct `/media/` references first.

## Security Impact
Closes unauthenticated access to every uploaded document. Highest-severity finding in the review.

## Performance Impact
Downloads go through Django. Acceptable at this scale.

## SaaS Impact
Per-instance media volumes remain isolated under [ADR-005](../adr/005-instance-per-tenant.md).

## Research/Thesis Impact
A document leak during the pilot would end the pilot.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Week 1

## Complexity
XS

## Acceptance Criteria
- [ ] `GET /media/<known uploaded filename>` returns 403 or 404, never the file.
- [ ] `grep -rn "/media/" frontend/src/` returns no direct asset links.
- [ ] An owner can still download via `/api/v1/documents/uploads/<id>/download/`.
- [ ] A non-owner receives 403 from that endpoint.

## Testing Requirements
A deployment smoke test asserting the `/media/` case, run against every deployed environment.

## Documentation Requirements
Recorded in `DOC-05`.

## Definition of Done
Merged; verified against the running interim deployment.

---

# S-02 · Enforce record visibility on `retrieve`

## Objective
Stop any authenticated user reading any record by primary key.

## Problem
The visibility filter is applied only to `list`. Every other action, including `retrieve`, runs against the unfiltered queryset with bare `IsAuthenticated`.

## Evidence
`records/views.py:50-58`:
```python
def get_queryset(self):
    if self.action == "list":
        return Record.objects.filter(pipeline_status__in=("published","approved","completed"))…
    return Record.objects.select_related(…)      # every other action: unfiltered
```
and `:67-72` — `get_permissions` returns `[IsAuthenticated()]` for `retrieve`.

## Current State
`GET /api/v1/records/<id>/` returns **any record**: another student's unsubmitted draft, a thesis under IERC ethics review, a rejected submission with reviewer comments. Ids are sequential. `RecordDetailSerializer` includes the abstract and related detail.

For a system managing confidential pre-publication IP disclosures, this is the most serious application-layer finding. Violates **NFR-S4**.

## Proposed State
`get_queryset()` returns `Record.objects.visible_to(self.request.user)` for **all** actions, so `retrieve` 404s on records the user may not see.

## Scope
Apply the scope to every action; add `IsOwnerOrStaff` to `retrieve`; audit `MyRecordsViewSet` and the dashboard views for the same pattern.

## Out of Scope
Building the scope (`B-05`) — this can ship with an inline filter and adopt the scope when it lands.

## Technical Approach
404 rather than 403, so existence is not confirmed.

## Dependencies
`B-01`. `B-05` provides the clean form.

## Risks
Low. Verify reviewers can still open records at their stage — that path runs through `reviewable_by`.

## Security Impact
Closes the broadest data leak in the API.

## Performance Impact
Neutral.

## SaaS Impact
None under instance-per-tenant.

## Research/Thesis Impact
Gates the Weeks 1–2 validation deployment.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Weeks 1–3

## Complexity
S

## Acceptance Criteria
- [ ] A student requesting another student's `draft` record receives 404.
- [ ] A student requesting a record in `parallel_review` they do not own receives 404.
- [ ] An owner can retrieve their own record at any status.
- [ ] A reviewer can retrieve a record at a stage they review.
- [ ] Any authenticated user can retrieve a `published` record.

## Testing Requirements
`T-02` — parametrised matrix over six roles × twelve pipeline statuses.

## Documentation Requirements
NFR-S4 traceability in `DOC-06`.

## Definition of Done
Merged; matrix test in CI; verified on the interim deployment.

---

# S-03 · Object-level authorization on six `documents` endpoints

## Objective
Stop any authenticated user reading, enumerating and writing documents on records they do not own.

## Problem
Six endpoints omit the ownership check their siblings perform. One has none at all.

## Evidence

| Endpoint | Line | Effect |
|---|---|---|
| `RecordFileDownloadAllView` | `documents/views.py:399` | **No check at all** — any user ZIPs every file on any record |
| `SubmitDocumentView` | `:14` | Upload a PDF into any record |
| `RecordUploadCreateView` | `:180` | Add a version to any record; `Record.objects.get()` also unguarded |
| `RecordUploadListView` | `:122` | Enumerate any record's upload history |
| `RecordFileListView` | `:242` | Enumerate any record's attachments |
| `RecordSlotListView` | `:103` | Read any record's slot structure |

Meanwhile the same four-line check is hand-written at `:226, 302, 336, 378` and in a fifth spelling at `reviews/views.py:183-192`.

**The write cases matter beyond confidentiality.** `resubmit_record` (`reviews/services.py:352-365`) requires a document uploaded after the last decline before a record may re-enter the pipeline — so a third party can satisfy another user's resubmission gate. That is a workflow-integrity defect against the thesis contribution.

## Current State
Six unprotected endpoints; five duplicated checks.

## Proposed State
All six enforce owner-or-staff via `IsOwnerOrStaff`; the five copies are replaced by the same class.

## Scope
Add checks to the six; replace the five copies; filter the two list endpoints by visible records.

## Out of Scope
The `is_staff` bypass inside those checks (`S-05`).

## Technical Approach
`IsOwnerOrStaff` exists and implements `has_object_permission`. For `APIView`-based endpoints, call `check_object_permissions` after fetching the record.

## Dependencies
`B-01`; `B-05` for list filtering.

## Risks
Low. Confirm staff review workflows still function — reviewers legitimately access records they do not own.

## Security Impact
Closes bulk document download, upload injection and enumeration.

## Performance Impact
One ownership query per request.

## SaaS Impact
None under instance-per-tenant.

## Research/Thesis Impact
Upload injection could corrupt the resubmission gate the evaluation measures.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Weeks 1–3

## Complexity
S

## Acceptance Criteria
- [ ] `GET /documents/files/download-all/?record=<not mine>` returns 403.
- [ ] `POST /documents/submit/` with another user's record id returns 403.
- [ ] `POST /documents/uploads/create/` with another user's record id returns 403.
- [ ] The three list endpoints return only records visible to the caller.
- [ ] `grep -c "is_staff_user = get_role_name" backend/apps/documents/views.py` returns 0.
- [ ] A reviewer at the correct stage retains access.

## Testing Requirements
`T-02` — parametrised non-owner test across all six.

## Documentation Requirements
`DOC-05`.

## Definition of Done
Merged; tests in CI; Jira `IR-7` updated.

---

# S-04 · Production configuration, secrets and CORS

## Objective
Close the deployment-time gaps that make a public URL unsafe.

## Problem
Production settings are 13 lines, four of them `TODO`s; credentials are hardcoded in version control; dev CORS allows any origin with credentials.

## Evidence

| Item | State |
|---|---|
| `ALLOWED_HOSTS` | `# TODO: set to real domain`; `base.py:8` defaults to `"localhost"` |
| `SECRET_KEY` | No default (correct — fails loudly), but `.env.example` ships `change-me-in-production` |
| DB credentials | `base.py:79-82` defaults to `iris_user`/`iris_password`; **both Compose files hardcode the same** |
| Dev CORS | `development.py:11` `CORS_ALLOW_ALL_ORIGINS = True` with `base.py:150` `CORS_ALLOW_CREDENTIALS = True` |
| Sentry | `sentry-sdk` in `production.txt`, never initialised |
| Download tokens | Signed with `SECRET_KEY`, same key as JWT |

**CSRF note:** `CsrfViewMiddleware` is enabled and correct for the Django admin. DRF with `JWTAuthentication` is not session-authenticated, so it is not load-bearing for the API — *because* tokens travel in a header. This is a reason not to move to cookie auth without designing CSRF.

## Current State
Working credentials in version control; unbounded host header; credentialed wildcard CORS in dev.

## Proposed State
Explicit `ALLOWED_HOSTS` from environment; real generated secrets; restricted dev CORS; Sentry initialised or removed.

## Scope
`ALLOWED_HOSTS` failing startup if unset in production; explicit dev origin list; DB credentials to `.env` in both Compose files; `${DB_PASSWORD:?err}` so a missing value fails loudly; initialise or remove Sentry.

## Out of Scope
S3 media (Phase 2). TLS termination (`D-03`). A secrets manager — disproportionate for one box.

## Technical Approach
Keep `python-decouple`. Add a startup assertion for production-only settings.

## Dependencies
None. **Gates the public URL.**

## Risks
Low. A too-strict `ALLOWED_HOSTS` breaks deployment — test on the interim VPS first.

## Security Impact
Removes credentials from version control, a credentialed-CORS hazard and unbounded host headers.

## Performance Impact
None.

## SaaS Impact
Per-instance secrets become part of the provisioning runbook (`SA-02`).

## Research/Thesis Impact
Required before the validation deployment.

## MVP Classification
MVP BLOCKER

## Priority
P0 — Weeks 1–3

## Complexity
S

## Acceptance Criteria
- [ ] Production settings with no `ALLOWED_HOSTS` fail at startup with a clear error.
- [ ] `grep -rn "iris_password" docker-compose*.yml backend/config/` returns nothing.
- [ ] `CORS_ALLOW_ALL_ORIGINS` appears nowhere; dev uses an explicit origin list.
- [ ] `.env.example` contains no usable secret.
- [ ] `DEBUG` is False in every deployed profile (smoke test).
- [ ] Sentry initialised or `sentry-sdk` removed.

## Testing Requirements
Deployment smoke test asserting `DEBUG=False` and a rejected bad Host header.

## Documentation Requirements
Secret generation in the setup guide; recorded in `DOC-05`.

## Definition of Done
Merged; verified on the interim VPS; credentials rotated.

---

# S-05 · Remove the `is_staff` authorization bypass

## Objective
Restore separation of duties between the four reviewing offices, as NFR-S4 and SRS Module 5 require.

## Problem
A migration and a helper together make ITSO and IERC de-facto administrators, and let any office approve at any workflow stage.

## Evidence
`accounts/migrations/0005` sets `is_staff=True` for `{RDCO, KTTO, ITSO, IERC}`. `core/permissions.py:23-25` defines `is_django_staff()` as `is_superuser or is_staff`. `IsAdmin` evaluates `is_django_staff(user) or role in ADMIN_ROLES` where `ADMIN_ROLES = {KTTO, RDCO}` — so **`ADMIN_ROLES` constrains nobody**.

ITSO/IERC consequently gain: `PATCH /users/<id>/role/` (assign any role, including RDCO — self-escalation), `PATCH /users/<id>/lock/`, `GET /users/sessions/`, `DELETE /users/sessions/<jti>/`, `PATCH /settings/<key>/`.

`reviews/services.py:76-79`:
```python
def _can_review(user, record):
    if is_django_staff(user):
        return True          # ← ITSO and IERC reach this
```
`_can_submit_clearance` likewise ends `if staff: return True, office`. **An ITSO user can perform RDCO's final approval and publish a record IERC never cleared.**

`is_staff=True` also grants Django admin login; `admin/` is mounted at `config/urls.py:7`.

## Current State
The four-office separation of duties — the substance of the thesis contribution — is advisory, not enforced.

## Proposed State
`IsAdmin` means `role in ADMIN_ROLES or is_superuser`; both workflow predicates drop `is_django_staff`; a migration reverses `is_staff` for ITSO and IERC; `admin/` is superuser-only.

## Scope
The four changes above, plus replacing the five hand-written `or request.user.is_staff` clauses (with `S-03`).

## Out of Scope
A break-glass path — if genuinely needed, gate on `is_superuser` only, make it an explicit `force=True`, and emit a distinct audit event.

## Technical Approach
Change `IsAdmin`, remove the bypass from both predicates, write the reversal migration.

## Dependencies
`W-05` shares the policy consolidation.

## Risks
**Medium — the highest coordination risk in the backlog.** It removes capabilities ITSO/IERC accounts may use daily. **Confirm with the team and communicate before applying, not after.**

## Security Impact
Closes privilege escalation and restores the model that is the system's reason for existing.

## Performance Impact
None.

## SaaS Impact
Office-role semantics become institution-configurable; the Django `is_staff` flag stops being an authorization signal, which is a precondition for that.

## Research/Thesis Impact
**Direct.** An unenforced separation of duties undermines the contribution's credibility at defence as much as its security.

## MVP Classification
MVP REQUIRED

## Priority
P1 — Week 4

## Complexity
S

## Acceptance Criteria
- [ ] An ITSO user calling `PATCH /users/<id>/role/` receives 403.
- [ ] An IERC user calling `DELETE /users/sessions/<jti>/` receives 403.
- [ ] An ITSO user approving at `rdco_review` is refused and the record does not advance.
- [ ] A KTTO user cannot act as adviser at `adviser_review`.
- [ ] RDCO retains every current capability.
- [ ] Django `admin/` is reachable only by superusers.

## Testing Requirements
`T-02` — `(role, stage, action) → allowed` table over six roles × six stages.

## Documentation Requirements
The authorization model in `DOC-05`; the decision in [ADR-009](../adr/009-authorization-model.md).

## Definition of Done
Merged; matrix test in CI; team notified of removed access.

---

# S-06 · Session expiry after 30 minutes of inactivity

## Objective
Satisfy NFR-S2, which the current token design does not meet.

## Problem
NFR-S2 requires expiry after 30 consecutive minutes of *inactivity*. The implementation expires *access tokens* after 30 minutes but issues a 7-day refresh token the client silently rotates — so an idle session never expires.

## Evidence
`settings/base.py:132-141`: `ACCESS_TOKEN_LIFETIME` 30 min, `REFRESH_TOKEN_LIFETIME` 7 days, `ROTATE_REFRESH_TOKENS` True. `src/api/client.ts` refreshes on any 401; `hydrateAuth` refreshes on page load.

NFR-S2's validation: *"authenticate, wait 31 minutes, attempt a protected API call, and verify an HTTP 401."* Today the client refreshes and the call succeeds — **the test fails**.

Mitigating: the refresh token lives in `sessionStorage`, so closing the tab ends the session. That is not inactivity expiry.

## Current State
NFR-S2 unmet.

## Proposed State
Server-side inactivity tracking; refresh refused beyond 30 minutes of no activity.

## Scope
Last-activity tracking per session; refuse and blacklist beyond the window; frontend handles the 401 with a clear reason; reconcile `REFRESH_TOKEN_LIFETIME` with NFR-S2.

## Out of Scope
httpOnly cookies.

## Technical Approach
A `TokenRefreshView` subclass consulting a last-seen timestamp updated by an authentication class. Store in Redis, not the database — one write per authenticated request.

## Dependencies
`FE-01`.

## Risks
Medium on usability — an aggressive implementation logs users out mid-form. "Activity" means any authenticated API call, not navigation.

## Security Impact
Satisfies NFR-S2; reduces the window for a stolen refresh token.

## Performance Impact
One Redis write per authenticated request.

## SaaS Impact
Session policy becomes institution-configurable in Phase 2.

## Research/Thesis Impact
An NFR with a defined validation method — required evidence for `V-06`.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] Authenticate, idle 31 minutes, call a protected endpoint → 401.
- [ ] The refresh token is rejected on all subsequent requests.
- [ ] A user active every 10 minutes is never logged out.
- [ ] The frontend redirects to login with a "session expired" reason.

## Testing Requirements
Automated test with a mockable clock; one real 31-minute confirmation for `V-06`.

## Documentation Requirements
Activity definition recorded in `DOC-05`.

## Definition of Done
Merged; NFR-S2 validation passed and recorded.

---

# S-07 · Audit log immutability

## Objective
Satisfy NFR-S5 and FR-M8-02 — 12-month retention, immutable, read-only.

## Problem
The audit log is an ordinary mutable Django model. A superuser can edit or delete rows through the admin.

## Evidence
`apps/audit/models.py::AuditEvent` is a normal model. NFR-S5 requires *"no user role, including System Administrators, shall be able to edit or delete log entries through any exposed interface"*, validated by attempting DELETE via **both** the REST API and the admin panel.

`AuditEventListView` uses `IsAdminUser` (Django `is_staff`) — so per `S-05` all four office roles can currently read the whole log, including `FAILED_LOGIN` events whose metadata contains attempted email addresses (`accounts/views.py:50`).

## Current State
Mutable, and readable by four office roles.

## Proposed State
Insert-only at the database layer; admin registration read-only; reads narrowed to `ADMIN_ROLES`.

## Scope
Revoke UPDATE/DELETE on the audit table at the database role level or via a trigger; `has_change_permission`/`has_delete_permission` return False; narrow read access after `S-05`.

## Out of Scope
Log shipping and retention automation (`D-05`).

## Technical Approach
**Application-level guards alone do not satisfy NFR-S5's "at the data layer" validation** — a database trigger or restricted role is required.

## Dependencies
`S-05`, `W-04`.

## Risks
Low. A DB-level restriction complicates legitimate maintenance — document the break-glass procedure.

## Security Impact
Directly satisfies NFR-S5 and FR-M8-02.

## Performance Impact
Negligible.

## SaaS Impact
Per-instance audit isolation is structural.

## Research/Thesis Impact
`W-04`'s instrumentation lives in this table — immutability protects the evaluation data as well as the compliance story.

## MVP Classification
MVP REQUIRED

## Priority
P2

## Complexity
M

## Acceptance Criteria
- [ ] `DELETE` on an audit event via the REST API is rejected.
- [ ] Deleting an audit event in the Django admin as a superuser is rejected **at the data layer**.
- [ ] Editing is likewise rejected.
- [ ] Only `ADMIN_ROLES` or superusers can read the audit log.

## Testing Requirements
NFR-S5 validation performed via both interfaces and recorded for `V-07`.

## Documentation Requirements
Break-glass procedure in the runbook; recorded in `DOC-05`.

## Definition of Done
Merged with the DB-level guard; NFR-S5 validation recorded.
