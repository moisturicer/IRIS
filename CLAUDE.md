# CLAUDE.md — IRIS

Guidance for AI assistants working in this repository. Keep changes grounded in what the code actually does.

## Repository

IRIS is an institutional research and IP disclosure workflow system for CIT-U, built as a four-person capstone thesis with a commercial track.

**The thesis contribution is the workflow**: type-differentiated routing, parallel multi-office clearance, and **clearance-aware resubmission** — when one office requires revisions, only that office's clearance resets and the others are preserved. **RAG is thesis-critical too, as of 2026-09-04** — the earlier "not the AI" framing is reversed; see [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Research Impact (amended) and the Scope rule below.

## Baseline branch

**`main`.** Cut every branch from it and target it in PRs. `feat/rag-service` — where the RAG/AI work in this file was built — is merged in as of this commit and is no longer a separate baseline.

`refactor/docker-service` is **retired** — it is fully contained in `main` (`git merge-base --is-ancestor` confirms it), so cutting from it now would branch from a dead ref. Earlier guidance naming it as the baseline, or as an "integration branch" alongside `main`, is superseded by this line.

## Jira and Git convention

**Every development task corresponds to a Jira issue, and the issue key is the identifier that ties the whole lifecycle together.**

**Branch** — `<type>/IR-XXX-short-description`, types `feature` `fix` `refactor` `test` `docs` `chore`:
```
feature/IR-124-rag-retrieval      fix/IR-131-pdf-validation
test/IR-140-document-ingestion    docs/IR-150-rag-architecture
```

**Commit** — Conventional Commits with the key as scope:
```
feat(IR-124): implement RAG retrieval
fix(IR-131): validate uploaded PDFs
```

**PR title** — `IR-124 Implement RAG retrieval`.

### Rules

1. **Identify the Jira issue before starting.** Read it and its acceptance criteria; confirm it is the right thing to work on.
2. **Never invent a Jira issue key.** If no issue exists for substantive work, **create one first or flag it** — do not fabricate an identifier or work without one.
3. Create the branch from the integration branch, named per the convention.
4. Move the card to **In Progress** when you start.
5. Implement, adding or updating tests where applicable.
6. Run the relevant checks and record what you ran and what happened.
7. Commit with the key in the scope. **No AI attribution** — no `Co-Authored-By`, no generated-with trailer.
8. Push **and open the PR in the same step.** A pushed branch without a PR is incomplete work.
9. Report CI and test status honestly, including failures and why.
10. Update the Jira card, moving it to **In Review** only once the PR exists.
11. **Never mark work Done because the implementation was written.** Done is defined in `docs/engineering/DEFINITION_OF_DONE.md` §4 and requires review, approval and evidence.

Full specification: [`docs/engineering/SDLC.md`](docs/engineering/SDLC.md) §2-4a.

## Architecture — what actually exists

| Component | Reality |
|---|---|
| Backend | Django 5 + DRF, `backend/apps/{accounts,records,reviews,documents,notifications,audit,ai}` |
| Frontend | React 18 + TypeScript + Vite + Tailwind + Zustand, `frontend/src/` |
| Database | PostgreSQL. `Record.search_vector` (GIN, weighted) is maintained and **works** |
| Async | Celery + Redis |
| Deployment | Docker Compose, dev and prod |
| **AI gateway** | `ai/` is FastAPI in ports-and-adapters shape: `domain/ports.py`, `infrastructure/openai_adapter.py` (the only adapter — no local model, ADR-008/015), `api/`. **[ADR-014](docs/adr/014-ai-gateway-as-a-service.md) adopts it as a sixth service, under five preconditions** — service-to-service auth, no public port, no CORS, **no direct DB access** (Django owns retrieval and visibility filtering), and it must boot. **[ADR-017](docs/adr/017-asgi-deployment-for-gateway-streaming.md) adds a sixth requirement on Django's side**: ASGI deployment (`gunicorn` + `uvicorn.workers.UvicornWorker`), so Django can call the gateway without blocking one of its four workers. **Corrected 2026-09-17, verified by importing the app**: the gateway **boots** and mounts `/api/v1/ai/ask` and `/api/v1/ai/embed` — `ai/services/chat_service.py` and `embedding_service.py` both exist (IR-156). The earlier "`chat_service` does not exist" claim is stale and removed. Service auth, no CORS and no public port are enforced (`ai/main.py`), and ADR-014's IR-826 amendment allows the runtime's `iris_ai_runtime` login. `backend` runs ASGI in production (gunicorn + `UvicornWorker`); IR-504 made SSE actually stream there (`apps/ai/streaming.py`). **[ADR-024](docs/adr/024-embedding-path-bypasses-the-gateway.md) takes embedding off the gateway entirely** — `tasks.embed_record` posted to `/api/v1/ai/internal/embed/` (a route that does not exist), and `EmbedResponse` returns no vector field anyway, so that call could never have worked. Django now embeds in-process via the `EmbeddingProvider` port — **done in IR-281**, for both record-level and chunk-level vectors, with a test that fails if any module under `apps/ai/` reads `AI_GATEWAY_URL` again. The gateway keeps only its ADR-014 streaming-chat mandate. **IR-722 adds AI-owned runs (ADR-049)**: schema `iris_ai`, migrated only by `python -m ai.runs.migrate` and written only by `iris_ai_runtime`, with submit/status/cancel/reopen/delete routes under `/api/v1/ai/runs` and `/api/v1/ai/conversations` authenticated by a Django-issued `reader_session` grant (`POST /api/v1/ai/runtime/grant/`) verified inside PostgreSQL. Deterministic executor only at IR-722 (superseded by IR-862 below: `RUNS_EXECUTOR=agent` builds the AGENT executor); every `RUNS_*` limit is required and none is approved. Django's own AskRuns are untouched. **IR-863 puts the reader on it behind one server-side switch**: `AI_RUNTIME_READER` (off) is read by the browser from `GET /api/v1/ai/reader/` and by nginx's entrypoint, and the edge grant refuses while it is off, so the browser cannot choose the runtime path itself; off, Ask IRIS sends exactly the requests it did before. **IR-719 gives those runs local, read-only research tools** (`ai/research/tools.py`: keyword `search`, `open_passage`, `read_page`, `outline`; `semantic_search` is declared and always `provider_gated`), reading under the `reader_session` grant, which `ai/0037` now lets read what its reader may, optionally scoped to one Paper Chat Record. Handles are run-bound, expire with the run and refuse a replaced source; no tool calls Django or a model. **IR-723 queues those runs**: submit commits a `queued` run and then wakes workers through Redis (`RUNS_REDIS_URL`, a hint only); `python -m ai.runs.worker` (Compose profile `runs`) claims from PostgreSQL with deep runs capped below the worker slots, per-reader caps and `503 busy` past the queue bounds, reading under the reader's stored grant, which a reconnect renews. Disconnect never cancels. **IR-726 gives the reader a reconnect cursor and an explicit Retry**: `GET /api/v1/ai/runs/<id>?after=N` (reader protocol) replays the run's journal past `N` as allowlisted entries and returns a `cursor`; `POST /api/v1/ai/runs/<id>/retry` (migration `0016_retry.sql`, `ask_run.retry_of`) starts a new linked AskRun for the reader's own run that ended `cancelled`, `expired` or `failed` with its Conversation unmoved, admitted afresh with the configured limits, so the first run's allowance and charges are never reset. Stop, Stop against final commit and takeover, and the lost-wakeup/deletion/delayed-worker seam are proven on real PostgreSQL in independent processes (`test_ai_runtime_lifecycle_db.py`, registered in the IR-608 `durability` suite); no live provider is involved. Every new `RUNS_*` limit is required and none is approved. **IR-880 keeps a running investigation reading past its first grant**: `RunService.execute` builds `ResearchTools(follow_stored_grant=True)`, so each tool call reads the run's *currently stored* `reader_grant` inside its own short transaction (no connection held across inference), which a reader's reconnect renews only for a grant of exactly the Conversation's scope (IR-723); the tools also refuse a stored grant whose scope differs from the claim's, a reader who stops reconnecting, is deactivated or loses access still ends the run at the next read or provider admission, and a tool built without the flag keeps reading under the grant it was given. **IR-724 resumes an interrupted investigation**: after each completed tool step the AGENT saves a fenced checkpoint (`iris_ai.run_checkpoint`, `0013_checkpoint.sql`; `ai/agent/checkpoint.py`) of the ordered Conversation, its call ids, source pointers, task key, pin, Bounds and spend; a worker that takes the run over restores it only when all still match and every recovered handle reauthorizes, else rebuilds from the question. Its budget starts at what the ledger already charged, so a takeover never renews the allowance or the steps; at most one Turn, not exactly-once billing. **IR-734 compacts a long Conversation**, optional and off unless `RUNS_AGENT_COMPACTION` is set (no value approved): at a capacity-checked threshold the same AGENT summarizes older whole exchanges, as an admitted, journalled `compact` attempt within the run's allowance and bound, into a derived handoff (`ai/agent/compaction.py`). The application keeps the shown order, focus, plan and compacted Turn ordinals. The handoff is committed to `iris_ai.conversation_handoff` (`0015_handoff.sql`) only under the run's fence at its base revision with current sources, and opens later runs while still valid; checkpoints are now `agent-checkpoint-3`, which adds a digest of the instructions and tool schemas the history was sent under (IR-736), so a changed prefix or schema rebuilds from the originals instead of replaying a signed artifact. **IR-754 lets a reader ask for compaction** (`POST /api/v1/ai/conversations/<id>/compact`, a run of its own with `pinned.kind = "compact"`, no question and no Turn, through the same summarizer, admission and handoff, reported by `capabilities.manual_compaction`) **and IR-735 lets the agent recover what compaction condensed** under pin `agent-research-4`/`research-4`, which the profile now pins: `recover_turn(turn)` rereads one original Turn the run's reader may still read (same live Conversation and scope, every source and counted Record current, else the same refusal as a missing Turn) and re-binds its citations to fresh passage handles, so an exact value is cited from the source, never from a summary. A run carrying a handoff rechecks its Turns and sources before every provider attempt and at commit, and stops `source_changed` if one is gone. Deletion needed no new table, and the reader projection publishes only `compaction` outcome and counts. No live paid effect: IR-725's guard still withholds tool results. **IR-727 adds the pinned AGENT contract** (`ai/agent/`): typed turns (text, parallel tool groups, stop reasons, opaque artifacts bound to the pin that produced them), a chat-completions dialect, and `AgentExecutor`, which refuses non-final output and unsupported pins as `unavailable`. `LLMProvider.converse` is additive and refuses by default. Only the recording provider implemented it at IR-727, when no route built the agent executor (superseded by IR-860 and IR-862 below). **IR-725 admits every AI-runtime provider attempt** (`ai/admission/`) in Django's own ledger (`ai_providercampaign`/`ai_providerreservation`, IR-545) — one ledger, rows marked `owner = 'ai'` (additive migration `ai/0038`), the same `AI_ADMISSION_*` limits, with the run's AskRun allowance as its ceiling across every fence. `AdmittedAgentProvider` reserves, rechecks run/reader/deadline/provider policy just before sending, sends the reserved cap and settles each attempt including retries; `AgentExecutor` refuses a paid provider that is not admitted. Its guard withholds any Record evidence, since the AI runtime has no disclosure decision yet. `python -m ai.admission.report <run_id>` shows a run's spending. **IR-732 fits every AGENT request to verified model capacity** (`ai/agent/context.py`): the serialized payload is measured against the adapter's declared `Capacity` with output, reasoning, next-result and one-repair reserves held back; unknown capacity refuses, a tool result that does not fit is withheld by an explicit marker, and occupancy stays an estimate distinct from the byte-based paid reservation. **IR-860 adds the real adapter** (`OpenAICompatibleAgentProvider`, `ai/infrastructure/openai_adapter.py`): plain `httpx` to the configured chat-completions endpoint, no retries, capacity declared per model in required `AGENT_LLM_*` settings (`agent_config.py`; an undeclared model stays `capacity_unknown`), and it refuses to send outside an attempt `AdmittedAgentProvider` admitted. **IR-862 wires it into the worker**: `RUNS_EXECUTOR=agent` pins new runs to the research Conversation and requires the whole profile (`ai/runs/agent_profile.py`: `RUNS_AGENT_MODEL`, per-depth `RUNS_AGENT_BOUNDS`, `RUNS_AGENT_RESERVES`, every `AGENT_LLM_*` and `AI_ADMISSION_*`), refusing to start without it. Each claimed run is answered by the executor its stored pin names, with the Bounds stored at submission; an agent worker still answers deterministic runs, and a worker leaves a run whose pin it does not serve queued for one that does (or for its deadline), never claimed or substituted. Every attempt is admitted. **IR-728 runs the bounded tool loop** (`ai/agent/executor.py`, pin `agent-research-1`/`research-1`): one Conversation searches, reads, plans and drafts, with required per-depth `Bounds` closing research while the final answer and one repair still fit the AskRun allowance. The final turn sends `tool_choice: none`. A draft is delivered only after IR-512-style checks and a source recheck. **IR-729 repairs a failing draft once** in the same Conversation (phase `repair`, inside the reserve and allowance IR-728 held for it), with the failing items as feedback and no reason code; a failing repair keeps only sentences their own citations support, plus a fixed limitation line, or ends `unavailable`. A source changed before or during the repair fences delivery. **IR-750 adds named papers and exact counts** under a new pin pair, `agent-research-2`/`research-2`, which the profile pinned until IR-733 (`research-1` runs keep their tools): `resolve_papers` (title tiers or Record id; ambiguity gives candidates, never a choice) and `count_records` (an exact count over `records_record` under the row policy, by Area, PSCED, type, years or IP flag, optionally grouped; no topic). A stated count is recomputed just before delivery. A Turn keeps its stated exact counts apart from keyword samples (`iris_ai.turn.facts`, `0012_metadata.sql`), and reopen withholds it once a counted paper is unreadable. There is no semantic screener in the runtime yet. **IR-733 adds whole-Manuscript reading** under `agent-research-3`/`research-3`, which the profile now pins (earlier pins keep their tools): `read_manuscript` returns a paper's active extracted text in document order from a run-bound cursor (`continue_after`, a passage handle from the same revision; another paper, revision or run is refused), shows text repeated from the previous chunk once while citations keep the whole passage, and reports covered/missing passage ranges, pages no passage starts on and formula/caption passages (`iris_ai` migration `0014_manuscript_read.sql`). Each read is sized to what the verified window and the run allowance still hold after one more exchange and the closing answer; a full window now closes research instead of failing the run. The run tracks inspected, model-visible and recoverable passages separately, and a delivered Turn keeps a `reading_coverage` fact (`visual_interpretation: false`, `exhaustive: false`); an IR-724 checkpoint carries that coverage, so a resumed run reports the same. No compaction yet (IR-734/IR-736), so a paper larger than the window is read in part and said so. **IR-731 keeps supported findings when a tool fails**: an exception inside a research tool is answered to the model as `unavailable`/`tool_unavailable` instead of ending the run `executor_failed`; a delivered answer then ends with a fixed outage limitation, and an `outage_absence` check refuses turning the failure into "none" or a zero count. `iris_ai` migration `0004_agent.sql` adds Conversation state (shown/selected/excluded) and clarification Turns. Only `RUNS_EXECUTOR=agent` builds it (IR-862); no profile value is approved and no live provider call has been made. Its database access is decided in IR-826. Do not deploy it until all preconditions hold |
| **Ask IRIS (chat)** | **Implemented, in Django — not via the AI gateway above — and on chunk-level retrieval as of IR-283.** `POST /api/v1/ai/ask/` (`ChatQueryView`) and `POST /api/v1/ai/search/` (`SemanticSearchView`) answer from **passages**, not from titles and abstracts: the stack is assembled in `apps/ai/composition.py` (degradation → reranking → two-stage vector retrieval) and the views hold no wiring. **IR-395 adds ADR-033 §1's hybrid retrieval, off by default** — `AI_KEYWORD_RETRIEVAL_ENABLED` and `AI_RETRIEVAL_FUSION_ENABLED` (both `False`) put `apps/ai/retrieval/fusion.py` inside reranking, where `fuse_by_rank` merges the keyword and vector lists by rank position with no weight or threshold to tune. Measured at **+0.192 recall@10** with reranking on the 40-paper arXiv proxy corpus, and still shipped off: ADR-033 §5 gives the defaults to IR-402. `composition_root()` is **overridable** (`use_composition_root`), which is what lets `apps/ai/tests/test_ask_http.py` drive the HTTP boundary with the deterministic fakes and no vendor account. Visibility is `Record.objects.visible_to(user)`, applied inside retrieval before anything is scored — the old `publicly_visible()` second rule is gone from this path. Synthesis is `apps/ai/providers/openai_compatible.py` (`LLM_API_KEY`, `LLM_MODEL`), reached **by naming an Inference task as of IR-378**: `apps/ai/inference/` holds the closed set (`answer`, `resolve`, `summary`, `describe_figure`, `route` — an unknown name raises) and one `Profile` per task carrying vendor, model, ordered same-vendor fallback models, reasoning visibility and the uniform no-training data policy, per ADR-036 §Amendment. `CompositionRoot.llm_for(task)` is the only way to reach a model — **the old untasked `llm()` accessor is deleted, not merely superseded, as of IR-388** (its cross-vendor fallback, `LLM_FALLBACK_*`, was already deleted by IR-385) — and the answer path goes through `InferenceTask.ANSWER`. The `answer` Profile inherits the flat `LLM_*` keys, so an existing `.env` behaves identically; **`summary` has its own caller as of IR-380** — a Record page's AI Overview (`apps/ai/overview/`) reaches `InferenceTask.SUMMARY` through `llm_for` itself, with no reasoning configuration sent — **grounded in the whole paper as of IR-431**: every chunk of the active `ChunkSet` in `sequence` order, no retrieval, and `answer_service()` no longer takes a `task`; **its citations name pages as of IR-434** (`apps/ai/overview/pages.py`, `PAGE_MARKER`), while chat citations stay chunk-level; `summary` inherits nothing, so an overview reports `unavailable` and calls no vendor until `LLM_SUMMARY_MODEL` is set. `resolve` has a Profile but no caller yet; `describe_figure` is reached only through `CompositionRoot.figure_describer()` and writes retrieval-only Figure descriptions (IR-852, OpenRouter with `zdr`; off while unset); when no model is reachable the answer is replaced by an explicit unavailable state and the sources are still returned (ADR-008) — **the extractive fallback that composed an answer out of the sources is gone**. `GET /api/v1/ai/status/` reports the active `EmbeddingSpace` and whether generation is configured, replacing the hardcoded `"postgres_fts"`. **Reasoning is stored and shown as of IR-381** — `Turn.reasoning` (migration 0016) keeps the model's working with the same lifetime as the Turn, `done.reasoning` and the transcript both carry it, and `ReasoningPanel` shows it **collapsed by default for every reader**, live and replayed alike. This reverses IR-327's "shown live, never stored"; the separation it guaranteed is untouched — reasoning is a different column from `answer`, is never joined into it, and is never scanned for citation markers, `<think>` leaks included. See [ADR-019](docs/adr/019-persisted-unified-conversation-history.md) §Amendment — 2026-09-29. **Citations are Passages as of IR-284** — each one carries its record, the page and the quoted text, `/ai/search/` returns the same shape, and the Record cards ride alongside both so the interface needs no fetch per citation. Acting on a citation opens the paper at that page (`/records/<id>?page=N` → `#page=N`). **`apps/ai/services/` is gone (IR-285)** — the record-level pipeline, its full-text retrieval module and `llm_generator`, plus the unreferenced legacy `text_chunker`, `vector_store` and `summarizer`. There is one retrieval stack and one visibility predicate: `GET /records/<id>/similar/` moved onto record-vector similarity (`apps/ai/similarity.py`, ADR-029 §5/§7) and was the last caller of `publicly_visible()` on a retrieval path. `apps/ai/tests/test_one_retrieval_stack.py` fails if either comes back. **A paper reaches the AI only once the Adviser or RDCO has released it (IR-811, IR-882, [ADR-052](docs/adr/052-each-paper-states-its-embargo-and-a-person-ends-it.md) as amended 2026-11-04)**: every paper starts embargoed (`Record.is_embargoed`, default true, migration `records/0032`), `Record.embargo_state` is Active or Released, only Released passes the gate, and a date never ends an embargo. Publish asks nothing (IR-816's `embargo-answer/` is deleted) and `submit/` needs no answer. **After submission, `embargo-set/` and `embargo-release/` are the Adviser's or RDCO's alone (IR-812, IR-882)**; owners can do neither. A release queues the paper again, and a Turn citing a paper the gate now refuses stays out of chat history, recall and the answer backfill. **RDCO can't publish an embargoed paper** (ADR-052 §14 as amended): its Decision offers keep unlisted or reject, and `decide/` refuses publish with a 400. **Test data releases itself as of IR-882**: `seed_demo` releases its submitted papers but two, and a loaded paper stays embargoed unless `load_corpus --clear-for-ai` or `mark_corpus_cleared` releases it. **Nothing real is indexed yet.** **IR-464 adds the evidence decision's deterministic half, consumed by nothing.** `apps/ai/evidence/` holds five rules emitting five reason codes — `scope_record` (structural) plus `institution_term`, `document_reference`, `sourcing_demand`, `aggregate_shape` (lexical) — run on the raw question **and** the stored Resolved question and combined by OR, so a rewrite cannot weaken an evidence requirement. `AI_EVIDENCE_DECISION` accepts `off` or `shadow` and **rejects `on`**; the institution and Area terms are read once in `AiConfig.ready()`, and Django refuses to start when they are blank while the decision is enabled. A rule may add retrieval and may never drive a refusal: a `Verdict` carries no field a consumer could read as one. `manage.py eval_evidence` is its curated instrument. **No view, task or answer path calls it.** [ADR-035](docs/adr/035-ask-iris-decides-whether-it-needs-evidence.md) is **Accepted** (2026-10-06) and supersedes ADR-028's decision. **IR-465 adds the model half, exercised offline and consumed by nothing**: `ToolCallingLLM` (`apps/ai/providers/tool_calling.py`) is a separate, **abstract** port — no default body, so no decorator can silently bypass it — implemented by `OpenAICompatibleAdapter`, by every provider on the `answer` chain (`RetryingLLMProvider`, `CircuitBreakingLLMProvider`, `FallbackLLMProvider`, `CompletionLoggingLLMProvider`) and by `ScriptedToolCallingLLM`; `generate`/`stream` still offer no tool. `apps/ai/evidence/model_decision.py` offers the model one no-parameter `search_corpus` tool and reads back a route: a call, or text and no call. Every malformed shape, timeout or rate limit routes to evidence with its own reason code; model-supplied arguments are **never read**; the call receives no Passage, recalled Turn or assistant answer text; a hypothetical direct answer is measured for length and discarded. `eval_evidence --model-decision` (spends credits) puts the model's route beside the detector's. The tool call is **never executed**. **IR-466 adds the reader-invisible shadow pilot**: both chat views now go through `apps/ai/orchestrator.py` (the AI Overview does not, by construction), which records the Turn and, when `AI_EVIDENCE_DECISION=shadow` and `AI_EVIDENCE_SHADOW_SAMPLE_RATE` (default 0) samples it, writes a pending `ShadowEvidenceDecision` (migration 0018) carrying a manifest and the detector's verdict, then enqueues `apps.ai.tasks.decide_evidence_shadow` on the `shadow` queue after commit. `apps/ai/evidence/shadow.py` claims the row atomically, fences every write by token, reclaims a stale row once, skips (counted) when the `answer` breaker is open or failing or shadow's own token lane (`Lane.SHADOW`, `AI_EVIDENCE_SHADOW_TOKENS_PER_MINUTE`) is spent, records parity differences rather than skipping, and stores the union route; `evidence.shadow.coverage()` reports what is missing. No answer, state, citation or source changes, and the flag-off answer request is pinned by `tests/test_shadow_off_snapshot.py`. **Do not enable shadow on real reader questions until ADR-035 §11's vendor-retention check is recorded.** Production `on`, web search and any agent loop are not built. **IR-544 adds queued questions, off by default** — with `AI_DURABLE_ASK` on, a Conversation question over `/ask/stream/` becomes an owned `AskRun` answered by `apps.ai.tasks.answer_queued_question` on `default`. The stream follows its public journal (`id:` cursor), `GET /ask/runs/<uuid>/stream/?after=N` reconnects, and fenced attempts write one Turn at most (`apps/ai/durable.py`, [ADR-040](docs/adr/040-durable-queued-ask-iris-questions.md), **Proposed**). Enablement waits on IR-545's queue and spend gates. **IR-548 adds cancel, retry and conversation addresses**: `POST /ask/runs/<uuid>/cancel/` commits a terminal `cancelled` (no Turn, no further provider admission); `POST /ask/runs/<uuid>/retry/` makes a new run linked by `retry_of` with its own deadline and caps; Conversation detail carries `latest_run`; the interface opens each conversation at `/ai/conversations/<id>`, which grants nothing (ADR-040 §Amendment). **IR-546 and IR-547 build the fixed `listing` and `count` workflows** (`apps/ai/research/listing.py`, research lane on only): at most twenty distinct candidates, shown `pending`, screened, and counted in code from the include decisions as a classified subset, never a total or a catalogue count (pilot README §11–§12). IR-547 adds a per-reader `ScreeningJudgment` verdict cache, **off and inert until `AI_SCREEN_CACHE` is on and `AI_SCREEN_CACHE_POLICY` names an approval**; cross-reader sharing is not built and needs a named person's approval. **IR-592 adds conversation state** (`apps/ai/conversation_state.py`, migration 0030): one revisioned `ConversationState` per Conversation holding the papers shown in order, selections, exclusions and the request, advanced only by a delivered Turn in its own transaction; reads recheck visibility, and Turns citing unreadable Records leave history, recall and planner history. Only the planner consumes it so far; the controller (IR-593) will. **IR-595 adds the public reader protocol, opt-in per request** (`protocol=public-1` or `X-IRIS-Protocol`): `apps/ai/public.py` is the one allowlist for live SSE, queued replay and reconnect, `/ask/` and a reopened transcript, sending `activity` and an optional validated `reasoning_summary` (`Turn.reasoning_summary`, migration 0032) and never routing, research steps, raw reasoning or validation codes; old Turns stay stored and are only projected. Adapters declare summary and continuation-artifact capabilities through their dialect, and opaque signatures are echoed to the vendor, never rendered. The legacy protocol is unchanged and the reader UI does not yet use the new one (IR-596). **IR-317's development bypass is deleted (IR-815)** — the setting, its startup check, its command and the status flag, and the indexing path no longer accepts a substitute for the gate. A line left in someone's `.env` does nothing |
| **Provider admission** | **Implemented, off by default (IR-545, [ADR-041](docs/adr/041-shared-provider-admission.md) Proposed).** With `AI_PROVIDER_ADMISSION=enforce`, every paid physical attempt is admitted before it is sent: a chat completion or tool call (`AdmittedLLMProvider`, inside the retry and fallback decorators, SDK retries off), a Voyage embed or rerank (`voyage._post`) and a Jev decision. Each reserves its worst case (byte-bounded input, the completion cap every request now carries, the dearest fallback model's price, its lease) in Postgres through the `admission` database alias, under a campaign row lock, then settles to reported usage. Unreported usage stays at the reservation. Limits are the campaign (with a protected reserve), per-run caps, per-lane and per-account concurrency, and prices. **Fail closed: no limit has a default and none is approved** (pilot README §6); an unset one refuses all paid work. `AI_DURABLE_ASK` refuses to start without enforcement, and a queued question is admitted to a bounded queue with per-asker caps (`503 busy`). Proven across independent processes against real Postgres with fakes only; nothing measures real throughput |
| **pgvector** | **Implemented.** `apps/ai/models/embedding.py` has a real `VectorField` + HNSW `vector_cosine_ops`, migrations `0001`/`0002`. ADR-007. **Migration `0002` hardcodes `dimensions=1536`** while the model reads a setting — [ADR-015](docs/adr/015-voyage-embedding-and-reranking.md) replaces this with `EmbeddingSpace`, and IR-280 re-dimensioned both vector columns to 1024. **Consumed by Ask IRIS retrieval as of IR-283** — the earlier "not yet consumed" line is superseded |
| **Chunking** | **Implemented end to end (IR-89 A–H).** [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) makes the chunk the retrievable unit. `apps/ai/chunking/` holds the domain, strategies and context-path decorator; `apps/ai/repositories.py` persists a `ChunkSet` and swaps it atomically, re-embedding only chunks whose `text_hash` changed; `apps/ai/ingestion/` holds the lifecycle transition table, the job idempotency key, and `pipeline.py`, which normalizes, chunks and persists. `ai.tasks.chunk_record_document` runs it in a worker and is queued by `documents.tasks.extract_pdf_text`, so an upload reaches an active chunk set with no manual step. **What is not done is IR-116's actual exit criterion**: nobody has read fifty chunks from a real submission, so `AI_CHUNK_MAX_TOKENS` and the front-matter policy are untested defaults. **The unit is real `voyage-context-4` tokens as of IR-287** — `chunking/tokens.py` counts with the vendored, SHA-256-pinned Qwen2 BPE vocabulary at `chunking/tokenizer/voyage-context-4.json` (HuggingFace `tokenizers`, pinned; no vendor SDK, nothing downloaded at build or run time). It counted whitespace *words* before that, and 512 of those measured ~700 real tokens, so IR-287 raised the ceiling to **700 in the same change** and a boundary-equivalence test proves chunk boundaries on prose did not move. Supersedes IR-243's "the number is not what it says". `manage.py inspect_chunks <record_id>` is the tool for that. **Chunk vectors are computed as of IR-281**: `apps/ai/indexing.py` embeds an active chunk set through the `EmbeddingProvider` port and `ai.tasks.embed_chunk_set` is queued automatically by `chunk_extraction`. **No real corpus can be indexed yet** — the disclosure gate refuses every record whose embargo hasn't been released (ADR-052), and a loaded record stays embargoed unless a test-data command releases it (IR-815, IR-882), and every vector observed so far came from the deterministic fake, not from Voyage. Design: [`docs/chunker_architecture.md`](docs/chunker_architecture.md) |
| **Embedding / rerank provider** | **Voyage, always** — embedding (`voyage-context-4`, a contextualized chunk embedder, 1024 dims default) and reranking, both stages, no alternative provider in scope. **IR-281 moved every embedding call to the contextualized endpoint** (`/contextualizedembeddings`) and added `EmbeddingProvider.embed_document_chunks`, which takes chunks grouped by document — the flat `/embeddings` endpoint serves the standard models and discards the sibling-chunk context this model exists for ([ADR-015](docs/adr/015-voyage-embedding-and-reranking.md)). **Not gated on governance sign-off** — that precondition was dropped 2026-09-04. Still gated on a `DisclosurePolicy` module (per-record IP status/embargo/consent) and confirmed vendor no-training terms |
| **Extraction (LlamaParse)** | **Implemented; Docling retired (IR-843).** [ADR-056](docs/adr/056-manuscript-extraction-moves-to-llamaparse.md) supersedes ADR-016 and ADR-025. `apps/ai/extraction/` is the `StructuredExtractor` port; `LlamaParseExtractor` (`llamaparse_client.py`, IR-841) is its only production adapter, chosen in `selection.py`, where `EXTRACTION_BACKEND` accepts only `llamaparse` (`use_extractor` and `InMemoryExtractor` for tests, `tests/contract.py` for the adapter contract). With `DEBUG` off Django refuses to start without `LLAMAPARSE_API_KEY` and a dated `LLAMAPARSE_VERSION`; with `DEBUG` on it starts and every read fails as unavailable until both are set. It stores the raw v2 result, credits and pages on `PdfExtraction` and deletes the uploaded file in a `finally`, tested on IR-849's recordings with no vendor call. **IR-840 supplies the shaping** (`extraction/shaping.py`, numbering depth per IR-859) and `labeled-structure-v1` chunking. **IR-845 stores its Figures** (`ExtractionFigure`, `apps/documents/figures.py`) per Manuscript revision and serves them only through `GET /records/<id>/figures/<figure_id>/` behind `visible_to`. **IR-846 sources Publish suggestions from LlamaExtract** (`extraction/llamaextract_client.py`), gated and admitted, off until `LLAMAEXTRACT_VERSION` is set. **There is no fallback extractor.** IR-843 deleted the `docling` service, `DoclingExtractor`, `docling_mapping.py`, `DOCLING_*` settings, GPU detection in `scripts/setup_env.py`, and the Docling-era repairs in the normalizer and context path (furniture, stranded page numbers, hyphen rejoining, numbering placement); structures Docling stored earlier still chunk on the generic path. IR-738's pending-extraction worker core stays, with no launcher until it is given LlamaParse |

Always distinguish **CURRENT / PROPOSED / DEFERRED / LEGACY**. Do not describe a proposed component as if it exists.

## Source-of-truth hierarchy

1. **`docs/adr/`** — **requirements, design and decision authority**
2. **`docs/engineering/`** — how the team builds, tests, reviews, releases
3. **Code and tests** — actual behaviour
4. **Jira** — planning and tracking, **never a requirements authority**

When these conflict, the higher one wins **and the lower one is corrected**. Do not silently reconcile — record the contradiction.

> **`docs/SRS.md` and `docs/SDD.md` are FROZEN (2026-09-03).** They are retained as **thesis deliverables** and are **not consulted, cited, or treated as authority** for any engineering work — not in code, tickets, ADRs, reviews or agent output. They are out of date and the team has decided not to maintain them. **Never cite an SRS or SDD section as justification.** Where a decision needs a written basis, that basis is an ADR — write one.
>
> `FR-`/`NFR-` ids survive as **stable labels only**, so existing ADRs and `docs/testing/TRACEABILITY.md` keep resolving. An id is a name, not a source: do not go to the SRS to read what it means.

## Commands that actually work

```bash
# Frontend  (frontend/)
npm install
npm run dev          # vite
npm run build        # tsc && vite build
npm run lint         # eslint src --ext ts,tsx
npm test             # vitest run — non-interactive, jsdom, axe-core (IR-210)
npm run test:changed # vitest run --changed origin/main: every test that imports a changed
                     # file, directly or through the route table (IR-922). Run it before
                     # pushing; a narrow single-file run missed a router test in IR-913.
                     # CI still runs the whole suite and is the gate.
npm run test:watch   # vitest in watch mode
# Queries go through the accessible tree (role + accessible name), never a class
# or a test id. axe-core fails the build on serious/critical only, and cannot
# check colour contrast under jsdom — contrast stays a manual check.
# On Windows the runner needs vitest's `forks` pool; see vitest.config.ts.

# Backend  (backend/)
pip install -r requirements/development.txt
python manage.py check
python manage.py migrate
python manage.py runserver
python -m pytest -n 4 -q                  # Full backend suite for ticket verification (IR-854).
                                          # Requires Postgres; separate database per worker.
                                          # Use -n 0 for serial/offline pure-test runs.
                                          # One run per Postgres server: a second exits at
                                          # once (IR-835). -m "not slow" skips migration
                                          # tests and a few others locally; CI runs all.
                                          # Reads only SECRET_KEY, RECOVERY_* and DB_*
                                          # from backend/.env, as CI supplies (IR-853)
python manage.py seed_demo                # accounts + Discover catalogue + every workflow_state
                                          # (IR-227). Logins are <role>@cit.edu / IrisDemo123!,
                                          # plus admin@cit.edu (System Admin, and a Django superuser; IR-781).
                                          # Office coordinators (IR-478): itso.coordinator@,
                                          # ierc.coordinator@, ktto.coordinator@ and
                                          # rdco.coordinator@cit.edu, same password. The plain
                                          # <role>@cit.edu office logins are members, not
                                          # coordinators; re-running restores both flags.
                                          # Replaced scripts/seed_demo_{users,records,clearances}.py
                                          # and seed_test_users, all deleted. Idempotent for records;
                                          # re-running resets passwords. Refuses with DEBUG off
                                          # unless --force. --accounts-only for logins alone.
                                          # Submissions enter adviser-first review through the
                                          # Record API. The Adviser must be named and cannot own
                                          # the record (IR-260). Its submitted papers are released
                                          # by their Adviser (IR-882), except two left embargoed so
                                          # both states can be seen: one dated a year ahead at RDCO,
                                          # which can't publish it, and one undated at its Adviser.
                                          # The draft stays embargoed. Re-running releases papers an
                                          # older run left embargoed with no date. Verified
                                          # 2026-11-04 on a copy of one developer's dev database.
python manage.py load_corpus <dir> --dry-run             # bulk-load PDFs as Records (IR-313).
                                   # One subfolder per category; each becomes a Classification.
                                   # Defaults: record type "Thesis / Research", status "published"
                                   # (publicly visible, so Ask IRIS retrieval can find them).
                                   # Idempotent by title within a category. Refuses with DEBUG off
                                   # unless --force. Drop --dry-run to write.
                                   # It creates the MANUSCRIPT PdfExtraction and queues extraction
                                   # itself — the viewset hook that normally does this does not fire
                                   # for ORM writes. Needs LlamaParse + a worker on the `extraction`
                                   # queue to complete; chunking is queued automatically after.
                                   # No vendor account needed: chunking does not embed, and the
                                   # gate refuses a loaded paper, which starts embargoed.
                                   # --clear-for-ai releases the embargo, with consent, for each new
                                   # TEST paper (IR-815, IR-882). The worker then embeds its chunks and queues
                                   # its AI Overview, which SPENDS credits, and retrieval can't find it
                                   # until backfill_embeddings adds its title-and-abstract vector.
                                   # Refuses with DEBUG off even with --force, and for --origin
                                   # institutional. Verified 2026-11-02 on a copy of one developer's
                                   # dev database, with no worker running: the answers only
                                   # Verified on the dev database 2026-09-25: a 20-paper, 4-category
                                   # corpus loaded 12 new records (8 already present from an earlier
                                   # partial load, correctly skipped) and every one extracted and
                                   # chunked cleanly — 354 chunks, zero failures
python manage.py backfill_abstracts --dry-run [--classification NAME ...]
                                   # fill EMPTY Record abstracts from each record's own
                                   # manuscript chunks (IR-703): an "Abstract" section, an inline
                                   # "Abstract", or text after "(Dated: ...)". Never overwrites.
                                   # Record vectors embed title + abstract, so re-embed afterwards.
                                   # Refuses with DEBUG off unless --force. Verified on the dev
                                   # database 2026-10-31: 40 of 40 proxy papers
python manage.py reextract_manuscripts --dry-run
                                   # LlamaParse cutover (IR-842): prices every manuscript the consent and
                                   # embargo gate permits, in credits and US$, and sends nothing. A real run
                                   # needs --credit-ceiling N and EXTRACTION_BACKEND=llamaparse; it queues
                                   # reads (gate + admission apply) and leaves the old ChunkSet active until
                                   # the new one swaps in. --record N narrows it; --rollback reactivates the
                                   # previous ChunkSet. Verified 2026-11-03 on 5 proxy papers (55 pages,
                                   # 1,256 credits). Figure descriptions not exercised
python manage.py read_review_texts --dry-run [--record N]
                                   # give Versions from before IR-871 their review text (ADR-058 §1
                                   # as amended): each read from its own manuscript file on this
                                   # machine with pdfplumber, no network and no model, so it spends
                                   # nothing and asks no embargo. A metadata-only Version shares the
                                   # previous one's; a missing file reads "text not kept"; texts left
                                   # `unavailable` are retried. Never re-reads a stored text. Needs
                                   # every REVIEW_TEXT_* limit and Linux, else refuses before writing.
                                   # Verified 2026-11-05 on a copy of the dev database: migrated from
                                   # records 0021 to 0033, and it found nothing to read, because none
                                   # of that copy's 18 Versions names a manuscript
python manage.py inspect_chunks <record_id> --limit 50   # read a record's chunks (IR-116)
python manage.py run_research_tool --user EMAIL --call TOOL='{json}' [--call ...]
                                   # run research-lane tools as a user, no model
                                   # (IR-509, IR-510). Calls share one run, so
                                   # `find_records` then `read_record_sections`
                                   # with its R handle works. Prints the planner
                                   # payload and each handle's stored pointer.
                                   # search_passages/find_records embed the query
                                   # (Voyage). Verified on the dev database
                                   # 2026-10-11 with count_records and corpus_facets.
                                   # --general runs IR-591's five general tools
                                   # (resolve_papers, search_research, read_papers,
                                   # aggregate_records, extract_evidence) with
                                   # run-scoped handles and prints each envelope.
                                   # Verified on the dev database 2026-10-15 with
                                   # aggregate_records and resolve_papers
python manage.py backfill_embeddings --dry-run           # what indexing the corpus would cost (IR-282).
                                   # Prints records/chunks/tokens and an approximate cost, then stops.
                                   # Drop --dry-run to run it inline; --queue hands each record to a
                                   # worker on the `embedding` queue instead. Refuses to start when
                                   # the estimate exceeds AI_EMBEDDING_TOKEN_CEILING (--token-ceiling
                                   # overrides; 0 disables). Resumable and idempotent: it embeds only
                                   # chunks with no vector in the space, recomputed every run.
                                   # --space N builds a PENDING space (IR-752): summaries into the space-keyed
                                   # table, passages into its chunk rows, the provider must be the space's pinned
                                   # model, and no active vector is touched (apps/ai/space_build.py). Other
                                   # states keep the older chunk-only fill. Nothing here activates a space.
                                   # Verified on the dev database 2026-09-20: 26 records, 1,236 chunks,
                                   # 381,073 estimated tokens (proxy
                                   # corpus: never a finding about CIT-U research, ADR-023)
python manage.py backfill_turn_vectors --dry-run          # give existing Turns the answer
                                   # vector IR-447 added (ADR-026 §7 as amended). A Turn written
                                   # before IR-447 carries only its question vector, so a fact
                                   # stated solely in an older answer stays unreachable until this
                                   # runs. Prints Turns, estimated tokens and an approximate cost,
                                   # then stops. Drop --dry-run to run it inline; --conversation N
                                   # and --limit narrow it, --space N fills a pending space.
                                   # Resumable and idempotent: it embeds only answered Turns with
                                   # no answer vector in the space, recomputed every run, so a
                                   # finished set re-runs for one query and no vendor call. Refuses
                                   # past AI_EMBEDDING_TOKEN_CEILING (--token-ceiling overrides;
                                   # 0 disables). Only `generated` Turns get one -- a no_sources,
                                   # unavailable or partial Turn's text is an explanation or a
                                   # fragment, and indexing it would make refusals findable.
                                   # Inline only, no --queue: an answer is a few hundred tokens.
                                   # Verified on the dev database 2026-10-02: 0 Turns, 0 tokens,
                                   # which is the whole history that database holds
python manage.py mark_corpus_cleared --dry-run           # release test papers ALREADY loaded
                                   # (IR-815, IR-882, ADR-052 decision 16): with consent, for
                                   # --owner-email's embargoed papers with no date that were never
                                   # released (default corpus-loader@cit.edu). Never overrides a date
                                   # someone set, skips drafts, and leaves --origin institutional
                                   # embargoed and named. Finding nothing, it says whose
                                   # papers are waiting. Sends nothing: backfill_embeddings --dry-run
                                   # says what vectors would cost. Refuses with DEBUG off and has no
                                   # --force. Steps: docs/evaluation/README.md §Clearing the proxy
                                   # corpus. Verified 2026-11-02 on that same copy, on papers loaded
                                   # for the check. THE 40 PROXY PAPERS ARE NOT MARKED: that database
                                   # doesn't hold them
python manage.py promote_embedding_space --space N --check   # is this space ready to go live? (IR-282, IR-739)
                                   # --dry-run runs the full verification (exits non-zero if it would be
                                   # refused); without either it verifies, then retires the active space and
                                   # activates N in ONE transaction (Record and Passage vectors move together,
                                   # no vector is written). Refuses, naming every reason: incomplete or stale
                                   # summary/passage coverage, wrong width or metric, a query provider that
                                   # does not name the space's model, a chunk set that is not the Record's
                                   # current Manuscript revision, or a vector index that misses what an exact
                                   # scan finds. Records the disclosure gate refuses are not owed a vector.
                                   # --rollback returns to the space the last promotion replaced (same
                                   # verification against today's corpus); --reopen-rollback-target makes a
                                   # behind target pending so `backfill_embeddings --space N` can catch it up;
                                   # --probe-user EMAIL searches before and after and checks every cited
                                   # passage is a current one that user may read (stored vectors as queries,
                                   # no vendor); --json, --actor, --skip-index-check. Nothing promotes
                                   # automatically and this does not authorize a production upgrade.
                                   # Verified 2026-11-05 on a copy of the dev database (21 Records, no chunks):
                                   # --dry-run of the retired 1536-d space refused with three coded reasons;
                                   # --rollback said there was no recorded previous revision.
                                   # check_vector_index --space N checks a pending space
python manage.py eval_pilot_milestone --set <labels.json> --tier proxy --base-url <url> --providers fake
                                   # IR-550: score the first fixed-workflow milestone (metadata
                                   # count, topic count, listing) against pinned labels, each
                                   # measure with its own denominator. --from-run <run.json>
                                   # --reviews <file> rescores with a person's verdicts. JWT in
                                   # IRIS_EVAL_TOKEN. --providers real refuses unless admission
                                   # enforces and the runs fit the campaign before its reserve
python manage.py eval_pilot_capacity --base-url <url> --questions <json> --n 100 --providers fake --cache cold --user EMAIL
                                   # IR-550: simultaneous burst (--user queues each question in
                                   # its own Conversation); every submission in the
                                   # denominator, latency from submission. Only real + cold +
                                   # >=100 distinct measures capacity. A paid burst that does not
                                   # fit the campaign sends nothing. Neither has run on a vendor
python manage.py provider_campaign                       # provider spend against the campaign
                                   # ceiling, core and whole, plus attempts in flight per lane
                                   # (IR-545). Reads only; calls no vendor. Charges are an upper
                                   # bound: open reservations and unreported usage count in full.
                                   # Needs every AI_ADMISSION_* limit set; without them it names
                                   # each unset one and exits non-zero. Verified 2026-10-12 on an
                                   # empty dev database: "nothing charged yet" with limits set
python manage.py check_vector_index                      # is vector search finding what it
                                   # should? (IR-442). Compares each HNSW index against an exact scan
                                   # using stored vectors as probes, at AI_HNSW_EF_SEARCH depth, and
                                   # exits non-zero below --min-recall (default 0.99). Calls no vendor,
                                   # so it is free to run after any corpus load. --titles also asks the
                                   # real retrieval stack about every published paper by name and needs
                                   # --user EMAIL; that costs one query embedding per record, so it is
                                   # opt-in and never CI. Verified 2026-10-01: chunk index 0.995, record index
                                   # 1.000, and 40 of 40 titles found. It warns when the planner read no
                                   # HNSW index, because that number says nothing about the index. A
                                   # stored-vector probe is an easier question than a real query vector,
                                   # which is why --titles exists as well
python manage.py eval_evidence --questions <set.json>     # does the evidence detector
                                   # get a question's evidence requirement right? (IR-464).
                                   # The curated instrument of ADR-035 §10 — the one that
                                   # supplies accuracy numbers; IR-466's shadow pilot will
                                   # supply operational figures only and carries no ground
                                   # truth. Reads the questions carrying IR-463's
                                   # `evidence_required`, runs the five-rule detector on the
                                   # raw text, on `resolved_question` and on the two combined
                                   # by OR, and reports over-fires and misses PER REASON CODE
                                   # per lane, plus coverage, institutional questions
                                   # separately, and categories under --min-examples as
                                   # INCONCLUSIVE. By default calls no model and no vendor, reads no
                                   # database, creates no Conversation, Turn or shadow row, so
                                   # it costs nothing and needs no --user. --model-decision
                                   # (IR-465) also asks the answer model for its route and
                                   # reports it beside the detector's — spends credits, manual
                                   # only, discards any hypothetical answer. Writes
                                   # docs/evaluation/runs/<stamp>-evidence-<set>.json with a
                                   # digest of the complete active rule set. Verified
                                   # 2026-10-06 on proxy_starter.json: 10 of 62 questions
                                   # annotated, raw 9/10, resolved 3/4, combined 10/10, zero
                                   # over-fires — and every category inconclusive at two
                                   # examples each, so the combined figure demonstrates the OR
                                   # rule and measures nothing. NOTHING CONSUMES A VERDICT:
                                   # ADR-035 is Proposed, not accepted
python manage.py eval_evidence --questions <set.json> --chain --from-run jev=<run.json> ... --search-cutoff N --direct-cutoff N
                                   # score the whole proposed decision chain offline (IR-486,
                                   # IR-484). Replays stored --model-decision files (repeat
                                   # --from-run jev=/label=/tool=; one file per replicate) or
                                   # collects fresh runs with --live jev,label,tool --repeats N
                                   # (spends credits; jev is the proxy tier only). Eight arms:
                                   # structural alone, detector, detector+label, +tool call,
                                   # +Jev, +Jev+LLM confirmation, Jev forced to fail (LLM
                                   # decides alone) and the no-Jev control. Missed searches
                                   # first, ambiguous apart, stable vs flaky misses, a
                                   # replicate over 5% fallbacks reported alone, Jev
                                   # calibration (Brier), failure/latency/cost per decider.
                                   # Both cutoffs are required: it chooses no operating point.
                                   # Writes <stamp>-chain-<set>.json, never an `evidence` file.
                                   # Verified 2026-10-10 on the stored IR-481/482 runs: the
                                   # band and rescue tables of proposal 12 §4 reproduce, except
                                   # that "missed by all" at cutoff 0.5 is 3, not the 4 printed
python manage.py eval_conversations --set <set.json> --validate [--lock <lock.json>] [--write-lock <lock.json>]
                                   # validate a multi-turn conversation set (IR-598): schema,
                                   # per-turn labels, the 100-conversation minimum, per-family
                                   # coverage of A01-A15 and development/held-out leakage by paper
                                   # title and topic. --write-lock records one SHA-256 per split;
                                   # --lock re-checks the set against it. Free: no database, no
                                   # vendor. --score reads collected runs and named human reviews
                                   # per arm, family and split (Wilson intervals, own denominators,
                                   # any access breach sets enablement_blocked); it collects nothing
                                   # and calls no model. It REQUIRES --lock (and refuses on a
                                   # mismatch) and refuses a draft_unreviewed set unless
                                   # --allow-draft, which marks the run exploratory_draft_labels.
                                   # --score has run only on test fixtures: no real reviews exist.
                                   # Label-reviewed 2026-10-31 (IR-702) on
                                   # docs/evaluation/general-tools/conversation_set_v1.json: 105
                                   # conversations (62 development, 43 held out, seven per family),
                                   # 39 supported and unambiguous, zero leakage. Signed by Jive Tyler
                                   # I. Revalde (`human_reviewed`; 89 confirmed, 16 corrected against
                                   # the dev database); lock rewritten and re-checked `valid`. Counts
                                   # assume a database holding only the 40 proxy papers: the dev
                                   # database also publishes 8 seed_demo records. No arm has been run.
                                   # scripts/label_review.py prep|finalize builds the worksheet and
                                   # the label-review file; finalize refuses untouched AI drafts.
                                   # IR-607: the lock also pins corpus and rubric_version (older
                                   # locks read stale); --write-lock refuses while A09 lacks
                                   # distinct a09_case missing_field/no_match/outage cases;
                                   # --label-review checks a named person's label review.
                                   # --score adds --packets (refuses evidence outside a reviewer's
                                   # packet) and --counted (refuses draft labels, a missing or
                                   # fixture label review, no packets, fake providers, another
                                   # corpus, single-reviewed conversations); every score
                                   # file states counted and not_counted_reasons. Two reviews plus
                                   # an adjudication stay in review_audit. Verified 2026-10-30 on
                                   # apps/ai/evaluation/fixtures/review/ (uncounted; --counted refused).
                                   # Guide: docs/evaluation/general-tools/review.md
python manage.py eval_campaign --report --set <s.json> --lock <lock.json> --runs controller=<r1.json> [--runs ...] --reviews <reviews.json> [--approvals a.json --scenarios ir608.json --counted]
                                   # IR-609: report a campaign of repeated arm runs (>=3 per arm
                                   # when counted). Free: no DB, no vendor. Refuses stale locks,
                                   # incomplete manifests, reused Conversations and unequal arms;
                                   # blocks on breaches, unreviewed families or unmeasured IR-608
                                   # scenarios. --smoke <run.json> --case-cost-usd X
                                   # --campaign-cost-usd Y --planned-cases N measures a development
                                   # smoke's spend against proposed caps. Writes .json + .md. Test-only so
                                   # far: no campaign has run. Guide: docs/evaluation/general-tools/campaign.md
python manage.py eval_readiness --build --report <campaign.json> --candidate runtime ...
                                   # IR-741: release-readiness manifest over an eval_campaign report.
                                   # Eleven gates, only `met` clears one; missing, fake, incomparable or
                                   # breached evidence blocks. --preflight names every unrecorded cap/approval;
                                   # --verify [--check-files] [--assert-ready --expect-commit SHA] is what
                                   # IR-742 reads; --assert-ready rebuilds the manifest from its inputs;
                                   # --validate-measurement checks a workload-measurement-1 file. Free: no DB, no vendor.
                                   # Authorizes nothing. Verified locally on synthetic fixtures only (no
                                   # real campaign, load run or human review exists). docs/evaluation/
                                   # general-tools/readiness.md
python manage.py eval_answer_quality --set ../docs/evaluation/answer-quality/answer-quality-v1.json --validate
                                   # IR-956: the switch measurement for IR-955. 108 questions in
                                   # twelve families (F01-F12), each through Django lanes-v1 and the
                                   # runtime agent on ONE paid run, scored automatically (exact
                                   # checks + a pinned model grader, rubric aq-rubric-1) and
                                   # reported pass/fail against IR-955's bar. --write-lock L
                                   # --grader-model M freezes it (never rewritten); --run needs the
                                   # lock, enforced admission on the runtime's campaign, both readers
                                   # by email (--reader-a, --reader-b), --runtime-url and
                                   # --runtime-model; --rescore and --reuse-django finish or redo a
                                   # run. --validate verified 2026-11-07; v2 frozen 2026-11-08 with grader
                                   # anthropic/claude-haiku-5.5 (owner's choice) in
                                   # answer-quality-v2.lock.json (F12 on ClusterCAD, record 71). NO PAID RUN YET. Guide:
                                   # docs/evaluation/answer-quality/README.md
python manage.py eval_review_packets --run <run.json> --reviewer EMAIL --reviewer-name NAME --out <packets.json>
                                   # one reviewer's packet (IR-607). Holds NO text (IR-721): which
                                   # turns Record.visible_to(reviewer) allows, record ids, source
                                   # revisions, citation pages and a blank review; a turn resting on
                                   # an unreadable record is withheld whole. Held-out output needs
                                   # --lock and a run newer than it. --show packets.json --run run.json
                                   # --reviewer EMAIL --reviewer-name NAME re-checks access and
                                   # revisions now and prints the text, writing nothing; --reopen
                                   # --out F writes the packet again for an account
                                   # Test-only so far (test_review_packets.py, test Postgres);
                                   # not yet run against the dev database
python manage.py eval_retrieval --questions <set.json> --dry-run   # recall@10 (IR-133/IR-394)
                                   # The retrieval eval harness. --dry-run costs nothing and calls no
                                   # vendor: it checks that every label resolves against this database,
                                   # which is what a labeller runs between questions. Drop it and pass
                                   # --user EMAIL for a real run — retrieval filters by
                                   # visible_to(user), so the user is part of what is measured.
                                   # --list-techniques prints ADR-033 §5's six switches, their
                                   # settings and whether each exists in this deployment yet
                                   # (none does); --technique NAME=on|off|<n> moves one for a run
                                   # and every run file records all six (IR-394). Asking for a
                                   # switch whose setting does not exist yet is refused, naming the
                                   # ticket that lands it — IR-395/396/397; IR-402 moves defaults.
                                   # Reports TWO numbers per configuration (ADR-023 §Amendment):
                                   # recall@10 over what retrieval returned, and recall over the final
                                   # set the model was given. Runs with and without reranking by
                                   # default and prints the delta; --reranking on|off picks one.
                                   # Plus correct refusal (IR-454): the share of unanswerable
                                   # questions (corpus + decline-no-evidence) given no passage, kept
                                   # apart from recall, and every answerable question given none
                                   # named by id as a false refusal. With every paper cleared it
                                   # reads 0 until IR-396's cut-off exists; n/a for a set with no
                                   # unanswerable question. Database tests only; not yet run live.
                                   # --drop-incomplete measures a partly-labelled set and names what
                                   # it skipped. Writes docs/evaluation/runs/<stamp>-<set>.json.
                                   # MANUAL ONLY, never CI — a real run spends Voyage credits.
                                   # Labels are Record + page + quote, never chunk ids. Question sets:
                                   # apps/ai/evaluation/fixtures/synthetic_set.json (committed, run by
                                   # the suite) and docs/evaluation/proxy_starter.json (52 labelled
                                   # questions over the 40-paper arXiv proxy corpus). Guide:
                                   # docs/evaluation/README.md.
                                   # **The baseline below was measured under pgvector's 40-row
                                   # scan cap (IR-440). Current (depth 200, 2026-09-30, run
                                   # 20260930-182254): recall@10 0.712 without reranking, 0.885
                                   # with; final-set 0.673 / 0.846. Fusion adds almost nothing
                                   # on top (0.894 / 0.875).**
                                   # Baseline 2026-09-30 (proxy tier, all 52 questions, all 40
                                   # papers embedded): recall@10 0.596 without reranking, 0.683
                                   # with; final-set 0.558 / 0.663. Run files in
                                   # docs/evaluation/runs/. Never cite it as a finding about CIT-U
                                   # research. The disclosure gate refuses unreleased papers;
                                   # release test papers with mark_corpus_cleared. Long papers are embedded in
                                   # windows under voyage-context-4's 32k limit (IR-423).
                                   # `--technique NAME=on|off|<n>` moves one of ADR-033 §5's six
                                   # switches for a run and records it; `--list-techniques` prints
                                   # them and says which are built. Two are, both off by default
                                   # (IR-395's fusion pair); asking for an unbuilt one is refused

# Docker  (repo root)
python scripts/setup_env.py         # REQUIRED first (IR-154): creates the repo-root .env Compose
                                   # interpolates DB_NAME/DB_USER/DB_PASSWORD from, deriving it from
                                   # backend/.env so it matches an existing postgres_data volume.
                                   # Idempotent; never overwrites, except to add
                                   # ADR-045's missing recovery secrets to backend/.env (IR-642).
                                   # Without it Compose stops by name
docker compose up --build          # ai-gateway needs ./ai/.env (gitignored, absent in CI) or Compose stops.
                                   # Given one it now boots (IR-156). Nothing on the indexing path calls
                                   # it any more — see ADR-024
docker compose config              # validate without building
python -m ai.runs.migrate          # (repo root) migrate the AI-owned `iris_ai` schema (IR-722) as
                                   # RUNS_MIGRATION_DATABASE_URL, a maintenance login given to this
                                   # command only, never in ai/.env (running services refuse it); refuses a runtime
                                   # login, re-grants iris_ai_runtime. Run after `manage.py migrate` and
                                   # `provision_research_roles`. Verified 2026-11-01 on a dev-DB copy
python -m ai.runs.purge            # remove deleted accounts' AI-owned Conversations (IR-722);
                                   # needs RUNS_DATABASE_URL. Verified 2026-11-01: purged 0
```

**Do not document a command without verifying it runs.** Several obvious-looking commands currently fail.

## Known-broken — do not be surprised

- **Corrected on this merge (2026-09-06), verified against the code, not assumed:** the URLconf imports cleanly (`manage.py check` and `python -c "import config.urls"` both pass) and `apps/ai` has real, field-bearing models (`chunk.py`, `embedding.py`, `embedding_space.py`, `ingestion_job.py`) — the "six undefined names" and "field-less stub models" claims below were stale and are removed. `frontend/nginx.conf` no longer serves `/media/` unauthenticated — the nginx alias, prod web-container mount, and Django's `DEBUG` `static()` route were all removed (IR-152); see `docs/testing/TRACEABILITY.md` NFR-S4
- **Fixed 2026-09-09 (IR-153):** `RecordViewSet.get_queryset` now applies `Record.objects.visible_to(user)` on **every** action — office staff, owner, assigned adviser, or the public catalogue. Because the filtering is in the queryset rather than a permission class, a refusal is a **404 identical to a missing record**, so the API never confirms someone else's draft exists. `list` narrows further to `PUBLICLY_VISIBLE_STATUSES` so Discover stays a catalogue rather than surfacing your own drafts. Supersedes the "returns any record to any authenticated user" claim previously here
- **Fixed 2026-09-07 (IR-164):** `CELERY_TASK_ROUTES` and `CELERY_TASK_DEFAULT_QUEUE` are now set in `config/settings/base.py`, routing `extract_pdf_text` to `extraction`, `embed_record` to `embedding`, and everything else (including `chunk_record_document`) to `default` — matching the three queues docker-compose's workers actually consume. Verified against the real stack, not just asserted from config: a task dispatched over the real Redis broker was observed consumed and completed by the real `celery-default` and `celery-extraction` containers. Supersedes the "no Celery task is ever processed" claim previously here — see `docs/engineering/DEVELOPMENT.md` §6
- **Audited and fixed 2026-09-09 (IR-153):** `apps/documents/` has now been swept endpoint-by-endpoint. Six endpoints resolved a record from a request parameter with **no ownership check at all** — `submit/`, `records/<id>/slots/`, `uploads/?record=`, `uploads/create/`, `files/?record=`, and `files/download-all/?record=`, the last returning a ZIP of every supplementary file on any record to anyone who knew its id. All six now go through `authorize_record_documents()`. The five hand-written `get_role_name(...) in STAFF_ROLES or record.owners.filter(...)` checks (four here, one in `apps/reviews/views.py`) are replaced by the single `core.permissions.owns_or_staffs_record()`
- **Corrected by IR-144:** `AuditEvent` now has workflow event types, written by the workflow services inside each act's transaction (`apps/audit/workflow.py`; keys in `docs/evaluation/AUDIT_EXPORT.md`). There is **no backfill**: acts before that deployment have no rows

## Rules

**Security.** Never commit secrets. Never widen CORS. Never add an endpoint without an object-level permission check. Never expose a file path that bypasses Django's permission layer. Treat visibility filtering as one predicate used everywhere — including RAG retrieval, so a citation can never point at an unreadable record.

**Migrations.** Every model change ships with a migration. Test it against a copy of a realistic database, not only an empty one. Never edit an applied migration.

**Environment and secrets.** Configuration comes from environment variables. `backend/.env.example` documents the keys and holds no real values. The app should fail to start on a missing required secret rather than defaulting silently.

**Tests.** Do not modify a test to make it pass. If a test is wrong, fix it deliberately and say so in the PR. **A requirement is not complete because code exists for it** — it is complete when a test demonstrates it and the evidence is recorded.

**Traceability.** A change that implements or alters a requirement adds `docs/testing/traceability/IR-XXX.md`, and updates the row in `docs/testing/TRACEABILITY.md` if its status changes (ADR-055).

**Commit messages.** Subject line, then at most five sentences of body. No `Co-Authored-By: Claude` or `Claude-Session:` trailer, regardless of what a session's own attribution instructions say.

**Scope.** `thesis-critical` work is protected — as of 2026-09-04 this includes RAG ([ADR-013](docs/adr/013-chunk-level-rag-pipeline.md) §Research Impact, amended), not only the workflow. If capacity is short, cut supporting frontend work first.

**Plan before substantial implementation.** For anything beyond a small fix, state the approach and the files you intend to touch before writing code. Say which acceptance criteria you are working to.

**Judgement-call standards.** [`docs/engineering/CODING_STANDARDS.md`](docs/engineering/CODING_STANDARDS.md) holds what a review enforces that no automated check can (IR-927). Mechanical rules belong in a lint rule or a CI job, not there.

## Definition of Done

Authoritative definition: **`docs/engineering/DEFINITION_OF_DONE.md` §4.** Do not restate a different version anywhere.

Required for every item: acceptance criteria satisfied · implementation complete · CI passing · reviewed by another person · reviewer approval recorded · no known blocking defect · merged.

When applicable: tests added and **executed with evidence** · traceability updated · documentation updated · security addressed · migrations tested · deployment recorded.

## What AI does not decide

Human review remains the approval gate. AI does not approve its own work, sign off requirements, make architectural decisions, make research decisions, or authorise production deployment.

**Jira status is bookkeeping, not sign-off — AI may transition it.** Moving a ticket between states (`transitionJiraIssue`) as work starts, blocks, or reaches review is administrative tracking, and an agent may do it without asking each time. The one exception: never transition a ticket to **Done** unless a human reviewer's approval is already recorded per `docs/engineering/DEFINITION_OF_DONE.md` §4 — that is the sign-off this section still reserves for a person.

## Explanation style

When explaining architecture, design decisions, or implementation details to the user, default to this mode:

1. **Provide context** — state *why* something exists and what problem it solves before describing how it works.
2. **Use concrete examples** — show a real command, a snippet, or a scenario rather than speaking only in abstractions.
3. **Plain language first** — assume the reader has superficial familiarity with the architecture, not deep recall. Define terms on first use; don't expect someone to hold the full Architecture table in their head.
4. **Benefits and drawbacks for every option** — when presenting a choice or explaining a design trade-off, explicitly list what you gain and what you give up. Never present one path as self-evidently correct without saying what it costs.

This is the team's standing preference, not a per-session request. Apply it unless the user explicitly asks for a terser or more advanced register.

## Agent skills

### Issue tracker

Jira (`citiris.atlassian.net`, project `IR`) via the Atlassian MCP server registered in `.mcp.json`. Holds the state mapping and label taxonomy. See `docs/agents/issue-tracker.md`.

**`.mcp.json` is gitignored and has never been committed, so a fresh clone has no Jira at all** — that includes every cloud session, every CI job and every newly cloned machine. It works only where someone created the file by hand. Its full contents are in `docs/agents/issue-tracker.md` §Access (no credentials; each person authenticates separately over OAuth), so recreating it is a copy-paste. **An agent that cannot reach Jira must not pretend otherwise:** build to the ADR, which is the requirements authority anyway, and then say plainly that the card was neither read nor transitioned — per that file's own rule, never claim an issue was created or moved when it was not.

### Triage labels

The five canonical triage roles map onto the existing IRIS taxonomy, adding only `ready-for-agent` (`needs-info` maps onto `not-ready`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `CONTEXT.md` (not yet created) and `docs/adr/`. See `docs/agents/domain.md`.
