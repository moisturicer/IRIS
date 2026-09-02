# 10 — Architecture Decisions Required & Decision Summary

Two parts: **open questions only the team can answer**, and the **ARCHITECTURE DECISION SUMMARY** requested by the brief.

---

# Part 1 — Decisions required

Each of these blocks or shapes a recommendation elsewhere in this review. None can be resolved by reading the code, because the code is ambiguous about intent — which is itself the finding.

---

## D-1 · Is `apps/storage` personal or institutional?

**Blocks:** SEC-3 (MVP BLOCKER)

**The ambiguity.** `StorageFolder.created_by` and `StorageFile.uploaded_by` model *personal* ownership. But the SRS lists both **FR-M2-06 Institutional File Storage Management** and **Personal File Storage** (SDD 3.2.6 and 3.2.7), and the views enforce neither — every endpoint is bare `IsAuthenticated` with unfiltered querysets, so any user can delete any user's files.

**The options.**

| Option | Implication |
|---|---|
| **A · Personal** | Filter every queryset by `created_by`/`uploaded_by`; detail views get `IsOwnerOrStaff` |
| **B · Institutional (shared, staff-managed)** | Reads open to authenticated users; **writes and deletes restricted to staff roles** |
| **C · Both** | Add an `owner`-nullable or `scope` field distinguishing personal from institutional trees |

**Recommendation: A for the MVP.** The models already say personal, it is the smaller change, and C can be added later without migrating A's data. **The one option that is not available is the status quo** — unrestricted delete by any authenticated user is not a design, it is an omission.

**Also required:** `/storage` currently routes to a 13-line `ComingSoonPage` stub while a 204-line `FolderBrowserPage` sits unrouted. Decide which ships; delete the other.

---

## D-2 · Are IRIS office roles Django administrators?

**Blocks:** SEC-4 / WF-4 (MVP BLOCKER)

**The ambiguity.** Migration `accounts/0005` sets `is_staff=True` for RDCO, KTTO, ITSO **and** IERC, with the stated rationale that "the DRF `IsStaff` permission check works via both the role name AND the Django flag." But `is_django_staff()` is then used as a blanket bypass in `IsAdmin`, `_can_review()` and `_can_submit_clearance()` — so ITSO and IERC gain user-role management, account locking, session revocation, and the ability to approve at any workflow stage including RDCO's final publication.

Two meanings of "staff" were merged: *IRIS reviewing office* and *Django site administrator*.

**The options.**

| Option | Implication |
|---|---|
| **A · Separate them** | Reverse `is_staff` for ITSO/IERC (and arguably KTTO); keep it only for genuine administrators. `IsStaff` continues to work via role names |
| **B · Keep the flag, remove the bypass** | Leave `is_staff=True` but stop treating it as authorization — `IsAdmin` tests `ADMIN_ROLES or is_superuser`; the workflow predicates drop `is_django_staff` entirely |
| **C · Status quo** | ITSO/IERC remain de-facto administrators and can bypass every review stage |

**Recommendation: B, optionally with A.** B is the minimal correct change and does not touch existing accounts' Django-admin access. C should be an explicit decision if chosen, because it makes the four-office separation of duties — the substance of SRS Module 5 and the reason IRIS exists rather than a shared drive — advisory rather than enforced.

**Warning:** this removes capabilities ITSO/IERC users may currently be using. Confirm before applying.

---

## D-3 · What is the record access PIN for?

**Blocks:** SEC-6 (MVP REQUIRED)

**The ambiguity.** `RecordAuthPin` issues and verifies one-time emailed PINs correctly, then enforces nothing: verification returns `{"verified": true}` and persists no grant that any later request consults. No view outside `RecordAuthPinViewSet` references the model. Any authenticated user can also request a PIN for any record id.

**The options.**

| Option | Implication |
|---|---|
| **A · Real access control** | Verification creates a server-side grant (row or short-lived scoped token bound to `user`+`record`); record and document endpoints require it. Appears to be the SDD's intent (3.5.2, "Auth PIN for Gated Record Access") |
| **B · Confirmation of intent** | Keep the UX, stop describing it as access control, and rely on role/ownership checks |
| **C · Remove** | Delete the model and views |

**Recommendation: A if the SRS requires gated access; otherwise B.** The status quo is the worst of the three because the gate is *relied upon* while enforcing nothing. Either way, restrict issuance to records the caller can already see.

---

## D-4 · Which AI provider, and does data leave campus?

**Blocks:** AI-5 (MVP REQUIRED), and shapes AI-2

**The ambiguity.** `settings/base.py` reads `OPENAI_API_KEY`; `.env.example` ships `ANTHROPIC_API_KEY`; `AI_EMBEDDING_MODEL` defaults to `"TBD"` in settings and `all-MiniLM-L6-v2` (a local model) in `.env.example`; a `CohereReranker` stub names a third vendor. A developer copying `.env.example` gets a key the settings never read.

**The real question underneath** is not which vendor but **whether unpublished research abstracts may be sent to a third-party API.** IRIS exists to manage confidential pre-publication IP disclosures. That is an institutional data-governance question, not a technical one.

**The options.**

| Option | Data leaving campus | Cost | Complexity |
|---|---|---|---|
| **A · API embeddings + API chat** | Abstracts and questions | Low, usage-based | Lowest |
| **B · Local embeddings + API chat** | Questions only | Chat only | ~500 MB weights, CPU inference |
| **C · Fully local (Ollama)** | Nothing | Free | Needs a GPU for usable latency |

**Recommendation: A for the MVP, behind `EmbeddingProvider` / `LLMProvider` protocols** so B or C is a one-module change. But **check with the research office first** — if the answer is "unpublished IP disclosures may not leave university systems," that is B or C, and it changes the deployment profile.

Whichever is chosen: record it as an ADR, and add the per-user spend cap from AI-6 before the first live key.

---

## D-5 · Is the Excel import's pipeline bypass intentional?

**Shapes:** WF-1, BE-5

**The ambiguity.** `import_excel` writes `pipeline_status="published"` directly, bypassing adviser approval, RDCO intake, IERC ethics, ITSO technical and KTTO IP review. The docstring says this is deliberate — *"Legacy imports bypass the review pipeline — staff is the implicit reviewer"* — which may be a legitimate business rule for migrating historical records.

**The problem is not the rule; it is that the rule is a bare assignment** indistinguishable from an oversight, in a method with no permission check beyond `IsStaff` and no audit event.

**The options.**

| Option | Implication |
|---|---|
| **A · Intentional, make it explicit** | A declared `legacy_import` transition in BE-1's table, restricted to RDCO, emitting an audit event |
| **B · Import to `draft`** | Imported records enter the pipeline like any other |
| **C · Import to a distinct `archived` status** | Visible in search, never claimed to be reviewed |

**Recommendation: A, restricted to RDCO.** Bulk import is a real need; it should be an auditable, named capability rather than a side effect of a spreadsheet upload available to four office roles.

---

## D-6 · Are the ten unused domain models still in scope?

**Shapes:** BE-9

**The ambiguity.** `ResearchLink`, `Publication`, `Conference`, `Budget`, `Collaboration` and five lookup tables (`PublicationLevel`, `ConferenceLevel`, `BudgetType`, `CollaborationType`, `AuthorRole`) have **zero** references in any serializer, view or service. But they map directly to SRS Module 2 fields.

**The options.**

| Option | Implication |
|---|---|
| **A · Still in scope, not yet built** | Keep; add a `TODO` naming the FR each serves |
| **B · Out of scope** | Drop them — a destructive migration |
| **C · Uncertain** | Keep for the MVP; revisit before the first production deployment |

**Recommendation: C, then A or B before deployment.** Dropping tables is irreversible without a backup; carrying ten unused models costs almost nothing. Check the SRS rather than the code — the code cannot answer this.

---

## D-7 · PyMuPDF's licence for a commercial future

**Shapes:** BLOCK-4, and profile 4 (future business product)

**The issue.** PyMuPDF is AGPL-3.0 with a paid commercial licence. Fine for a thesis and for internal university deployment. **If IRIS becomes a commercial product**, AGPL obligations attach to network-accessible use.

**The options.** Accept for now and revisit at commercialisation · switch to `pdfplumber` (MIT) or `pypdf` (BSD) now, at some extraction-quality cost · budget for the commercial licence.

**Recommendation: accept for the MVP, record it as an ADR** so it surfaces at the commercialisation decision instead of being discovered then. `pdfplumber` is the drop-in fallback.

---

## D-8 · Who owns the missing documentation?

**Shapes:** AI-7

**The issue.** `docs/README.md` presents itself as the engineering documentation hub and links **nine documents, seven of which do not exist**: `SOFTWARE_ENGINEERING_PLAN.md`, `SDLC_PROCESS.md`, `SECURITY.md`, `SECURITY_RISK_REGISTER.md`, `TEST_PLAN.md`, `TRACEABILITY_MATRIX.md`, `DEVELOPMENT_GUIDE.md`. The prior architecture review also cites a companion `architecture_review_and_aws_roadmap.md` that is absent, and both RAG documents link source files via `file:///c:/Users/edlav/...` — another contributor's local filesystem.

**Options.** Write them · remove the links · mark them explicitly as planned.

**Recommendation: remove the dead links now (10 minutes), and write `TEST_PLAN.md` and `SECURITY.md` for real** — both are assessable thesis artefacts, and this review supplies most of the content for both. Replace absolute paths with repository-relative links.

---

# Part 2 — ARCHITECTURE DECISION SUMMARY

---

## KEEP

Working, correctly chosen, or carrying its weight. Do not change these.

| What | Why |
|---|---|
| **Django + DRF** | Right framework for a workflow-heavy, permission-heavy records system |
| **Eight-app boundary split** | `accounts / records / reviews / documents / notifications / audit / storage` follow real domain seams |
| **`storage` separate from `documents`** | A personal file browser and per-record attachments are different concepts; merging concentrates complexity |
| **`reviews/services.py` as a service layer** | A genuine state machine with guarded transitions — the pattern the rest of the backend should copy |
| **The `RecordClearance` model** | The right abstraction for parallel office review; a single status field could not express it |
| **Clearance-smart resubmission** | Resetting only the declining office is real domain insight. Keep it |
| **The unified `AuditEvent` model** | One table + JSONB metadata replacing six event tables was the right call |
| **JWT with rotation + blacklisting** | Correctly configured; `ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION` |
| **`django-axes`** | NFR-S6 satisfied for near-zero cost |
| **Read-only `role` / `is_staff` in `UserSerializer`** | The check that prevents self-escalation via `PATCH /users/me/`. Verified correct |
| **Session management** (`ActiveSessionsView` / `RevokeSessionView`) | Genuinely good and rare at this project size |
| **Download tokens** | Short-lived, typed, signed, re-verified against the DB |
| **PostgreSQL + FTS + pgvector in one store** | No second stateful service, no sync path, no second backup target |
| **Celery + Redis** | Real async need, correctly identified |
| **React + TypeScript (strict) + Vite + Tailwind** | All correct; the `ui/` primitives are a real design system |
| **Zustand for client state** | Right size for auth and UI state |
| **`@tanstack/react-table`** | Already wrapped by `DataTable`; use it more, not less |
| **react-hook-form + Zod** | The form standard to converge on |
| **One-box Docker Compose hosting** | Correct for all four target profiles up to real institutional adoption |

---

## CHANGE

| What | To what | Priority |
|---|---|---|
| `records/views.py` undefined names + misplaced methods | Import six names; move four methods back into `DownloadRequestViewSet` | **BLOCKER** |
| Ten Docker services | **Five** — `db`, `redis`, `backend`, `celery`, `frontend` | **BLOCKER** |
| Three Celery workers + beat on dead queues | **One worker**, default queue | **BLOCKER** |
| Three-tier PDF chain with no installed libraries | **PyMuPDF only** | **BLOCKER** |
| Prod port `80:80` | `80:8080` (nginx-unprivileged listens on 8080) | **BLOCKER** |
| `RecordViewSet.get_queryset` filtering only `list` | `visible_to(user)` for **all** actions | **BLOCKER** |
| Twelve endpoints with no object-level check | Route through `core.permissions` | **BLOCKER** |
| `is_django_staff` as a blanket authorization bypass | `ADMIN_ROLES or is_superuser`; remove from workflow predicates | **BLOCKER** |
| Vectors as pickled `BinaryField` + Python cosine loop | pgvector `VectorField` + HNSW + ORM `CosineDistance` | REQUIRED |
| Provider config naming three vendors | One provider, behind protocols; all three config sources agree | REQUIRED |
| Workflow transitions with no transaction | `transaction.atomic()` + `on_commit` notifications | REQUIRED |
| 12 bare `except Exception: pass` | `logger.exception(...)` | REQUIRED |
| Token refresh writing to unread `localStorage` | One storage module; interceptor calls `setTokens`; dedupe in-flight refresh | REQUIRED |
| Dev `CORS_ALLOW_ALL_ORIGINS` with credentials | Explicit origin list | REQUIRED |
| Four bare-array endpoints typed as paginated | Paginate them; one shared `PaginatedResponse<T>` | REQUIRED |
| RAG docs written in the present tense | Retitle as target architecture; add per-phase status; fix dead links | REQUIRED |
| 18 `pipeline_status` assignments in 4 modules | One `RecordLifecycle` transition table | RECOMMENDED |
| Five encodings of `{ITSO, IERC, KTTO}` | One `TextChoices` enum per concept | RECOMMENDED |
| Server state hand-rolled in 28 components | TanStack Query, one hook per resource | RECOMMENDED |
| 14 hand-rolled tables | `RecordListPage` / `ApprovalQueuePage` on `DataTable` | POST-MVP |
| Two form stacks | react-hook-form + Zod everywhere | RECOMMENDED |

---

## REMOVE

| What | Why |
|---|---|
| **`ai-gateway` and `docling` compose services** | One builds from a non-existent directory; the other is called by no code |
| **`celery-extraction`, `celery-embedding`, `celery-beat`** | Consume queues nothing publishes to; beat has no schedule |
| **The nginx `/media/` location** | Serves every uploaded document with no authentication |
| **`apps.ai`** (app, `INSTALLED_APPS` entry, 15 files) | Never routed, no migrations, models shadowed, all services `pass` |
| **The dead AI chat UI** (~840 lines) | `RAGChatPage` + 7 components + `chatStorage` + `types/chat.ts` — unrouted |
| **Superseded router guards** | `PrivateRoute`, `RoleRoute`, `ForbiddenPage` — replaced by `ProtectedRoute` |
| **Colliding `useRole` / `useIsStaff` exports** in `auth.store.ts` | Name-collide with `hooks/useRole.ts` and behave differently |
| **`notifications.store.ts`** | Server state as client state; already diverges from the server |
| **Duplicate `features/discover/discoverUtils.ts`** | Conflicting duplicate of `lib/discoverUtils.ts` with different badge rules |
| **Unrouted pages** | `AccessRequestsPage`, `FolderBrowserPage` (pending D-1) |
| **Dead API modules** | `api/dashboard.ts`, `api/storage.ts` |
| **`MyRecordsViewSet`** | Unrouted duplicate of `RecordViewSet.mine` |
| **`build_zip_for_record`** | Zero callers, and contains an undefined `BytesIO` |
| **Five unused permission classes, four unused exceptions** | Zero references, while their intent is re-implemented inline |
| **`LegacyFolder`** | `managed=False`; docstring says "DO NOT use" |
| **28 lines of commented-out view** | `records/views_dashboard.py:55-82` |
| **`formik`, `yup`** | One login form; superseded |
| **`@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone`** | **Zero importers** |
| **Duplicate `pgvector` entry** | Listed twice in `requirements/base.txt` |
| **Seven dead links in `docs/README.md`** | The documents do not exist |

---

## DEFER

| What | Until |
|---|---|
| **FastAPI `ai-gateway`** | Measured evidence that AI load degrades CRUD endpoints — **and the code to extract exists** |
| **Docling-serve** | Scanned submissions prove common enough to justify 4 GB |
| **Domain-event bus** | A **second** real subscriber appears (one adapter is a hypothetical seam; two is a real one) |
| **`ApprovalRequest` helper** | After the blockers; share the guard-and-stamp, never the model |
| **TS client codegen from OpenAPI** | CI exists to hang it on |
| **`django-storages` S3** | Media outgrows one box — note `build_zip`'s `.path` breaks that day |
| **Gunicorn `gthread` workers** | AI endpoints ship |
| **`RecordListPage` / `ApprovalQueuePage`** | TanStack Query lands first |
| **Splitting `DocumentsPage` / `SignupPage`** | Readability only |
| **httpOnly refresh cookies** | Post-MVP; needs CSRF design and an ADR |
| **Migration squashing** | Before the first real deployment |
| **Full WCAG 2.1 AA audit** | Institutional adoption |

---

## INVESTIGATE

| What | Question | Owner |
|---|---|---|
| **D-1 `storage` scope** | Personal, institutional, or both? Blocks SEC-3 | Team + SRS |
| **D-2 `is_staff` semantics** | Are office roles Django administrators? Blocks SEC-4 | Team |
| **D-3 PIN purpose** | Access control or confirmation? Blocks SEC-6 | SRS / SDD 3.5.2 |
| **D-4 AI provider + data governance** | May unpublished abstracts leave campus? | Research office |
| **D-5 Excel import bypass** | Intentional? Restricted to whom? | Team |
| **D-6 Ten unused models** | Still in SRS Module 2 scope? | SRS |
| **D-7 PyMuPDF AGPL** | Acceptable for a future commercial product? | Team |
| **D-8 Missing documentation** | Write, remove, or mark as planned? | Team |
| **Dead API members** | Per-member call-site audit not completed in this pass | Dev |
| **KTTO resubmission inference** (WF-7a) | Should the declining stage be recorded rather than inferred? | Dev |
| **`_all_clearances_done` semantics** (WF-7b) | Should it count `cleared`, not `not pending`? | Dev |
| **`Record.access_count`** | Incremented by an endpoint any user can call, with no dedup — is it a metric anyone trusts? | Team |

---

## Closing

The architecture is **not** the problem. The domain model is sound, the app boundaries are real, the workflow design is genuinely good, and the technology choices are appropriate for every one of the four target profiles.

The problem is that **nothing executes the code before it is committed**. Zero tests, no working lint, no typecheck step, no CI. Five things that stop IRIS running are all machine-detectable, and four of them would be caught by a workflow that takes an afternoon to write and under two minutes to run.

Fix the blockers, close the authorization holes, then add that workflow — and the rest of this review becomes safe to attempt.
