# 08 — Framework & Library Evaluation

Every major dependency, current and candidate, evaluated against: problem solved · complexity · maintenance burden · deployment cost · free-tier compatibility · thesis suitability · production suitability · scalability · vendor lock-in.

**Governing rule:** *do not introduce a framework unless its benefit clearly exceeds its complexity.* Applied symmetrically — it also argues against removing something that is carrying its weight.

---

## Decision table

| Library | Verdict | One-line reason |
|---|---|---|
| Django | **KEEP** | Right framework; batteries used, not fought |
| Django REST Framework | **KEEP** | Correct choice; use more of it (generics, exception handler) |
| `djangorestframework-simplejwt` | **KEEP** | Well configured — rotation + blacklist |
| `django-axes` | **KEEP** | Satisfies NFR-S6 for ~zero cost |
| `django-filter` | **KEEP** | Used properly in `RecordFilter` |
| `django-cors-headers` | **KEEP** | Fix the dev `ALLOW_ALL` setting |
| PostgreSQL | **KEEP** | FTS + pgvector in one store is the whole argument |
| Celery + Redis | **KEEP, collapse to one worker** | Right tool; the three-queue split is unjustified |
| WhiteNoise | **KEEP** | Correct for single-box static serving |
| `pyexcel` + `openpyxl` | **KEEP** | FR-M2-04 needs both |
| `python-decouple` | **KEEP** | Fine; `django-environ` is equivalent, not better |
| `django-storages[s3]` | **DEFER** | Installed, unconfigured. Keep for the S3 path; not MVP |
| `pgvector` | **KEEP — and actually use it** | Listed twice, in no `INSTALLED_APPS`, vectors pickled into a `BinaryField` |
| `openai` | **KEEP, pending AI-5** | Decide the provider first; config names three |
| `sentence-transformers` | **REMOVE** or install deliberately | Imported by code, absent from requirements |
| PyMuPDF | **ADD** | The only extractor worth shipping for MVP |
| `unstructured[pdf]`, `pytesseract`, `Pillow` | **DO NOT RE-ADD (MVP)** | Hundreds of MB for a fallback born-digital PDFs never reach |
| Docling-serve | **DEFER** | 4 GB, called by no code |
| `drf-spectacular` | **ADD** | One dep; kills a defect class and documents the API for the defence |
| `pytest` + `pytest-django` + `factory-boy` | **ADD** | The highest-value addition in this document |
| React 18 | **KEEP** | Right choice |
| TypeScript | **KEEP** | Strict config; needs a `typecheck` script |
| Vite | **KEEP** | Fast, correct, the Dockerfile is already right |
| Tailwind | **KEEP** | Consistently used; `ui/` primitives are good |
| Zustand | **KEEP for client state, shrink** | Right size for auth/UI; `notifications.store.ts` should go |
| `react-router-dom` v6 | **KEEP** | Data-router API used correctly |
| `axios` | **KEEP** | One client, interceptors — fix FE-5 |
| `@tanstack/react-table` | **KEEP** | Already wrapped by `DataTable`; use it in 14 places, not 2 |
| **`@tanstack/react-query`** | **ADD** | See the extended evaluation below |
| `react-hook-form` + `zod` + `@hookform/resolvers` | **KEEP** | The standard to converge on |
| `formik` + `yup` | **REMOVE** | One login form; superseded |
| `@tiptap/react` + `@tiptap/starter-kit` | **REMOVE** | **Zero importers** |
| `recharts` | **REMOVE** | **Zero importers** |
| `react-dropzone` | **REMOVE** | **Zero importers** (`FileUploadZone` is hand-rolled) |
| `react-markdown` + `remark-gfm` + `rehype-highlight` + `highlight.js` | **DEFER** | Only used by the unrouted RAG chat UI. Keep if AI ships; remove with FE-9 if not |
| `date-fns` | **INVESTIGATE** | One importer; `Intl.DateTimeFormat` may cover it |
| ESLint 9 + `@typescript-eslint` + `eslint-plugin-react-hooks` | **KEEP — make it run** | Installed, no flat config, so all three do nothing |
| `vitest` + `@testing-library/react` | **ADD** | No frontend test runner exists |
| LangChain / LlamaIndex | **DO NOT IMPLEMENT** | ~60 lines of explicit code |
| Qdrant / Weaviate / Milvus | **DO NOT IMPLEMENT** | pgvector; no second stateful service |
| FastAPI (the `ai-gateway`) | **DEFER** | Second runtime for unwritten code; see [04](04-ai-rag-architecture.md) |
| n8n | **DO NOT IMPLEMENT** | Already rejected by the team; agreed |
| AWS ECS / RDS / ElastiCache / ALB | **DO NOT IMPLEMENT** | ~$400/mo for a workload that fits on one box |

**Net: −6 dependencies removed, +6 added, and 4 of the additions are test/quality tooling.**

---

## Extended evaluations

Only the decisions where the answer is not obvious.

---

### TanStack Query — **ADD**

**Problem solved.** Server-state caching, request deduplication, invalidation-after-mutation, retry, and one consistent loading/error path. Currently re-decided in 28 components, mostly by omission — `PendingRecordsPage.tsx:14` has no `.catch` at all, and a network failure renders "No pending records."

**The three-way comparison (repeated from [03](03-frontend-architecture.md) because the brief asks for it explicitly):**

| | Keep hand-rolled | One `useApi<T>` hook (~40 lines) | TanStack Query |
|---|---|---|---|
| Cost | 0 | 0 | ~13 KB gz, 1 dep |
| Fixes missing `.catch` | ✗ | ✓ | ✓ |
| Fixes 10 duplicated loading divs | ✗ | ✓ | ✓ |
| Deduplication | ✗ | ✗ | ✓ |
| Cache / stale-while-revalidate | ✗ | ✗ | ✓ |
| Invalidation after mutation | ✗ | ✗ | ✓ |
| Retry / backoff | ✗ | ✗ | ✓ |
| Deletes `notifications.store.ts` | ✗ | partial | ✓ |
| Lines removed | 0 | ~150 | ~300 |
| Learning cost | 0 | 0 | 1–2 days |

**Why the library wins.** The deciding evidence is that this codebase has *already* hand-rolled two of the three things option B does not cover, and got both wrong: `PublishedRecordsPage.tsx:71` uses `JSON.stringify(filters)` as a dependency with an `eslint-disable` — that is a query key — and `notifications.store.ts` is a client-side cache that diverges from the server on the first `markRead`. Writing those correctly *is* writing a smaller, worse TanStack Query. That is the point where benefit exceeds complexity.

**The honest case against.** It is a real concept to learn under deadline. If time is short, **do option B and stop** — it captures the error-handling win for free. Do not do neither. And do not adopt Query while keeping `notifications.store.ts`; two caches for one resource is worse than either alone.

- **Complexity:** Medium (28 pages, but incremental — both styles coexist)
- **Maintenance:** Low; stable API, very widely used
- **Deployment cost / free tier:** None — client-side
- **Thesis suitability:** Good — a defensible, citable architectural decision
- **Production suitability:** High
- **Scalability:** N/A (client)
- **Lock-in:** **Low** — hooks are swappable, server data untouched
- **Risk:** Low · **Dependencies:** **FE-5 first**, or retries amplify the refresh race
- **MVP:** **MVP RECOMMENDED**

---

### Celery + Redis — **KEEP, one worker**

**Problem solved.** PDF extraction (seconds to minutes) and email dispatch must not block the request cycle. Genuinely asynchronous work; a real need.

**Alternatives considered.**

| Option | Verdict |
|---|---|
| **Celery + Redis** | **Keep.** Already integrated, Redis already deployed, the team knows it |
| `django-q2` / Huey | Lighter, fewer moving parts — but Celery is already working and switching costs more than the ~100 MB saved |
| Postgres-backed queue (`django-tasks`) | Removes Redis entirely, attractive for a one-box deployment. **Defer** — Redis is also the right cache for AI-6, so it earns its place |
| `threading.Thread` | Rejected — no retry, no durability; a lost extraction is silent |

**What changes:** three specialised workers and a beat scheduler become **one worker**. No task routing exists (BLOCK-3), so `-Q extraction` and `-Q embedding` consume queues nothing publishes to, and `celery-beat` has no schedule.

- **Complexity:** Low (already integrated) · **Deployment cost:** ~100 MB for Redis
- **Free tier:** Upstash has a usable free tier; a local container is free
- **Lock-in:** Low — `@shared_task` signatures port easily
- **MVP:** **MVP REQUIRED** (one worker)

---

### pgvector vs a dedicated vector database — **pgvector**

**Problem solved.** Similarity search over document embeddings.

| Option | Verdict |
|---|---|
| **pgvector in the existing Postgres** | **KEEP.** No new service, no new backup target, transactional consistency with `Record`, and the compose image is already `pgvector/pgvector:pg16`. Comfortable to hundreds of thousands of vectors — orders of magnitude beyond one university's thesis corpus |
| Qdrant / Weaviate / Milvus | **DO NOT IMPLEMENT.** A second stateful service, a second backup story, a second consistency problem, and an ID-sync path between two stores |
| Pinecone (managed) | Rejected — recurring cost, vendor lock-in, and research abstracts leave campus |
| FAISS in-process | Rejected — no persistence, no concurrency story |

**Deletion test on a separate vector DB: fails.** Removing it and using pgvector *reduces* total complexity by one service.

**Current state is the problem, not the choice.** `pgvector` is listed **twice** in `requirements/base.txt`, is not in `INSTALLED_APPS`, and `RecordEmbedding.embedding` is a `BinaryField` holding `pickle.dumps()` output searched by a Python loop. The `TODO` in `apps/ai/models.py` specifies the correct migration — follow it (AI-3).

- **Complexity:** Low · **Deployment cost:** **Zero** — same container
- **Free tier:** Neon and Supabase both ship pgvector
- **Scalability:** HNSW is sub-second well past this corpus size
- **Lock-in:** Low — it is Postgres
- **MVP:** **MVP REQUIRED**

---

### PDF extraction — **PyMuPDF for MVP, Docling deferred**

**Problem solved.** Text extraction from submitted theses for FTS and embedding.

**Current state:** `documents/tasks.py` implements a three-tier chain (`unstructured` → PyMuPDF → Tesseract). **None of the three is in `requirements/base.txt`** — line 14-17 records their deliberate removal for a Docling migration that was never made. Every extraction fails.

| Option | Memory | Handles scans | Verdict |
|---|---|---|---|
| **PyMuPDF (`fitz`)** | ~50 MB | ✗ | **ADD.** Fast, permissive-enough licence for academic use, excellent on text-layer PDFs — which is what a submitted thesis is |
| Docling-serve | **4 GB** | ✓ | **DEFER.** Over half the hosting budget for a case the MVP corpus rarely contains. Revisit if scanned submissions prove common |
| `unstructured[pdf]` | ~500 MB+ | via OCR | Do not re-add — heavy, and its `fast` strategy is roughly PyMuPDF anyway |
| Tesseract | ~200 MB + system binary | ✓ | Do not re-add for MVP |
| `pdfplumber` / `pypdf` | ~20 MB | ✗ | Viable alternatives; PyMuPDF is faster and more robust on complex layouts |

**Recommendation.** Add `pymupdf`, keep the chain's *structure* (so tiers can return), and let extraction fail honestly on scanned documents — `PdfExtraction.status = "failed"` with a clear error is better than a 4 GB container nothing calls.

> **Licence note worth checking:** PyMuPDF is AGPL-3.0 with a commercial option. Fine for a thesis and for internal university deployment; **verify before profile 4 (commercial product)**. `pdfplumber` (MIT) is the fallback if that becomes a constraint. Flagged in [10](10-architecture-decisions-required.md).

- **Complexity:** Trivial · **Deployment cost:** ~30 MB vs 4 GB
- **MVP:** **MVP BLOCKER** (something must work)

---

### LLM and embedding provider — **decide, then make config agree**

**Problem.** Three configuration sources name three different vendors:

| Source | Says |
|---|---|
| `settings/base.py:180` | `OPENAI_API_KEY` |
| `.env.example:31` | **`ANTHROPIC_API_KEY`** |
| `settings/base.py:179` | `AI_EMBEDDING_MODEL` default **`"TBD"`** |
| `.env.example:32` | `all-MiniLM-L6-v2` (a *local* model) |
| `apps/ai/services/cohere_reranker.py` | a third vendor, as an empty class |

A developer copying `.env.example` gets a key the settings never read.

**Options.**

| Option | Cost | Data leaves campus | Verdict |
|---|---|---|---|
| **API embeddings + API chat model** | ~$0.02 per 1M embedding tokens; chat is the real cost | Yes | **Recommended for MVP** — no model weights, no GPU, no CPU inference in the worker |
| **Local embeddings** (sentence-transformers) **+ API chat** | Embeddings free | Only queries | **Strong alternative for an on-campus deployment.** ~500 MB of weights and CPU inference, but abstracts never leave the building — which matters for pre-publication IP |
| Fully local (Ollama) | Free | No | Rejected for MVP — needs a GPU for usable latency |

**Recommendation.** Pick one, record an ADR, put both behind thin `EmbeddingProvider` / `LLMProvider` protocols so the decision is reversible in one module — and so tests inject a fake and never call a paid API. Replace `"TBD"` with a real default and fail at startup when the key is missing, not at first query.

**Cost control is not optional here** (AI-6): a per-user daily cap via a DRF `ScopedRateThrottle` plus token counts in `AuditEvent.metadata`. A student project needs a spend ceiling more than it needs throughput.

- **Lock-in:** **Medium without the protocols, Low with them.** ~20 lines buys the difference
- **MVP:** **MVP REQUIRED**

---

### LangChain — **DO NOT IMPLEMENT**

**Problem it would solve.** Orchestrating multi-step LLM pipelines, retriever abstractions, provider swapping, memory.

**IRIS's actual pipeline:** embed query → `ORDER BY embedding <=> q LIMIT 5` → format a prompt → one chat completion → return text plus record ids. Roughly **60 lines** of explicit Python.

| Option | Verdict |
|---|---|
| **Explicit code** | **Recommended.** Every step legible, independently testable, no version churn |
| LangChain | Rejected — large transitive tree, frequent breaking changes, and abstractions whose value appears with agents, tool use and complex graphs. IRIS has one chain |
| LlamaIndex | Rejected — same reasoning, RAG-specialised |
| n8n | Already rejected by the team in the SRS change history (May 2026). Agreed — a workflow-automation server is not an application framework |

**Deletion test:** removing LangChain from a five-step pipeline moves complexity *out* of a dependency and into 60 readable lines. That is a gain, not a relocation. Provider swappability — the one real benefit — costs ~20 lines of protocol.

- **MVP:** **DO NOT IMPLEMENT**

---

### `drf-spectacular` — **ADD**

**Problem solved.** The API contract is retyped by hand in `frontend/src/types/` with no drift detection — and it has already drifted: `PaginatedResponse<T>` declared four times, four endpoints returning bare arrays typed as paginated, a local `Department` dropping two fields.

**Recommendation, split by cost:**

| Step | Cost | Verdict |
|---|---|---|
| Add `drf-spectacular`, expose `/api/schema/` + Swagger UI | 1 dep, ~10 lines of settings | **MVP RECOMMENDED.** Also doubles as thesis-defence API documentation, which is worth something on its own |
| Generate the TS client and wire it into the build | New codegen step, regenerate-on-change discipline | **POST-MVP.** Real, but it is a build-pipeline commitment and there is no CI to hang it on yet |
| One shared `PaginatedResponse<T>`; paginate the four bare-array endpoints | Trivial | **MVP REQUIRED.** Do this regardless |

- **Complexity:** Low · **Lock-in:** None — OpenAPI is a standard
- **MVP:** **MVP RECOMMENDED**

---

### Testing stack — **ADD (highest value in this document)**

**Problem solved.** Zero tests across both codebases, and it is the direct cause of every blocker in this review.

| Layer | Recommendation | Why |
|---|---|---|
| Backend runner | `pytest` + `pytest-django` | Parametrisation is what makes the table-driven lifecycle and policy tests cheap |
| Backend fixtures | `factory-boy` | Six roles × twelve statuses needs factories, not fixture JSON |
| Frontend runner | `vitest` | Shares the Vite config; no separate transform pipeline |
| Frontend rendering | `@testing-library/react` | The standard; encourages behaviour over implementation |
| Lint | ESLint 9 flat config | All three plugins are **already installed and doing nothing** |
| Typecheck | `"typecheck": "tsc --noEmit"` | Types are currently checked only as a side effect of `build` |

**Alternatives.** Django's built-in `TestCase` — works and avoids a dependency, but loses parametrisation, which is precisely what tiers 4-5 need. Jest — rejected, needs its own transform config. Biome instead of ESLint — faster, but `eslint-plugin-react-hooks` has no equal-maturity Biome equivalent, and both plugins are already paid for.

**Start with the seams, not coverage.** In order: import-smoke test → `makemigrations --check` → `docker compose config` → lifecycle table → policy table → one regression test per fixed IDOR.

- **Complexity:** Low (setup) · **Deployment cost:** None (dev-only)
- **Thesis suitability:** **High** — a test plan is an assessable artefact, and `docs/README.md` already promises a `TEST_PLAN.md` that does not exist
- **MVP:** **MVP BLOCKER** (the first three tiers)

---

### Zustand — **KEEP, shrink**

Right-sized for client state: three small stores, no boilerplate, no context nesting. `auth.store.ts` is a legitimate use.

Two changes: delete the three colliding exports at `auth.store.ts:100-102` (FE-2 — an exported `useRole` that name-collides with `hooks/useRole.ts` and behaves differently), and delete `notifications.store.ts` entirely once TanStack Query lands — it is server state modelled as client state, and it already diverges from the server on the first `markRead`.

- **Lock-in:** Very low · **MVP:** **KEEP**

---

### Tailwind — **KEEP**

Consistently applied; the `ui/` primitives (Button, Input, Modal, Card, Badge, Spinner, Toast) are a real, used design system. No component library (MUI, Chakra, shadcn) is warranted — one would duplicate what exists.

One observation: repeated literal class strings — the loading state `p-8 text-center text-gray-400 text-[13px]` appears in **10 files** while `Spinner` exists and is used in 5. That is a component problem, not a Tailwind problem, and FE-3/FE-8 fix it at the primitive level.

- **MVP:** **KEEP**

---

## Additions and removals

**Add (6):** `pymupdf`, `drf-spectacular`, `pytest` + `pytest-django` + `factory-boy`, `@tanstack/react-query`, `vitest` + `@testing-library/react`, and an `eslint.config.js` (no new package — three are already installed and inert).

**Remove (6+):** `formik`, `yup`, `@tiptap/react`, `@tiptap/starter-kit`, `recharts`, `react-dropzone`. Deduplicate the double `pgvector` entry. Remove `sentence-transformers` from the code or add it to requirements — currently imported and uninstalled.

**Defer (4):** Docling-serve, FastAPI gateway, `django-storages` S3 configuration, TS client codegen.

**Never (5):** LangChain, LlamaIndex, n8n, a dedicated vector database, AWS managed infrastructure.
