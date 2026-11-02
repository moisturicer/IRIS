# Security

**Purpose.** How IRIS protects institutional research and IP data, and what is still open.
**Owns.** Authentication, authorization, file access, API security, secrets, boundaries, external AI, privacy, audit, dependencies, and the open risk list.
**Does not own.** The authorization decision ([ADR-009](../adr/009-authorization-model.md)) · the threat model and ASVS checklist ([IR-617](https://citiris.atlassian.net/browse/IR-617)) · process ([`../engineering/SDLC.md`](../engineering/SDLC.md)).
**Authority.** Authoritative for security posture and known defects.
**Update when.** A control changes, a defect is found or closed, or a boundary moves.
**Checked against.** `main` on 2026-11-02. Every statement about behaviour below was read from the code that day.

> **A separate risk register is not maintained.** §11 is the register, and §12 lists what has closed.

---

## 1 · What is being protected

Unpublished research, IP disclosures before filing, ethics submissions, and personal data of students, advisers and reviewers. **A disclosure leak before filing can destroy patentability**, so the consequence is legal and irreversible, not only reputational.

Under RA 10173 (Data Privacy Act), personal data in submissions and consent records is in scope.

---

## 2 · Authentication

JWT through SimpleJWT, with rotation and blacklist after rotation.

| Control | How it works today |
|---|---|
| Access token | 30 minutes by default |
| Refresh token | 7 days by default, the absolute limit on a session. Used once, then blacklisted. Only the refresh token is stored in the browser, in `sessionStorage` (`frontend/src/lib/authStorage.ts`) |
| Refresh in the client | `refreshOnce` shares one refresh between concurrent 401s, and the new pair goes through `setTokens` (`frontend/src/api/client.ts`) |
| Inactivity | A session idle for 30 minutes is ended on the server for good, and polling doesn't count as activity ([IR-166](https://citiris.atlassian.net/browse/IR-166), `apps/accounts/sessions.py`) |
| Failed sign-ins | `django-axes` locks a username and client address pair after 3 failures for 10 minutes by default, answering 429 with `unlock_at`. The address comes from `TRUSTED_PROXY_COUNT`, so it is the real client behind nginx ([IR-656](https://citiris.atlassian.net/browse/IR-656)) |
| Manual lock | `User.is_locked`, set by an administrator. It never lifts on its own and ends the person's sessions at once ([IR-644](https://citiris.atlassian.net/browse/IR-644)) |
| Password change or reset | Ends every session and revokes unused reset links. API passwords meet `AUTH_PASSWORD_VALIDATORS` ([IR-644](https://citiris.atlassian.net/browse/IR-644)) |
| Session revoke | An administrator's revoke ends the session, so its access token stops working on the next request ([IR-657](https://citiris.atlassian.net/browse/IR-657)) |
| Rate limits | Sign-in 300/hour and registration 60/hour per client address, by default ([IR-661](https://citiris.atlassian.net/browse/IR-661), merged and awaiting review) |
| Password recovery | Self-service by email, [ADR-045](../adr/045-account-recovery-contract.md) ([IR-642](https://citiris.atlassian.net/browse/IR-642)) |
| Registration | Accepts any email domain. **Open:** [IR-660](https://citiris.atlassian.net/browse/IR-660) |
| Sign-in audit | Refused sign-ins of locked or unverified accounts, lockouts, registration and activation leave no audit row. **Open:** [IR-659](https://citiris.atlassian.net/browse/IR-659) |
| SSO and MFA | **Deliberately deferred**, not a gap: they need CIT-U IT to provide an identity provider ([IR-652](https://citiris.atlassian.net/browse/IR-652)) |

---

## 3 · Authorization

Governed by [ADR-009](../adr/009-authorization-model.md).

- **Record visibility** is one predicate, `Record.objects.visible_to(user)`, applied on every `RecordViewSet` action and inside RAG retrieval. A refused record answers 404, the same as a missing one ([IR-153](https://citiris.atlassian.net/browse/IR-153)).
- **Document endpoints** resolve their record through `authorize_record_documents()` ([IR-153](https://citiris.atlassian.net/browse/IR-153)).
- **Authorization reads the application role only.** The `is_staff` bypass is gone ([IR-165](https://citiris.atlassian.net/browse/IR-165)).
- **The route matrix** in `apps/tests/access/` declares every URLconf route, with no pending exemption ([IR-615](https://citiris.atlassian.net/browse/IR-615), [IR-616](https://citiris.atlassian.net/browse/IR-616)).
- **`apps/storage`** and its unauthorized endpoints were deleted ([IR-62](https://citiris.atlassian.net/browse/IR-62)).

### Who holds administrator powers

`ADMIN_ROLES` is `{RDCO}`, so **RDCO holds them**: accounts, locks, sessions, system settings and the Audit Log. [ADR-051](../adr/051-system-admin-account-deletion-and-consent.md) accepts a separate System Admin role, and it isn't built yet ([IR-781](https://citiris.atlassian.net/browse/IR-781)).

Django's admin site is separate. It is guarded by Django's own `is_staff` flag, and §7 describes its exposure.

---

## 4 · File and document access

Files are served only through Django views that authorize the reader and write a `DOWNLOAD` audit event: `RecordUploadDownloadView`, `RecordFileDownloadView` and `RecordFileDownloadAllView`. There is no public `/media/` route in nginx, in the production web container or in Django ([IR-152](https://citiris.atlassian.net/browse/IR-152)).

If download throughput ever matters, the answer is `X-Accel-Redirect`, where nginx serves the bytes and Django still authorizes. It is never a public alias.

- **Uploads:** a file is accepted only if it opens as a PDF with at least one page ([IR-665](https://citiris.atlassian.net/browse/IR-665)). **Uploads aren't scanned for malware. Open:** [IR-666](https://citiris.atlassian.net/browse/IR-666).
- **Manuscript downloads:** an approved request becomes a time-limited grant, 30 days by default, used while signed in. No link is emailed ([IR-675](https://citiris.atlassian.net/browse/IR-675)).
- **Downloaded copies:** each carries a footer naming the downloader, a diagonal "CIT-U" background and matching PDF metadata ([IR-676](https://citiris.atlassian.net/browse/IR-676)).

---

## 5 · API security

- Endpoints require authentication except those a signed-out person needs, such as login, registration, activation and recovery. Each route's rule is declared in the matrix (§3).
- 404 and 403 must be indistinguishable for a record the user may not see, because a 403 confirms the record exists.
- Result counts must be computed after visibility filtering.
- Responses carry Referrer-Policy, nosniff and X-Frame-Options ([IR-663](https://citiris.atlassian.net/browse/IR-663)). **The Content-Security-Policy is report-only**, so it reports violations and blocks nothing until the manual walk-through recorded in `TRACEABILITY.md` passes.
- Production trusts the proxy's scheme header and redirects to HTTPS without a loop ([IR-662](https://citiris.atlassian.net/browse/IR-662)).

---

## 6 · Secrets and configuration

- `SECRET_KEY` and the database credentials are required, and Django refuses to start without them ([IR-154](https://citiris.atlassian.net/browse/IR-154)).
- Production also requires `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and `TRUSTED_PROXY_COUNT`, and `config/settings/validation.py` refuses `DEBUG`, a `*` host or allow-all CORS ([IR-154](https://citiris.atlassian.net/browse/IR-154)).
- System settings are read and changed only by administrators, and each change writes an audit event ([IR-667](https://citiris.atlassian.net/browse/IR-667)).
- `backend/.env.example` documents the keys and holds no real values.
- CI's `Security` job runs gitleaks, `pip-audit`, `npm audit`, bandit and semgrep under a high/critical gate with a reviewed allowlist, `security/allowlist.yml` ([IR-613](https://citiris.atlassian.net/browse/IR-613), [IR-614](https://citiris.atlassian.net/browse/IR-614), [IR-633](https://citiris.atlassian.net/browse/IR-633)).

---

## 7 · Boundaries

**Production** (`docker-compose.prod.yml`) publishes only `frontend`. `db`, `redis`, `backend`, `docling`, `ai-gateway` and the Celery services stay on the Compose network. Redis requires a password ([IR-669](https://citiris.atlassian.net/browse/IR-669)).

**Development** (`docker-compose.yml`) publishes Postgres and Redis on `127.0.0.1` only, and Redis requires a password ([IR-669](https://citiris.atlassian.net/browse/IR-669)). `backend`, `frontend` and `docling` are still published on every interface (§11).

**TLS.** nginx listens on plain 8080 and takes the scheme from the proxy in front of it, so TLS must end upstream. This repository doesn't configure that proxy (§11).

**Django admin.** nginx closes `/django-admin/` except to `DJANGO_ADMIN_ALLOWED_NETWORKS` ([IR-668](https://citiris.atlassian.net/browse/IR-668)), but **Django still serves its admin at `/admin/`, which nginx leaves open**, because that path also carries IRIS's own pages. The allowlist protects the admin only once [IR-782](https://citiris.atlassian.net/browse/IR-782) moves it.

**`ai-gateway`** is adopted by [ADR-014](../adr/014-ai-gateway-as-a-service.md) under preconditions. It sets no CORS, publishes no port and refuses any request without the shared service secret (`ai/main.py`). **It still receives `DATABASE_URL`**, against ADR-014's "no direct DB access" (§11).

**Tenancy** is one instance per tenant ([ADR-005](../adr/005-instance-per-tenant.md)). Each institution gets its own database and media volume, so a missing tenant filter can't leak across institutions.

---

## 8 · External AI services

[ADR-015](../adr/015-voyage-embedding-and-reranking.md) sends chunk text to Voyage, and it dropped the earlier written sign-off precondition on 2026-09-04. Its remaining conditions:

1. **A disclosure check before sending.** `apps/ai/policy/disclosure.py` refuses on IP status, embargo state and missing consent. An Unknown embargo is refused, and nothing yet sends an embargo answer, so **new submissions stay refused until [IR-250](https://citiris.atlassian.net/browse/IR-250) finishes**.
2. **Voyage's training opt-out**, an account setting. The repository can't show whether it was exercised (§11).
3. **`VOYAGE_API_KEY` as a production secret.**

IR-317's development bypass is deleted ([IR-815](https://citiris.atlassian.net/browse/IR-815)), and the indexing path no longer accepts a substitute for the check. Test papers get an answer instead: `load_corpus --clear-for-ai` and `mark_corpus_cleared` refuse with `DEBUG` off, and `--force` doesn't change that. Neither answers for a paper declared `institutional`, but neither can recognise a real paper whose origin was never declared, so they depend on `DEBUG` and on who runs them. `seed_demo` answers only for its own synthetic papers, whose text it wrote.

`apps/ai/policy/outbound.py` rechecks withheld or revoked sources before each provider attempt ([IR-720](https://citiris.atlassian.net/browse/IR-720), partially implemented and awaiting review). Retrieval is filtered by `visible_to(user)` before anything is scored.

---

## 9 · Privacy

- **Consent at submission:** `Record.dpa_accepted_at` and `dpa_accepted_by` are stamped by `RecordViewSet.submit` alone. They record who and when, **not the IP address**, and no serializer can write them.
- **Consent at signup:** `User.consent_given` is a separate boolean.
- **Consent has no version and can't be withdrawn.** **Open:** [IR-789](https://citiris.atlassian.net/browse/IR-789), [IR-791](https://citiris.atlassian.net/browse/IR-791).
- **The notice itself** needs DPO review, and existing consent needs re-collecting. **Open:** [IR-123](https://citiris.atlassian.net/browse/IR-123).
- **Account deletion, a copy of one's data and retention** are accepted in ADR-051 and not built. **Open:** [IR-785](https://citiris.atlassian.net/browse/IR-785), [IR-786](https://citiris.atlassian.net/browse/IR-786), [IR-794](https://citiris.atlassian.net/browse/IR-794).

Research artefacts aggregate; they do not copy institutional records.

---

## 10 · Audit

`AuditEvent` covers authentication, files, accounts, settings, recovery, download requests and the workflow. Workflow events are written inside each act's transaction ([IR-144](https://citiris.atlassian.net/browse/IR-144), `apps/audit/workflow.py`), with no backfill for earlier acts.

A PostgreSQL trigger refuses every changing UPDATE and every DELETE ([IR-166](https://citiris.atlassian.net/browse/IR-166), `audit/0005_auditevent_insert_only`). TRUNCATE isn't caught, and a table owner can drop the trigger by a deliberate migration.

Only administrators read the log (`apps/audit/views.py`, §3).

---

## 11 · Open risks

Severity is this document's estimate. [IR-617](https://citiris.atlassian.net/browse/IR-617)'s threat model is where it gets reviewed.

| # | Risk | Severity | Why | Closed by |
|---|---|---|---|---|
| 1 | Django's admin is reachable from the internet at `/admin/`, guarded only by `is_staff`, with no MFA | **High** | One stolen staff password opens a separate path to the database | [IR-782](https://citiris.atlassian.net/browse/IR-782), then [IR-668](https://citiris.atlassian.net/browse/IR-668)'s allowlist applies (spec [IR-655](https://citiris.atlassian.net/browse/IR-655)) |
| 2 | Uploads aren't scanned for malware | **High** | A hostile file reaches the parser and the people who download it | [IR-666](https://citiris.atlassian.net/browse/IR-666) (spec [IR-654](https://citiris.atlassian.net/browse/IR-654)) |
| 3 | No backups and no rehearsed restore | **High** | A lost disk loses records that can't be recreated | [IR-167](https://citiris.atlassian.net/browse/IR-167) (parent [IR-151](https://citiris.atlassian.net/browse/IR-151)) |
| 4 | TLS is configured but hasn't run on a deployed domain, and HSTS isn't confirmed for one | **High** | Passwords, tokens and unpublished work could be read in transit until it has | [IR-847](https://citiris.atlassian.net/browse/IR-847), [IR-806](https://citiris.atlassian.net/browse/IR-806) |
| 5 | Security-relevant sign-in events leave no audit row | **Medium** | Password guessing leaves nothing to investigate | [IR-659](https://citiris.atlassian.net/browse/IR-659) (spec [IR-652](https://citiris.atlassian.net/browse/IR-652)) |
| 6 | Registration accepts any email domain | **Medium** | Anyone can get a signed-in account | [IR-660](https://citiris.atlassian.net/browse/IR-660) (spec [IR-652](https://citiris.atlassian.net/browse/IR-652)) |
| 7 | One office holds workflow and system administration powers together | **Medium** | One compromised account reaches both sets of powers | [IR-781](https://citiris.atlassian.net/browse/IR-781) (spec [IR-779](https://citiris.atlassian.net/browse/IR-779)) |
| 8 | Consent has no version and can't be withdrawn, and the notice lacks DPO review | **Medium** | RA 10173 duties stay unmet once real people's data is held | [IR-789](https://citiris.atlassian.net/browse/IR-789), [IR-791](https://citiris.atlassian.net/browse/IR-791), [IR-123](https://citiris.atlassian.net/browse/IR-123) |
| 9 | No account deletion, personal data copy or retention job | **Medium** | RA 10173 duties stay unmet once real people's data is held | [IR-785](https://citiris.atlassian.net/browse/IR-785), [IR-786](https://citiris.atlassian.net/browse/IR-786), [IR-794](https://citiris.atlassian.net/browse/IR-794) (spec [IR-779](https://citiris.atlassian.net/browse/IR-779)) |
| 10 | `ai-gateway` still receives `DATABASE_URL` | **Medium** | A compromised gateway could read records past Django's visibility rule | [IR-826](https://citiris.atlassian.net/browse/IR-826) |
| 11 | Voyage's training opt-out has no recorded evidence | **Medium** | Nothing shows the vendor isn't training on unpublished text | [IR-827](https://citiris.atlassian.net/browse/IR-827) |
| 12 | The ASVS checklist is a draft awaiting review | **Medium** | Its statuses come from reading code, and nobody has confirmed them | [IR-617](https://citiris.atlassian.net/browse/IR-617) (spec [IR-611](https://citiris.atlassian.net/browse/IR-611)) |

[`SECURITY_CHECKLIST.md`](../testing/SECURITY_CHECKLIST.md) lists further Level 1 gaps: [IR-819](https://citiris.atlassian.net/browse/IR-819), [IR-820](https://citiris.atlassian.net/browse/IR-820), [IR-821](https://citiris.atlassian.net/browse/IR-821), [IR-822](https://citiris.atlassian.net/browse/IR-822), [IR-823](https://citiris.atlassian.net/browse/IR-823), [IR-824](https://citiris.atlassian.net/browse/IR-824), [IR-825](https://citiris.atlassian.net/browse/IR-825).

**Deferred deliberately:** SSO and MFA, until CIT-U IT provides an identity provider ([IR-652](https://citiris.atlassian.net/browse/IR-652)).

**Fails closed until finished:** the embargo answer. Unanswered records are refused for AI use until [IR-250](https://citiris.atlassian.net/browse/IR-250) is complete, so this delays RAG and leaks nothing.

---

## 12 · Closed

| Was | Closed by |
|---|---|
| Every uploaded document publicly readable through `/media/` | [IR-152](https://citiris.atlassian.net/browse/IR-152) |
| Any signed-in user could read any record, and document endpoints had no ownership check | [IR-153](https://citiris.atlassian.net/browse/IR-153) |
| Hardcoded credentials, permissive CORS, unset `ALLOWED_HOSTS` | [IR-154](https://citiris.atlassian.net/browse/IR-154) |
| The `is_staff` bypass, and the Audit Log open to every office | [IR-165](https://citiris.atlassian.net/browse/IR-165) |
| No inactivity expiry, and an audit log that could be changed | [IR-166](https://citiris.atlassian.net/browse/IR-166) |
| `apps/storage` endpoints with no authorization | [IR-62](https://citiris.atlassian.net/browse/IR-62) |
| Locking an account or changing a password left sessions running | [IR-644](https://citiris.atlassian.net/browse/IR-644) |
| Lockout counted the proxy's address, not the client's | [IR-656](https://citiris.atlassian.net/browse/IR-656) |
| A revoked session's access token kept working | [IR-657](https://citiris.atlassian.net/browse/IR-657) |
| CI didn't run `ai/tests`, including the gateway's service authentication test | [IR-844](https://citiris.atlassian.net/browse/IR-844) |
| Development `backend`, `frontend` and `docling` listened on every interface | [IR-828](https://citiris.atlassian.net/browse/IR-828) |
| Production HTTPS redirect loop behind the proxy | [IR-662](https://citiris.atlassian.net/browse/IR-662) |
| No browser security headers | [IR-663](https://citiris.atlassian.net/browse/IR-663) |
| Uploads accepted without checking the content was a PDF | [IR-665](https://citiris.atlassian.net/browse/IR-665) |
| System settings not limited to administrators or audited | [IR-667](https://citiris.atlassian.net/browse/IR-667) |
| Manuscript downloads without a time-limited, signed-in grant | [IR-675](https://citiris.atlassian.net/browse/IR-675) |
| Downloaded manuscripts didn't identify the downloader | [IR-676](https://citiris.atlassian.net/browse/IR-676) |
| No authorization matrix across every route | [IR-615](https://citiris.atlassian.net/browse/IR-615), [IR-616](https://citiris.atlassian.net/browse/IR-616) |

---

## 13 · Reporting a vulnerability

Report privately to the team lead. Do not open a public issue. Include what you found, how to reproduce it, and what it exposes. During the pilot, a vulnerability affecting real institutional data is escalated immediately and the instance is taken offline if disclosure is ongoing.
