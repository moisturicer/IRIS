# IRIS

Institutional research and IP disclosure workflow system for CIT-U. The thesis contribution is the workflow (type-differentiated routing, parallel multi-office clearance, clearance-aware resubmission); RAG (Ask IRIS) is thesis-critical as of 2026-09-04. See `docs/adr/` for the decision record.

## Language

**Declared origin**:
The recorded category of a work's provenance, independent of its authors, submitting owner and import actor.
_Avoid_: Inferred origin, author affiliation

**Institutional research**:
Research declared to be CIT-U work.
_Avoid_: Any research stored in IRIS

**Imported reference**:
Externally sourced research kept as reference material, including real external papers used in evaluation.
_Avoid_: Synthetic paper, institutional output

**Synthetic research**:
Deliberately fabricated research used for demonstrations or testing.
_Avoid_: Imported reference, real evaluation paper

**Unknown origin**:
A work's origin has not been recorded.
_Avoid_: Institutional by default

**Publication year**:
The recorded year a work was published, distinct from its completion year and the date it was added to IRIS.
_Avoid_: Completion year, added year

**Author**:
A person or organization explicitly credited with creating the work.
_Avoid_: Submitting owner, import actor

**Record**:
One research/IP disclosure submission moving through the workflow. Has one or more uploads, authors (byline names, not accounts), and owners (the `User` accounts who submitted/manage it).
_Avoid_: Submission, paper, thesis (a Record's `record_type` may be a thesis, but not every Record is one), document (too generic — see Upload/Extraction below for the file-shaped things).

**Extraction**:
The structured document read out of one PDF (a `PdfExtraction` row): its elements in reading order with page boxes, the flattened search text derived from them, and the Provenance of the Extractor that produced it.
_Avoid_: Parse, OCR result, the PDF text

**Review text**:
What reviewers compare and comment against: one Version's sections and passages, each with its page, read from that Version's own Manuscript on campus with no AI. Every Version that changes the Manuscript has its own. Distinct from the Extraction, which the AI reads, exists only for the latest released Version, and comes from a different reader, so the two can disagree about the same page.
_Avoid_: Extraction (the AI's text, not the reviewers'), Version text alone (ambiguous between the two), diff text.

**Extractor**:
The adapter that turns PDF bytes into an Extraction behind the `StructuredExtractor` port. `EXTRACTION_BACKEND` chooses which one runs; every non-legacy Extractor passes the contract suite.
_Avoid_: Parser, Docling (one legacy Extractor, not the role)

**PDF evidence**:
What IRIS reads from a Manuscript's PDF itself at extraction time, with no vendor: word boxes, page labels, bookmarks, fonts and table-of-contents entries. Stored beside the Extractor's raw result, so shaping can recover exact highlights, printed page numbers and heading depth without opening the PDF again. Proposed (ADR-067), not built (IR-1053).
_Avoid_: Review text (what reviewers read, a different thing), OCR, local extraction (it is not an Extraction).

**Trial chunk set**:
A chunk set built only for an evaluation run, with a named strategy and options, and never made active. It is how two chunking strategies or sizes are compared on the same papers without touching what readers see. Proposed (ADR-067), not built (IR-1051).
_Avoid_: Test chunks, candidate index, shadow chunk set.

**Target size**:
The chunk length, in `voyage-context-4` tokens, the chunker aims for. Chosen by measurement; chunks may come out shorter or longer. Proposed (ADR-067), not built: today the chunker has one 700-token ceiling (IR-1050).
_Avoid_: Max tokens, chunk limit, ceiling (that is the Safety ceiling).

**Safety ceiling**:
The length no chunk may exceed, 2,000 `voyage-context-4` tokens, checked by the chunker's tests whatever the Target size. It exists so a table or list too long to keep whole is split, not so chunks grow to it. Proposed (ADR-067), not built (IR-1050).
_Avoid_: Target size, max tokens.

**Transient failure** / **Permanent failure**:
How an Extraction attempt failed (IR-839). Transient is an unavailable Extractor and is retried; permanent is everything else, an unexpected exception included, and fails once.
_Avoid_: Retryable (that names the reader's retry action, offered after either kind)

**Conversation**:
A persisted, multi-turn Ask IRIS chat thread, owned by exactly one `User`. Optionally scoped to one `Record` (a "Paper Chat" conversation) via a nullable FK; unscoped when general Ask IRIS. One `Conversation` model covers both the full-page Ask IRIS surface and the per-record docked panel — they are two presentations of the same underlying thread, not two features.
_Avoid_: Chat, session, thread (used loosely elsewhere in the codebase for unrelated things), Paper Chat (a UI surface/preset scope, not a distinct data concept).

**Ask IRIS**:
The product name for IRIS's retrieval-augmented chat/search feature (`apps/ai`, `POST /api/v1/ai/ask/`). Retrieval is always grounded in the real record corpus. Synthesis is generative when an LLM provider is configured; when none is reachable the answer is replaced by an explicit unavailable state and the sources are still returned (ADR-008). There is no extractive fallback — the one that composed an answer out of the sources was deleted in IR-285.
_Avoid_: RAG chat, chatbot (fine in casual conversation, but "Ask IRIS" is the product-facing name used in the UI and should be used in specs/tickets too).

**AI Overview**:
An AI-generated account of a Record's content, grounded in the whole Record (every chunk of its active `ChunkSet`, in order, with no retrieval) rather than in retrieved passages, and cached per active `ChunkSet`. Shown on the record's detail page. Deliberately distinct from **Abstract** (below) — the Abstract is what the author wrote, the AI Overview is what IRIS derived, and the two must never be presented as interchangeable.
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
A picture inside a Record's document — a chart, diagram, schematic or photograph — identified by the page and the rectangle it occupies rather than by any text it contains. Distinct from its **caption**, which is the text labelling it and is read as ordinary prose, and from a [[Passage]], which is quoted text a reader can check. A Figure is shown to a reader and is not quoted. IRIS stores a machine-written description of it for retrieval only: the description is never shown and never cited as a Passage, so IRIS makes no claim to a reader about what a Figure depicts (ADR-056).
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

**Evidence decision**:
Working out, before retrieval and from the question alone, whether answering it needs the corpus. Its result is an [[Evidence route]]. It is never a function of what retrieval found or why nothing was kept (ADR-035 §7). Under ADR-035's proposed 2026-10-10 amendment, it runs as a fixed sequence: hard policy, then the detector, then the [[Decider]]s. A direct answer needs every signal that ran to permit it, and any doubt or failure routes to evidence. The detector is an additive floor and never a classifier: it may require evidence and may never permit a direct answer. Nothing a reader sees depends on it yet: the setting accepts only `off` and `shadow`.
_Avoid_: Classifier (implies the decision sorts questions by kind; it only decides whether evidence is needed), router (choosing which model writes the reply is a separate decision), relevance (that is a property of retrieved passages, not of the question).

**Evidence route**:
The outcome of an [[Evidence decision]]: either *evidence*, so the question is answered from retrieved passages, or *direct*, so it gets an [[Ungrounded answer]] with no retrieval. A route only selects a path. It never widens scope, identity or visibility, and no model output can make it do so.
_Avoid_: Mode (the wire field that says how an answer was produced), tool call (one mechanism that once produced a route, not the route itself).

**Decider**:
A model whose only job is to give one opinion toward an [[Evidence route]], and which writes no answer. Two are proposed (ADR-035, 2026-10-10 amendment, not accepted): Jev (TypeSafe's decision model, reached through OpenRouter's Decisions API), which returns a probability that the question needs the corpus, and an LLM route label, which returns `search` or `answer`. A Decider is advisory. It can never overrule hard policy or the detector, and a direct answer normally needs both Deciders to permit it. The one proposed exception: when Jev fails, the route label decides alone. A Decider receives the question, the Resolved question, earlier reader questions and a fixed corpus description, and never Passages or earlier answers.
_Avoid_: Classifier, judge, router (see [[Evidence decision]]), detector (the deterministic word rules, which are not a model).

**Ungrounded answer**:
An answer written from the model's general knowledge with no Passage behind it. It is stored in its own `ungrounded` state, labelled as not from the repository, never cited, and kept out of the model's history (ADR-034). Accepted ADR-034 §2 reaches it when no passage clears the relevance cut-off. ADR-034's 2026-10-10 amendment (proposed, not accepted) would change that: only a *direct* [[Evidence route]] chosen before retrieval reaches it, and a question that searched and found nothing would be `no_sources`. Not built yet.
_Avoid_: General answer or fallback answer (both blur whether it came from the corpus), fabrication (that is a grounded-looking answer that is not grounded; this one says plainly what it is).

**Area**:
A named subject grouping that Records belong to, and the unit a question about the collection aggregates over. Today an Area is a Classification or PSCED category — assigned by a person at submission, so it has a name someone chose and siblings to be compared against. An Area is always named: a grouping nobody can name is not yet an Area, which is what makes a claim about one checkable.
_Avoid_: Topic, cluster, field, domain, category used alone (each is either vaguer than an Area or names one particular way of arriving at one).

**Research landscape**:
The shape of the corpus across Areas — which are well covered, which are sparse next to their siblings, which are growing. What a reader is asking about with "what is trending?" or "where are the gaps?", as opposed to asking about the contents of any one Record. A landscape claim is always relative to what the asker is permitted to see, so two people can correctly be shown different landscapes.
_Avoid_: Trends or gaps alone (each is one question asked of a landscape, not the landscape), overview, analytics, the corpus (the Records themselves, not their shape).

**Collaboration opt-in**:
A Record owner's explicit, separate permission for their Proposal to be surfaced to another researcher working in a similar area. Its own decision, deliberately not the Data Privacy Act acceptance a submission already carries — accepting terms for how data is processed is a different act from agreeing that strangers may be told your unsubmitted work exists, and someone may reasonably say yes to one and no to the other. An opt-in permits an introduction; it never makes a Record readable.
_Avoid_: Consent alone (ambiguous next to AI consent), DPA consent, sharing, visibility (an opt-in changes neither).

**Novelty check**:
Comparing a newly submitted Proposal against work the institution has already completed, to tell a proposer that something close to their idea has been done here before. Distinct from collaboration matching, which compares one Proposal against other Proposals: a Novelty check looks only at finished work that is already in the public catalogue, so it discloses nothing and needs no [[Collaboration opt-in]].
_Avoid_: Duplicate detection (that is about two Proposals overlapping with each other), plagiarism check (a different question about finished work, deliberately out of scope), similarity search.

### Review workflow

**Specialist office**:
ITSO, IERC or KTTO, and TBI once ADR-068 is built: an office a Record is routed to for a question only it can answer (technical review, ethics compliance, IP, commercial potential). Each is staffed by several people. RDCO is an office but not a specialist office; it decides, it does not clear.
_Avoid_: Clearing office, department, Party (the code's word, which also covers the Adviser and RDCO).

**ITSO**:
The Innovation & Technology Support Office, which handles technical review of research outputs. Questions about IP go to [[KTTO]].
_Avoid_: IP office.

**IERC**:
The Institutional Ethics Review Committee, responsible for ethics compliance review of research submissions.

**KTTO**:
The Knowledge and Technology Transfer Office. In a paper's review it answers whether the paper holds intellectual property to protect, and whether it should be filed before publication. It owns a paper's [[IP application]]s (ADR-066). Commercial potential is [[TBI]]'s question (ADR-068).

**TBI**:
The Technology Business Incubator, a [[Specialist office]] that answers a paper's commercial potential in its review, and owns its [[Commercialization application]]. Accepted in ADR-068, not built yet.
_Avoid_: KTTO / TBI (IPAMS's shared step), incubator office.

**Specialist path**:
A Thesis/Research or Project that RDCO sent to at least one [[Specialist office]]. Otherwise RDCO decides it alone.
_Avoid_: Full review, RDCO path.

**Pool**:
An office holding a Record that nobody in it is reviewing yet: the office's shared work, until a member claims it, a coordinator assigns someone, or whoever routed it nominated someone.
_Avoid_: Queue (My Reviews is the queue; a Pool is one of the things in it), unassigned.

**My Reviews**:
A reviewer's own [[Seat]]s, plus their office's [[Pool]], arranged as the work to do (To review), the work under way (In review) and the decisions already made (Done). Nobody sees another reviewer's My Reviews; an office coordinator alone may see every Seat in their own office. Rejected, Cleared and the other outcomes are filters on Done, never tabs, because they are results rather than work.
_Avoid_: Review Queue (the retired page, whose tabs were outcomes), queue or inbox alone (both suggest a shared list everyone works from).

**Seat**:
One person's part in an office's review of a Record: "this member is reviewing it for that office". An office can hold a Record with several Seats, and its review is finished only when every Seat that was not withdrawn is done.
_Avoid_: Assignment (the office holding the Record, not a person), reviewer slot.

**Finding**:
A [[Seat]] holder's recorded negative verdict on a Record, always with a written reason. A Finding never rejects and never sends the Record back: specialist offices cannot do either. RDCO sees it and decides.
_Avoid_: Rejection, decline, negative review, Not cleared (an office's outcome, not one reviewer's verdict).

**Clearance**:
A [[Specialist office]]'s outcome on a Record, *Cleared* or *Not cleared*, settled when that office's review completes. *Not cleared* means at least one [[Seat]] recorded a [[Finding]]. Each Seat's own verdict is separate from the Clearance and stays visible beside it.
_Avoid_: Approval (an office clears its own question; it does not approve the Record), office decision.

**Hand-back**:
A retired step: IRIS opening RDCO's [[Pool]] on a Record when the last active specialist office finished. RDCO now holds the Record from the moment its Adviser sends it, and an office finishing only notifies RDCO.
_Avoid_: Route to RDCO, escalation, final routing.

**Review round**:
One [[Specialist office]]'s review of a Record, from being routed the Record until its [[Seat]]s are done. An office routed the same Record again starts a new Review round, and the latest completed one sets the office's [[Clearance]]; the earlier outcome stands until then.
_Avoid_: Round alone (a chat exchange is a [[Turn]]), assignment in prose (reads as a person being assigned, which is a Seat), pass.

**Due date**:
When a party's turn at a Record is expected to finish: a [[Review round]] for a [[Specialist office]], or the Adviser's or RDCO's turn. Set from that party's [[Turnaround]] when the party receives the Record, in working days, and fixed from then on except by an [[Extension]]. It belongs to the office, not a person, so an unclaimed [[Pool]] has one too; every [[Seat]] shows the same date. A due date only prompts reminders and an [[Escalation]]; it never decides, clears or routes anything (ADR-043).
_Avoid_: Deadline (implies something happens automatically when it passes), SLA (an external commitment IRIS does not make), seat due date.

**Turnaround**:
How many working days a party is given for its turn at a Record, set per party by an administrator. A party with no Turnaround has no [[Due date]] at all; IRIS never supplies one. Changing it affects only turns that start afterwards.
_Avoid_: SLA, deadline, review period.

**Extension**:
Moving a [[Due date]] later, always with a reason and always visible beside the original date. Made by a coordinator of that office, or by IRIS itself while the office's own document request waits on the owner. An Adviser's due date is never extended by hand.
_Avoid_: Reset (a new Version gives reopened parties a fresh due date, which is not an Extension), postponement.

**Escalation**:
Telling an office's coordinators that its [[Due date]] has passed. Only a notification: the Record, its [[Seat]]s and its [[Clearance]]s are unchanged. The Adviser stage has no Escalation.
_Avoid_: Using it for the [[Hand-back]] to RDCO, auto-escalation (suggests the Record moves).

**Resolved notification**:
A notification that asked its recipient to act, once the task it asked for has ended, whoever ended it: cleared, claimed by a colleague, withdrawn, or closed by a [[Decision]]. It stays in the list as history but no longer counts as unread. It is final: if a resubmission asks the same office again, that is a new notification. A notification that only informs is never resolved.
_Avoid_: Read (a person's own act, which a Resolved notification does not need), dismissed, archived.

**Revision request**:
One party asking a Record's owners to revise the Record itself, made against one [[Version]] and always with a reason. Each party holds at most one open at a time, whichever of its reviewers asked. While any is open the Record waits on its author and only RDCO can decide it; the party that asked cannot finish its own review either. Answered by the next Version, withdrawn by the party that asked, or withdrawn by RDCO's [[Decision]]. Distinct from a document request, which asks for a missing file and leaves the Record as it is.
_Avoid_: Resubmission request (the code's name for it), decline or sent back (the retired pipeline's words), changes requested (how a party with an open Revision request is shown, not the request itself).

**Decision**:
An act that ends a Record's review: on a Thesis/Research or Project, accept & publish or keep [[Unlisted]] by RDCO alone, or reject by RDCO or the Adviser; on a Proposal, its Adviser's accept or reject. It closes every other piece of open work on the Record, with that work's history kept. An Adviser's Decision is refused while any [[Revision request]] is open; RDCO's withdraws them. Accept & send to RDCO is not a Decision: it is how an Adviser accepts a Thesis/Research or Project, it closes nothing, and it is refused while a Revision request is open.
_Avoid_: Final decision, approval, verdict (one reviewer's own conclusion, which a Decision also records).

**Accepted**:
A Proposal its Adviser accepted: its resting state. It is not published, and nothing further is decided on it. Only a Proposal is ever Accepted as a state. An Adviser or RDCO accepting a Thesis/Research or Project is an act, and it reads "Accepted" on that reviewer's own Done row while the Record itself reads by where it rests.
_Avoid_: Approved (the stored name), ongoing, completed (the state of the retired *complete* act).

**Continuation**:
The Thesis/Research or Project a researcher starts from their own [[Accepted]] Proposal, carrying it forward into a manuscript submission with its own [[Manuscript]] and its own review. A Proposal has at most one Continuation, and each names the other; a reader is shown that link only when they may open the Record it names.
_Avoid_: Child record, child manuscript, derived record, fork, follow-up.

**Unlisted**:
A Thesis/Research or Project that RDCO accepted but kept out of Discover and Ask IRIS, for example ahead of a patent filing. Its owners and reviewers can still open it.
_Avoid_: Completed (the code's status name), embargoed, hidden.

**Embargo**:
A hold that stops a Record's text going to outside AI companies, for a reason such as a sponsor's agreement or a journal that publishes first. Its date is a reminder, and it ends only when the Adviser or RDCO releases it. It doesn't hide the Record from readers in IRIS, which is what [[Unlisted]] does.
_Avoid_: Expired (an embargo doesn't expire), hidden, private.

**Archived**:
How a rejected Record is shown to readers. It is terminal: the owner cannot answer it with a new [[Version]] and must submit a new Record.
_Avoid_: Closed, deleted, declined (the retired pipeline's word for a revision request).

**Version**:
A numbered snapshot of what a Record put in front of its reviewers: the [[Manuscript]] as it stood when the Record was submitted (v1) or resubmitted (each later one). A resubmission that changed only the details still makes a Version, pointing at the same Manuscript as the one before, because a reviewer asked for it. A review is made against one Version. Earlier Versions are review material: only the Record's participants see them, and a reader of a published paper sees the paper. A history may start after v1 where the earlier Versions were never recorded; none is made up to fill the gap.
_Avoid_: Revision (the act that produces a Version, not the Version), file version or upload version (the per-slot numbering of supplementary files, a different thing), draft (the Record's state before it is submitted).

**Review discussion**:
The private conversation on a submitted Record between its owners and everyone who has held a [[Seat]] on it, shown in its review timeline. Never mixed with [[Comment]]s.
_Avoid_: Comments (the public thread), notes, chat.

### Templates

**Requirement**:
A document a record type asks for, labelled Required or Optional, which RDCO sets. A submitted Record keeps its file for that requirement; the label informs and never stops a submission.
_Avoid_: Upload slot (the code's name for it), checklist item, mandatory document.

**Template**:
A file people download and follow when preparing a document for a Record, such as a blank Release Form or a proposal format. RDCO attaches one to a [[Requirement]]; an [[Adviser]] can share their own for Proposals. What people produce from it is the document they submit.
_Avoid_: Form (the filled-in document, not the file to follow), request template (that is a [[Request preset]]).

**Request preset**:
An office's saved list of documents, sent together as one document request. Deferred until an office shows it needs one (IR-118).
_Avoid_: Request template, checklist, template.

### Comments

**Comment**:
A message in a published paper's public thread, written by any signed-in account. Only its writer edits or deletes it; RDCO or the [[System Admin]] may also delete it, and the writer is then told why. A deleted Comment that has replies stays in place as a marker with its words gone. Comments exist only on published papers, never on drafts, papers under review or Proposals.
_Avoid_: Public discussion (the ADR's name for the thread), post, review comment.

**Comment report**:
A reader telling RDCO that a [[Comment]] needs attention, with a reason. Only RDCO sees reports; the Comment's writer never learns one was made.
_Avoid_: Flag, complaint.

### Library

**Library**:
A reader's private collection of [[Saved Record]]s and [[Saved Call]]s. It belongs to the reader's account, and nobody else can see it.
_Avoid_: Repository, catalogue (that is Discover), collection, bookshelf.

**Saved Record**:
A Record a reader has kept in their [[Library]]. A reader saves a Record at most once, and saving tells no one else anything.
_Avoid_: Like, star, favourite, bookmark.

**Reading status**:
Where a reader is with a [[Saved Record]]: Want to read, Reading or Completed. A Saved Record has at most one; giving a Record a status saves it, and unsaving it clears the status.
_Avoid_: Status folder, shelf, progress.

**Folder**:
A named group a reader makes for their own [[Saved Record]]s. A Reading status is not a Folder, even where the interface shows them side by side.
_Avoid_: Collection, list, tag.

**Reading history**:
The papers recently opened in this browser. It is not part of the [[Library]], never leaves the browser, and is cleared on sign-out.
_Avoid_: Recently viewed, activity, reading log.

### People

**Profile**:
A page about one account that any signed-in user can open: their name, affiliation and role, the photo, bio, research interests and ORCID iD they chose to add, the published papers they own or advised, and their [[Collaborator]]s. It never shows their email address. The role shown is Student, Adviser or the office's name (ITSO, IERC, KTTO, RDCO). A [[System Admin]] has no Profile, and a [[Suspension]] hides one. Where a name has no Profile to open, as for a suspended or former user on a paper, it shows as plain text and is left out of Collaborators.
_Avoid_: Account (the sign-in identity), user page, bio, Faculty (the role is Adviser).

**Collaborator**:
Another account that shared a published paper with this person, as a co-owner, as its Adviser, or as an advisee. Byline authors without an account are not collaborators.
_Avoid_: Co-author (a byline name, not an account), team member.

**People search**:
Finding [[Profile]]s from Discover's one search bar, by name or research interest, narrowed by college, department and role. It needs a search term or a filter and never lists everyone. A result shows the person's photo, name, role, affiliation and how many published papers they own or advised, and says which interest matched when it was not the name. Never an email address. Suspended and former users, and System Admins, do not appear.
_Avoid_: Directory (it never lists everyone), user search.

**Contact person**:
The one owner of a Record who gets its review emails, and whom IRIS names when someone outside it needs to reach its owners, such as the owners of a similar open Proposal. By default it is the owner who submitted the Record; any owner can choose another. Their email is shown only where a decision says so, never on their Profile.
_Avoid_: Representative, group leader, primary author (authors are byline names, not accounts).

### Downloads

**Download**:
Saving a copy of a published paper's [[Manuscript]] to take out of IRIS. Distinct from reading it inside IRIS, which stays open to every reader who can see the paper.
_Avoid_: Export, access, view.

**Download request**:
A reader asking RDCO to [[Download]] one published paper, always with a note saying why. RDCO alone approves or declines it, and a decline always carries a note. A reader holds at most one pending request per paper; a declined or expired one may be made again. The paper's owners, its Adviser, office staff and its assigned reviewers download without one.
_Avoid_: Access request (the old page's name), download link.

**Download grant**:
What an approved [[Download request]] gives its reader: they may download that paper while signed in, as often as they like, until the grant expires or RDCO revokes it with a note. It is never a link, and nothing emailed works on its own.
_Avoid_: Download link, token, download permission.

### Discover

**View**:
One account's first opening of a published paper. A paper's views are the number of distinct accounts that have opened it since it was published: opening it again never adds one, and its owners never count. Which accounts viewed a paper is used only to count them and is never shown.
_Avoid_: Access (the audit log's word for one opening), hit, read, reader count.

**Trending**:
Published papers ordered by the [[View]]s they gained in the last 30 days, then by all-time views, then newest first. Distinct from Most Viewed, which orders by all-time views alone.
_Avoid_: Popular, hot, most viewed.

### Calls & Conferences

**Call**:
An invitation to submit papers on the Calls & Conferences board, to a conference, congress, symposium, workshop, journal or book. It has a paper deadline, one or more [[Area]]s and, when there is an event, the event's dates. RDCO or an Adviser posts it. An Adviser changes only the Calls they posted; RDCO can change any.
_Avoid_: Opportunity (the code's name, which readers never see), announcement, posting.

**Call request**:
An Adviser's [[Call]] waiting for RDCO to confirm or reject it. Only that Adviser and RDCO can see it, and it becomes public only once confirmed.
_Avoid_: Post request, pending post, submission (that is a Record's).

**Saved Call**:
A [[Call]] a reader has kept in their [[Library]]. A reader saves a Call at most once, and it stays saved after the Call is over, until the reader removes it or RDCO deletes the Call.
_Avoid_: Bookmark, reminder.

### IP and commercialization

These terms come from ADR-066, accepted 2026-11-13. None is built yet.

**IP application**:
A request to protect one kind of intellectual property in a paper (Patent, Utility Model, Industrial Design, Trademark or Copyright), owned by KTTO and running beside the paper's publishing rather than inside its review. It moves forward through For Application, Reviewed, Filed, and then Approved or Disapproved by the IP office; KTTO can end it as Not filed, and the owners can withdraw it before filing. A Thesis/Research or Project can have several, at most one open per kind.
_Avoid_: IP review (that is a [[Specialist office]]'s clearance in the paper's review), patent request, IP status.

**Commercialization application**:
A request for TBI to review a paper's commercial potential and record its recommendations, running beside the paper's publishing like an [[IP application]]. Designed in IR-979, once TBI is an office.
_Avoid_: Commercialization flag (the paper's old Yes/No), KTTO review.

**Inventor**:
A person named on an [[IP application]] as having contributed to what it protects. Kept as a name, not an account. The list starts as the paper's byline and KTTO edits it, so it can differ from the paper's owners.
_Avoid_: Author (a byline name on the paper), owner (an account that owns the paper), applicant.

**Publishing gate**:
The warning RDCO sees before publishing a paper whose [[IP application]] hasn't been filed yet, because making an invention public first can cost it its novelty. RDCO can publish anyway, with a reason that is recorded.
_Avoid_: Publication block, IP hold (RDCO is warned, not stopped).

### Accounts

**Sign in**:
Entering IRIS with an existing account's CIT-U email and password.
_Avoid_: Login, log in, sign on.

**Register**:
Asking for an IRIS account as a Student or an [[Adviser]], with a CIT-U email address. A registrant cannot sign in until they verify their email, and gets their role only once RDCO approves the request. A registration nobody verifies is eventually deleted, and registering again replaces it.
_Avoid_: Sign up, signup, create account (the screen's title, not the act).

**Unverified registration**:
An account whose registrant has not yet verified their email. RDCO never sees it, nobody can make it a co-owner, and its role request can't be approved. It expires a fixed time after registering unless something links to it, and registering again on its address replaces it. Expiring and replacing are not [[Account deletion]], and the time is not a [[Retention period]].
_Avoid_: Abandoned signup, pending account, inactive account.

**Adviser**:
The role of the person who reviews their advisees' Records first and routes them onward. It is a role someone asks for when they register, not a job title.
_Avoid_: Faculty, faculty adviser, professor.

**RDCO**:
The Research and Development Coordinating Office, responsible for final approval and archiving of all research and IP submissions. It is the highest office staff role and runs the research workflow: it approves roles, manages accounts and office coordinators, and answers download and delete requests. It is not the [[System Admin]].
_Avoid_: Admin, administrator.

**System Admin**:
The role that runs IRIS itself rather than its research workflow. It decides [[Account deletion]] requests, sets [[Retention period]]s and alone reads the Audit Log, and it shares removing Comments with RDCO. It sees who published each [[Notice]] but does not publish one. Nobody can ask for it; developers set up the first one.
_Avoid_: Admin (on its own), administrator, superuser.

**Suspension**:
RDCO's hold on an account, always with a written reason. The person is emailed the reason when it starts and again when it is lifted. While it lasts they cannot sign in, and their [[Profile]] and search entry are hidden; their papers and [[Comment]]s stay where they are. Not the same as the pause after repeated failed sign-ins, which hides nothing and emails no one, nor as [[Account deletion]].
_Avoid_: Lock (the code's word), lockout (the failed-attempts pause), deactivation, ban.

**Account deletion**:
Removing a person from IRIS at their own request, once the System Admin confirms it and nobody is waiting on them. Their personal details go and they can't sign in. A published paper keeps their name as an Author or as Adviser, and elsewhere they show as "Former user".
_Avoid_: Closure, close account, deactivate.

**Notice**:
The text a person answers to give Signup consent and AI consent. RDCO alone publishes each new version by pasting it, and a published version never changes.
_Avoid_: Terms, DPA terms, privacy policy (a document the university writes).

**Signup consent**:
A person's acceptance of the Notice, which having an account requires. Withdrawing it means Account deletion.
_Avoid_: Consent (on its own), terms.

**AI consent**:
A person's Yes or No to AI using their papers, asked with the Notice. A No leaves their account as it was. A Record takes its Contact person's answer when it is created and keeps it, so a later change only reaches later Records, unless a person going from No to Yes chooses to include their earlier ones.
_Avoid_: Consent (on its own), Submission consent (the per-paper version this replaced), DPA acceptance, Discoverable (a separate decision).

**Retention period**:
How long IRIS keeps one kind of personal data before erasing it for good. The System Admin enters it once the data protection officer approves it, and a blank period erases nothing.
_Avoid_: Expiry, TTL.
