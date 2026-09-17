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

**Embedding Space**:
The named combination of embedding model, vector dimension and distance metric that a stored vector belongs to. Exactly one Space is active at a time; vectors from different Spaces are never comparable, so a Space is what makes a stored vector meaningful rather than just a list of numbers. Changing embedding model means introducing a new Space and re-indexing into it, not editing vectors in place.
_Avoid_: Model, dimensions, or index used alone to mean this (each names one attribute of a Space, not the Space); vector store (the storage, not the identity of what is stored).

**Passage**:
A quoted span of a Record's text that an Ask IRIS answer is grounded in, carrying the page it came from so a reader can go and check it. The reader-facing counterpart of a chunk: a chunk is how IRIS divides a document for retrieval, a Passage is what a citation shows a person.
_Avoid_: Chunk (the internal retrieval unit — correct in code, wrong in UI copy and specs aimed at a reader), snippet, excerpt, source (a Passage cites a source; it is not itself the source).

**Figure**:
A picture inside a Record's document — a chart, diagram, schematic or photograph — identified by the page and the rectangle it occupies rather than by any text it contains. Distinct from its **caption**, which is the text labelling it and is read as ordinary prose, and from a [[Passage]], which is quoted text a reader can check. A Figure is shown to a reader; it is not quoted, and IRIS makes no claim about what it depicts.
_Avoid_: Image (the rendering of a Figure, not the Figure itself), picture (the extractor's word), diagram or chart (kinds of Figure, not synonyms for it), figure caption used to mean the Figure.

**Turn**:
One exchange in a [[Conversation]] — a question and the answer it produced, kept together. The unit IRIS remembers: a Turn is what gets stored, searched when an older part of the conversation becomes relevant again, and returned whole when it does. A question without its answer is half a Turn, not a Turn.
_Avoid_: Message (one half of a Turn — correct for the stored row, wrong for the thing being recalled), exchange, round, prompt.

**Resolved question**:
The self-contained question IRIS actually searches with, worked out from what the reader typed plus the earlier Turns of the Conversation. "What about its limitations?" resolves to "What are the limitations of *[paper]*?". Distinct from what the reader typed, and shown to them — a Resolved question that gets the subject wrong changes what was asked, so it is never hidden.
_Avoid_: Rewrite or rewritten query (names the mechanism, not the thing), expanded query (a different technique — expansion adds phrasings, resolution supplies a missing subject), the question (ambiguous once the two differ).
