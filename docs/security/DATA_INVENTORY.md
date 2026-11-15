# Sensitive data inventory

**Purpose.** Every kind of sensitive data IRIS creates or processes: where it is stored, who may read it, whether it leaves the deployment, and how it is handled ([IR-824](https://citiris.atlassian.net/browse/IR-824), ASVS 4.0.3 8.3.4).

**Status.** Drafted 2026-11-15 by Claude Code at Ashlee Sean's direction, from `main` at `ca273b99`. **Awaiting review by a named person**, who signs off at the end. Retention periods are [ADR-051](../adr/051-system-admin-account-deletion-and-consent.md)'s and IR-794's, and aren't repeated here. What the notice tells people is IR-123's.

**How to keep it true.** `backend/apps/accounts/personal_data/registry.py` declares every Django model that relates to a person, and `test_personal_data_export.py` fails when one is added undeclared. When that test makes you declare a model, check its row here too. That test doesn't cover the AI runtime's own schema (`iris_ai`), files on disk, or logs, so those rows depend on whoever changes them.

**Reading the tables.**
- *Who reads* names the API rule, not the database. Anyone with database or server access reads everything, so that sits in its own row at the end.
- *Leaves* lists every place the data goes outside the one IRIS server.

---

## 1 · Research content

The data whose leak does the most harm: an unpublished invention disclosed before filing can lose its patentability ([SECURITY.md](SECURITY.md) §1).

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Record details: title, abstract, keywords, authors, IP flags, embargo | PostgreSQL, `records_record` and related tables | `Record.objects.visible_to(user)` on every action: owners, the assigned Adviser, office staff holding the review, everyone once published. A refusal is a 404 (IR-153) | Title and abstract go to **Voyage** as a record vector, only when the disclosure gate passes (ADR-015, `apps/ai/policy/disclosure.py`) | Abstract at most 10,000 characters (IR-926). Embargo stated per paper and released by a person (ADR-052) |
| Manuscript PDFs and supplementary files | `media_files` volume, `documents/` | Only `RecordUploadDownloadView`, `RecordFileDownloadView` and the manuscript and figure views, each behind `visible_to` and audited. nginx serves no `/media/` (IR-152) | Whole PDF to **LlamaParse** while it is the Extractor (ADR-056), and to **Unstructured** after IR-988 (ADR-067), only past the disclosure gate and admission. The uploaded file is deleted afterwards and `disable_cache` is set | Downloads carry a "CIT-U" watermark drawn over the content, and the reader an overlay naming the reader (IR-1127, IR-1128, ADR-048) |
| Extracted text, chunks, figures, formulas, overviews, briefs | PostgreSQL: `PdfExtraction` (raw vendor result), `DocumentChunk`, `ExtractionFigure`, `RecordOverview`, `PaperBrief` | The same rule as the paper. Figures only via `GET /records/<id>/figures/<figure_id>/` | Chunk text to **Voyage** for embedding and reranking. Passages to the **LLM vendor** when they answer a question or write an overview | Derived from the paper. Not in the personal-data export (registry: "made by the system from a paper's text") |
| Vectors | PostgreSQL, pgvector tables (`ChunkEmbedding`, `RecordEmbedding`, `RecordSpaceEmbedding`) | No API returns them | Computed by **Voyage** from text that already went there | Only for papers the gate allows |
| Review text, threads, comments, findings, decisions | PostgreSQL, `reviews_*`, `records_reviewtext` | `may_read_review`: the paper's reviewers and the offices on it, and owners for what is sent to them. Drafts only to their writer | Nothing | Must fix / Suggestion threads, drafts sent on Finish review (ADR-032) |

## 2 · People

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Account: email, names, role, college, department, course, verification and lock state | PostgreSQL, `accounts_user` and profiles | The person (`/users/me/`); RDCO and the System Admin for administration; other users see a name where IRIS shows authorship or a reviewer | Email address to the **mail server** (SMTP, `EMAIL_HOST`) whenever IRIS emails the person | The email can't be changed by its owner (`UserSerializer` keeps it read-only) |
| Password | PostgreSQL, `accounts_user.password`, as Django's salted hash | No one; never returned | Never | 12 to 128 characters, not common or breached (IR-819, once merged). Changing or resetting it ends every session and notifies the owner (ADR-045, IR-820) |
| Sessions | PostgreSQL, `UserSession`: id, created, last activity, ended and why. No IP or device | The person | Never | Ended on password change or reset; 30-minute idle expiry (IR-166) |
| Sign-in tokens | Browser memory and storage; refresh tokens in `token_blacklist` tables | The person's browser | Never | Rotated and blacklisted, and bound to the account's credential version |
| Recovery and verification mail | PostgreSQL, `RecoveryIntent`, `RecoveryToken` | No API returns them | The link, in an email, to the **mail server** | The recipient address and raw token are stored only encrypted (Fernet, `RECOVERY_MAIL_ENCRYPTION_KEY`); counters keyed by HMAC. Single use, short lived (ADR-045) |
| Failed sign-ins | PostgreSQL, django-axes `AccessAttempt` (username, client address, user agent) | Django superusers only | Never | **Lockout is off by default** (`AXES_ENABLED=False`, IR-865), so nothing is recorded until it is turned on (SECURITY.md §11 risk 15) |
| Consent and notice answers | PostgreSQL, `NoticeAnswer`; `Record.dpa_accepted_at/by`; `Record.ai_consent` | The person; RDCO for the notice | Never | Versioned notice (IR-789); DPO review still open (IR-123) |
| Profile: bio, interests, photo | PostgreSQL; the photo on the media volume | Any signed-in user on a public profile | Never | Bio at most 500 characters. The photo is served privately with a day-long private cache |
| Library: saved papers, reading notes, highlights | PostgreSQL, `library_*` | The person only | Never | Notes at most 20,000 characters |
| Notifications | PostgreSQL, `notifications_*` | The recipient, or members of the role a broadcast went to | Some are also emailed: the text to the **mail server** | — |
| Download and delete requests, role requests, deletion requests | PostgreSQL | The person, and the people who decide them | Decisions may be emailed | Notes at most 500 characters |

## 3 · Ask IRIS and Paper Chat

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Questions and answers (the AI runtime, since IR-957) | PostgreSQL schema `iris_ai`: conversations, runs, journals, turns, checkpoints, handoffs. Written only by `iris_ai_runtime` | The asking reader, through a Django-issued `reader_session` grant checked inside PostgreSQL (ADR-049) | The question and the passages retrieved for it to the **LLM vendor** (`AGENT_LLM_ENDPOINT`, OpenRouter in `ai/.env.example`). The query to **Voyage** for search embeddings | Retrieval is filtered by what the reader may read before anything is scored. `python -m ai.runs.purge` removes deleted accounts' conversations. **Not in the personal-data export**, which covers Django models only |
| Earlier Django conversations (before IR-957) | PostgreSQL, `ai_conversation`, `ai_turn`, `ai_turncitation` | The owner only (others get a 404) | No longer: Django's answer path is retired (410) | Read-only; in the personal-data export |
| Provider spending | PostgreSQL, `ai_providercampaign`, `ai_providerreservation` | Operators (`manage.py provider_campaign`) | Never | No content, only amounts and leases (ADR-041) |

## 4 · Records of what happened

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Audit Log | PostgreSQL, `audit_auditevent` (actor, event, record, metadata) | The System Admin only (IR-165) | Its CSV export, downloaded by the System Admin | Written inside each act's transaction. Exempt from retention erasure (ADR-051 decision 19). Not in the personal-data export, because rows name other people |
| Web server logs | Docker `json-file` logs of `caddy` and `frontend`, 10 MB × 3 per service (IR-1017) | Whoever has the server | Never, unless an operator copies them | nginx logs client address, method, path **without query strings**, status and size (`iris_safe`), and redacts the retired activation links. A deploy deletes container logs |
| Application logs | Docker logs of `backend`, Celery and the AI services | Whoever has the server | Never, unless copied | Recovery tokens are never logged; development keeps mail in memory so links can't reach a log |

## 5 · Secrets

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| `SECRET_KEY`, recovery keys, database and Redis passwords, vendor API keys, the gateway's service secret | `.env`, `backend/.env`, `ai/.env` on the server, gitignored | The server's operators | Each vendor key only to its own vendor | No defaults; the app refuses to start without the required ones. Never committed ([SECURITY.md](SECURITY.md) §6) |

## 6 · Anyone with the server

| Data | Stored | Who reads | Leaves | Handling |
|---|---|---|---|---|
| Everything above | The one EC2 instance: the `postgres_data` and `media_files` volumes, the `.env` files and container logs | Anyone with shell access, through Session Manager (IR-1016), or with the AWS account | **No backups exist** ([IR-167](https://citiris.atlassian.net/browse/IR-167); SECURITY.md §11 risk 3) | `private` network with no route out (IR-825); only Caddy is published; TLS 1.2+ with HSTS (ADR-057) |

---

## Where data leaves the deployment

| Recipient | What | When | Gate |
|---|---|---|---|
| Voyage | Chunk text, titles and abstracts, search queries | Indexing; every search | Disclosure gate (IP status, embargo, consent); ADR-041 admission |
| LlamaParse (now), Unstructured (after IR-988) | Whole Manuscript PDFs | Each read of a permitted paper | The same gate, checked again just before sending; admission; file deleted after |
| LLM vendor (OpenRouter for the AI runtime; `LLM_BASE_URL` for Django's overviews and briefs) | Questions; retrieved passages; paper text for overviews | Each answer; each overview | Reader-scoped retrieval; the disclosure gate decided at indexing (IR-996) |
| Mail server (SMTP) | Recipient address; the message, including one-time links | Verification, recovery, notices, notifications | ADR-045 for recovery mail |
| Certificate authority | The domain name | Certificate renewal | — |

Open conditions on these vendors (no-training evidence, retention and region in writing) are SECURITY.md §11 risks 11 and 13.

---

## Review

| Reviewer | Date | Outcome |
|---|---|---|
| *(a named person)* | | |
