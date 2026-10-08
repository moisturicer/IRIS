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
The product name for IRIS's retrieval-augmented chat/search feature (`apps/ai`, `POST /api/v1/ai/ask/`). Retrieval is always grounded in the real record corpus. Synthesis is generative when an LLM provider is configured; when none is reachable the answer is replaced by an explicit unavailable state and the sources are still returned (ADR-008). There is no extractive fallback — the one that composed an answer out of the sources was deleted in IR-285.
_Avoid_: RAG chat, chatbot (fine in casual conversation, but "Ask IRIS" is the product-facing name used in the UI and should be used in specs/tickets too).

**AI Overview**:
An AI-generated account of a Record's content, grounded in that Record's own passages and cached per active `ChunkSet`. Shown on the record's detail page. Deliberately distinct from **Abstract** (below) — the Abstract is what the author wrote, the AI Overview is what IRIS derived, and the two must never be presented as interchangeable.
_Avoid_: AI Summary (the earlier name for this, now retired — the code, the API field and the UI all say Overview), Summary alone (ambiguous next to Abstract), DocumentSummary (an internal name that no longer matches the model).

**Manuscript**:
The paper itself: the one document a Record is about, which a reader opens, a citation points into, and reviewers review. Distinct from a supplementary file, which supports the Record without being it (an ethics form, a data sheet, a file an office attached). Once a Record has been submitted, its Manuscript changes only through a new [[Version]].
_Avoid_: Abstract file (the code's historical field name; the Manuscript is the whole paper, not its abstract), upload or document alone (both also cover supplementary files), paper in specs (fine in UI copy).

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

**Formula**:
Mathematical notation recovered from a Record as LaTeX, shown to a reader rendered. Delimited as displayed math in a chunk's `content` and never in its `text`, so the vector is unaffected. Retrieved through its surrounding prose, never by the notation: "search by equation" is not a capability (ADR-025 §Amendment — 2026-10-01).
_Avoid_: Equation (one kind of Formula), math (ambiguous with the rendering), symbol.

**Turn**:
One exchange in a [[Conversation]] — a question and the answer it produced, kept together. The unit IRIS remembers: a Turn is what gets stored, searched when an older part of the conversation becomes relevant again, and returned whole when it does. A question without its answer is half a Turn, not a Turn.
_Avoid_: Message (one half of a Turn — correct for the stored row, wrong for the thing being recalled), exchange, round, prompt.

**Reasoning**:
The model's working on its way to an answer, arriving on its own channel and kept there. Stored with its [[Turn]] and shown in a panel that is collapsed by default, so a reader opens it by choice — which is what keeps it from being read as the answer. Never part of the answer text, never quotable, and never scanned for citation markers: a citation-shaped marker inside Reasoning points at nothing because nothing looks for it there. Requested per Inference task; only answering asks for it.
_Avoid_: Thinking or chain of thought (the vendor's words, and both suggest the panel is the reasoning rather than a record of it), explanation (what an answer gives a reader; Reasoning is not addressed to them), justification (claims the answer follows from it).

**Resolved question**:
The self-contained question IRIS actually searches with, worked out from what the reader typed plus the earlier Turns of the Conversation. "What about its limitations?" resolves to "What are the limitations of *[paper]*?". Distinct from what the reader typed, and shown to them — a Resolved question that gets the subject wrong changes what was asked, so it is never hidden.
_Avoid_: Rewrite or rewritten query (names the mechanism, not the thing), expanded query (a different technique — expansion adds phrasings, resolution supplies a missing subject), the question (ambiguous once the two differ).

**Area**:
A named subject grouping that Records belong to, and the unit a question about the collection aggregates over. Today an Area is a Classification or PSCED category — assigned by a person at submission, so it has a name someone chose and siblings to be compared against. An Area is always named: a grouping nobody can name is not yet an Area, which is what makes a claim about one checkable.
_Avoid_: Topic, cluster, field, domain, category used alone (each is either vaguer than an Area or names one particular way of arriving at one).

**Research landscape**:
The shape of the corpus across Areas — which are well covered, which are sparse next to their siblings, which are growing. What a reader is asking about with "what is trending?" or "where are the gaps?", as opposed to asking about the contents of any one Record. A landscape claim is always relative to what the asker is permitted to see, so two people can correctly be shown different landscapes.
_Avoid_: Trends or gaps alone (each is one question asked of a landscape, not the landscape), overview, analytics, the corpus (the Records themselves, not their shape).

**Collaboration opt-in**:
A Record owner's explicit, separate permission for their Proposal to be surfaced to another researcher working in a similar area. Its own decision, deliberately not the Data Privacy Act acceptance a submission already carries — accepting terms for how data is processed is a different act from agreeing that strangers may be told your unsubmitted work exists, and someone may reasonably say yes to one and no to the other. An opt-in permits an introduction; it never makes a Record readable.
_Avoid_: Consent alone (ambiguous next to the DPA acceptance the disclosure gate reads), DPA consent, sharing, visibility (an opt-in changes neither).

**Novelty check**:
Comparing a newly submitted Proposal against work the institution has already completed, to tell a proposer that something close to their idea has been done here before. Distinct from collaboration matching, which compares one Proposal against other Proposals: a Novelty check looks only at finished work that is already in the public catalogue, so it discloses nothing and needs no [[Collaboration opt-in]].
_Avoid_: Duplicate detection (that is about two Proposals overlapping with each other), plagiarism check (a different question about finished work, deliberately out of scope), similarity search.

### Review workflow

**Specialist office**:
ITSO, IERC or KTTO: an office a Record is routed to for a question only it can answer (IP, ethics, commercialisation). Each is staffed by several people. RDCO is an office but not a specialist office; it decides, it does not clear.
_Avoid_: Clearing office, department, Party (the code's word, which also covers the Adviser and RDCO).

**Specialist path**:
A Thesis/Research or Project that its Adviser accepted and routed to at least one [[Specialist office]]. The only path on which RDCO takes part; the alternative is the Adviser's accept & publish, where RDCO is never involved.
_Avoid_: Full review, RDCO path.

**Pool**:
An office holding a Record that nobody in it is reviewing yet: the office's shared work, until a member claims it, a coordinator assigns someone, or whoever routed it nominated someone.
_Avoid_: Queue (My Reviews is the queue; a Pool is one of the things in it), unassigned.

**Seat**:
One person's part in an office's review of a Record: "this member is reviewing it for that office". An office can hold a Record with several Seats, and its review is finished only when every Seat that was not withdrawn is done.
_Avoid_: Assignment (the office holding the Record, not a person), reviewer slot.

**Finding**:
A [[Seat]] holder's recorded negative verdict on a Record, always with a written reason. A Finding never rejects and never sends the Record back: specialist offices cannot do either. It travels to RDCO, which decides.
_Avoid_: Rejection, decline, negative review, Not cleared (an office's outcome, not one reviewer's verdict).

**Clearance**:
A [[Specialist office]]'s outcome on a Record, *Cleared* or *Not cleared*, settled when that office's review completes. *Not cleared* means at least one [[Seat]] recorded a [[Finding]]. Each Seat's own verdict is separate from the Clearance and stays visible beside it.
_Avoid_: Approval (an office clears its own question; it does not approve the Record), office decision.

**Hand-back**:
IRIS opening RDCO's [[Pool]] on a Record when the last active specialist office finishes. Happens only on the [[Specialist path]]; nobody routes to RDCO by hand.
_Avoid_: Route to RDCO, escalation, final routing.

**Review round**:
One [[Specialist office]]'s review of a Record, from being routed the Record until its [[Seat]]s are done. An office routed the same Record again starts a new Review round, and the latest completed one sets the office's [[Clearance]]; the earlier outcome stands until then.
_Avoid_: Round alone (a chat exchange is a [[Turn]]), assignment in prose (reads as a person being assigned, which is a Seat), pass.

**Version**:
A numbered snapshot of what a Record put in front of its reviewers: the [[Manuscript]] as it stood when the Record was submitted (v1) or resubmitted (each later one). A resubmission that changed only the details still makes a Version, pointing at the same Manuscript as the one before, because a reviewer asked for it. A review is made against one Version. Earlier Versions are review material: only the Record's participants see them, and a reader of a published paper sees the paper. A history may start after v1 where the earlier Versions were never recorded; none is made up to fill the gap.
_Avoid_: Revision (the act that produces a Version, not the Version), file version or upload version (the per-slot numbering of supplementary files, a different thing), draft (the Record's state before it is submitted).
