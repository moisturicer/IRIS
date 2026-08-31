# 10 — MVP Validation Tasks

Eighteen validation tasks, each with a **measurable pass/fail criterion**. Where the SRS defines a threshold and a validation method, these tasks use the SRS's own numbers rather than inventing them.

**Common fields.** To avoid repeating identical text eighteen times, these apply to every task in this document unless overridden:

- **Out of Scope:** fixing what the validation finds — failures become new tickets
- **Framework Impact:** none
- **Deployment Impact:** requires a deployed stack (`DEP-01`, `DEP-02`)
- **Definition of Done:** the procedure is executed, evidence (numbers, logs, screenshots) is attached to the ticket, the result is recorded as PASS/FAIL, and every failure is ticketed
- **Suggested Jira Type:** Task
- **Dependencies:** the implementation tasks named per row, plus a running stack

**Traceability summary**

| Task | Validates | SRS reference |
|---|---|---|
| VAL-01 | Authentication | NFR-S2, NFR-S6, FR-M1-01 |
| VAL-02 | Authorization | **NFR-S4**, NFR-S5 |
| VAL-03 | Document upload | NFR-P5, FR-M3-01 |
| VAL-04 | Document processing | **NFR-P4** |
| VAL-05 | Workflow | FR-M5-01 |
| VAL-06 | Reviewer routing | FR-M5-01, NFR-S4 |
| VAL-07 | RAG ingestion | FR-M3-02, FR-M3-03 |
| VAL-08 | RAG retrieval | FR-M4-01 |
| VAL-09 | Answer groundedness | FR-M4-01 |
| VAL-10 | Citation correctness | FR-M4-01 |
| VAL-11 | Summarization | FR-M4-02 |
| VAL-12 | AI latency | **NFR-P3** |
| VAL-13 | Frontend usability | **NFR-U1, NFR-U2** |
| VAL-14 | Accessibility | **NFR-U3** |
| VAL-15 | Concurrency | **NFR-P1, NFR-P2, NFR-R3** |
| VAL-16 | Deployment | NFR-S3, NFR-R1, NFR-S1 |
| VAL-17 | Failure recovery | **NFR-R2, NFR-R4** |
| VAL-18 | Operating cost | — (thesis viability) |

---

# VAL-01 · Validate authentication

**Objective.** Prove login, verification, lockout and session expiry behave as NFR-S2 and NFR-S6 specify.

**Problem.** Authentication has never been tested end to end. `SEC-08` identifies that NFR-S2's inactivity expiry is not met by the current design.

**Current State.** `LoginView` authenticates via `django-axes`; `AXES_FAILURE_LIMIT=3`, `AXES_COOLOFF_TIME=10min`. Access tokens last 30 minutes; refresh tokens 7 days with rotation and silent client-side refresh — so inactivity never expires a session.

**Proposed State.** All five criteria below pass on a deployed instance.

**Scope.** Registration → email verification → login → lockout → unlock → session expiry.

**Technical Approach.** Manual or scripted against a deployed stack; NFR-S2's 31-minute wait can use a mockable clock in the automated version but must be confirmed once with a real wait.

**Dependencies.** `SEC-08`, `FE-01`, `DEP-02`.

**Risks.** NFR-S2 is expected to FAIL until `SEC-08` lands — run it early to confirm the gap.

**Security Impact.** Primary evidence for two security NFRs.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if 6 consecutive failed logins for one account produce HTTP 403 on the 6th, the account shows as locked in the admin interface, and a lock event exists in the audit log (NFR-S6 validation, verbatim).
- [ ] **PASS** if authenticating, idling 31 minutes, then calling a protected endpoint returns **HTTP 401**, and the token is rejected on all subsequent requests (NFR-S2 validation, verbatim).
- [ ] **PASS** if an unverified account cannot log in (403 "Email not verified").
- [ ] **PASS** if a locked account cannot log in even with correct credentials.
- [ ] **PASS** if an administrator can unlock a locked account and the user can then log in.

**Complexity.** S · **Priority.** Critical · **Labels.** `validation`, `security`, `auth`, `nfr-s2`, `nfr-s6`

---

# VAL-02 · Validate authorization

**Objective.** Prove NFR-S4 — no user can access records above their workflow tier — using the SRS's own validation method.

**Problem.** Twelve endpoints currently lack object-level authorization. This task is the acceptance gate for `SEC-02` through `SEC-05`.

**Current State.** See `05-security-tasks.md`. Four defects exploitable by any Student account.

**Proposed State.** Every criterion passes; the run output is the NFR-S4 evidence artefact.

**Scope.** All record, document and storage endpoints, all six roles, plus the audit-log immutability check.

**Technical Approach.** Run `TEST-04`'s suite against a deployed instance, not only in CI, and capture the output.

**Dependencies.** `SEC-01`…`SEC-05`, `SEC-07`, `TEST-04`.

**Risks.** Expected to FAIL before the `SEC-0x` tasks land — run it first as a baseline.

**Security Impact.** The single most important validation in this document.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if a Student-role account calling every RDCO-restricted endpoint receives HTTP 403 **with no restricted data in any response body** (NFR-S4 validation, verbatim).
- [ ] **PASS** if `GET /api/v1/records/<id>/` for a record the user does not own and that is not published returns 404 for every non-owner, non-reviewer role.
- [ ] **PASS** if `GET /api/v1/documents/files/download-all/?record=<not mine>` returns 403.
- [ ] **PASS** if `GET /media/<known uploaded filename>` does not return the file.
- [ ] **PASS** if no user can delete another user's storage folder.
- [ ] **PASS** if an ITSO account cannot change a user's role and cannot approve at `rdco_review`.
- [ ] **PASS** if deleting an audit event via the REST API **and** via the Django admin as a superuser are both rejected at the data layer (NFR-S5 validation).

**Complexity.** M · **Priority.** Critical · **Labels.** `validation`, `security`, `rbac`, `nfr-s4`, `nfr-s5`

---

# VAL-03 · Validate document upload

**Objective.** Prove upload accepts valid PDFs, rejects oversized ones per NFR-P5, and enforces ownership.

**Problem.** `SubmitDocumentView` validates format and size but not ownership (`SEC-03`).

**Current State.** `MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024`; the view returns HTTP 400 on exceed. **NFR-P5 requires HTTP 413** and specifies rejection "at the gateway level (NGINX/Django)" — a discrepancy to resolve.

**Proposed State.** All criteria pass, including the 413 status.

**Scope.** Format validation, size limit, status code, ownership, versioning.

**Technical Approach.** Upload fixtures of 1 MB, 49 MB and 51 MB, plus a non-PDF and a PDF with a spoofed extension. Set `client_max_body_size` in nginx so the gateway rejects before Django buffers 51 MB.

**Dependencies.** `SEC-03`, `DEP-02`.

**Risks.** The 400-vs-413 discrepancy may require an nginx change or an SRS clarification.

**Security Impact.** Confirms upload injection is closed.

**Performance Impact.** Confirms a large upload does not exhaust memory.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if uploading a 51 MB PDF returns **HTTP 413** (NFR-P5 validation, verbatim).
- [ ] **PASS** if a 49 MB PDF uploads successfully.
- [ ] **PASS** if a `.docx` renamed to `.pdf` is rejected.
- [ ] **PASS** if uploading to a record the user does not own returns 403.
- [ ] **PASS** if a second upload to the same slot increments `version` to 2 and both versions remain retrievable.

**Complexity.** S · **Priority.** High · **Labels.** `validation`, `documents`, `nfr-p5`, `fr-m3-01`

---

# VAL-04 · Validate document processing

**Objective.** Prove extraction, keyword tagging and embedding complete within NFR-P4's 30-second budget.

**Problem.** Extraction currently always fails (`AI-01`); embedding never runs (`AI-03`).

**Current State.** Three-tier chain with uninstalled libraries; no queue routing; `apps.ai` models shadowed.

**Proposed State.** Full indexing completes within 30 seconds for a standard document.

**Scope.** Extraction → cleaning → FTS vector → chunking → embedding.

**Technical Approach.** NFR-P4's method verbatim: upload 5 representative research papers of ~10 MB / 10 pages each and time each from upload confirmation to embedding stored.

**Dependencies.** `AI-01` (or `AI-02`), `AI-03`, `AI-04`, `AI-05`, `BE-03`.

**Risks.** If `FW-03` selects Docling, OCR on a scanned document may exceed 30 s — measure both paths.

**Security Impact.** None.

**Performance Impact.** The subject of the task.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if all 5 sample papers complete extraction, FTS indexing and embedding **within 30 seconds each** of upload confirmation (NFR-P4 validation, verbatim).
- [ ] **PASS** if `PdfExtraction.status == "done"` with non-empty text for all 5.
- [ ] **PASS** if each document is findable by full-text search on a phrase from its body within 30 s.
- [ ] **PASS** if each has `RecordEmbedding` rows covering all its chunks.
- [ ] **PASS** if a corrupt PDF is marked `failed` with a clear error and does not block the queue.

**Complexity.** M · **Priority.** Critical · **Labels.** `validation`, `ai`, `extraction`, `nfr-p4`, `fr-m3-01`

---

# VAL-05 · Validate the workflow end to end

**Objective.** Prove all three type-differentiated routes traverse correctly from draft to terminal state.

**Problem.** The workflow is the system's core and has never been executed end to end.

**Current State.** `reviews/services.py` implements the routes; seven transitions live outside it; none is transactional.

**Proposed State.** All three routes complete; declines and resubmissions behave as specified.

**Scope.** Proposal, Thesis/Research and Project routes; decline, reject, resubmit; clearance-smart resubmission.

**Technical Approach.** Seeded accounts for each role; walk each route through the UI, then repeat via API.

**Dependencies.** `BE-01`, `WF-01`, `WF-05`, `TEST-03`.

**Risks.** Requires one account per role — use `seed_test_users`.

**Security Impact.** Confirms separation of duties holds in practice (with `VAL-06`).

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if a Proposal goes `draft → adviser_review → approved` and is publicly visible, and RDCO can then mark it `completed`.
- [ ] **PASS** if a Thesis/Research goes `draft → rdco_intake → parallel_review (IERC+KTTO) → rdco_review → published`.
- [ ] **PASS** if a Project goes `draft → rdco_intake → itso_review → parallel_review → rdco_review → published`.
- [ ] **PASS** if a record advances out of `parallel_review` **only** after every office clearance is `cleared`.
- [ ] **PASS** if a decline by IERC, followed by resubmission, resets **only** the IERC clearance and preserves KTTO's.
- [ ] **PASS** if a `rejected` record cannot be resubmitted.
- [ ] **PASS** if resubmission is refused when no new document was uploaded after the decline.

**Complexity.** M · **Priority.** Critical · **Labels.** `validation`, `workflow`, `fr-m5-01`

---

# VAL-06 · Validate reviewer routing

**Objective.** Prove each role sees exactly the records it should review, and can act on exactly those.

**Problem.** The role→stage mapping is encoded twice, independently (`WF-02`), so the queue and the authorization check can disagree.

**Current State.** `reviews/views.py:61-67` builds the queue; `reviews/services.py:76-93` authorizes the action. The adviser case already differs between them.

**Proposed State.** Queue and authorization agree for every role at every stage.

**Scope.** Pending queues for all six roles; notification delivery to the correct party.

**Technical Approach.** Create records at each stage; log in as each role; compare queue contents against expectation; attempt an action on a record **not** in the queue.

**Dependencies.** `WF-02`, `SEC-05`, `VAL-05`.

**Risks.** Requires notification email capture — use a local SMTP catcher.

**Security Impact.** Confirms `SEC-05`'s separation of duties.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if an Adviser's queue contains only `adviser_review` records where they are the assigned adviser — no others.
- [ ] **PASS** if RDCO's queue contains exactly the `rdco_intake` and `rdco_review` records.
- [ ] **PASS** if ITSO's queue contains only `itso_review` records with a pending ITSO clearance.
- [ ] **PASS** if KTTO's queue spans `itso_review` and `parallel_review` with a pending KTTO clearance.
- [ ] **PASS** if **every record in a user's queue is actionable by that user**, and every record absent from it is refused.
- [ ] **PASS** if submitting a record notifies exactly the correct party (adviser for Proposal; RDCO for Thesis/Project) and no one else.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `workflow`, `rbac`, `fr-m5-01`

---

# VAL-07 · Validate RAG ingestion

**Objective.** Prove documents are chunked and embedded completely and idempotently.

**Problem.** Ingestion does not exist. `embed_record` currently embeds only title + abstract, not the extracted full text.

**Current State.** `text_chunker.py` is `class TextChunkerService: pass`. `DocumentChunk` is a field-less stub.

**Proposed State.** Every published record's extracted text is chunked and embedded, with no gaps or duplicates.

**Scope.** Chunking coverage, embedding completeness, idempotency, re-index.

**Technical Approach.** Ingest a corpus of ~20 documents; verify chunk coverage against source length; re-run to confirm idempotency.

**Dependencies.** `AI-03`, `AI-04`, `AI-05`, `VAL-04`.

**Risks.** Chunk size and overlap affect `VAL-08` — record the values used.

**Security Impact.** Confirms only permitted content is embedded.

**Performance Impact.** Chunk count drives cost (`VAL-18`).

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if concatenating a document's chunks (removing overlap) reproduces its extracted text with no gaps.
- [ ] **PASS** if every chunk of every ingested document has a stored embedding — zero missing.
- [ ] **PASS** if re-running ingestion on an unchanged document creates **no** duplicate chunks or embeddings and makes **zero** provider calls.
- [ ] **PASS** if `POST /ai/embed/all/` indexes every record lacking embeddings and reports an accurate count (FR-M8-03).
- [ ] **PASS** if a failed embedding is recorded as `failed` in `EmbeddingJob` with an error and is retryable.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `ai`, `rag`, `fr-m3-03`

---

# VAL-08 · Validate RAG retrieval

**Objective.** Prove semantic search returns relevant results and never returns records the user may not see.

**Problem.** Retrieval does not exist. The security dimension is the critical one: retrieval must not become a bypass around every access control.

**Current State.** `vector_retriever.py` is `class VectorRetriever: pass`. The shadowed `apps/ai/views.py` loads **every** embedding and scores in Python.

**Proposed State.** Indexed pgvector retrieval, filtered by record visibility.

**Scope.** Relevance, ordering, k, and visibility filtering.

**Technical Approach.** Build a 20-query relevance set with human-judged expected documents. Then a **negative test**: a Student queries for content that exists only in another user's unpublished draft.

**Dependencies.** `AI-03`, `AI-06`, `BE-06`, `VAL-07`.

**Risks.** Relevance judgement is subjective — fix the query set and judgements before running.

**Security Impact.** **Highest in the AI section.** A retrieval leak bypasses `SEC-02` entirely.

**Performance Impact.** Retrieval latency feeds `VAL-12`.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if, for ≥80% of 20 judged queries, the expected document appears in the top 5.
- [ ] **PASS** if results are ordered by descending similarity score.
- [ ] **PASS** if **a Student's query never returns a chunk from a record they cannot see** — zero leaks across the full query set (hard fail on any).
- [ ] **PASS** if retrieval over ≥100 embedded records completes in under 200 ms.
- [ ] **PASS** if retrieval issues **one** SQL query using the `<=>` operator with `LIMIT` (verified in query logs).

**Complexity.** M · **Priority.** Critical · **Labels.** `validation`, `ai`, `rag`, `security`, `fr-m4-01`

---

# VAL-09 · Validate answer groundedness

**Objective.** Prove the chatbot answers from retrieved context and refuses when it has none.

**Problem.** An ungrounded answer in a research-integrity system is worse than no answer.

**Current State.** `AskView` returns `{"answer": None}` — retrieval without generation.

**Proposed State.** Answers are traceable to retrieved chunks; absent evidence produces an explicit refusal.

**Scope.** Groundedness, refusal behaviour, hallucination resistance.

**Technical Approach.** 20 questions in three classes: (a) answerable from the corpus, (b) plausible but absent from the corpus, (c) adversarial ("summarise the 2019 paper on X" where no such paper exists). Human-score each answer.

**Dependencies.** `AI-06`, `VAL-08`.

**Risks.** Requires human judgement — define the rubric before running.

**Security Impact.** A confident fabrication about IP status is an institutional risk.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if ≥90% of class-(a) answers are judged supported by at least one retrieved chunk.
- [ ] **PASS** if **100%** of class-(b) and class-(c) questions produce an explicit "not found in the repository" response rather than a fabricated answer (hard fail on any fabrication).
- [ ] **PASS** if no answer asserts a specific fact (author, year, finding) absent from the retrieved chunks.
- [ ] **PASS** if provider failure yields an explicit error, never a fabricated answer.
- [ ] **PASS** if querying an empty corpus returns a clear message rather than an error.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `ai`, `rag`, `groundedness`, `fr-m4-01`

---

# VAL-10 · Validate citation correctness

**Objective.** Prove every citation points to a real, relevant, permitted record.

**Problem.** Citations are the reviewer-auditability mechanism the SRS promises; a wrong citation is worse than none.

**Current State.** `AskView` returns record ids as citations with no answer.

**Proposed State.** Citations resolve, are relevant, and respect visibility.

**Scope.** Resolution, relevance, completeness, permission.

**Technical Approach.** Reuse `VAL-09`'s 20 questions; for each citation, verify the record exists, is visible to the asker, and contains the cited content.

**Dependencies.** `AI-06`, `VAL-08`, `VAL-09`.

**Risks.** None beyond judgement effort.

**Security Impact.** A citation to an invisible record leaks its existence and title even if content is withheld.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if **100%** of returned citation ids resolve to existing records (zero dangling).
- [ ] **PASS** if **100%** of citations are for records the asking user is permitted to see (hard fail on any).
- [ ] **PASS** if ≥90% of citations are judged relevant to the answer they support.
- [ ] **PASS** if every factual claim in an answer has at least one citation.
- [ ] **PASS** if citations render as working links to the record detail page.

**Complexity.** S · **Priority.** High · **Labels.** `validation`, `ai`, `rag`, `citations`, `fr-m4-01`

---

# VAL-11 · Validate summarization

**Objective.** Prove FR-M4-02's four-part structured summary is produced, accurate and persisted.

**Problem.** The endpoint returns HTTP 501.

**Current State.** `SummarizeView` returns `{"detail": "Summarization not yet implemented."}, status=501`.

**Proposed State.** Four populated sections, sourced from the record's extracted text.

**Scope.** Structure, accuracy, error handling, caching, permission.

**Technical Approach.** Summarise 10 documents; a subject reader scores each section for accuracy against the source.

**Dependencies.** `AI-07`, `VAL-04`.

**Risks.** Long documents may exceed the context window — test one deliberately.

**Security Impact.** Must respect record visibility.

**Performance Impact.** May exceed 30 s for long documents — record timings.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if all four sections (objectives, methodology, findings, conclusion) are non-empty for 10/10 documents.
- [ ] **PASS** if ≥80% of sections are judged accurate against the source by a human reader.
- [ ] **PASS** if no summary asserts a finding absent from the source (hard fail on any).
- [ ] **PASS** if a record with no completed extraction returns 404, not a fabricated summary.
- [ ] **PASS** if a user without visibility receives 403.
- [ ] **PASS** if a repeat request returns the persisted summary with **zero** provider calls.

**Complexity.** M · **Priority.** Medium · **Labels.** `validation`, `ai`, `summarization`, `fr-m4-02`

---

# VAL-12 · Validate AI latency

**Objective.** Measure chatbot response time against NFR-P3, and record whether the requirement is achievable.

**Problem.** **NFR-P3 requires a 3-second p95 for a complete response. A synchronous LLM round-trip is typically 3–10 seconds.** The requirement may be unachievable as specified — see `FW-05`.

**Current State.** No AI endpoint runs. `NFR-P3` validation: *"automated query timing test sending 20 consecutive representative natural language queries against the deployed RAG pipeline and measuring the 95th percentile response time."*

**Proposed State.** A measured p95 against whichever target `FW-05` settles on.

**Scope.** End-to-end query latency, broken down by phase.

**Technical Approach.** 20 consecutive queries, timing each. **Break the measurement down** — query embedding, retrieval, generation — so the bottleneck is evidenced rather than assumed. If streaming is chosen, also measure time-to-first-token.

**Dependencies.** `AI-06`, `FW-05`, `VAL-08`.

**Risks.** **This validation is expected to FAIL against the literal 3-second target.** Run it early: the result is the evidence `FW-05` needs to either amend the NFR or adopt streaming.

**Security Impact.** None.

**Performance Impact.** The subject of the task.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if the p95 of 20 consecutive queries is **≤ 3 seconds** (NFR-P3 as written), **or** ≤ the amended target from `FW-05` with the amendment recorded in the SRS.
- [ ] **PASS** if per-phase timings (embedding, retrieval, generation) are recorded and the bottleneck identified.
- [ ] **PASS** if, where streaming is implemented, time-to-first-token p95 is ≤ 3 seconds.
- [ ] **PASS** if a provider timeout returns HTTP 503 within the configured timeout rather than hanging.
- [ ] **FAIL and escalate to `FW-05`** if the p95 exceeds the target with no amendment recorded.

**Complexity.** S · **Priority.** Critical · **Labels.** `validation`, `ai`, `performance`, `nfr-p3`

---

# VAL-13 · Validate frontend usability

**Objective.** Meet NFR-U1 (SUS ≥ 75) and NFR-U2 (submission within 10 minutes after training).

**Problem.** No usability testing has been done, and both NFRs specify human studies with defined thresholds.

**Current State.** Feature-complete UI; `DocumentsPage` is 793 lines and `SignupPage` 457, both carrying multiple error states.

**Proposed State.** Both NFRs measured with real participants.

**Scope.** SUS survey across ≥3 role groups; timed submission task with ≥5 first-time students.

**Technical Approach.** NFR-U1 and NFR-U2 verbatim: the standard 10-question SUS (SRS Appendix B) administered within two weeks of deployment; a 1-hour onboarding then an unassisted timed submission.

**Dependencies.** A deployed, working system (`VAL-05` must pass first — you cannot usability-test a broken workflow).

**Risks.** Requires participant recruitment and ethics clearance — **start scheduling early**, this has the longest lead time of any task in the backlog.

**Security Impact.** None.

**Performance Impact.** Perceived performance affects SUS — run after `VAL-15`.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if the mean SUS score across all respondents is **≥ 75** (NFR-U1).
- [ ] **PASS** if respondents span **at least three role groups**.
- [ ] **PASS** if **all 5** first-time participants complete a full IP disclosure submission, including PDF upload and consent acknowledgment, **within 10 minutes** unassisted after a 1-hour onboarding (NFR-U2).
- [ ] **PASS** if no participant requires external assistance to complete the task.
- [ ] Qualitative friction points are recorded and ticketed regardless of pass/fail.

**Complexity.** L · **Priority.** High · **Labels.** `validation`, `usability`, `nfr-u1`, `nfr-u2`

---

# VAL-14 · Validate accessibility and responsiveness

**Objective.** Meet NFR-U3 — all core workflows usable at 360 px with no horizontal scrolling.

**Problem.** Wide data tables have no horizontal-scroll container outside `DataTable`, and icon-only buttons have no accessible name.

**Current State.** 52 `aria-*` attributes across 128 files. `DataTable`'s pagination buttons are icon-only and unlabelled. `<th>` elements lack `scope`.

**Proposed State.** NFR-U3 met; no critical `axe-core` violations on core screens.

**Scope.** Login, IP disclosure submission, RAG chatbot query, workflow status view — the four NFR-U3 names.

**Technical Approach.** NFR-U3 verbatim: Chrome DevTools emulation at 360 px **plus a physical test on a 360 px-width Android device**. Add `axe-core` for the accessibility half.

**Dependencies.** `FE-08`, ideally `FE-05`.

**Risks.** Requires a physical budget Android device per the SRS.

**Security Impact.** None.

**Performance Impact.** None.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if all four core workflows complete at 360 px with **no horizontal scrolling, no overlapping elements and no broken components** (NFR-U3 validation, verbatim).
- [ ] **PASS** if verified on both DevTools emulation **and** a physical 360 px Android device.
- [ ] **PASS** if `axe-core` reports **zero critical violations** on the four screens.
- [ ] **PASS** if every interactive control has an accessible name.
- [ ] **PASS** if every data table scrolls within its own container rather than the page.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `accessibility`, `responsive`, `nfr-u3`

---

# VAL-15 · Validate concurrency and load

**Objective.** Meet NFR-P1 (100 concurrent sessions), NFR-P2 (2 s p95) and NFR-R3 (integrity under concurrent writes).

**Problem.** No load testing has been done, and `WF-05` identifies a concurrency defect that can advance a record past an office that never cleared it.

**Current State.** `gunicorn --workers 4` (sync). Four concurrent requests per container; a fifth waits. No transaction boundaries on workflow transitions.

**Proposed State.** All three NFRs measured and met.

**Scope.** MVP-baseline load test, response-time percentiles, concurrent-write integrity.

**Technical Approach.** The SRS's methods verbatim — JMeter, **100 virtual users, 30-minute continuous duration, 5-minute ramp-up** for NFR-P1; percentile report across core routes for NFR-P2; **50 virtual users submitting PDFs simultaneously** for NFR-R3.

**Dependencies.** `WF-05`, `BE-08`, `DEP-01`, `DEP-02`.

**Risks.** Four sync workers may not sustain 100 concurrent sessions — if it fails, `DEP-04`'s `gthread` change is the first remedy, not more hardware.

**Security Impact.** NFR-R3 failures could produce records advancing without required clearances.

**Performance Impact.** The subject of the task.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if 100 virtual users over 30 minutes produce **zero crashes and sub-2-second average response throughout** (NFR-P1 validation, verbatim).
- [ ] **PASS** if the **95th-percentile** response is ≤ 2 seconds across the student portal, role dashboards, upload interface and KPI dashboard (NFR-P2).
- [ ] **PASS** if 50 simultaneous PDF submissions produce a record count **exactly matching** the number of successful upload responses, with no duplicates and no missing fields (NFR-R3 validation, verbatim).
- [ ] **PASS** if concurrent clearance submissions by two offices produce exactly two clearance rows and correct advancement.
- [ ] **PASS** if zero session failures occur under the sustained load.

**Complexity.** L · **Priority.** High · **Labels.** `validation`, `performance`, `concurrency`, `nfr-p1`, `nfr-p2`, `nfr-r3`

---

# VAL-16 · Validate deployment

**Objective.** Prove the system deploys reproducibly, serves HTTPS per NFR-S3, and encrypts data at rest per NFR-S1.

**Problem.** Neither Compose file currently builds, and the production frontend maps a port nothing listens on.

**Current State.** `ai-gateway` builds from a non-existent directory; prod maps `80:80` while nginx listens on 8080; no TLS configuration; no encryption-at-rest verification.

**Proposed State.** A clean clone deploys and serves HTTPS.

**Scope.** Clean-clone deploy, HTTPS, redirect, encryption at rest, uptime baseline.

**Technical Approach.** From a fresh clone on the target host: copy `.env.example`, set secrets, `docker compose up`, verify. NFR-S3's method: confirm HTTPS access and the port-80 redirect; certificate validity via the browser padlock.

**Dependencies.** `DEP-01`, `DEP-02`, `DEP-05`, `DEP-06`, `SEC-01`.

**Risks.** TLS via Cloudflare Tunnel differs from direct certificate management — document whichever is used.

**Security Impact.** NFR-S1 and NFR-S3 evidence.

**Performance Impact.** Baseline for NFR-R1.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if a clean clone deploys to a running stack with documented steps only, no undocumented manual fixes.
- [ ] **PASS** if the deployment URL is reachable over **HTTPS with a valid certificate** (browser padlock) and TLS ≥ 1.2 (NFR-S3).
- [ ] **PASS** if an HTTP request on port 80 redirects to HTTPS with a **301** (NFR-S3 validation, verbatim).
- [ ] **PASS** if storage volumes are confirmed mounted with encryption enabled and raw disk access without the passphrase exposes no readable data (NFR-S1 validation).
- [ ] **PASS** if `docker compose config` exits 0 for both files.
- [ ] **PASS** if uptime monitoring is deployed and reporting, establishing the NFR-R1 baseline.

**Complexity.** M · **Priority.** Critical · **Labels.** `validation`, `deployment`, `nfr-s1`, `nfr-s3`, `nfr-r1`

---

# VAL-17 · Validate failure recovery and backups

**Objective.** Meet NFR-R2 (5-minute recovery, no committed-data loss) and NFR-R4 (daily backup, RPO ≤ 24 h, verified restore).

**Problem.** No backups exist and no recovery has ever been attempted.

**Current State.** No backup configuration. `restart: unless-stopped` is set, but `backend`, `frontend` and every Celery service have **no health check**, so a wedged worker never restarts.

**Proposed State.** Both NFRs demonstrated by drill.

**Scope.** Forced-restart recovery, committed-data integrity, backup schedule, restore drill.

**Technical Approach.** The SRS's methods verbatim — NFR-R2: forced server restart **under active load**, measuring elapsed time to first successful authenticated request and verifying pre-restart committed records. NFR-R4: schedule review plus a **restoration drill on a staging instance**.

**Dependencies.** `DEP-03`, `DEP-04`.

**Risks.** **A backup that has never been restored is not a backup.** The drill is the point of the task.

**Security Impact.** Backups contain confidential IP and must be encrypted (NFR-S1).

**Performance Impact.** Backups should run off-peak.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if, after a forced restart under active load, the system serves a successful authenticated request **within 5 minutes** (NFR-R2).
- [ ] **PASS** if **all** pre-restart committed records remain intact with zero loss (NFR-R2).
- [ ] **PASS** if a `pg_dump` runs daily on schedule, evidenced by timestamped files.
- [ ] **PASS** if a **restoration drill on a staging instance** recovers all records and uploaded files intact (NFR-R4 validation, verbatim).
- [ ] **PASS** if measured RPO is ≤ 24 hours.
- [ ] **PASS** if killing the Celery worker causes an automatic restart within 60 seconds.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `reliability`, `backup`, `nfr-r2`, `nfr-r4`

---

# VAL-18 · Validate operating cost

**Objective.** Establish what IRIS costs to run per month, and confirm it is sustainable for a thesis and a low-budget deployment.

**Problem.** No cost model exists. AI usage is unmetered and uncapped — a real risk when a student's card may back the API key.

**Current State.** No token accounting, no spend cap. DRF's global `1000/day` user throttle is not a spend control. No caching of embeddings or answers, so re-indexing an unchanged document re-charges it.

**Proposed State.** A measured monthly cost with a hard ceiling in place.

**Scope.** Hosting, AI API (embedding + generation + summarization), storage growth, backup storage.

**Technical Approach.** Instrument token counts into `AuditEvent.metadata`; run a representative month of simulated usage (or extrapolate from a measured week); price against the chosen provider.

**Dependencies.** `AI-05`, `AI-06`, `FW-06`, `DEP-06`.

**Risks.** Without a cap, a loop or a misconfigured re-index can produce a large bill overnight. **The cap should be in place before the first live key**, not after this measurement.

**Security Impact.** Cost exhaustion is an availability risk.

**Performance Impact.** Caching reduces both cost and latency.

**MVP Classification.** **MVP Required**

**Pass/fail criteria**
- [ ] **PASS** if the projected monthly cost at expected usage is documented with per-component breakdown.
- [ ] **PASS** if a **per-user daily cap** on AI endpoints is enforced and demonstrated (request beyond the cap returns 429).
- [ ] **PASS** if token counts per request are recorded in the audit log.
- [ ] **PASS** if re-indexing an unchanged document makes **zero** provider calls (embedding cache).
- [ ] **PASS** if a repeat summarization makes **zero** provider calls.
- [ ] **PASS** if the projected monthly cost is within the budget recorded in `DEP-06`'s ADR.
- [ ] **PASS** if a documented ceiling exists beyond which AI features degrade gracefully rather than billing without limit.

**Complexity.** M · **Priority.** High · **Labels.** `validation`, `cost`, `ai`, `sustainability`
