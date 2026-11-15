# Sensitive data inventory

**Purpose.** Every kind of sensitive data IRIS creates or processes: where it is stored, who may read it, whether it leaves the deployment, and how it is handled ([IR-824](https://citiris.atlassian.net/browse/IR-824), ASVS 4.0.3 8.3.4).

**Status.** Drafted 2026-11-15 by Claude Code at Ashlee Sean's direction, from `main` at `ca273b99`, then fact-checked against the code; corrections are in the PR. **Awaiting review by a named person**, who signs off at the end. Retention periods are [ADR-051](../adr/051-system-admin-account-deletion-and-consent.md)'s and IR-794's, and are not repeated here. What the notice tells people is IR-123's.

**What it describes.** `main` as it is. Work in open pull requests is marked **(pending)** and is not counted as done.

**How to keep it true.** `backend/apps/accounts/personal_data/registry.py` declares every Django model that relates to a person, and `test_personal_data_export.py` fails when one is added undeclared. When that test makes you declare a model, check its row here too. That test doesn't cover the AI runtime's schema (`iris_ai`), files on disk, Redis, or logs, so those rows depend on whoever changes them.

**Reading the tables.**
- *Who reads* names the rule in the API.
- **Django admin** (`/django-admin/`, `is_staff` accounts from allowlisted networks, IR-668) can read every model registered there, including `User`, `RecordFile` and `PdfExtraction` (`accounts/admin.py`, `documents/admin.py`).
- Anyone with the server reads everything (§6).

---

## 1 · Research content

The data whose leak does the most harm: an invention disclosed before filing can lose its patentability ([SECURITY.md](SECURITY.md) §1).

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Record details: title, abstract, keywords, authors, IP and ethics flags, embargo dates | PostgreSQL, `records_record` and related tables | `Record.objects.visible_to(user)` on every action: owners, the assigned Adviser, **all office staff (ITSO, IERC, KTTO, RDCO) for every record**, and every signed-in user once published. Anonymous users read nothing. A refusal is a 404 (IR-153) | Title and abstract to **Voyage** as a record vector, only past the disclosure gate (ADR-015, `apps/ai/policy/disclosure.py`). **Titles go to the mail server** in notification emails | No length limit on the abstract today; IR-926 adds 10,000 (pending). The embargo is stated per paper and released by a person (ADR-052) |
| Manuscript PDFs and supplementary files, with their original filenames | `media_files` volume, `documents/`; filenames in `records_record`, `documents_recordupload` | Only the download, manuscript and figure views, each behind `visible_to` and audited. nginx serves no `/media/` (IR-152). Django admin sees `RecordFile` | Whole PDF to **LlamaParse**, the current Extractor (ADR-056), only past the disclosure gate and admission. The uploaded file is deleted afterwards and `disable_cache` is set, but **the parse job's result stays with the vendor**: LlamaExtract later reads it by job id (`llamaextract_client.py`). ADR-067 moves extraction to **Unstructured** at IR-988 (pending) | Downloads carry a "CIT-U" watermark and **the downloader's name and email** in the footer and metadata (`records/watermark.py`, ADR-048). The reader shows an overlay naming the reader (IR-1128) |
| Extracted text, chunks, figures, formulas, overviews, briefs | PostgreSQL: `PdfExtraction` (raw vendor result), `DocumentChunk`, `ExtractionFigure`, `ExtractionFormula`, `RecordOverview`, `PaperBrief`, `ReviewText` | The paper's rule. Figures only via `GET /records/<id>/figures/<figure_id>/`. Django admin sees `PdfExtraction` | Chunk text to **Voyage** for embedding and reranking. Passages, overviews' source text, **figure images and formula crops** to an **LLM vendor** (`ai/overview`, `ai/figure_descriptions.py`, `ai/formula_transcriptions.py`) | Derived from the paper. Not in the personal-data export |
| Vectors | PostgreSQL, pgvector tables | No API returns them | Computed by **Voyage** from text that already went there | Only for papers the gate allows |
| Review text: threads, comments, findings, decisions, mentions, saved replies | PostgreSQL, `reviews_*` | `may_read_review`: the paper's reviewers and offices, and owners for what is sent to them. Drafts only to their writer; saved replies only to their owner | Decisions and notices by email (the mail server) | Review comments at most 10,000 characters |
| Document requests: messages, rejection reasons | PostgreSQL, `documents_documentrequest*` | The requesting party and the paper's owners | By email in notifications | No length limit today; IR-926 adds 10,000 (pending) |

## 2 · People

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Account: email, names, role, college, department, course, verification and lock state | PostgreSQL, `accounts_user` and profiles | The person (`/users/me/`); RDCO and the System Admin; **every signed-in user can list every Adviser's name and email** (`GET /users/advisers/`, `AdviserOptionSerializer`); others see a name where IRIS shows authorship or a reviewer | The email address to the **mail server** (SMTP, `EMAIL_HOST`) whenever IRIS emails the person | The email can't be changed by its owner (`UserSerializer` keeps it read-only) |
| Password | `accounts_user.password`, Django's default salted hash | No one; never returned | Never | **Today:** at least 8 characters, not common, not all digits (`AUTH_PASSWORD_VALIDATORS`); a reset caps it at 128. **(pending)** IR-819 raises the minimum to 12, caps all paths at 128 and adds a breached list. A change or reset ends every session (ADR-045). A reset emails a notice; a signed-in change does not yet (IR-820, pending). A password set in Django's admin ends no session and sends nothing (IR-1146) |
| Sessions | `UserSession`: id, created, last activity, ended and why. No IP or device | The person | Never | 30-minute idle expiry (IR-166) |
| Sign-in tokens | Browser `sessionStorage` (refresh) and memory; outstanding and blacklisted refresh tokens in `token_blacklist` | The person's browser | Never | Rotated, blacklisted, and bound to the account's credential version |
| Recovery and verification mail | `RecoveryIntent` (recipient address and payload **encrypted**, Fernet), `RecoveryToken` (**the email in plain text** and a SHA-256 digest of the token, never the token) | No API returns them | The link, in an email, to the **mail server** | Single use, short lived (ADR-045). Counters keyed by HMAC |
| Failed sign-ins | django-axes `AccessAttempt` (username, client address, user agent); once enabled, also `AccessLog` on every successful sign-in, because `AXES_DISABLE_ACCESS_LOG` is unset | Django admin, by any staff account with view permission | Never | **Off by default** (`AXES_ENABLED=False`, IR-865), so nothing is recorded until it is turned on (SECURITY.md §11 risk 15) |
| Throttle counters | Redis, keyed by the client address (`accounts/throttles.py`) | No API returns them | Never | Expire with their window |
| Consent and notice answers | `NoticeAnswer`; `Record.dpa_accepted_at/by`; `Record.ai_consent` | The person; RDCO for the notice | Never | Versioned notice (IR-789); DPO review still open (IR-123) |
| Profile: bio, interests, photo | PostgreSQL; the photo on the media volume | **Any signed-in user can fetch any active account's photo** (`accounts/views.py`); public profiles to signed-in users | Never | Bio at most 500 characters. The photo is `private, max-age=86400` when the request names the current version (`?v=`), else `private, no-cache` |
| Activity: papers opened, Discovery interests and dismissals, saved papers and feeds | PostgreSQL: `RecordView`, `DiscoveryInterests`, `DiscoveryDismissal`, `library_*` | The person only | Never | — |
| Reading notes and highlights | PostgreSQL, `library_*` | The person only | Never | Notes at most 20,000 characters |
| Public comments | PostgreSQL, `records_publiccomment` | Every signed-in reader of the published paper | Never | At most 2,000 characters; removed by their writer or RDCO |
| Notifications | PostgreSQL, `notifications_*` | The recipient, or members of the role a broadcast went to | **Emailed** ones send their text, record titles and RDCO notes included, to the **mail server** (`notifications/services.py`). Before sending, the subject, body and recipient sit in the **Celery broker** (Redis) as task arguments (`core/utils.py`) | Not encrypted in the broker; Redis is on `private` and needs a password (IR-669) |
| Download, delete, role and deletion requests | PostgreSQL | The person, and the people who decide them | Decisions may be emailed | Download and RDCO notes at most 500 characters. Role requests carry no note. A deletion-rejection reason has no limit today (IR-926 adds one, pending) |
| Download grants | `publication.ManuscriptWork` (a grant token) | The grantee, through the download view | Never | A credential: never exported |
| Opportunities | PostgreSQL, `opportunities_opportunity` | Every signed-in user | Never | Posted by RDCO and Advisers only |

## 3 · Ask IRIS and Paper Chat

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Questions and answers (the AI runtime, since IR-957) | PostgreSQL schema `iris_ai`: conversations, runs, journals, turns, checkpoints, handoffs. Written only by `iris_ai_runtime` | The asking reader, through a Django-issued `reader_session` grant checked inside PostgreSQL (ADR-049) | The question and the passages retrieved for it to the **LLM vendor** (`AGENT_LLM_ENDPOINT`, OpenRouter in `ai/.env.example`); search queries to **Voyage** | Retrieval is filtered by what the reader may read before anything is scored. `python -m ai.runs.purge` removes deleted accounts' conversations. **Not in the personal-data export**, which covers Django models only |
| Earlier Django conversations and runs (before IR-957) | The `Conversation`, `Turn`, `TurnCitation`, `AskRun*` and `ChatSubmission` models (app `ai`) | The owner only (others get a 404) | No longer: Django's answer path is retired (410) | Read-only. Turns are in the personal-data export; run mechanics are not |
| Provider spending | `ai_providercampaign`, `ai_providerreservation` (amounts, leases, an account fingerprint, never the key) | Operators (`manage.py provider_campaign`) | Never | No content (ADR-041) |

## 4 · Records of what happened

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Audit Log | `audit_auditevent` (actor, event, record, metadata) | The System Admin only (IR-165) | Its CSV export, downloaded by the System Admin | Written inside each act's transaction. Exempt from retention erasure (ADR-051 decision 19). Not in the personal-data export, because rows name other people |
| nginx access log | Docker `json-file` log of `frontend`, 10 MB × 3 (IR-1017) | Whoever has the server | Never, unless an operator copies it | `iris_safe`: method, path **without the query string**, status, size, and `$remote_addr`, which is **Caddy's container address**, not the client's (no `set_real_ip_from`). The retired activation links are redacted. The Caddyfile writes no access log. A deploy deletes container logs |
| Backend logs | Docker logs of `backend`, Celery and the AI services | Whoever has the server | Never, unless copied | Django raises `uvicorn.access` to INFO (`config/settings/base.py`), so these **probably hold full request paths with query strings** (searches, filter values). Not checked on the server. Recovery tokens are never logged; development keeps mail in memory |
| Error reporting | — | — | — | `sentry-sdk` is installed but not configured (`production.py`), so nothing is sent |

## 5 · Secrets

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| `SECRET_KEY`, recovery keys, database and Redis passwords, vendor API keys, the gateway's service secret | `.env`, `backend/.env`, `ai/.env` on the server, gitignored | The server's operators | Each vendor key only to its own vendor | No defaults for the required ones; the app refuses to start without them. Never committed ([SECURITY.md](SECURITY.md) §6) |

## 6 · Anyone with the server

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Everything above | The one EC2 instance: the `postgres_data` and `media_files` volumes, Redis, the `.env` files and container logs | Anyone with shell access (Session Manager, IR-1016) or the AWS account | **No backups exist** ([IR-167](https://citiris.atlassian.net/browse/IR-167); SECURITY.md §11 risk 3) | `db` and `redis` sit only on `private`, which has no route out (IR-825). `backend`, `ai-gateway`, `ai-runs-worker`, the Celery workers that call vendors, and `caddy` also join `egress`, which reaches any host. Only Caddy is published; TLS 1.2+ with HSTS (ADR-057) |

---

## Where data leaves the deployment

| Recipient | What | When | Gate |
|---|---|---|---|
| Voyage | Chunk text, titles and abstracts, search queries | Indexing; every search | Disclosure gate (IP status, embargo, consent); ADR-041 admission |
| LlamaParse (now); Unstructured after IR-988 (pending) | Whole Manuscript PDFs; the parse result stays with the vendor for LlamaExtract | Each read of a permitted paper | The same gate, checked again just before sending; admission; uploaded file deleted after |
| LLM vendors: OpenRouter for the AI runtime (`AGENT_LLM_ENDPOINT`); the `LLM_SUMMARY_*` profile for overviews and briefs; the figure and formula models | Questions and retrieved passages; paper text; figure images and formula crops | Each answer, overview, figure description, formula | Reader-scoped retrieval; the disclosure gate decided at indexing (IR-996) |
| Mail server (SMTP) | Recipient addresses; message text including record titles, RDCO notes and one-time links | Verification, recovery, notices, notifications | ADR-045 for recovery mail |
| Downloaded copies | The downloader's name and email, stamped into each PDF | Each download | `visible_to`, a download grant, the audit event |
| Certificate authority | The domain name | Certificate renewal | Caddy only |

Open conditions on these vendors (no-training evidence, retention and region in writing) are SECURITY.md §11 risks 11 and 13. LlamaParse keeping the parse result is part of risk 13.

---

## Review

| Reviewer | Date | Outcome |
|---|---|---|
| *(a named person)* | | |
