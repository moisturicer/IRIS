# Requirements Traceability

This file says where each requirement stands. Each row's history and evidence are in [`traceability/`](traceability/), and [ADR-055](../adr/055-traceability-evidence-lives-in-one-file-per-ticket.md) says why.

## Adding evidence

Add `traceability/IR-XXX.md` for your ticket, and name the requirements it affects:

```markdown
# IR-XXX: what changed

**Requirements:** FR-M3-02

What was done, what ran, and what the result was.
```

Change a row here only when the requirement's status changes. To see every note on a requirement, run `git grep -l FR-M3-02 docs/testing/traceability`.

## Status vocabulary

| Status | Means |
|---|---|
| **VERIFIED** | Implemented, tested, evidence recorded and linked |
| **IMPLEMENTED** | Code exists, **no test evidence** — not complete |
| **PARTIAL** | Some of the requirement is met |
| **STUBBED** | Placeholder exists, does not function |
| **NOT STARTED** | No implementation |
| **DEFERRED** | Formally descoped, with an ADR or SRS amendment |
| **BLOCKED** | Cannot proceed — reason recorded |

> **A requirement is never marked VERIFIED because source code exists.** IMPLEMENTED is the ceiling until a test demonstrates it and the evidence is linked.

---

## Current position

**Almost nothing in IRIS is VERIFIED.** A pytest harness landed with IR-82 and the `apps/ai` extraction and chunking work now carries tests, so the blanket "there are no automated tests" that stood here is no longer true. Tests now also exist outside `apps/ai` — `apps/accounts`, `apps/documents`, `apps/opportunities`, `apps/records`, `config`, and the authorization matrix in `apps/tests` — so the "everything outside `apps/ai` has no test evidence" that stood here is corrected. This table records the honest position; it is not a to-do list disguised as a status report.

> **CI evidence dated before 2026-09-06 does not mean the test ran.** The workflow executed `pytest` with no database service, and `conftest.py` skips every `TransactionTestCase` — which DRF's `APITestCase` is — when Postgres is unreachable. Every database-backed test in the repo was collected, skipped, and reported green. IR-165 added the service; IR-163 made a wholesale skip fail the run rather than pass it. **Treat any "CI green" evidence in the rows below that predates those two as unverified**, and re-establish it from a run that provably executed. This is recorded rather than swept, per the source-of-truth rule.

> **Labels (IR-97, 2026-11-02):** every `FR-` and `NFR-` label used in the ADRs, code and engineering docs has one row. Labels found only in the frozen SRS have none.
>
> **This document is itself out of date in places** and its header still names `../SRS.md` as the baseline, which [`../../CLAUDE.md`](../../CLAUDE.md) has since frozen in favour of `docs/adr/`. Recorded rather than silently reconciled, per the source-of-truth rule. Rows below are corrected as the work that touches them lands, not in one sweep.

| Req | Requirement | Details | Status |
|---|---|---|---|
| FR-M2-01 | Record submission | [details](traceability/FR-M2-01.md) | **IMPLEMENTED** |
| FR-M2-02/03 | Download and delete request queues | [details](traceability/FR-M2-02-03.md) | **PARTIAL** |
| FR-M2-04 | Bulk import from a template | [details](traceability/FR-M2-04.md) | **IMPLEMENTED** |
| FR-M3-01 | PDF text extraction | [details](traceability/FR-M3-01.md) | **IMPLEMENTED** |
| **IR-116** | End-to-end ingestion on a real thesis — its exit criterion (fifty chunks from a real submission, read by a person) | [details](traceability/IR-116.md) | **IMPLEMENTED** |
| **IR-290** | Formulas recovered as LaTeX — extends FR-M3-01 (stable label only, per the frozen-SRS rule) | [details](traceability/IR-290.md) | **PARTIAL** |
| **IR-367** | Docling's `do_ocr`/`table_mode`/`do_formula_enrichment` become settings, not a hardcoded dict — extends FR-M3-01 (stable label only, per … | [details](traceability/IR-367.md) | **IMPLEMENTED** |
| **IR-313** | Bulk-load a corpus of PDFs from a directory | [details](traceability/IR-313.md) | **IMPLEMENTED** |
| **IR-315** | Staff bulk-import legacy records from an `.xlsx`/`.xls` sheet (`POST /records/import_excel/`) | [details](traceability/IR-315.md) | **IMPLEMENTED** |
| **IR-637** | An Excel import row is all-or-nothing: its Record, primary owner and authors are saved together or not at all | [details](traceability/IR-637.md) | **IMPLEMENTED** |
| **IR-638** | A cell value the system cannot accept skips its import row and says why | [details](traceability/IR-638.md) | **IMPLEMENTED** |
| **IR-667** | System settings are readable and writable by RDCO only; a PATCH cannot create a key; every change is audited | [details](traceability/IR-667.md) | **IMPLEMENTED** |
| **IR-794** | A daily job erases personal data past the retention period the System Admin sets; a blank period erases nothing, and audit rows are never touched. Subtask 15 of IR-779 (ADR-051 decision 19) | [details](traceability/IR-794.md) | **PARTIAL** |
| **IR-795** | The System Admin's Retention page at `/admin/retention`: each type's period and last run, blank erases nothing, the data protection officer approves first, and a period that would erase existing data says how much and asks first. Subtask 16 of IR-779 (ADR-051 decisions 3 and 19) | [details](traceability/IR-795.md) | **PARTIAL** |
| FR-M3-02 | Semantic indexing | [details](traceability/FR-M3-02.md) | **PARTIAL** |
| FR-M3-03 | Vector embeddings | [details](traceability/FR-M3-03.md) | **PARTIAL** |
| FR-M4-01 | RAG chatbot (Ask IRIS) | [details](traceability/FR-M4-01.md) | **PARTIAL** |
| FR-M4-02 | Summarization (AI Overview) | [details](traceability/FR-M4-02.md) | **IMPLEMENTED** |
| **IR-334** | Citation regions reach the wire, the manuscript is servable again, generation actually streams, and the AI Overview is generated once — … | [details](traceability/IR-334.md) | **IMPLEMENTED** |
| **IR-378** | Inference tasks and Profiles — a caller names a task instead of asking for "the LLM" — no FR- id; part C of IR-375's spec, and the expand … | [details](traceability/IR-378.md) | **IMPLEMENTED** |
| **IR-335** | PDF.js reader with citation highlighting, centred Paper View, markdown overview — the frontend consumer of IR-334's wire contract | [details](traceability/IR-335.md) | **IMPLEMENTED** |
| **IR-353** | Find in this paper: search the open PDF's text and jump to each match — a reader feature on IR-335's PDF.js reader | [details](traceability/IR-353.md) | **VERIFIED** |
| **IR-354** | A citation lands on the highlighted passage, clear of the header and the chat — corrects where IR-335's reader scrolls to | [details](traceability/IR-354.md) | **VERIFIED** |
| **IR-355** | Following a cross-paper citation keeps the originating Paper Chat conversation — the panel stays on the conversation the reader followed a … | [details](traceability/IR-355.md) | **IMPLEMENTED** |
| **IR-411** | Paper View sections and the capabilities adapter — F5 of the IR-374 frontend redesign; no FR- id (FR-M5-03's document vocabulary and … | [details](traceability/IR-411.md) | **IMPLEMENTED** |
| **IR-412** | The Review section: the paper, a timeline and an action bar — F6 of the IR-374 frontend redesign; no FR- id | [details](traceability/IR-412.md) | **IMPLEMENTED** |
| **IR-477** | A cited passage lands clear of the Review tab's sticky action bar — follow-up to IR-412, IR-374 redesign; no FR- id | [details](traceability/IR-477.md) | **IMPLEMENTED** |
| **IR-415** | Reviewer seats, the office pool and coordinators — ADR-032 §14's T1; touches FR-M5-01 (stable label only) | [details](traceability/IR-415.md) | **IMPLEMENTED** |
| **IR-261** | Every record enters at its Adviser; the Adviser accepts and routes, and offices route onward, into office pools — touches FR-M5-01 (stable … | [details](traceability/IR-261.md) | **IMPLEMENTED** |
| **IR-269** | An office reviewer clears or records a finding; an office completes when all its seats are done; RDCO opens only on the specialist path — … | [details](traceability/IR-269.md) | **IMPLEMENTED** |
| **IR-479** | Reviewer names and review comments are read by participants only — security; no FR- id | [details](traceability/IR-479.md) | **IMPLEMENTED** |
| **IR-272** | A reviewer requests a revision against the version they reviewed, and the party that asked may withdraw it — the precondition of ADR-003's … | [details](traceability/IR-272.md) | **IMPLEMENTED** |
| **IR-416** | Record versions: v1 at submission, the next at each resubmission, a review made against one, and the version picker — ADR-032 §14's T2; … | [details](traceability/IR-416.md) | **IMPLEMENTED** |
| **IR-419** | Review comments: a private, versioned discussion in the review timeline — ADR-032 §14's "review timeline and `ReviewComment`", renamed T5 … | [details](traceability/IR-419.md) | **IMPLEMENTED** |
| **IR-273** | The owner answers the open revision requests with a new version; only the requesting parties' clearances and seats reset — ADR-003's … | [details](traceability/IR-273.md) | **IMPLEMENTED** |
| **IR-632** | Under `RESTART_ALL` every reset office that had completed reviews the new version again, with the same reviewer — ADR-004's control arm … | [details](traceability/IR-632.md) | **IMPLEMENTED** |
| **IR-268** | My Reviews: a reviewer's own seats plus their office's pool, as To review · In review · Done — touches FR-M5-01 (stable label only) | [details](traceability/IR-268.md) | **IMPLEMENTED** |
| **IR-478** | RDCO grants and removes office coordinators on the Users page; demo coordinators — ADR-032 §4, after IR-415; touches FR-M5-01 (stable label … | [details](traceability/IR-478.md) | **IMPLEMENTED** |
| **IR-797** | RDCO replaces a paper's Adviser, adds an owner and withdraws a paper in review — ADR-051 decision 10; touches FR-M5-01 (stable label only) | [details](traceability/IR-797.md) | **PARTIAL** |
| **IR-798** | RDCO's controls on Paper View: replace the Adviser, add an owner, withdraw a paper in review, each asking first and saying who is told — ADR-051 decision 10; touches FR-M5-01 (stable label only) | [details](traceability/IR-798.md) | **IMPLEMENTED** |
| **IR-413** | The sidebar: one short list, My Reviews only for review work, and an account menu — no FR- id; F1's navigation slice. The redirect table, … | [details](traceability/IR-413.md) | **IMPLEMENTED** |
| **IR-534** | F1b: the redirect table, Discover home for everyone, the post-login landing on `review_access`, and the My Library needs-action dot (B2) — … | [details](traceability/IR-534.md) | **IMPLEMENTED** |
| **IR-537** | A declined applicant is told so: `role_request` on `/users/me/`, and the pending screen in the entry frame — no FR- id; subtask 3 of IR-533 … | [details](traceability/IR-537.md) | **IMPLEMENTED** |
| **IR-539** | Every register control has a name: the `Select` primitive, `Input` adoption, the role radio group — no FR- id; subtask 5 of IR-533 (entry … | [details](traceability/IR-539.md) | **IMPLEMENTED** |
| **IR-934** | Discover's Filters button names itself with the words it shows, its cover placeholder has enough contrast, and the 360px reflow check measures the settled layout — no FR- id; WCAG 2.5.3 and 1.4.10, found by IR-902's pinned run | [details](traceability/IR-934.md) | **VERIFIED** |
| **IR-902** | Playwright journeys for Discover search and filters, opening a published paper, and opening its manuscript at `?page=N` — no FR- id; subtask of the browser-test work around IR-631 (its AC6 without Ask IRIS) | [details](traceability/IR-902.md) | **PARTIAL** |
| **IR-904** | A small Playwright smoke tier gates every pull request that touches `frontend/`, against the built app with the network mocked — no FR- id; subtask … | [details](traceability/IR-904.md) | **PARTIAL** |
| **IR-908** | Axe runs in a real browser on every routed screen, every dialog and every state of the UI states matrix in CI, failing on serious and critical findings, each finding fixed or filed; seven dialog sources are named as not yet scanned — no FR- id; subtask of IR-896 … | [details](traceability/IR-908.md) | **PARTIAL** |
| **IR-909** | PR-gated keyboard-only core journeys and narrow-viewport 400%-equivalent reflow checks; 320 CSS px coverage does not emulate browser zoom or verify text resizing | [details](traceability/IR-909.md) | **PARTIAL** |
| **IR-907** | Every cell of the UI states matrix is forced in a real browser by intercepting its request, asserting what the reader sees and can do next; a guard fails when the matrix and the tests disagree; a cut-off Ask IRIS answer offers Retry — no FR- id; subtask of IR-895 | [details](traceability/IR-907.md) | **PARTIAL** |
| **IR-918** | CI checks that the built frontend bundle holds no secrets or personal data, that no address carries personal data, and that `npm audit` is triaged — no FR- id; subtask of IR-900 | [details](traceability/IR-918.md) | **PARTIAL** |
| **IR-910** | Every routed screen is opened at 360, 768, 1280 and 1745 px in CI: no sideways page scroll, a reachable primary action, a documented small-screen behaviour for tables — no FR- id; subtask of IR-897 … | [details](traceability/IR-910.md) | **PARTIAL** |
| **IR-915** | A change to a covered response shape on the backend fails a test, and a covered response that no longer fits the frontend's type fails a test — no FR- id; subtask of IR-899; recorded fixtures checked by a backend test, no `drf-spectacular`; slice 1 of 2 (non-AI endpoints) | [details](traceability/IR-915.md) | **PARTIAL** |
| **IR-695** | People add a photo, bio and research interests to their account, and no one else edits them; the photo is re-encoded and served only to signed-in users through Django — no FR- id (NFR-S4, FR-M6-06 touched); subtask of IR-694; ORCID iD dropped 2026-11-07 | [details](traceability/IR-695.md) | **IMPLEMENTED** |
| **IR-696** | Any signed-in user opens a person's public profile with their papers, advised papers and collaborators; hidden accounts answer one 404; no email, totals or citation counts — IR-694; no FR- id (NFR-S4); ORCID iD dropped | [details](traceability/IR-696.md) | **IMPLEMENTED** |
| **IR-701** | Discover previews up to five matching people above papers and switches to a college, department and role filtered People directory with linked profile cards — subtask 7 of IR-694, builds on IR-697 | [details](traceability/IR-701.md) | **PARTIAL** |
| **IR-697** | Signed-in Discover people search matches names and research interests, filters by college, department and role, pages safe profile fields and published-paper counts, and hides unapproved, inactive, suspended or deleted accounts — IR-694; no FR- id (NFR-S4) | [details](traceability/IR-697.md) | **IMPLEMENTED** |
| **IR-778** | The account menu's accessible name begins with the name and role it shows — no FR- id; WCAG 2.1 2.5.3 Label in Name, found by IR-631's axe … | [details](traceability/IR-778.md) | **PARTIAL** |
| **IR-777** | The notification bell's accessible name contains the count it shows — no FR- id; WCAG 2.1 2.5.3 Label in Name, found by IR-631's axe run … | [details](traceability/IR-777.md) | **PARTIAL** |
| **IR-774** | Scrolling regions are reachable and scrollable from the keyboard: Workflow Analytics tables at 360px and the office Review pane at 200% — … | [details](traceability/IR-774.md) | **IMPLEMENTED** |
| **IR-540** | Register gets informed consent and an honest finish: an interim data notice, next steps, an in-place confirmation — no FR- id of its own; … | [details](traceability/IR-540.md) | **IMPLEMENTED** |
| **IR-565** | A long Manuscript opens at its first or cited page, and only a bounded window of pages is painted — no FR- id; subtask 12 of IR-552 (User … | [details](traceability/IR-565.md) | **IMPLEMENTED** |
| **IR-569** | Paper view: one record bar, a full-height reading workspace that follows the content width, and one Ask IRIS everywhere — no FR- id; … | [details](traceability/IR-569.md) | **IMPLEMENTED** |
| **IR-674** | RDCO alone decides a download request, cannot decide their own, and only RDCO is notified of a new one | [details](traceability/IR-674.md) | **IMPLEMENTED** |
| **IR-675** | An approved download request is a time-limited grant used while signed in; no bearer link is issued | [details](traceability/IR-675.md) | **PARTIAL** |
| **IR-676** | Every copy saved through the download route names who downloaded it, or is not served | [details](traceability/IR-676.md) | **PARTIAL** |
| **IR-677** | The paper page shows where the reader's own download stands, and saves a copy only through the download route | [details](traceability/IR-677.md) | **PARTIAL** |
| **IR-688** | A download request carries the reader's note, a decline or revocation carries RDCO's, the reader may cancel a pending request, and RDCO may … | [details](traceability/IR-688.md) | **PARTIAL** |
| **IR-743** | The reader may cancel a pending download request on the paper page, sees RDCO's note beside Request again, and has a My Library view of … | [details](traceability/IR-743.md) | **PARTIAL** |
| **IR-270** | The Adviser accepts & publishes or rejects a Thesis/Project; RDCO decides specialist-path records — touches FR-M5-01 (stable label only) | [details](traceability/IR-270.md) | **IMPLEMENTED** |
| **IR-271** | The Adviser alone decides a Proposal: request revision, reject (Archived) or accept — touches FR-M5-01 (stable label only) | [details](traceability/IR-271.md) | **IMPLEMENTED** |
| **IR-274** | Contract: the fixed office pipeline and the intake party are removed — the final expand–contract step of IR-255; touches FR-M5-01 (stable … | [details](traceability/IR-274.md) | **IMPLEMENTED** |
| **IR-393** | Chunks carry a stored keyword index the database maintains — no FR- id; part C of IR-390's spec, and the asset the hybrid retrieval in … | [details](traceability/IR-393.md) | **IMPLEMENTED** |
| **IR-395** | An exact term finds its papers — keyword and vector search fused behind a switch — no FR- id; part E of IR-390's spec, and the first of … | [details](traceability/IR-395.md) | **IMPLEMENTED** |
| **IR-656** | The sign-in lockout counts the real client behind the proxies: a stranger's guesses no longer lock the owner out, and a forged … | [details](traceability/IR-656.md) | **IMPLEMENTED** |
| **IR-406** | The Publish dialog can offer the manuscript's own title and abstract — no FR- id; B1 of the IR-374 frontend redesign spec (§4.5, Appendix … | [details](traceability/IR-406.md) | **IMPLEMENTED** |
| **IR-409** | The Publish dialog offers the manuscript's own title and abstract as chips — no FR- id; F3b of the IR-374 frontend redesign spec (§4.5 … | [details](traceability/IR-409.md) | **IMPLEMENTED** |
| **IR-380** | The AI Summary runs as its own Inference task — no FR- id; part F of IR-375's spec, and the first caller to move off `answer`'s model | [details](traceability/IR-380.md) | **IMPLEMENTED** |
| **IR-431** | The AI Overview is assembled from the whole paper, in its own module — no FR- id; part A of IR-425's spec | [details](traceability/IR-431.md) | **IMPLEMENTED** |
| **IR-437** | The whole-document disclosure is on the record — no FR- id; part G of IR-425's spec | [details](traceability/IR-437.md) | **DOCUMENTED** |
| **IR-657** | An administrator revoking a session ends it at once: its access and refresh tokens are refused on their next use, with a code that says an … | [details](traceability/IR-657.md) | **IMPLEMENTED** |
| **IR-435** | Whole-paper overview generation leaves the HTTP request and is queued after chunking; readers receive `generating` and poll until ready or … | [details](traceability/IR-435.md) | **IN PROGRESS** |
| **IR-434** | An overview citation names a page — no FR- id; part D of IR-425's spec | [details](traceability/IR-434.md) | **IMPLEMENTED** |
| **IR-433** | The AI Overview is a structured account, not two paragraphs of prose — no FR- id; part C of IR-425's spec | [details](traceability/IR-433.md) | **IMPLEMENTED** |
| **IR-604** | Each paper gets a one-sentence hook, written with the Overview — no FR- id; part H of IR-425's spec, needed by IR-567's Discover card | [details](traceability/IR-604.md) | **IMPLEMENTED** |
| **IR-577** | Save a private custom feed from Discover's filters: owner-only `SavedFeed` holding Discover's own query, capped at 10, stale values corrected first — no FR- id; user stories 15 to 17 of IR-557's spec | [details](traceability/IR-577.md) | **IMPLEMENTED** |
| **IR-567** | For you from the Areas the reader chooses, with a reason on every item and a stable cursor — no FR- id; user stories 1, 2, 4, 5, 8, 9, 12 of IR-557's spec (file written after the fact) | [details](traceability/IR-567.md) | **IMPLEMENTED** |
| **IR-575** | My saved research shapes For you: saved Records' Areas join the chosen ones, saved Records sink, saves invalidate the feed — no FR- id; user stories 3, 7, 11 of IR-557's spec | [details](traceability/IR-575.md) | **IMPLEMENTED** |
| **IR-665** | An uploaded PDF must really be one: its bytes carry the signature and it opens with at least one page; `uploads/create/` no longer skips … | [details](traceability/IR-665.md) | **IMPLEMENTED** |
| **IR-383** | Question resolution runs as its own Inference task, on a model that exists — no FR- id; part E of IR-375's spec, and the ticket that closes … | [details](traceability/IR-383.md) | **IMPLEMENTED** |
| **IR-382** | Groq dialect: the vendor's request shape behind the adapter, with citation-marker normalisation — no FR- id; part H of IR-375's spec, and … | [details](traceability/IR-382.md) | **IMPLEMENTED** |
| **IR-852** | Figures are described for retrieval only, never shown to readers — no FR- id; part of IR-848 (ADR-056 §10) | [details](traceability/IR-852.md) | **IMPLEMENTED** |
| **IR-647** | The API enforces the configured password policy — no FR- id; subtask 4 of IR-644 (account-security findings, 2026-10-30) | [details](traceability/IR-647.md) | **VERIFIED** |
| **IR-829** | The ASVS items marked "Needs manual check" are run: 16 of 21 have a result, and every Fail is ticketed (IR-923, IR-924, IR-925, IR-926, IR-928, IR-929); four wait for IR-806's server and one for the DPO — no FR- id; from IR-617, covers NFR-S1…S6 | [details](traceability/IR-829.md) | **PARTIAL** |
| **IR-645** | A refused session's 401 says why it ended — no FR- id; subtask 1 of IR-644 (account-security findings, 2026-10-30), extends NFR-S2 (IR-166) | [details](traceability/IR-645.md) | **IMPLEMENTED** |
| **FR-M5-01** | Hierarchical submission workflow | [details](traceability/FR-M5-01.md) | **VERIFIED** |
| FR-M5-03 | Explicit document requests, distinct from resubmission | [details](traceability/FR-M5-03.md) | **IMPLEMENTED** |
| FR-M5-05 | IP type on published records | [details](traceability/FR-M5-05.md) | **IMPLEMENTED** |
| FR-M6-01 | Authentication | [details](traceability/FR-M6-01.md) | **PARTIAL** |
| FR-M6-02 | DPA consent | [details](traceability/FR-M6-02.md) | **IMPLEMENTED** |
| FR-M6-03 | Role-based access control | [details](traceability/FR-M6-03.md) | **IMPLEMENTED** |
| FR-M6-05 | Session monitoring for administrators | [details](traceability/FR-M6-05.md) | **IMPLEMENTED** |
| FR-M6-06 | Data privacy consent at signup | [details](traceability/FR-M6-06.md) | **PARTIAL** |
| FR-M7-01 | KPI dashboard | [details](traceability/FR-M7-01.md) | **DROPPED** |
| FR-M7-02 | Not defined outside the frozen SRS | [details](traceability/FR-M7-02.md) | **BLOCKED** |
| FR-M8-01 | Not defined outside the frozen SRS | [details](traceability/FR-M8-01.md) | **BLOCKED** |
| FR-M8-02 | Audit log: read-only, 12-month retention | [details](traceability/FR-M8-02.md) | **PARTIAL** |
| FR-M8-03 | Embedding index administration | [details](traceability/FR-M8-03.md) | **IMPLEMENTED** |
| FR-M2-06/07 | Institutional / personal storage | [details](traceability/FR-M2-06-07.md) | **DEFERRED** ([ADR-001](../adr/001-mvp-scope-boundary.md)) |
| **ADR-019** | Persisted conversation history — no FR- id exists for this; ADR-019 is the requirement, and ADR-019 §Related Requirements says so explicitly | [details](traceability/ADR-019.md) | **IMPLEMENTED** |
| **ADR-026 §12-§15 · ADR-027 §9** | Retry, multi-part questions, Listing questions and reader-feedback privacy — no FR- id exists for these; the ADRs are the requirement, and … | [details](traceability/ADR-026-12-15-ADR-027-9.md) | **NOT STARTED** |
| **ADR-026 §7-§8 (amended) · §13 · ADR-015 rule 3 note** | Conversational memory correctness — no FR- id exists for it; the ADRs are the requirement. Resolution runs on every follow-up and a Turn's … | [details](traceability/ADR-026-7-8-amended-13-ADR-015-rule-3-note.md) | See details |
| **ADR-033** | Hybrid retrieval and passage selection — no FR- id; ADR-033 (Accepted 2026-09-28, IR-391) is the requirement. Keyword search over the whole … | [details](traceability/ADR-033.md) | **PARTLY BUILT** |
| **ADR-034** | An ungrounded answer is a distinct state, never a grounded one — no FR- id; ADR-034 (Accepted 2026-10-02, IR-453) is the requirement. A new … | [details](traceability/ADR-034.md) | **ACCEPTED, NOT BUILT** |
| **ADR-026 §13 · ADR-034 (answer-state presentation)** | Every answer state has an explicit wire presentation, and an unknown one fails safe — no FR- id; a live defect found under IR-456, fixed by … | [details](traceability/ADR-026-13-ADR-034-answer-state-presentation.md) | **BUILT and executed** |
| **ADR-034 §2 (retrieval outcome classification)** | Retrieval reports why it returned nothing — no FR- id; IR-459 (retrieval reports why it returned nothing), a prefactor under IR-456 — the … | [details](traceability/ADR-034-2-retrieval-outcome-classification.md) | **BUILT and executed** |
| **ADR-035 (proposed)** | Ask IRIS decides whether it needs evidence — no FR- id; ADR-035 is the requirement once accepted, and it is `Proposed`, not accepted. … | [details](traceability/ADR-035-proposed.md) | **PROPOSED — NOT ACCEPTED, and not Done** |
| **ADR-035 §5 · §10 (proposed)** | A question's evidence requirement is detected and recorded — no FR- id; ADR-035 §5 is the requirement once accepted, and it is `Proposed`, … | [details](traceability/ADR-035-5-10-proposed.md) | See details |
| **ADR-035 §2 · §4 · §8 · §10** | The provider can carry a tool-calling decision, exercised offline — no FR- id; ADR-035 (Accepted 2026-10-06; supersedes ADR-028's … | [details](traceability/ADR-035-2-4-8-10.md) | See details |
| **ADR-035 §1 · §3 · §4 · §6 · §10 · §11** | Reader-invisible shadow decisions on real traffic — no FR- id; ADR-035 (Accepted 2026-10-06). IR-466 under IR-456 | [details](traceability/ADR-035-1-3-4-6-10-11.md) | See details |
| **ADR-035 §10 · §11** | The pilot reports what it found — no FR- id; ADR-035 (Accepted 2026-10-06). IR-467 under IR-456 | [details](traceability/ADR-035-10-11.md) | See details |
| **ADR-035 §2 · §3 · §8 (route-label mode)** | The Evidence route can be asked as a bare label — no FR- id; ADR-035. IR-481 under IR-480 | [details](traceability/ADR-035-2-3-8-route-label-mode.md) | **BUILT and measured on the proxy corpus only** |
| **ADR-035 §2 · §3 · §8 (Jev Noul mode)** | The Evidence route can be asked as a probability — no FR- id; ADR-035, ADR-036 §Amendment 2026-10-08. IR-482 under IR-480 | [details](traceability/ADR-035-2-3-8-Jev-Noul-mode.md) | Not Done |
| **ADR-035 §2 · §3 · §10 (chained decision evaluation)** | The proposed decision chain can be scored offline — no FR- id; ADR-035 as amended by IR-487 (pending approval). IR-486 under IR-484 | [details](traceability/ADR-035-2-3-10-chained-decision-evaluation.md) | **BUILT, offline, exploratory** |
| **ADR-038 (proposed)** | Ask IRIS gains a bounded research lane — no FR- id; ADR-038 (Proposed 2026-10-11, IR-499; awaiting a named approver) is the requirement … | [details](traceability/ADR-038-proposed.md) | **PROPOSED; TOOL LAYER BUILT ON A BRANCH** |
| **ADR-023** | Retrieval quality is measured — no FR- id; ADR-023 (Accepted 2026-09-17, amended 2026-09-28 by IR-391) is the requirement: recall@10 over a … | [details](traceability/ADR-023.md) | **HARNESS IMPLEMENTED, PROXY BASELINE RECORDED (2026-09-30)**; correct-refusal measure added by [IR-454](traceability/IR-454.md), not yet run on the proxy set |
| **IR-423** | A paper longer than voyage-context-4's 32k-token window can be indexed — extends FR-M3-02 (stable label only) | [details](traceability/IR-423.md) | **IMPLEMENTED** |
| **IR-424** | Answer presentation: Markdown structure, delimited formulas and no invented images — no FR- id; changes answer-path behaviour (IR-426 … | [details](traceability/IR-424.md) | **IMPLEMENTED** |
| **IR-440** | Retrieval looks past 40 candidates — no FR- id; a bug fix, not a technique | [details](traceability/IR-440.md) | **IMPLEMENTED** |
| **IR-442** | A retrieval miss is detectable rather than silent — no FR- id; the checker for the failure class ADR-023 measures in aggregate but cannot … | [details](traceability/IR-442.md) | **IMPLEMENTED** |
| **IR-568** | Related works says why it is empty (ready, no matches, not indexed, incompatible, unavailable) without revealing hidden Records — no FR- id; user story 14 of IR-557's spec | [details](traceability/IR-568.md) | **IMPLEMENTED** |
| **IR-312** | A proposer sees when their idea was already done here — the Novelty check; FR-M4 (stable label only) | [details](traceability/IR-312.md) | **IMPLEMENTED** |
| **IR-786** | A person downloads a copy of their own data from one owner-only, audited, rate-limited endpoint — ADR-051 decision 13; FR-M6-06 (stable label only) | [details](traceability/IR-786.md) | **PARTIAL** |
| **IR-791** | A paper keeps its Contact person's AI answer from draft creation, the disclosure gate reads it, submit asks no consent, and a person changes their own answer — ADR-054 decisions 5, 6, 9-13, 16-17; FR-M6-02 (stable label only) | [details](traceability/IR-791.md) | **IMPLEMENTED** |
| **IR-793** | Settings shows the person's AI answer and its notice version and lets them change it: Yes to No says it reaches only papers from now on; No to Yes asks All my papers or Only papers from now on, neither preselected; no per-paper control — under IR-779, ADR-054 decisions 11–13; no FR- id | [details](traceability/IR-793.md) | **PARTIAL** |
| **IR-800** | A Notices page where RDCO publishes the next data notice and RDCO and the System Admin read every version; every screen shows the server's notice as plain text — under IR-779, ADR-051 decisions 16–17, ADR-063 decision 9 | [details](traceability/IR-800.md) | **PARTIAL** |
| **IR-826** | The AI gateway gets no Django database login; ADR-014's accepted amendment allows its runs login only | [details](traceability/IR-826.md) | **VERIFIED** |
| **IR-832** | Publish blocks readable exact Manuscript duplicates and requires acknowledgement of likely matches | [details](traceability/IR-832.md) | **IN PROGRESS** |
| **IR-833** | Publish fills in a reliable title and abstract from the PDF and never overwrites the author's edits — no FR- id; IR-830 decisions 14–18 | [details](traceability/IR-833.md) | **IMPLEMENTED** |
| **IR-846** | Publish suggestions for a LlamaParse Manuscript come from LlamaExtract, each with its page, cited text and reported confidence — no FR- id; ADR-056 §15 within IR-830's contract | [details](traceability/IR-846.md) | **IMPLEMENTED** |
| **IR-886** | The agent's search finds permitted Passages by meaning as well as by keyword, narrowed by Area, PSCED area, record type or years, with one read policy — under IR-712, ADR-049 (2026-11-07 amendment); no FR- id | [details](traceability/IR-886.md) | **PARTIAL** |
| **IR-994** | The runtime agent answers follow-ups, exact counts and complete listings: earlier answers carry their sources, and counts and title lists pass the send guard as metadata — under IR-955, ADR-049 (2026-11-08 amendment); no FR- id | [details](traceability/IR-994.md) | **PARTIAL** |
| **IR-995** | A withheld or unmatched result no longer ends an agent run; titles and category names match whatever their case or punctuation; Paper Chat names its paper; two answer repairs under `research-7` — under IR-955, ADR-049 (2026-11-09 amendment); no FR- id | [details](traceability/IR-995.md) | **PARTIAL** |
| **IR-957** | Ask IRIS and Paper Chat are answered by the AI runtime; Django's answer path is retired, its routes answer 410, in-flight runs end `retired` and earlier Conversations stay readable — under IR-955, ADR-049 (2026-11-09 amendment, switched before IR-955's bar passed); no FR- id | [details](traceability/IR-957.md) | **PARTIAL** |
| **IR-996** | No runtime guards: disclosure is decided once at indexing; the AI runtime's send guard, IR-889 approval and source screen are removed, tool results reach the model whole, and no code requires a vendor no-training policy — under IR-955, ADR-049 (2026-11-09 IR-996 amendment); no FR- id | [details](traceability/IR-996.md) | **PARTIAL** |
| **IR-1007** | A simultaneous multi-reader burst through the runtime gateway, every submission counted; one paid 100-question burst at the production-shaped limits: 99 answered, 20.5 a minute on one worker — under IR-955; no FR- id | [details](traceability/IR-1007.md) | **PARTIAL** |
| **IR-1012** | The runtime's database connections pooled per process, exhaustion answered `503 busy`, and production sizing for 100 readers (120 slots over five workers, wider lanes, `max_connections` 300); paid 100-reader bursts answered 100 of 100 twice with a median queue wait under 1 s — under IR-955; no FR- id | [details](traceability/IR-1012.md) | **PARTIAL** |
| **IR-1004** | Repository questions answered from the repository or declined, a fixed decline when no sentence stands, repairs that never mention the draft, under `research-8`; F12 87.5% on the merged code, F09 blocked by the removed manual compaction — under IR-955, ADR-049 (2026-11-09 amendment); no FR- id | [details](traceability/IR-1004.md) | **PARTIAL** |
| **IR-953, IR-1003** | Prompt-cache hits recorded per attempt; a per-run query-vector cache (on) and prompt-cache key (off); a tool group's read-only calls fetched concurrently and folded in call order — under IR-712, ADR-049 (IR-953 amendment); no FR- id | [details](traceability/IR-953.md) | **PARTIAL** |
| **IR-885** | A runtime question runs at deep depth unless the reader chooses ordinary | [details](traceability/IR-885.md) | **PARTIAL** |
| **IR-884** | ADR-049 and the AI runtime spec are on `main`; IR-714's resume, export and review questions have owners | [details](traceability/IR-884.md) | **PARTIAL** |
| **IR-863** | Ask IRIS opens AI-runtime runs only when the deployment's `AI_RUNTIME_READER` switch says so; the browser reads it and cannot choose — under IR-714, ADR-049; no FR- id. The switch is removed by IR-957: the runtime always answers | [details](traceability/IR-863.md) | **PARTIAL** |
| **IR-754** | A reader deliberately compacts an owned Conversation from Ask IRIS or Paper Chat as a run of its own, through IR-734's mechanism, and sees what happened — under IR-715, ADR-049 §19; no FR- id | [details](traceability/IR-754.md) | **PARTIAL** |
| **IR-736** | A long-paper investigation continues across repeated compactions and safely rebuilds when native continuation state is incompatible — under IR-715, ADR-049 §19–20; no FR- id | [details](traceability/IR-736.md) | **PARTIAL** |
| **IR-785** | A person asks to delete their account; the System Admin confirms it once nobody is waiting on them, erasing their details and private data and keeping the row — under IR-779, ADR-051 decisions 8–12, 28; no FR- id | [details](traceability/IR-785.md) | **PARTIAL** |
| **IR-801** | Any owner names another owner of the same paper its Contact person, on every paper until it is deleted; a stranger is never added, the paper always has exactly one, both people are told in-app and the change is audited — under IR-779, ADR-051 decision 27; no FR- id | [details](traceability/IR-801.md) | **PARTIAL** |
| **IR-787** | Settings offers "Download my data" with progress and failure states, and "Delete my account", which says what goes and what stays before confirming, shows a pending request with its blockers and Cancel, and a rejection with its reason — under IR-779, ADR-051 §8, decisions 11, 13 and 18; no FR- id | [details](traceability/IR-787.md) | **PARTIAL** |
| **IR-788** | The System Admin's Account Deletion Requests page shows blockers, and confirms or rejects from the API's capabilities — under IR-779, ADR-051 decisions 8–9; no FR- id | [details](traceability/IR-788.md) | **PARTIAL** |
| **IR-790** | Registration and sign-in show the server's data notice with the agreement and a required Yes or No on AI; a signed-in person who hasn't answered sees only it, with Sign out and Request account deletion — under IR-779, ADR-054 decisions 1–3, 13; no FR- id | [details](traceability/IR-790.md) | **PARTIAL** |
| **IR-799** | RDCO publishes a new data notice version by pasting its whole text; versions never change, a stale publish is refused, RDCO sees how many accounts must answer, RDCO and the System Admin read every version — under IR-779, ADR-051 decisions 16–17 as amended by ADR-063 decision 9; no FR- id | [details](traceability/IR-799.md) | **IMPLEMENTED** |
| **IR-928** | The verification link keeps its secret in the URL fragment and the page posts it in a body; links already emailed keep working for the 3 days their tokens live — from IR-829 (ASVS 8.3.1); no FR- id | [details](traceability/IR-928.md) | **PARTIAL** |
| **IR-643** | Resend account verification email: single-use, 24-hour verification links on IR-642's durable recovery path, registration on the same path, and the old activation links retired — ADR-045; closes IR-937's removal; no FR- id | [details](traceability/IR-643.md) | **PARTIAL** |
| **IR-660** | Registration accepts only the domains in `REGISTRATION_EMAIL_DOMAINS`, matched exactly and ignoring case; production refuses to start without it — pilot access control under IR-655; no FR- id | [details](traceability/IR-660.md) | **PARTIAL** |
| **IR-784** | RDCO is told once, in the app, of a Student or Adviser role request when the person verifies their email; an unverified or repeated link alerts nobody — under IR-779, ADR-051 decision 20; no FR- id | [details](traceability/IR-784.md) | **PARTIAL** |
| **IR-880** | A running AI-runtime investigation keeps reading under its reader's renewed grant, never widens scope, and still ends at the next read or admission once the reader stops reconnecting or loses access — under IR-713, ADR-049 §6, §9; no FR- id | [details](traceability/IR-880.md) | **PARTIAL** |
| **IR-726** | A reader stops, reconnects with a journal cursor, or explicitly retries one AI-runtime investigation across worker races without duplicate delivery, continued admissions or a renewed allowance — under IR-713, ADR-049 §11; no FR- id | [details](traceability/IR-726.md) | **PARTIAL** |
| **IR-752** | An operator builds a pending Embedding Space beside the active one, with space-keyed Record and Passage vectors, while readers keep searching the active space — under IR-716, ADR-049 §23; additive expand only, no activation (IR-739); no FR- id | [details](traceability/IR-752.md) | **PARTIAL** |
| **IR-739** | An operator verifies and atomically promotes a complete Embedding Space pair (Record and Passage vectors), or rolls back to the previous revision, with readers and the `ai/` runtime moved onto space-keyed Record vectors and no revoked source resurrected — under IR-716, ADR-049 §23; no live provider, no production upgrade; no FR- id | [details](traceability/IR-739.md) | **PARTIAL** |
| **IR-721** | After access changes a reader or reviewer cannot recover revoked research by reopening, reconnecting, replaying or opening a saved Conversation, and a review packet is judged again by the opening account's access — under IR-712, ADR-049 §15; no FR- id | [details](traceability/IR-721.md) | **PARTIAL** |
| **IR-740** | IR-605 collects the dedicated runtime through its real authenticated routes under an explicit engine identity, and rescores old baselines with effective-condition preflight and a separate capability report — under IR-716, ADR-049 §24; no FR- id | [details](traceability/IR-740.md) | **PARTIAL** |
| **IR-741** | The release-readiness manifest reports quality, safety, baseline, scenario, workload and cost evidence per gate and refuses to call missing, fake or incomparable evidence a pass — under IR-716, ADR-049 §25-§26; no FR- id | [details](traceability/IR-741.md) | **PARTIAL** |
| **IR-956** | One frozen 108-question set across twelve families goes through Django `lanes-v1` and the runtime agent on one paid run each, is scored automatically by exact checks and a pinned model grader, and is reported as pass or fail against IR-955's bar — under IR-955, ADR-049 §24–26 as amended 2026-11-07; no FR- id | [details](traceability/IR-956.md) | **PARTIAL** |
| **IR-882** | Every paper starts embargoed; Publish asks no embargo question; only the Adviser or RDCO date or release one, and RDCO publishes only a released paper — extends FR-M3-02 (stable label only); ADR-052 IR-879 amendment | [details](traceability/IR-882.md) | **IMPLEMENTED** |
| **IR-871** | Each Version keeps its review text, read on campus with pdfplumber and no AI, whatever the embargo or consent; never chunked, embedded or retrieved, and served only under `may_read_review` — ADR-058 §1 as amended 2026-11-05; touches FR-M5-01 (stable label only); run on three Version pairs of real CIT-U papers | [details](traceability/IR-871.md) | **IMPLEMENTED** |
| **IR-874** | Review threads, backend: anchored threads, *Must fix* and *Suggestion*, drafts sent by Finish review, *Comment only*, resolving and answering, and what an open *Must fix* blocks — ADR-032 §7 (2026-11-04, corrected 2026-11-06); no FR- id | [details](traceability/IR-874.md) | **IMPLEMENTED** |
| **IR-875** | Review threads, frontend: comment on a selection or find match, the Threads tab, and the Finish review dialog, driven by server capabilities — ADR-032 §7 (2026-11-04, corrected and noted 2026-11-06); no FR- id | [details](traceability/IR-875.md) | **IMPLEMENTED** |
| **IR-878** | RDCO publishes an Unlisted paper later, only once its embargo is released, and the history keeps its Decision as *kept unlisted* — ADR-047 §10, ADR-052 decision 14 as amended; no FR- id | [details](traceability/IR-878.md) | **IMPLEMENTED** |
| **IR-873** | Two Versions compared section by section, both read by one reader, never naming it, in the reviewer's Changes tab — ADR-058 §3 as amended 2026-11-08; FR-M5-01 (label only) | [details](traceability/IR-873.md) | **VERIFIED** |
| **IR-876** | A thread follows its passage into later Versions and goes Outdated where it changed; suggested wording; the response to reviewers frozen onto each Version — ADR-032 §7 and its IR-876 build notes; no FR- id | [details](traceability/IR-876.md) | **VERIFIED** |
| **IR-1008** | A thread's quote is found in a Version's text whatever its spaces at line breaks, so it is placed found or changed, not removed — fix to IR-876; no FR- id | [details](traceability/IR-1008.md) | **VERIFIED** |
| **IR-1009** | A thread says why it isn't followed into a later Version (no text for a Version, or still looking) instead of saying nothing — follow-up to IR-876; no FR- id | [details](traceability/IR-1009.md) | **VERIFIED** |
| **IR-877** | Viewed marks, saved replies and @mentions in the review — ADR-032 §7 Conveniences and its IR-877 build notes, ADR-058 §3 point 7; no FR- id. Built in three stacked PRs: [#663](https://github.com/moisturicer/IRIS/pull/663), [#664](https://github.com/moisturicer/IRIS/pull/664), [#665](https://github.com/moisturicer/IRIS/pull/665) | [details](traceability/IR-877.md) | **VERIFIED** |
| **IR-1005** | The review-text reader loads its text encodings before its sandbox closes, so a PDF in an embedded font is read, not stored as no text — fix to IR-871; no FR- id | [details](traceability/IR-1005.md) | **VERIFIED** |
| **IR-690** | Comments on published papers: write, reply, edit and delete — ADR-032 §7, amendment 2026-10-31, and its IR-690 build notes; no FR- id. PR [#672](https://github.com/moisturicer/IRIS/pull/672) | [details](traceability/IR-690.md) | **VERIFIED** |
| **IR-1014** | A script gets a fresh Ubuntu server ready for IRIS: Docker, swap, the clone and DuckDNS, safe to run twice; never starts IRIS or writes a `.env` — epic IR-805; no FR- id. Awaits the run on a fresh EC2 instance with a reboot | [details](traceability/IR-1014.md) | **IMPLEMENTED** |
| **IR-1013** | A CloudFormation template makes the AWS demo server from one file: instance, firewall, fixed IP and Session Manager access, running the IR-1014 script at first boot — epic IR-805; no FR- id. Awaits a real-account run at the next migration | [details](traceability/IR-1013.md) | **IMPLEMENTED** |
| **IR-1015** | Cost and uptime guards for one server: an account budget alert, an alarm that recovers the instance, and an optional daily stop and start, each optional — epic IR-805; no FR- id. PR [#676](https://github.com/moisturicer/IRIS/pull/676); verified on iris-demo 2026-11-11 | [details](traceability/IR-1015.md) | **VERIFIED** |
| **IR-1016** | The server's logs are read without SSH, through a free Session Manager shell; CloudWatch Logs deferred — epic IR-805; no FR- id. Checked on iris-demo 2026-11-11 | [details](traceability/IR-1016.md) | **VERIFIED** |

### Non-functional

| Req | Requirement | Details | Status |
|---|---|---|---|
| NFR-S1 | Transport security | [details](traceability/NFR-S1.md) | **PARTIAL** |
| NFR-S2 | 30-minute inactivity expiry | [details](traceability/NFR-S2.md) | **VERIFIED** |
| NFR-S3 | Secure configuration | [details](traceability/NFR-S3.md) | **PARTIAL** |
| NFR-S4 | Server-side authorization | [details](traceability/NFR-S4.md) | **PARTIAL** |
| NFR-S5 | Audit immutability | [details](traceability/NFR-S5.md) | **VERIFIED** |
| NFR-S6 | Account protection | [details](traceability/NFR-S6.md) | **PARTIAL** |
| **IR-999** | Soft rate limits: each budget has a per-minute burst whose refusal clears in under a minute, and a daily backstop; extends NFR-S6 (IR-661) | [details](traceability/IR-999.md) | **IMPLEMENTED** |
| NFR-P1 | 100 concurrent sessions | [details](traceability/NFR-P1.md) | **NOT STARTED** |
| NFR-P2…P5 | Performance and processing | [details](traceability/NFR-P2-P5.md) | **NOT STARTED** |
| NFR-R1 | Uptime | [details](traceability/NFR-R1.md) | **NOT STARTED** |
| NFR-R2 | Graceful degradation | [details](traceability/NFR-R2.md) | **IMPLEMENTED** |
| NFR-R3, R4 | Reliability and recovery | [details](traceability/NFR-R3-R4.md) | **NOT STARTED** |
| NFR-U1 | General usability | [details](traceability/NFR-U1.md) | **NOT STARTED** |
| **NFR-U2** | Submission in under 10 min, 5 of 5 participants | [details](traceability/NFR-U2.md) | **NOT STARTED** |
| **IR-700** | Another person's Profile at `/people/:id` over the draft IR-696 contract, with Adviser and owner names linking to it, and no middle-initial or ORCID iD field on Edit profile — IR-694; no FR- id; waits on IR-696 and IR-692 | [details](traceability/IR-700.md) | **PARTIAL** |
| **IR-948** | Your own Profile mounts the shared view; IR-949 adds its own papers and collaborators — IR-694; no FR- id | [details](traceability/IR-948.md) | **PARTIAL** |
| **IR-949** | Your own Profile reads its Research, Advised and Collaborators lists from IR-696; own-ID backend check returns 200; browser review at 375 and 1280 px remains | [details](traceability/IR-949.md) | **PARTIAL** |
| **IR-326** | Streaming Ask IRIS endpoint — no FR- id; part C of IR-323's "event-shaped answer path", under ADR-028 (one deterministic retrieval call … | [details](traceability/IR-326.md) | **IMPLEMENTED** |
| NFR-U3 | Responsive at 360 px, no horizontal scroll | [details](traceability/NFR-U3.md) | **PARTIAL** |
| NFR-A1 | WCAG 2.1 AA on interactive controls | [details](traceability/NFR-A1.md) | **PARTIAL** |

---

## Open defects

### IR-300: a failed notification left nothing in the logs — FIXED

Every notify function in `apps/notifications/services.py` wrapped its whole body in `except Exception: pass` (18 blocks), so a renamed `NotificationType`, a bad query or a failing email dropped the notice silently. Each function still never raises into its caller; the `except` now calls `_log_failure`, which logs at ERROR with the traceback through the module logger, naming the function and the record (or the request and its record, or the user for a role request).

**Test.** `apps/notifications/test_failures_and_scope.py::NotifyFailureIsLoggedTests` rejects a record through `POST /records/<id>/decide/` with `Notification.objects.create` patched to raise: the decision returns 200, exactly one ERROR record names `notify_decided` and the record, and it carries the traceback. `::NoSilentExceptTests` parses the module and fails on any handler whose body is only `pass`.

Evidence, 2026-10-11, local against a pgvector Postgres: `pytest apps/notifications/test_failures_and_scope.py` — **11 passed**; full backend suite — **2907 passed, 2 failed**. Both failures also fail on `main` without this change: the `ktto_review` and policy source scans walk into a `backend/venv/` checked out inside the tree and cannot decode a cp1252 file there.

**Merged with `main` 2026-10-11.** IR-274 deleted three of the converted functions (`notify_record_reviewed`, `notify_clearance_result`, `notify_resubmit`) and IR-517 added three with bare `except Exception: pass` (`notify_record_withdrawn`, `notify_record_deleted`, `notify_delete_requested`); those three now call `_log_failure` too, so the count is still 18. `pytest apps/notifications` — **20 passed**, IR-517's delete-notification tests included; full backend suite — **3266 passed, 5 failed**, the same five that fail on `main` (the two `venv/` source scans, the two `test_complete_authority` old-URL subtests, and the IR-202 chunker flake).

---

### IR-422: a long paper title crashed record creation (FR-M2-01) — FIXED

`Record.abstract_file` was declared with no `max_length` override, so Django's `FileField` default of 100 applied — a ceiling on the whole stored path (`abstracts/<name>.pdf`), not the filename alone. `load_corpus` (IR-313) and the ordinary submission path both derived the stored filename directly from the source filename or title with no truncation, so any title with a stem over roughly 90 characters crashed with `SuspiciousFileOperation` instead of saving. Found loading a 20-paper astrophysics corpus for the IR-133/IR-394 retrieval eval: 6 of 20 real arXiv filenames (145-149 characters) hit this and aborted the whole `load_corpus` run at the first offender.

**Fix.** `abstract_file_path` (`apps/records/models.py`) replaces the bare `upload_to="abstracts/"` string: the stored name is now a random UUID plus the original extension, so the title's length and any filesystem-hostile characters (`--`, runs of `.`) never reach storage. `max_length` is raised to 255 (migration `records.0013`) for headroom regardless. `load_corpus` also now catches `SuspiciousFileOperation` per-record and reports it like a non-PDF file rather than aborting the batch, as defense in depth for the same class of storage-layer failure. `download_service.resolve_record_download_file` was updated to rebuild the download's suggested filename from `record.title` rather than reading it back off the now-random stored path, avoiding a UX regression (a meaningless UUID filename on download).

**Test.** `apps/records/tests.py::LongManuscriptFilenameTests` posts a manuscript with a 145-char filename stem (matching the reproduction) through the real API and asserts a 201 and a correctly-saved file, rather than only inspecting the field definition. `apps/records/test_load_corpus.py::test_a_title_past_the_old_100_char_ceiling_loads_without_crashing` proves the same at the point the bug was found — a bulk load. `test_a_storage_failure_is_skipped_per_record_not_fatal_to_the_batch` proves the per-record catch independently of the model fix.

Evidence, 2026-09-30, local: `python manage.py test apps.records apps.documents apps.ai` — **252 passed**.

---

### IR-233: a resubmission refused by the upload guard looks like the Record went back to declined (FR-M5-01) — FIXED

**Superseded 2026-10-10 by IR-260:** the new-version endpoint accepts a
metadata-only revision, the strict xfail marker is removed, and all three
regression cases pass. The reproduction and xfail evidence below describe the
pre-cutover system.

**Reproduced 2026-09-15** against the report's own Record (seed_demo's `[DEMO] Declined by IERC, ITSO and KTTO preserved`, id 38 in the dev database). The backend log shows the owner's first `POST /api/v1/reviews/resubmit/` returning **400** with a 77-byte body. That is exactly `{"detail":"Please upload at least one updated document before resubmitting."}`. The Record stayed `declined`, and the paper view kept showing the IERC decline twice: once in the clearance track and once in the review history. After an upload, the second resubmission succeeded, leaving `parallel_review`, IERC `pending`, and ITSO and KTTO `cleared` with `preserved: true`. **The clearance-aware transition itself works.**

**Root cause.** There are two halves. (1) `resubmit_record` accepts only a new `RecordUpload` as evidence of a revision, so a resubmission with no revision is refused, and so is one that only edits metadata. (2) The paper view shows the refusal as a small red line under a button that offers no upload, so a refusal reads as a second decline. The other candidates were ruled out. **Candidate 2:** the IERC decline stored `Review.stage = "ierc"`, so the preserving branch ran: IERC `pending`, ITSO and KTTO preserved. **Candidate 3:** the page did refetch after the successful resubmit, and the refused attempt changed no state to go stale. **Candidate 4:** the UI never called `records/<id>/submit/`. That action still accepts `declined` with no `(declined, submit)` edge in the table, a separate broken entry point that IR-260 removes. **Removed by:** **IR-260** (backend cutover) for the guard, which will accept an upload or a metadata edit under ADR-021 §11. **IR-259** for the display, which moves refusals into the Action required panel. IR-262/IR-263 let an office ask for a document without declining at all.

**Test.** `apps/reviews/test_resubmission_regression.py` sits outside every suite IR-260 retires, and it asserts behaviour through the API rather than stage names.
- `test_resubmission_with_no_revision_is_refused_…` passes. It pins the reported click path, which stays correct under ADR-021 §11, and stops IR-260 flipping the xfail by simply deleting the guard.
- `test_resubmission_after_an_upload_…` passes. It guards the clearance-aware path that already works.
- `test_resubmission_after_a_metadata_revision_…` is `xfail(strict=True, raises=AssertionError, reason="IR-233…")`, so an unexpected pass fails the build and a broken setup step errors instead of passing as the known defect. **IR-260 removes the marker.**

**Note that the xfail pins ADR-021 §11's metadata-edit rule, not the reported click path.** A strict xfail of the literal report is impossible: with an upload it passes today, and with no revision it must keep failing after the fix. **The display half has no regression test**; that is owed to IR-259's Vitest suite.

Evidence, 2026-09-15, backend container: `pytest apps/reviews/test_resubmission_regression.py` gave **2 passed, 1 xfailed**. Without the marker, the xfail test fails on `400 != 200 … Please upload at least one updated document`. With a strict xfail added to the upload test instead, the run reports `XPASS(strict)` → FAILED. The full backend suite gave **841 passed, 1 xfailed, 8 skipped, 4 failed**, run before the no-revision test was added. None of the four failures touches this change: `test_celery_routing` (IR-199, container-only broker difference); a Hypothesis `FailedHealthCheck` in `test_chunker_core[fixed-window]`; and two source-file sweeps (`test_lifecycle` policy mentions, `test_enum_vocabulary` `ktto_review`) that crash on a cp1252 file in a gitignored local `backend/venv/`, visible only through the container's bind mount.

---

## The audit gap — closed by IR-144

Until IR-144, `AuditEvent` had no workflow event, so the research metrics in
[`../mvp-validation/03-final-evaluation-plan.md`](../mvp-validation/03-final-evaluation-plan.md)
(turnaround time and preserved-clearance counts) had no data source. IR-144 adds the workflow
types (see its section above and [`../evaluation/AUDIT_EXPORT.md`](../evaluation/AUDIT_EXPORT.md)).
**The log is not backfilled:** acts before the deployment that carries IR-144 have no rows, and
events not written during the Weeks 11-12 pilot cannot be reconstructed afterwards.

---

## Maintenance

- Add your ticket's file **in the same PR** as the change that affects a requirement, and update this table if a status changes
- Never move a row to VERIFIED without a link to actual evidence
- If a requirement is descoped, set DEFERRED and cite the ADR or SRS amendment — do not delete the row
- Review the whole table before the technical defence; an unverified requirement reported as unverified is defensible, a false VERIFIED is not

### IR-730 — Safe reader progress and bounded depth (ADR-049 §13–17)

Ask IRIS and Paper Chat share an opt-in `runs-reader-1` transport and reader component.
Live/reopened plans use actual journalled IDs, statuses and revisions; run activity is
separate, unknown context has no guessed capacity, and Stop/reconnect/deep requests keep
the reader grant and Record scope. Public projections exclude internal pins, journals,
provider/tool state and diagnostic reasons. Reopened evidence and dependent plans are
withheld when source revisions or current RLS access no longer match. No schema change.

**Tests:** `test_runtime_reader_progress.py`, `test_runtime_reader_edge.py`;
`RuntimeReader.test.tsx`, existing Ask IRIS/Paper Chat/notice suites. Real PostgreSQL
checks include queued/live/reopened/completed/deep/cancelled states from the bounded
AGENT loop. Keyboard/narrow-layout evidence replays those captured public snapshots.
See [verification, public recording and screenshot](evidence/IR-730/README.md).

**Limits:** disabled by default (since IR-863 by the server's `AI_RUNTIME_READER`, not a build flag); the reader refuses the operator echo executor until
an AGENT service is composed. No paid enablement or cutover. Manual compaction is
IR-754, which is implemented and reported as `capabilities.manual_compaction`. Clean-install verification resolves the earlier frontend/typechecking failures;
publication evidence records 5,696 passing backend tests, 1,706 passing frontend
tests and the isolated CI-equivalent setup. Automated standards/spec reviews were performed and
their material findings addressed; independent human approval and CI remain required.

### IR-889 — AI-runtime paid research disclosure (development proxy only)

Research tool outcomes now retain their source revisions outside the provider
payload. Tool messages, recalled Conversation state and subsequent model turns
carry those dependencies through the agent loop. Persisted earlier answers with
no source manifest are explicitly unverified and refused by the paid transport.
The send guard now admits explicitly listed source revisions from public
proxy or synthetic Records in an expiring IR-889 development manifest **through
the recording provider**. Real vendor adapters remain closed until IR-827's
account-specific no-training and retention evidence is recorded. Each
physical attempt rechecks the running fence, reader grant, row-security read,
Paper Chat scope, active chunk revision, non-IP origin and answered embargo.
The exact model, endpoint, account digest and campaign must match the manifest;
production and unconfigured deployments refuse. Changed, revoked, withheld,
untagged and unverifiable prior content sends nothing. Capacity-withheld tool
results become a fixed neutral marker with no source-dependent byte length;
only trusted local control results may use an empty dependency set. Real institutional
Records remain refused. Merged PR #534 records the development decision, while
IR-791's canonical Contact-person answer and IR-827's OpenRouter account and
eligible-endpoint policy evidence remain prerequisites. The exact Luna model
also needs a verified capacity and conservative price before a smoke run.

**Evidence (2026-11-05):** seventeen pure source-provenance and recording-provider
tests passed, covering an allowed proxy payload, withheld/revoked/changed
sources, retry rechecks, missing approval and production refusal. Changed
Python files compiled and passed the repository's flake8 configuration.
The AI runtime suite passed 59 tests; affected backend context and agent-loop
contract tests passed 64 tests. Eight focused real-PostgreSQL tests then passed
under the restricted runtime login: one approved source, five changed/withheld
facts, one expired approval, and one search → read → final-answer run. A full
backend run stopped on unrelated
pre-existing local configuration (`AI_DISCLOSURE_BYPASS_FOR_DEVELOPMENT` in
production-settings test); with it disabled, the next failure was in the
already-dirty `apps.ai.tasks` chunking callback signature.
No live vendor call, cost, or quality result is claimed. IR-889 remains
blocked before real-paper and live-pilot criteria.
