# ADR-019: Persisted conversation history, unified across Ask IRIS and Paper Chat

## Status

Accepted — 2026-09-07.

**Reverses, for this one capability, the exclusion in [ADR-001](001-mvp-scope-boundary.md) §Scope** ("conversational RAG with history" was out of scope for Semester 2) **and in [ADR-013](013-chunk-level-rag-pipeline.md) §Decision** ("Still excluded: conversational memory and history"). Neither ADR is otherwise superseded — their remaining scope calls and the RAG pipeline decision stand. Document summarization, the other half of ADR-013's same exclusion line (FR-M4-02), is **not** reversed by this ADR; it is being specified separately as an independent capability with its own trigger, provider fallback and consumer, deliberately not bundled with conversation history even though both surfaced from the same grilling session.

## Context

Ask IRIS has no memory today. `POST /api/v1/ai/ask/` (`ChatQueryView`) is fully stateless — every question re-runs retrieval from nothing, and the "multi-turn" experience that exists is a frontend illusion: `chatStorage.ts` keeps a `Conversation`/`ChatMessage` shape in `localStorage`, and `buildRagQuestion()` glues every prior turn into one text blob that gets sent as if it were a single question.

The stub models this illusion is patterned after already exist server-side and go nowhere: `apps/ai/models/conversation.py` defines `Conversation` and `ChatMessage` as field-less `pass` classes, exported from `apps/ai/models/__init__.py`, with a migration, and zero consumers anywhere in the tree.

There are, in fact, **two** independent chat surfaces in the frontend, not one:

- **Ask IRIS** (`RAGChatPage.tsx`) — a dedicated page, general-purpose, with a conversation list sidebar backed by `chatStorage.ts`.
- **Paper Chat** (`PaperChatPanel`/`PaperChatDock`) — a docked or floating panel shown only while viewing one record's detail page, scoped to that record by prefixing its title onto the question text (`` `${record.title}. ${question}` ``). It persists nothing — its turns live in a plain `useState` and vanish when the panel closes.

Building persisted history without addressing this would mean picking one of two bad shapes: bolt persistence onto Ask IRIS alone and leave Paper Chat as a second, inconsistent, unpersisted chat system; or build two separate persistence mechanisms that happen to look similar, doubling the model, API and invalidation surface for what is conceptually one feature (asking IRIS a question, sometimes with a paper already in mind).

## Decision

**One `Conversation` model, not two chat systems.**

A `Conversation` belongs to exactly one `User` and is optionally scoped to one `Record` via a nullable foreign key:

- Started from the Ask IRIS page with no record in mind → `Conversation.record = None`.
- Started from a record's Paper Chat panel → `Conversation.record = <that record>`.

Both UI surfaces read and write through the same `Conversation`/`ChatMessage` models and the same API surface. Paper Chat stops being a separate, memoryless component with a string-prefix hack for scoping, and becomes "open (or continue) a `Conversation` pre-filtered to this record," using the same machinery Ask IRIS uses. The two surfaces may still be presented differently (full page vs. docked panel) — that is a UI decision, explicitly not settled by this ADR (see Related Tasks).

Alongside unification, this ADR reverses ADR-001/013's specific exclusion of conversational memory: `POST /api/v1/ai/ask/` gains an optional `conversation_id`, the backend loads and extends the real message history (not a reconstructed text blob) for both retrieval and LLM synthesis, and citations are stored as live references (record id only, re-checked against `Record.objects.publicly_visible()` on every read) rather than frozen snapshots — so a citation in old history can never point at a record the reader can no longer see, matching the same guarantee ADR-013 §Security Impact already requires of live retrieval.

## Alternatives Considered

**Persist Ask IRIS only, leave Paper Chat as-is.** Rejected. It ships the illusion that Paper Chat has been fixed when it hasn't — a user who asks a follow-up in Paper Chat still loses it on panel close, while the same action in Ask IRIS now survives. Two different reliability guarantees for what looks, to a user, like the same feature.

**Two separate models (`Conversation` for Ask IRIS, something record-scoped and lighter for Paper Chat).** Rejected. The two would diverge in schema and invalidation rules for no functional reason — a Paper Chat conversation is not meaningfully different from an Ask IRIS conversation that happens to have a record attached. Maintaining two versions of "store a question, an answer, and its citations" is pure duplication.

**Keep today's frontend text-concatenation as the multi-turn mechanism, just persist the resulting blob.** Rejected. It would ship persistence without fixing the actual defect it's piggybacking on — follow-up questions still get answered by pattern-matching over a stitched string rather than real conversational context, and the fix (passing real turn history to retrieval and to the LLM) costs little once the model and API already exist for persistence.

## Decision Rationale

ADR-001 excluded conversational history because Semester 2's budget didn't fund it against higher-priority workflow scope. That capacity argument doesn't disappear, but the situation on the ground has changed the same way ADR-013's did: the illusion already exists in the frontend, one surface already fakes persistence with `localStorage`, and the server-side models this feature needs are already scaffolded (empty, but present, migrated, and shaped correctly) — so the marginal cost is building the real thing, not inventing it from nothing.

Once the decision is "build it," unifying the two surfaces is close to free relative to building it twice, and building it twice is the one path that guarantees a future maintainer finds two near-identical models and has to reconstruct why they aren't one.

## Consequences

**Positive.** One model, one invalidation story, one API surface for both chat entry points. Paper Chat gains real persistence for the first time. Follow-up questions in both surfaces get genuinely conversation-aware retrieval instead of a text-stitching hack.

**Negative.** Paper Chat's current scoping trick (prefixing the record title onto the question) needs to be replaced by the backend actually consulting `Conversation.record`, which touches `rag_pipeline.py`'s call signature, not just the frontend.

**Risk.** None of this changes retrieval's visibility guarantee (`search_records()` already filters to `publicly_visible()` on every call) — the new risk surface is narrow: a `ChatMessage` must never store enough of a citation to reconstruct restricted content once the underlying record's visibility changes. Live-reference citations (this ADR's Decision) is the mitigation, not an afterthought.

## Revisit when

A real product reason emerges to give Paper Chat behavior Ask IRIS shouldn't have (or vice versa) that can't be expressed as "this conversation happens to have `record` set." Until then, one model is the right shape.

## MVP Impact

Not MVP-required (ADR-001's Semester 2 boundary stands as the record of what shipped by then) — this is scoped work for the current phase of RAG development, which CLAUDE.md now classifies as thesis-critical alongside the workflow.

## SaaS Impact

Under [ADR-005](005-instance-per-tenant.md), conversation data is isolated per instance like everything else. No cross-tenant concern.

## Security Impact

**A new object-level permission surface.** `Conversation`/`ChatMessage` endpoints must scope to `request.user` — CLAUDE.md already states this as a standing rule ("never add an endpoint without an object-level permission check"), not a new decision, but it's the first time this specific model needs it enforced. Live-reference citations mean a `ChatMessage` is never itself the thing that leaks a restricted record — the existing `publicly_visible()` check, re-run on every read, is.

## Deployment Impact

None. No new services; `Conversation`/`ChatMessage` are ordinary Django models in `apps.ai`, and the conversation-aware retrieval path runs in the same request/worker boundary Ask IRIS already uses.

## Research Impact

RAG is thesis-critical per ADR-013's 2026-09-04 amendment. Persisted, conversation-aware retrieval is a direct quality improvement to that thesis-critical capability, not a peripheral UX feature — a system that answers follow-up questions correctly is a stronger demonstration of the RAG contribution than one that only answers isolated questions well.

## Related Requirements

Conversational memory and history, as named (unlabeled by an FR- id in ADR-001/013 — only "summarization" carries one, FR-M4-02, and that requirement is unaffected by this ADR).

## Related Tasks

None yet. Tracked once Jira tickets are opened from the accompanying spec (`/to-spec` → `/to-tickets`). UI presentation for the unified conversation surface (how Ask IRIS and Paper Chat each display it) is explicitly deferred to those tickets and not decided here.
