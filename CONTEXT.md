# IRIS

Institutional research and IP disclosure workflow system for CIT-U. The thesis contribution is the workflow (type-differentiated routing, parallel multi-office clearance, clearance-aware resubmission); RAG (Ask IRIS) is thesis-critical as of 2026-09-04. See `docs/adr/` for the decision record.

## Language

**Record**:
One research/IP disclosure submission moving through the workflow. Has one or more uploads, authors (byline names, not accounts), and owners (the `User` accounts who submitted/manage it).
_Avoid_: Submission, paper, thesis (a Record's `record_type` may be a thesis, but not every Record is one), document (too generic — see Upload/Extraction below for the file-shaped things).

**Conversation**:
A persisted, multi-turn Ask IRIS chat thread, owned by exactly one `User`. Optionally scoped to one `Record` (a "Paper Chat" conversation) via a nullable FK; unscoped when general Ask IRIS. One `Conversation` model covers both the full-page Ask IRIS surface and the per-record docked panel — they are two presentations of the same underlying thread, not two features.
_Avoid_: Chat, session, thread (used loosely elsewhere in the codebase for unrelated things), Paper Chat (a UI surface/preset scope, not a distinct data concept).

**Ask IRIS**:
The product name for IRIS's retrieval-augmented chat/search feature (`apps/ai`, `POST /api/v1/ai/ask/`). Retrieval is always grounded in the real record corpus; synthesis is generative when an LLM provider is configured, else extractive (quotes sources, says so).
_Avoid_: RAG chat, chatbot (fine in casual conversation, but "Ask IRIS" is the product-facing name used in the UI and should be used in specs/tickets too).

**AI Summary**:
A short, AI-generated summary of a Record's content, cached per active `ChunkSet` and shown to users (e.g. on a record's detail page). Deliberately distinct from **Abstract** (below) — the two must never be presented as interchangeable.
_Avoid_: Summary alone (ambiguous next to Abstract), DocumentSummary (the internal model/table name — fine in code, not in UI copy or specs aimed at a reader).

**Abstract**:
The author-submitted summary of a Record, provided at submission time. Existed before AI Summary; not generated, not cached, not related to the chunk pipeline.
_Avoid_: Summary alone.
