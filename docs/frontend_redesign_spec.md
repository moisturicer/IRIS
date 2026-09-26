# Frontend redesign for the settled workflow — specification (IR-374)

**Status: APPROVED by the project lead — 2026-09-26, after one reconciliation pass (§0, Appendices J–L).** Tracked on [IR-374](https://citiris.atlassian.net/browse/IR-374). **Its subtasks are not yet created, and Appendix J's changes to existing tickets are not yet applied.** All §7.1 decisions are settled (§7.3 records the 2026-09-26 design session).

**Governing decisions:**

- [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md) (Accepted), which is "the settled IRIS submission/review workflow" below. It sits on [ADR-021](adr/021-reviewer-directed-routing.md)'s machinery and [ADR-022](adr/022-explicit-document-requests.md)'s document requests.
- [`ui-ux/16-paper-view-and-review.md`](ui-ux/16-paper-view-and-review.md), which this spec extends and amends in one place (§4.6).

**Decisions confirmed for this spec (project lead, 2026-09-26):**

1. **Test seams.** Three seams: Vitest page tests over a mocked API, the backend REST API, and recorded browser checks at fixed viewports. No new e2e runner.
2. **Publish requires the manuscript only.** Every other document is asked for later through ADR-022 document requests.
3. **AI prefill is Docling-only, with no LLM, for the MVP.**
4. **This spec lives in the repo** until it is approved.
5. **Sidebar.** Submit / Disclosure and My Workspace leave the sidebar.
6. **Discover and Publish.** Discover gains **Publish**, which opens a dialog.
7. **My Library.** It absorbs My Workspace without its counters.
8. **Scope of the redesign.** This is a full interaction and visual redesign, not a geometry pass.

## 0. Workflow invariants the frontend must not violate

These restate [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md). **The frontend decides none of them; it only renders what the server says.** A ticket whose UI would break one is wrong, whatever its acceptance criteria say.

1. **No Intake / Triage stage.** No screen, label, route preview or copy names Intake as a current step. Historical rows read *Intake (retired)*, and that label comes from the server.
2. **Every record enters with its Adviser**, including Proposals. The frontend never picks a first reviewer beyond the owner naming their Adviser.
3. **The Adviser is never an owner.** The frontend prevents it; the server refuses it (IR-260).
4. **Revisions are versions of the same record.** No UI path creates a new record to answer a revision. Metadata-only changes during a revision are part of the next version (IR-273), never a silent edit.
5. **A rejected record is terminal and archived.** No *New version*, *Continue*, *Continue as…* or *Edit details* is ever offered on it.
6. **An accepted Proposal continues as a *new* Thesis or Project record** linked to it, and the Proposal is never mutated or re-typed.
7. **Direct Thesis/Project submission stays available** in Publish, without any Proposal.
8. **Specialist routing targets an office**, with nominating a person optional. No dialog requires the router to know an individual reviewer.
9. **Reviewers join through office seats:** claimed from the pool, assigned by a coordinator, nominated, or added by a seat holder. An office can hold several seats.
10. **The frontend never routes to RDCO and never offers an RDCO decision while specialist review is unresolved.** RDCO's assignment opens only by server hand-back.
11. **RDCO decides the specialist path.** An Adviser may publish only on the no-specialist path, and only when the server grants that capability.
12. **Specialist offices never reject or publish.**
13. **A Discoverable Proposal is never presented as published research.** It lives in its own section with the *Proposal · In development* label, shows a summary only, and is never cited by Ask IRIS.
14. **Public discussion and private review discussion never share a surface or a component**, and review content never renders in Reading or Summary mode.
15. **Clearance-aware resubmission is visible, not reimplemented.** The UI shows which clearances were preserved from server fields; it never computes them.
16. **Every action is offered only when the server grants it** (capabilities, §4.8), and every endpoint re-checks.

**During the transition** — until IR-260 cuts over — the live backend still runs the legacy pipeline, including RDCO intake for Thesis/Research and Project. The frontend therefore **reads current holders and labels from the server rather than asserting the ADR-032 flow in copy.** For example, Publish's success screen names whoever the server says now holds the record (§4.4); it does not hard-code "Sent to your adviser".

Sections 1–6 follow the project's `to-spec` template. The appendices hold what the request asked for beyond it:

- **A.** Current frontend architecture.
- **B.** Current backend/API architecture.
- **C.** View-by-view audit.
- **D.** Backend/API gap analysis.
- **E.** Jira conflict analysis.
- **F.** Proposed ticket architecture, with acceptance criteria.
- **G.** Dependency graph and implementation order.
- **H.** Agent-ready work.
- **I.** Explicitly not implemented.
- **J.** Ticket reconciliation matrix.
- **K.** IR-350 family (reader / Paper Chat) reconciliation.
- **L.** Duplication check: F/B tickets against the seven ADR-032 tickets.

File paths appear only in the appendices, where they are findings, not decisions.

---

## 1. Problem Statement

IRIS's screens were added one ticket at a time, and it shows. A student who wants to put research into IRIS gets:

- a sidebar with two separate "IP Management" destinations, *Submit Disclosure* and *My Workspace*;
- a third, *My Library*, that means something different again;
- a three-step administrative wizard on its own page, whose third step lists every supporting-document slot for the type. *(Correction, reconciliation pass: none of those slots is required any more. IR-118's migration `documents/0005` set every `is_required` to false, and the wizard already asks only for the manuscript. The problem is the length and placement of the flow, not a requirement.)*

Their own submissions live on a dashboard of counters and six tabs named after office stages ("Validation", "IP Assessment", "Commercialization"). Those tabs describe the old fixed pipeline, not what the student needs to do next.

Reviewers get something worse:

- They read the paper on one page (Paper View) and decide on another (`/review/:id/evaluate`), which drops them out of the paper.
- Document management is a third page.
- Their queue is labelled with the old vocabulary ("Awaiting me / Cleared / Sent back").

**Nothing in the interface presents the settled workflow:**

- an Adviser-first review;
- office pools;
- versions;
- lineage;
- a pull-request-style review conversation.

**The interface also mixes two ways of deciding what a user may do.** Some screens read the server's `can_act`. Others compare role names on the client, for example "RDCO or the assigned Adviser may mark completed".

**It is visually inconsistent:**

- two empty-state components;
- four different renderings of "a research record";
- a Discover page with its own private header;
- a header search box that does nothing;
- status wording that sometimes comes from the server and sometimes from a client map.

## 2. Solution

IRIS becomes three places and a dialog:

- **Discover** is where research is found and where it starts. It lists published research and, once the backend supports it, Discoverable Proposals. A single **Publish** button opens a short dialog:
  1. drop the manuscript;
  2. confirm what IRIS read from it;
  3. name your adviser;
  4. submit.

  There is no document checklist. Reviewers ask for further documents when they need them.
- **My Library** is the user's own research space. It shows their research as cards, each stating the one thing that matters next ("IERC asked for revisions — upload a new version"). Saved papers sit alongside, in the folder model My Library already has. There are no counters.
- **Paper View** is the one page for a record, for every role. It has four sections: Overview, Paper, Review and Files. Who sees which section, and which buttons, is decided by the server. A reviewer opens the review *inside* Paper View, with the paper on one side and the review conversation on the other, and acts from there. There is no separate decision page.
- **My Reviews** replaces the review queue, with the tabs **To review · In review · Done**. It appears for a user **only when the server says they have review work or review capability** (§4.2), not because of their role name.

Everything else either:

- moves into a dialog (Publish, Edit details, Request document, Route…);
- becomes a section of Paper View (Files, Action required);
- or leaves the sidebar (Notifications stays in the header bell; Settings moves to the account menu).

The visual language set on Paper View by IR-356 becomes the whole product's:

- editorial serif titles on content;
- Inter for the interface;
- white surfaces on a soft grey canvas;
- maroon only for the primary action, focus and active states;
- status in four meaning-based tones.

## 3. User Stories

### Finding research (any signed-in user)

1. As a reader, I want Discover to open on the newest published research, so that I see what CIT-U has produced without configuring anything.
2. As a reader, I want one search box on Discover that searches titles, abstracts and authors, so that I don't have to guess which field holds a word.
3. As a reader, I want to filter by record type (Thesis/Research, Project), college, classification, year and "has IP", so that I can narrow a large catalogue.
4. As a reader, I want active filters shown as removable chips, so that I can see and undo what I've narrowed by.
5. As a reader, I want to sort by newest or most viewed, so that I can find what's current or what's popular.
6. As a reader, I want each result card to show the type, title, authors, college, year and IP tags, so that I can judge relevance before opening it.
7. As a reader, I want to cite or save a paper straight from its card, so that I don't have to open it first.
8. As a reader, I want a clear message when my search returns nothing, with a way to clear filters, so that an empty page isn't a dead end.
9. As a reader, I want Discover to load more results as I continue down, without losing my place, so that browsing isn't paginated busywork.
10. As a reader on a phone, I want the filters in a sheet I can open and close, so that results aren't pushed off-screen.
11. As a reader, I want a **Proposals** section showing proposals their authors made Discoverable, clearly labelled "In development — not approved research", so that I can find collaborators without mistaking a proposal for published work.
12. As a reader, I want a Proposal card to show only its title, abstract, authors and what they're looking for, so that I can see what the idea is without reading the unprotected manuscript.

### Publishing (Student, Adviser as author)

13. As an author, I want a **Publish** button on Discover, so that starting a submission is one click from where I already am.
14. As an author, I want to choose Proposal, Thesis/Research or Project with a one-line explanation of each, so that I pick the right type.
15. As an author, I want to drag my manuscript onto the dialog, or pick it from a file browser, so that uploading works however I prefer.
16. As an author, I want a PDF that's too large or the wrong type rejected immediately, with the limit stated, so that I don't wait for an upload that will fail.
17. As an author, I want to see upload progress and be able to retry a failed upload without re-entering anything, so that a network blip isn't a restart.
18. As an author, I want IRIS to fill in the title and abstract it found in my PDF, marked "Found in your PDF", so that I type less.
19. As an author, I want to accept, edit or discard each suggestion, and I never want a suggestion to overwrite something I've typed, so that I stay in control.
20. As an author, I want to keep going if IRIS can't read my PDF, with a plain "We couldn't read details from this file — please fill them in", so that extraction is help, not a gate.
21. As an author, I want to name my adviser from a searchable list, so that my submission reaches the right person.
22. As an author, I want IRIS to refuse me as my own adviser, so that nobody can approve their own work.
23. As an author, I want to add co-authors by name, so that credit is recorded.
24. As an author, I want less-common fields (PSCED, IP and ethics hints, commercialisation) behind a "More details" disclosure, so that the dialog stays short.
25. As an author, I want to flag "this may involve IP / human subjects / commercialisation" as a hint to my adviser, so that I can raise a concern without choosing offices myself.
26. As an author, I want a review screen showing exactly what I'm about to submit, so that I can catch mistakes.
27. As an author, I want to accept the data-privacy terms on that review screen, so that consent is given where the submission happens.
28. As an author, I want to close the dialog and find my unfinished submission under Drafts in My Library, so that I can finish later.
29. As an author, I want to reopen a draft into the same dialog at the step I left, so that nothing I entered is lost.
30. As an author, I want a success screen naming who will review my work, with "Open paper" and "Publish another", so that I know what happens next.
31. As an author submitting a Proposal, I want to choose Private or Discoverable, told plainly that Discoverable shows my title, abstract and name and lets IRIS's AI suggest collaborators, so that I decide whether others can find my idea (once supported by the backend).
32. As an author, I don't want to be asked for ethics forms, patent searches or similarity reports at submission, so that I'm only asked for them if a reviewer actually needs them.

### My Library (everyone; research sections for authors)

33. As an author, I want My Library to open on my own research as cards, so that my work, not a dashboard, is the focus.
34. As an author, I want each card to state its status in plain words and the next step if one is mine, so that I know what to do without opening it.
35. As an author, I want to narrow my research to Drafts, In review, Needs my action, Accepted & published, Proposals or Archived, so that I can find a record quickly.
36. As an author, I want "Needs my action" to stand out when something is waiting on me, so that I don't miss a revision or document request.
37. As an author, I want a draft's card to offer **Continue**, reopening the Publish dialog, so that finishing a draft is one click.
38. As an author with an accepted Proposal, I want its card to offer **Continue as Thesis / Project**, so that I can take the next step from my library (once lineage exists).
39. As a reader, I want my saved papers in folders (Want to read, Reading, Completed, and my own), so that I can organise what I read.
40. As a reader, I want my reading history, so that I can find a paper I opened last week.
41. As a reader, I want to be told saved papers live in this browser only, so that I'm not surprised on another device.
42. As a reviewer who doesn't author, I want My Library to open on Saved papers, so that I don't see an empty "my research" section.
43. As a mobile user, I want the library's folder rail to collapse into a selector, so that cards get the full width.

### Paper View (everyone, with sections by capability)

44. As a reader, I want Paper View to show the type, status, title, authors and adviser at the top, so that I know what I'm looking at.
45. As a reader, I want the Overview section to show the abstract, the AI overview and the key facts, so that I can decide whether to read the paper.
46. As a reader, I want the Paper section to be the paper and Ask IRIS side by side, as it is today, so that reading is uninterrupted.
47. As a reader, I want Cite, Save and Share available on every record I can read, so that the common actions are always there.
48. As an owner, I want the page to show a banner at the top when something is waiting on me, so that I see my next step first.
49. As an owner, I want to upload a requested document from that banner, so that answering a request is one step.
50. As an owner, I want each requested document to read Requested → Uploaded, awaiting review → Accepted, or Replacement needed with the reviewer's reason, so that I always know where each one stands.
51. As an owner, I want to edit my record's details in a dialog from Paper View, so that a metadata-only revision doesn't send me to another page.
52. As an owner asked for revisions, I want **Submit new version** where the revision is requested, so that answering a revision is obvious.
53. As an owner, I want the Files section to list my manuscript and every supporting document, with upload, replace and download, so that files live with the record rather than on a separate page.
54. As a participant, I want the Review section to show the whole history of the review as one timeline (who routed it where and why, each finding, each request, each version), so that the review reads like a pull request, not a set of forms.
55. As a reviewer, I want to open the review with one button and then see the paper and the review timeline side by side, so that I review while reading.
56. As a reviewer, I want to switch to the Paper tab to ask Ask IRIS about the paper, and come back to the review where I left it, so that questioning the paper never loses my review.
57. As a reviewer, I want only the actions I'm allowed to take right now in an action bar, so that I'm never offered something the server will refuse.
58. As a reviewer, I want terminal actions (reject, publish) to ask for confirmation and state the consequence, so that I can't end someone's work by accident.
59. As a reviewer, I want disabled actions to say why (for example "Waiting for the author's revision"), so that I understand the state.
60. As a reviewer, I want request-document, request-revision and routing to open dialogs from the action bar, so that I never leave the paper to act.
61. As a reviewer, I want to see which offices are involved and where each stands, in one status strip, so that I know who else is looking.
62. As a participant, I want to comment in the review timeline (once review comments exist), so that questions and answers stay with the record.
63. As a reader of a published paper, I want a public discussion under it (once it exists), kept visibly separate from any private review, so that I never see internal review comments.
64. As a participant, I want to switch between versions of the manuscript (once versions exist), so that I can see what changed.
65. As a reader of a Thesis developed from a Proposal, I want a link to that Proposal (once lineage exists), so that the history is traceable.
66. As a stranger opening a Discoverable Proposal, I want the summary and not the PDF, so that the author's idea stays protected.
67. As a user who follows a stale or forbidden link, I want the same "not found" as a missing record, so that IRIS never confirms a private record exists.

### My Reviews (Adviser, ITSO, IERC, KTTO, RDCO)

68. As a reviewer, I want **My Reviews** to list what I need to review, what I've opened, and what I've finished, as To review · In review · Done, so that my work is organised by what I need to do.
69. As an office member, I want unassigned records routed to my office in To review with **Claim**, so that the office's shared work is visible (once pools exist).
70. As a reviewer, I want each row to show the record type, title, who routed it and why, and how long it's waited, so that I can prioritise.
71. As a reviewer, I want rows waiting on the author marked "Waiting on author" or "Waiting on document", so that I don't open something I can't act on.
72. As a reviewer, I want the tab I'm on kept in the URL, so that back and bookmarks work.
73. As a reviewer, I want to land on My Reviews when I sign in, so that my work is the first thing I see.

### Navigation and consistency (everyone)

74. As any user, I want a short sidebar (Discover, Ask IRIS, My Library, My Reviews if I review, Calls & Conferences), so that the product feels simple.
75. As any user, I want notifications in the header bell, and settings under my account menu, so that they don't crowd the main navigation.
76. As a user with an old link to Submit Disclosure, My Workspace, a review evaluation page or a documents page, I want to land in the right new place, so that nothing I bookmarked breaks.
77. As any user, I want status words to be the same everywhere a record appears, so that "In review" means one thing.
78. As a keyboard user, I want every dialog to trap focus, return focus when closed, and close on Escape, so that I can work without a mouse.
79. As a screen-reader user, I want status changes (upload finished, row moved tab, action done) announced, so that I know the result of what I did.
80. As a phone user, I want every screen usable at 360 px with no sideways scrolling, so that IRIS works on the device I have.

### Operator / developer

81. As a developer, I want every "can this user do X" decision to come from one capabilities adapter over the server's fields, so that no screen compares role names.
82. As a developer, I want one research-record card used by Discover, My Library and My Reviews, so that a record looks the same everywhere.
83. As a developer, I want removed routes to redirect rather than 404, so that the redesign doesn't break links.
84. As a developer, I want the palette guard to stay green as screens are replaced, so that the palette rollout isn't undone.

---

## 4. Implementation Decisions

### 4.1 Information architecture — before and after

```
BEFORE (sidebar, by section)                 AFTER
Research Exploration                         Discover            [Publish ▸ dialog]
  Discover                                   Ask IRIS
  Ask IRIS                                   My Library          (My research + Saved)
  My Library                                 My Reviews          (only when the server grants it)
  Calls & Conferences                        Calls & Conferences
IP Management                                ── Administration (RDCO only) ──
  Submit Disclosure        → dialog            Import Records
  My Workspace             → My Library        Role Requests
  Import Records (RDCO)                        Download Requests
Review Queue                                   Delete Requests
  Review Queue             → My Reviews        Audit Log
  Approved Proposals (RDCO)→ removed
Tools                                        Header: notification bell · account menu
  Notifications            → header bell            (Settings & Profile, Help, Sign out)
  Settings & Profile       → account menu
Administration (RDCO) — unchanged
```

**What disappears, and where it goes:**

| Removed | Becomes | Old URL behaviour |
|---|---|---|
| Submit Disclosure page | Publish dialog on Discover | `/records/add` → `/?publish=new` |
| My Workspace page and its counters | My Library → *My research* | `/workspace` → `/records/mine?section=research` |
| Review evaluation page | Paper View → Review section | `/review/:id/evaluate` → `/records/:id?section=review` |
| Record documents page | Paper View → Files section | `/records/:id/documents` → `/records/:id?section=files` |
| Edit Record page | "Edit details" dialog in Paper View | `/records/:id/edit` → `/records/:id?edit=details` |
| Approved Proposals page | nothing. ADR-032 retires the Proposal *complete* act and gives RDCO no Proposal role | `/review/approved-proposals` → `/review` |
| Header search box (inert) | Discover's search | — |
| Role-split home page | Discover for everyone. Reviewers still land on My Reviews after sign-in | — |

**What remains:**

- **Kept routes:** Ask IRIS, Calls & Conferences, Notifications (route kept, reached from the bell), Settings, Help, all Administration pages, and the authentication screens.
- **"Review Queue" is renamed "My Reviews"**, at the same `/review` path. Its content (tabs, rows, claim/assign) is IR-268's; F1 only changes the navigation entry and its gate.

**Why a redirect table rather than deleting the routes:** bookmarks, notification links and emails already sent point at the old paths. Every redirect is one entry in the router, and a test asserts each one.

### 4.2 Navigation mechanics

- **The access map stays the single source** for which screens a role may open, and for the sidebar. That is IR-160's design, and it is correct for *screen* access.
- **The access-map changes:**
  - It gains a `publish` capability for authors, which gates the Publish button, not a route.
  - It loses the `submit`, `workspace`, `editRecord`, `evaluate` and `approvedProposals` screens, which become redirects.
  - The *Tools* section leaves the sidebar.
- **The access map is never used for record-level decisions** such as "may I review this record". Those come from the record's capabilities (§4.8).
- **My Reviews is gated by the server, not the role (reconciliation pass).** Today the access map shows the Review Queue to every Adviser, ITSO, IERC, KTTO and RDCO user, including an Adviser with no advisees. Instead, `GET /users/me/` gains a `review_access` object (B3, Appendix D):

  ```
  "review_access": { "my_reviews": bool, "offices": ["itso", ...], "is_coordinator": bool }
  ```

  - `my_reviews` is true when the user holds or has held a seat or assignment on any record, **or** is a member of an office party. Office members need the page even with no seats, because the office pool (claim) lives there.
  - **Before seats exist** (phase 1), the server computes it from what exists: the user is `record.adviser` on any submitted record, or staffs an office party (`staffable_parties`), or has written a `Review`. When the ADR-032 seats ticket lands, it replaces that computation with seats, without changing the field.
  - Both the sidebar entry and the `/review` route guard read this flag. The access map keeps `reviewQueue` only as the outer role gate, and the server's queue endpoint still scopes every row.
  - Landing after sign-in follows the same flag: My Reviews when `my_reviews` is true, otherwise Discover.
- **The sidebar's workspace badge becomes a dot on My Library.** It is shown only when something needs the user's action. It is justified because it is actionable, not a count for its own sake. **Correction found while verifying:** today's badge reads `/dashboard/stats/`'s `pending_mine`, which counts the user's records that are *in review*, not records *waiting on the user*. The dot therefore needs `needs_action_mine` added to that endpoint (B2, Appendix D).
- **One app header on every screen.** Discover's private header is removed, and Discover becomes a normal page under the shared header. The header holds only:
  - the menu toggle (mobile);
  - the breadcrumbs slot;
  - the notification bell;
  - the account menu.

### 4.3 Discover

**The page's primary task is to find research, with a secondary task of starting a submission.** From the top:

- **Page head.** "Discover" (serif display title), then one line of description. **Publish** sits on the right, as the page's one primary pill. It appears for authors only.
- **Search.** The existing search composer, full width.
- **Content tabs:**
  - **Research** (published Thesis/Research and Project; the default).
  - **Proposals**, rendered only once the Discoverable backend exists. It is **never** shown empty before that.
- **Filter bar:**
  - one row of filter buttons: Type · College · Classification · Year · IP & patents;
  - a **Sort** menu: Newest · Most viewed;
  - active filters as removable chips beneath;
  - below `md` the filters collapse into a "Filters" button that opens a bottom sheet.
- **Results.** A responsive grid of `ResearchCard`, with *Load more* kept (it is honest about how many remain).

**What goes:**

- **The "saved views" row** (For you · Latest · Most viewed · IP & Patents · Theses) is dissolved:
  - "For you" has no personalisation signal and duplicated Latest, so it is removed as fabricated;
  - Latest and Most viewed become Sort;
  - IP & Patents and Theses become filters.

  Tabs are kept only for a real content split (Research vs Proposals).
- **Discover's private `EmptyState` is deleted** in favour of the shared one.

**States:**

- **Loading:** skeleton cards in the grid shape.
- **Empty catalogue:** "Nothing has been published yet." Authors also see a Publish call to action.
- **No results:** "No research matches these filters", with **Clear filters**.
- **Error:** "We couldn't load research", with **Try again**.
- **Rate-limited:** IR-368's message, when that lands.

### 4.4 Publish dialog

**Pattern: one dialog, three steps, with a slim progress indicator.**

It is not a long form, and not a full-page wizard. Three steps is the fewest that keep upload, confirmation and consent separate. Each step fits one screen at 1280×720 without scrolling the dialog body, except for a long abstract.

At `sm` and above it is a centred dialog up to 720 px wide. Below `sm` it is a full-screen sheet. It is built on the existing `Modal` (focus trap, Escape, return focus).

**Opening.** The Publish button, or the URLs `/?publish=new` and `/?publish=<draftId>` (so redirects and *Continue draft* land here). The URL state is cleared on close.

**Step 1 — "Your manuscript".**

- **Record type:** three large radio cards (Proposal · Thesis/Research · Project), each with one sentence. The server's record types are the source; the sentences are copy.
- **Drop zone:**
  - the manuscript, drag-and-drop or *Choose file*;
  - accepted types and the size limit are stated in the zone;
  - type and size are checked client-side before any upload.
- **On a valid file:**
  - the client **creates the draft Record at once**, with the type and a provisional title taken from the file name (title is the Record's only required field), and the manuscript as `abstract_file`;
  - it shows upload progress;
  - the server already queues Docling extraction for the manuscript on that save (see Appendix B).
- **Failure:** a failed upload shows the reason and **Retry**, which keeps the type and the file. Replacing the file re-uploads over the same draft.
- **Continue** is enabled once the upload succeeds.

**Step 2 — "Details".**

- **Essential fields:** title, abstract, adviser (searchable, from the existing advisers endpoint), co-authors, year.
- **More details** (a disclosure, closed by default): classification, PSCED, and "Flag for your adviser" hints (possible IP · human subjects · commercialisation). These are the existing `is_ip`, `requires_ethics_review`, `for_commercialization` and `requested_*` fields. Under ADR-032 they are hints the Adviser sees, not routes, and the copy says so.
- **Prefill** (§4.5): a field the server found text for shows a "Found in your PDF" chip with **Use** and **Dismiss**. A suggestion **never overwrites** a field the user has typed in.
- **While extraction runs:** the title and abstract fields show a quiet inline "Reading your PDF…" line. They are **never** disabled, so the user may type over them at any time.
- **Adviser ≠ owner.** The client disables choosing oneself, with an explanation. The server refuses it as well (IR-260 owns the server rule).
- **Validation:**
  - inline, on blur and on Continue;
  - each error is linked to its field (`aria-describedby`);
  - the first invalid field receives focus.
- Details are patched onto the draft on Continue, so closing the dialog never loses them.

**Step 3 — "Review & submit".**

- A read-only summary grouped as *Manuscript · Details · Hints*, each with an **Edit** link back to its step.
- The data-privacy consent, reusing `DpaConsentInline`.
- For a Proposal, once the backend supports it: a **Visibility** choice (Private · Discoverable), with the consent text from ADR-032 §8 as amended. There is no "Looking for" note.
- **Submit** calls the existing submit action with the consent flag.

**Success.** The dialog body becomes a confirmation:

- a check icon;
- "Sent to Prof. Santos for review", with the name taken from `current_holders`;
- a short "what happens next", written from the record type and the settled workflow, and never inventing a timeline.

  **Who it names comes from the server.** After submit, the dialog re-reads the record and names `current_holders`. During the transition that may still be RDCO intake for a Thesis or Project (§0). The adviser-first sentence appears only once the server's holder is the Adviser.
- **Open paper** and **Publish another**.

A polite live region announces the result.

**Failure recovery.**

- A server refusal on submit keeps the dialog on step 3. It shows the server's message and field errors, jumping back to step 2 when a field is at fault.
- A network failure offers Retry.
- Closing at any point keeps the draft. My Library → Drafts → **Continue** reopens it at the first incomplete step.

**What is deliberately absent:**

- the upload-slot checklist, since the manuscript alone is required (decision 2);
- office selection;
- the route preview's "RDCO Intake" bookends, which are ADR-021 vocabulary that ADR-032 retired.

**Continuing a Proposal reuses this dialog.** *Continue as Thesis / Project* (ADR-032 §6, owned by the lineage ticket) asks the server to create the child draft. The dialog then opens at `/?publish=<childDraftId>` with the pre-filled fields, and the owner uploads the full manuscript. There is one submission path, not two.

**Replaces** `AddRecordPage` and its steps. The Details step becomes a shared **`MetadataForm`**, reused by the *Edit details* dialog (§4.6), so metadata is edited in one component everywhere.

### 4.5 Docling prefill (MVP) — the only AI in Publish

**What exists (verified):**

1. Saving a Record with `abstract_file` queues `extract_manuscript_text`. The extraction runs on the `extraction` Celery queue against Docling-serve.
2. The result, a `PdfExtraction` with `kind=MANUSCRIPT`, stores `structure`: a serialized `NormalizedDocument` whose `title` comes from Docling's `title` label, plus its headed sections.
3. **No endpoint exposes either the extraction status or the structure for a Record's manuscript**, and nothing proposes metadata.

**Minimum backend (one endpoint, no model, no migration):**

`GET /records/<id>/metadata-suggestions/`, owner-only. It reads the manuscript `PdfExtraction` and returns:

```
{ "state": "pending" | "ready" | "failed" | "unsupported",
  "suggestions": { "title": str | null, "abstract": str | null },
  "source": "pdf_structure" }
```

- **`title`** is the structure's title. A title that equals the file name is discarded, so a provisional title is never "suggested" back.
- **`abstract`** is the text of the section whose heading is *Abstract* (case-insensitive), up to the next heading, and `null` when there is no such section.
- **No LLM and no vendor call**, so no cost, no disclosure-policy question (IR-250) and no latency beyond extraction itself.
- It imports the extraction serializer from the AI package **read-only**. It adds nothing to `apps/ai`, which is Jive's.

**Client behaviour:**

- Poll every 2 s while `pending`, backing off to 5 s after 20 s, and stop after 90 s or when the dialog leaves step 2.
- `failed` or `unsupported` shows one neutral line, "We couldn't read details from this file — fill them in below", and never an error state.
- A scanned PDF with no text layer comes back `ready` with nulls, and the UI simply shows no chips.

**Large documents:**

- Extraction is asynchronous, and the dialog never waits on it.
- The size limit is the existing upload limit.
- A 90 s ceiling means a 300-page thesis simply produces no chips in time. That is acceptable, because prefill is assistance.

**Confidence.** No confidence score is shown: Docling does not produce one, and inventing one is the fabrication ADR-008's spirit forbids. The chip says *where* the text came from ("Found in your PDF"), which is the honest signal.

**Privacy.** The manuscript never leaves the IRIS deployment for this: Docling-serve is a local service. The endpoint returns data only to the owner. Visibility is through `visible_to()` plus an ownership check, with a 404 otherwise.

**Post-MVP (recorded, not planned):** LLM-proposed keywords, classification and IP hints. That would be Jive's area, gated on IR-250's disclosure policy, with cost and latency to be decided.

### 4.6 Paper View — one page, four sections

**Header** (all sections):

- **Top line:** type label and state chip (the server's `workflow_state_label`), in IR-358 tones.
- **Title:** the serif display title.
- **Byline:** authors · adviser · college · year.
- **Slots**, each rendered only when its data exists:
  - lineage ("Developed from Proposal #123 →" / "Continued as Thesis #456 →");
  - the version picker.
- **Action row:** Cite · Save · Share, plus whatever the record's capabilities add (for example *Open review*, *Edit details*, *Submit new version*). There is one primary pill, chosen by priority:

  | Priority | Primary action |
  |---|---|
  | 1 | the owner's pending action |
  | 2 | the reviewer's *Open review* / *Continue review* |
  | 3 | otherwise, Save |

**Sections** (a tab list under the header, kept in the URL as `?section=`):

| Section | Shown when | Content |
|---|---|---|
| **Overview** (was "Abstract") | the record is readable | Action-required banner (owner), abstract, AI overview, key facts, public discussion (once it exists) |
| **Paper** | there is a manuscript | IR-352's contained reader with Ask IRIS docked right, **unchanged** (IR-372) |
| **Review** | the user is a participant (owner or seat holder) | paper on the left, a side pane on the right, and the action bar (§4.7) |
| **Files** | participant | manuscript + supporting files + document requests, with upload, replace, download |

**The right rail on Overview** keeps the facts, the governance block and, for participants only, the party status strip (Adviser ✓ · ITSO ● · …) from the tracker.

**Decided 2026-09-26: Ask IRIS is not in the Review section.** The Review section is two panes: the paper, and the review pane with the action bar. A reviewer who wants to ask about the paper switches to the Paper tab, where IR-372's layout is unchanged and the conversation persists across tabs. This avoids any conflict with IR-356's chat header and IR-372's rule. It can be revisited if pilot reviewers ask for it. The analysis that led here is kept below.

*Background:* doc 16 put Ask IRIS as a *floating* dock in Review mode. IR-372 has since removed floating mode from the Paper tab, and three panes (paper, timeline, chat) do not fit, as IR-350 measured. **Candidate:** the Review section's right pane is one pane with a segmented switch, Review | Ask IRIS, the same width as IR-352's docked chat and reusing its pane geometry.

**What must be checked first:**

- IR-356 designed the chat panel's header, which holds the AI label and the scope toggle. A second switch above it risks two competing headers.
- IR-372's rule that the chat docks right, full width, applies to the Paper tab only. It must be decided whether the Review section inherits it.
- IR-354's citation landing must hold in the new pane.

*(Superseded by the decision above.)*

**What goes:**

- the separate evaluation page, the documents page and the edit page (redirects in §4.1);
- the client role checks for *Mark as completed* (ADR-032 retires the act) and for the IP tagger;
- **an ungated *Edit details*.** It is offered only under the `edit_details` capability, which the server grants for a `draft`, or for `awaiting_resubmission` to an owner, where the edit becomes part of the next version (IR-273, invariant 4). While a record is under review, or after a decision, its details are not editable from the UI. Today the edit page is gated the same way client-side (the IR-259 hand-over), and the gate moves into the capability;
- the tagger instead renders from a server capability (§4.8).

**Not found.** A record the user cannot read renders the same "not found" state as a missing one. That matches the server's 404 (IR-153).

### 4.7 Review section — the pull-request model

**The side pane's Review view is a timeline.** It is one ordered list, newest last, with a composer at the bottom once comments exist. It is built from the tracker endpoint, which already returns:

- routing events (grouped);
- reviews and findings;
- resubmission requests and their resolution;
- document requests.

Versions and comments join the timeline when their backend lands (ADR-032 §5, §7). **Each entry shows actor · act · party · when · version tag.**

**The action bar** sits below the pane and is a `toolbar` landmark. Its buttons come from capabilities only. Terminal actions are last and use `ConfirmDialog`, with the consequence stated (ui-ux/16 §4 copy).

**Mapping onto what exists today, so nothing breaks (revised in the reconciliation pass):**

- **The legacy decision form is not ported.** Porting `EvaluationPage`'s decisions into the new action bar would rebuild, in new UI, the legacy pipeline's intake-era actions, which IR-260 retires. That is throwaway work, and it would put ADR-021 behaviour into ADR-032's screen.
- **Instead,** until the cutover the Review section's action bar shows *Request document* (ADR-022, already on the new model) plus one secondary link: **"Record a decision (current form)"**. The link opens the existing `EvaluationPage`, left as it is.
- **`EvaluationPage` is deleted by IR-274**, after IR-260, as IR-274 already planned. Its best copy (the *Request Revision* description) moves into IR-272's dialog verbatim.
- **As each ADR-032 action ships**, it adds a button and a dialog to this bar:
  - route (IR-261);
  - finding (IR-269);
  - accept & publish (IR-270);
  - the Proposal decision (IR-271);
  - revision against a version (IR-272).

  **Those tickets' held frontend criteria are satisfied here, not in a separate screen.**

**Opening a review.** *Open review* (seats, ADR-032 §4) moves the user into the Review section. Until seats exist, the button simply navigates to the section; it records nothing.

### 4.8 Capabilities contract

**Today the server sends:**

- `can_act`, the parties the user may act as;
- `can_request_document`;
- `workflow_state` / `workflow_state_label`;
- `current_holders`.

**The client adds:**

- ownership (`isOwner(record, user.id)`);
- two role-name checks (complete, tag).

**Decision.** One frontend module, the **capabilities adapter**, turns a Record detail payload into the set of action keys ADR-032 §10 names:

- `open_review` · `request_document` · `request_revision` · `route` · `decide` · `create_version` · `edit_details` · `continue_as` · `set_visibility` · `tag_ip` · `comment_review` · `comment_public` · `cite`.

Every screen asks the adapter. No component reads a role name or `can_act` directly.

**Phase 1 (no backend change).** The adapter derives from the server fields that exist: `can_act` non-empty → review actions; `can_request_document`; owner + `workflow_state` → author actions.

- `tag_ip` stays role-derived **inside the adapter only**, with a comment pointing at phase 2.
- The Proposal *complete* action is **dropped**, per ADR-032.

**Phase 2 (backend).** The record detail serializer adds `capabilities: string[]`, computed by `core.permissions` (ADR-032 §10). The adapter becomes a pass-through, and a table-driven test proves each capability matches its endpoint's own refusal. This is the ADR-032 "capabilities payload" ticket; it is not new work invented here.

**A guard** (a Vitest source scan, like the palette guard) fails if a file under Paper View, My Library, My Reviews or Publish compares role names or reads `can_act` outside the adapter.

### 4.9 My Library

**The page's primary task is to see and continue my own research, and secondarily to find what I saved.**

**Layout:** the folder rail on the left (IR-350-era `LibraryFolderRail`, extended) and the content on the right. This follows the library model already built on the alphaXiv reference:

- reading-status folders that overlap;
- the user's own folders;
- history.

**The rail, top to bottom:**

- **My research** (authors only), with the filters: All · Drafts · In review · Needs my action · Accepted & published · Proposals · Archived.
  - These are **filters over `/records/mine/`** (its `pipeline_status` query parameter, plus `workflow_state` on the returned records for *Needs my action*), not stored folders, and not counts.
  - "Needs my action" carries an attention dot when non-empty, because it is actionable.
  - Every other item shows no number.
- **Saved:** Want to read · Reading · Completed, plus the user's folders (localStorage, as today, with the "this browser only" note kept).
- **History.**

**Default view:** *My research · All* for authors, *Saved · Want to read* for everyone else.

**Cards.** `ResearchCard` in a list layout (one per row at every width, since My Library is a working list, not a gallery):

- type label;
- the title (serif) linking to Paper View;
- authors · adviser;
- a **status line** in plain words from `workflow_state_label`;
- the **next-step line** when the user owes something ("IERC asked for revisions — submit a new version", "Ethics clearance requested");
- updated date;
- a contextual action: *Continue* (draft, which reopens Publish), *Respond* (needs action, which opens Paper View at the right section), or *Continue as…* (an accepted Proposal, once lineage exists).

**What goes:**

- the stat cards;
- the six stage tabs (Validation / Review & Routing / IP Assessment / Commercialization / Past Review);
- the formatted case id;
- `WorkspaceOfficePills`, which the status line and Paper View's status strip replace.

The per-record stage derivation in `workspaceStages` becomes unnecessary once the status and next step come from server fields. It is deleted. IR-344 and part of IR-345 go with it (Appendix E).

**States:**

- **Empty *My research*:** "You haven't published anything yet", with **Publish**.
- **Empty filter:** "Nothing here", naming the filter.
- **Saved empty:** as today.
- **Error:** with retry.

### 4.10 Document requirements

**No new system.** ADR-022 is built:

- IR-262 and IR-263 are done;
- IR-349 is in review;
- IR-346 is To Do.

The frontend is visually weak, not functionally missing.

**The decisions:**

- **One vocabulary everywhere:**

  | Stored item state | Shown as |
  |---|---|
  | `missing` | **Requested** |
  | `uploaded` | **Uploaded · awaiting review** |
  | `accepted` | **Accepted** |
  | `rejected` | **Replacement needed** (the reviewer's reason shown) |

- **Owner surfaces:**
  - the Action-required banner at the top of Overview, which is the existing `ActionRequiredPanel` restyled into a banner plus list;
  - the same items in the Files section;
  - "Needs my action" in My Library.
- **Reviewer surfaces:**
  - *Request document* is a dialog from the action bar, reusing `RequestDocumentDialog`;
  - accept, reject and withdraw sit on each item in the Files section, reusing `ReviewerDocumentRequests`' logic.
- **The upload control is the shared `UploadDropzone`** (below), in both Files and the banner.
- **IR-346** makes a normal upload to a requested slot fulfil the request. It is a dependency of the Files section's single upload path, and it stays its own ticket.

### 4.11 Versions, lineage, discussions, Discoverable Proposals

All four need ADR-032 backend that does not exist yet (Appendix D). The frontend decision is where each one renders, so that its ticket adds a slot rather than a screen:

| Feature | Renders in |
|---|---|
| **Versions** | the header's version picker; version tags in the timeline; *Submit new version* in the owner's action row |
| **Lineage** | the header's lineage slot; *Continue as…* on My Library cards and in the Overview action row of an accepted Proposal |
| **Review comments** | the timeline composer |
| **Public discussion** | the bottom of Overview, visually separate: a different surface, the heading "Public discussion", and never inside the Review pane |
| **Discoverable Proposals** | Discover's Proposals tab (in-review Proposals only); Summary mode in Paper View; the Visibility choice in Publish step 3 and in Edit details; the owner-only "Similar open proposals" and "Related published research" lists on the owner's Overview |

**Until each ships, its slot renders nothing.** It never shows an empty or fake state. For example, no "v1" when versions don't exist, and no "0 comments".

### 4.12 Visual language and design-system consolidation

This extends the IR-356 direction (in `ui-ux/01-design-system.md` §0) from Paper View to every redesigned screen. **Every change is written into doc 01 in the same PR.**

- **Typography:**
  - EB Garamond (`font-display`) for content titles: page titles, record titles, dialog titles;
  - Inter for everything else.
  - **One scale:** display 28/34, title 20/28, heading 16/24, body 15/24, small 13/20, label 12/16 (sentence case, never all-caps tracking below 12 px);
  - it replaces the scattered 10–11 px uppercase labels.
- **Spacing:** a 4-px base with a 16/24/32 section rhythm; card padding 20 (desktop) / 16 (mobile).
- **Surfaces:** a `stone-50` canvas; white cards with a 1 px `stone-200` border and no resting shadow. Shadow is kept for things that float: dialogs, menus, the mobile sheet.
- **Action hierarchy:** one maroon primary pill per region (`pillStyles`), secondary as outline pills, tertiary as text buttons. Danger is `brand-dark` with its glyph (IR-359).
- **Status:** IR-358's four tones only, and the wording always comes from the server.
- **Focus:** a visible 2 px maroon ring with an offset on every interactive element.
- **Motion:** 150–200 ms opacity/transform only, and none under `prefers-reduced-motion`.

**Consolidation — only where duplication is real:**

| Component | Justification | Replaces |
|---|---|---|
| `ResearchCard` (grid and list layouts; slots for status line, next step, actions) | four renderings of a record today | `DiscoverRecordCard`, `LibraryRecordTable` rows, My Workspace's case card, the queue row markup |
| `EmptyState` (shared, extended with an action slot and a tone) | two implementations | Discover's local copy |
| `UploadDropzone` (upgrade of `FileUploadZone`: progress, error + retry, accepted-types line, keyboard) | three upload surfaces | the Publish, Files and Action-required uploads |
| `MetadataForm` | the same fields edited in two places | the wizard's details steps and `EditRecordPage` |
| `ReviewTimeline` | the tracker is shown as a list today; the timeline is its presentation | `ReviewRoutingTracker`'s history lists (the status strip stays) |
| `PageHeader` adoption | pages each hand-roll a head | Discover's private header and others |

**Not proposed:** `PublicationCard` (it is `ResearchCard`), a separate `ActionRequiredCard` (a variant of the banner), `FilterBar` as a generic component (Discover is its only user), and `WorkflowTimeline` separate from `ReviewTimeline`.

### 4.13 Responsive and accessibility requirements (all tickets)

- **Viewports verified in a real browser and recorded in each PR:**

  | Viewport | Device class |
  |---|---|
  | 360×740 | phone |
  | 768×1024 | tablet |
  | 1280×800 | laptop |
  | 1745×777 | the IR-350 measurement width |

  For the method, see the fixed-size same-origin iframe in the `iris-ir350-paper-reading-workspace` memory. There is no horizontal page scroll at 360.
- **Below `md`:** the sidebar is a drawer (as today); Discover filters are a sheet; the library rail is a select; Paper View's Review section stacks the paper above the pane with a sticky action bar; the Publish dialog is a full-screen sheet.
- **Dialogs:** `Modal`'s focus trap, labelled by the title, Escape closes (the Publish dialog asks to confirm only if an upload is mid-flight), and focus returns to the opener.
- **Live regions:** upload progress/result, "Moved to In review", action outcomes.
- **Colour:** status is never colour-only (icon + word). Text contrast is ≥ 4.5:1: no `stone-400` text on white (IR-360 finding), and checkboxes use `accent-brand`.
- **Automated checks:** axe clean for serious and critical issues on every page test. Contrast is checked manually, because jsdom cannot compute it.

---

## 5. Testing Decisions

**What a good test is here.** It renders a real page or dialog against a mocked API client that returns contract-shaped payloads. It acts through the accessible tree (role and accessible name, never a class or a test id). It asserts what a user would observe: text, enabled/disabled state, navigation, and requests sent.

It never asserts internal state, hook calls or component structure. It is written before the change and seen failing. Visual layout is **not** claimed by jsdom tests. It is verified in a browser at the §4.13 viewports and recorded.

**Seam 1 — frontend pages (Vitest + axe, the existing IR-210 harness):**

- Publish dialog: each step, each state (upload progress, failure/retry, pending/ready/failed prefill, suggestion accept/dismiss, never overwriting typed text, self-as-adviser disabled, submit refusal kept on step 3, success), closing to a draft and resuming.
- Discover: filters to query params, chips, sort, the empty/no-results/error states, Publish visible to authors only, and the Proposals tab absent until the backend flag.
- My Library: sections and filters, status and next-step lines, Continue reopening Publish, no numeric counters rendered, the non-author default.
- Paper View: sections by capability; redirects of the old URLs; the action bar rendering exactly the adapter's capabilities; terminal confirmations; the not-found state.
- The capabilities adapter: a table of payloads → expected capabilities.
- **The navigation map:** the access-map test updated; every removed route redirects.
- **Source-scan guards:** no role-name comparison outside the adapter; the palette guard unchanged and green.
- **Prior art:** `PaperViewPage.test.tsx`, `DiscoverPage.test.tsx`, `MyWorkspacePage.test.tsx`, `RequestDocumentDialog.test.tsx`, `ActionRequiredPanel.test.tsx`, `access.test.ts`, `palette.test.ts`.

**Seam 2 — backend REST API (pytest in the container, one run at a time):**

- `metadata-suggestions`: owner gets each state; non-owner and stranger get 404; the title equal to the file name is suppressed; the abstract section is found or null; no network call is made. The Docling client is faked, as in the existing extraction tests.
- The ADR-032 capability payload (phase 2) is tested in its own ticket, table-driven against the endpoints' refusals.
- **Prior art:** `apps/records/test_tracker.py`, `apps/ai/extraction/tests`, and the IR-153 404-not-403 matrix.

**Seam 3 — recorded browser verification:**

- Each UI ticket records the four viewports, keyboard-only walkthroughs of its dialogs, and 200 % zoom on its main screen.
- F12 aggregates these as evidence for IR-96 (NFR-U1/U3), and runs the NFR-U2 timed-submission rehearsal on the Publish flow.

---

## 6. Out of Scope

- **The workflow itself:** ADR-032 is settled; this spec only presents it.
- **Backend for versions, lineage, seats/pools, review comments, public discussion, Discoverable Proposals, and the capabilities payload.** These are ADR-032's own tickets. This spec reserves their UI slots and depends on them.
- **An LLM step in Publish.** It is post-MVP, Jive's area, and gated on IR-250 (§4.5).
- **A server-side library** (bookmarks, folders, history). My Library's Saved sections stay in localStorage.
- **Recreating the legacy IPAMS form, or any upload-slot checklist at submission.**
- **Paper reader and Paper Chat mechanics:** IR-350's subtasks (351–356, 372). Reused as-is.
- **Ask IRIS page redesign:** IR-365 (palette) and IR-332, IR-301, IR-162.
- **Administration screens:** visual palette only, via IR-363.
- **Analytics, dashboards or counters of any kind.**
- **A Playwright/e2e runner** (IR-224).

---

## 7. Further Notes

### 7.1 Decisions (revised in the reconciliation pass, 2026-09-26)

1. **Adviser-publish wording — PRODUCT-LANGUAGE DECISION, open.** ADR-032 decides the *rule* (an Adviser may accept & publish when no specialist review is needed, §3) but not the words students or advisers see. ui-ux/16's confirmation text (*"This publishes the thesis to Discover. No office will review it."*) is a draft, not a decision. The project lead approves the Adviser's confirmation text and any student-facing mention before IR-270's UI ships.
2. **IR-118 is re-scoped, not closed.** Preset document lists fit ADR-022's existing architecture: a document request already carries items drawn from the record type's upload slots (the `document-requests/slots` picklist), plus free-text *Other*. IR-118 becomes **"request templates"**: an office's named preset list of slots, which a reviewer sends as one `DocumentRequest` in one click. It adds no new requirement system, no submission-time requirement, and no parallel model; possibly one small table (template → slots), decided in IR-118.
3. **Upload slots are not required — no change needed.** The spec no longer assumes the seeded slots are required. IR-118's migration `documents/0005` already set every slot `is_required = false`, and the wizard already requires only the manuscript. The earlier recommendation to migrate the seeds is **withdrawn**. The Publish dialog does not read `is_required` at all.
4. **Notifications move to the header bell and Settings to the account menu — ADOPTED.** Both routes stay; only the sidebar entries go (F1).
5. **The Review | Ask IRIS switch — NEEDS VALIDATION against IR-356 and IR-372** (§4.6). It is not decided in isolation. It is settled with a mode-by-mode layout preview before F6's pane layout is final.
6. **Import Records stays an RDCO administration page — ADOPTED.** It is filing on behalf of others, not Publish.
7. **Student identity on Discoverable Proposals — PRIVACY / PRODUCT DECISION, open.** ADR-032 §8 lists authors' names on the summary. That is the first place student names appear on unapproved work, to every signed-in user. The project lead decides, with the DPO question already open on IR-123, whether:
   - names are shown;
   - names are shown only with a separate consent;
   - or the summary shows a contact action without names.

   This blocks the Discoverable ticket's UI, not the rest of the spec.

### 7.3 Design-session decisions (project lead, 2026-09-26)

**Closing §7.1:**

- **Item 1.** The Adviser's confirmation reads *"Publish without specialist review?"*, with the body from ui-ux/16, and shows the IP, ethics and commercialisation hints the author flagged. Students see no advance warning.
- **Item 5.** Ask IRIS is not in the Review section (§4.6).
- **Item 7.** Authors' names are shown on a Discoverable Proposal. The Discoverable text itself is the consent, and it names the AI comparison.

**New in the session:**

- **Q4.** Abandoned Publish drafts stay in My Library → Drafts, with Continue and Delete; there is no cleanup job.
- **Q5.** B1 is built in the records app, with Jive as reviewer.
- **Q12–Q13.** The "Looking for" note is dropped. A Discoverable Proposal is listed only while in review, and acceptance ends listing and matching. Private is the only early close.
- **Q15–Q23.** The matching rules live in ADR-029's 2026-09-26 amendment:
  - both proposals must be open;
  - matching is institution-wide;
  - it runs on submission and when an in-review Proposal becomes Discoverable;
  - the notification carries the title, names and a link;
  - a newcomer is notified about its top 3 matches at most, once per pair;
  - an owner-only list shows matches later;
  - the threshold is tuned by the AI track;
  - the Adviser duplicate view is kept, institution-wide;
  - the novelty check is kept.
- **Q9.** IR-141 is closed as superseded by F5.
- **Q10.** IR-162 moves under IR-146, and IR-149 closes with a pointer to IR-374.
- **Q6 and Q11.** Every ticket is created at once after this PR merges:
  - IR-374 subtasks titled `F0 ·` / `B1 ·`;
  - ADR-032 tickets numbered `20 ·` to `26 ·` under IR-255;
  - no assignees;
  - `ready-for-agent` only where nothing blocks the ticket.

### 7.2 Things this spec corrects in the repository's own record

- `AddRecordPage`'s header says Docling is unimplemented and the LLM provider undecided. Both are stale: Docling is implemented (IR-107/ADR-016), and generation is OpenAI-compatible (ADR-021-openai). The page is deleted by F3, so it is not edited.
- `lib/submissionRoutes.ts` shows "RDCO Intake" bookends. That is ADR-021 vocabulary that ADR-032 retired. It is deleted by F3.
- This spec's own first draft claimed the wizard demands up to 13 required attachments. That was stale: `documents/0005` (IR-118) removed every requirement. Corrected in §1 and §7.1.
- **IR-372's Jira description says Ask IRIS docks on the *left*.** Its summary, the code (`dock = onPaperTab ? "right"`) and `ui-ux/14` say *right*. The description is stale and should be corrected on the card; bookkeeping only.
- ADR-032 §14 names two of its new tickets *"capabilities payload and Paper View modes"* and *"review timeline and `ReviewComment`"*. Both overlap this spec's F5 and F6. Appendix L resolves this by renaming them when created.
- A memory note recorded a lead decision of "no Discussions (no backend)". ADR-032 §7 supersedes it.

---

# Appendices

## Appendix A — Current frontend architecture (findings, `main` at fc779a3)

**Stack:** React 18, TypeScript, Vite, Tailwind, Zustand (auth, ui, notifications stores), React Router data router, and an axios `apiClient`. Font Awesome icons. Vitest + jsdom + axe (IR-210).

**Routes** (`router/index.tsx`). Everything is under `ProtectedRoute(EVERYONE)` → `AppShell`:

| Route | Page | Gate |
|---|---|---|
| `/` | `HomePage` → `DiscoverPage` for all (the non-student branch renders a re-export of Discover) | everyone |
| `/records/:id` | `PaperViewPage` | everyone (server decides visibility) |
| `/records/:id/documents` | `DocumentsPage` (795 lines) | everyone |
| `/records/mine` | `MyLibraryPage` | everyone |
| `/opportunities` `/notifications` `/ai` `/help` `/settings` | — | everyone |
| `/records/add` | `AddRecordPage` (3-step wizard) | authors |
| `/workspace` | `MyWorkspacePage` | authors |
| `/records/:id/edit` | `EditRecordPage` | authors |
| `/review` | `ReviewQueuePage` (Awaiting me / Cleared / Sent back) | reviewers |
| `/review/:id/evaluate` | `EvaluationPage` | reviewers |
| `/review/approved-proposals` `/records/import` `/admin/*` | — | RDCO |

**Navigation:**

- `lib/access.ts` (IR-160) is one role→screen map feeding both the router and `Sidebar`. It has five sections: Research Exploration, IP Management, Review Queue, Tools, Administration.
- Sidebar badges: a workspace count from `/dashboard/stats/`, and role requests.
- **Header:** the breadcrumbs, a **non-functional search box** (hidden on Paper View), and the bell.
- **Discover and Ask IRIS** are "full-bleed": `AppShell` omits the shared header, and **Discover renders its own header** with its own menu toggle and bell.
- Landing after sign-in (`lib/roleDashboard.ts`): students go to Discover; every reviewer role goes to `/review`.

**Pages of interest:**

- **Discover:**
  - "saved views" (For you = Latest, Most viewed, IP & Patents, Theses);
  - a filter panel with dropdowns;
  - `DiscoverRecordCard`;
  - Cite and Save;
  - Load more;
  - Proposals explicitly filtered out of the type options (IR-264);
  - **its own `EmptyState`**.
- **My Library:** saved/liked/history, all localStorage (`lib/recordLibrary.ts`); `LibraryFolderRail` (status folders + topic folders); `LibraryRecordTable`.
- **My Workspace:**
  - stat cards;
  - six stage tabs;
  - case cards;
  - `WorkspaceOfficePills`;
  - `lib/workspaceStages.ts` derives the stage sequence client-side from server fields.
- **Paper View:**
  - Abstract/Paper tabs;
  - a right rail (`ReviewRoutingTracker`, `PaperGovernance`, `PaperDocuments`);
  - `ActionRequiredPanel` (owner) and `ReviewerDocumentRequests` (reviewer);
  - `PaperAiOverview`;
  - `PaperChatDock`;
  - `PaperPdfReader` (the IR-352 contained viewer);
  - Cite, Save and Share;
  - the *Review this record* link to `EvaluationPage`;
  - the *Mark as completed* action;
  - `IpTagger`.
- **EvaluationPage:** the decision form (approve / request revision / reject), `PeerClearanceStrip`, and `reviewDraft` persistence.
- **AddRecordPage:** the steps `TypeRouteStep` (with `submissionRoutes` bookends), `PaperDetailsStep` (+ `RecordDetailsStep`, `TitleAbstractStep`), and `UploadsStep`. The last lists every `UploadSlot` and enforces required slots on the client. The manuscript is uploaded **at submit time**, after the draft exists.

**Shared components:**

- `ui/`: Badge, Button, Card, Input, Modal (focus trap), Skeleton, Spinner, Toast, `statusTones` (IR-358 TONES), `pillStyles`.
- `shared/`: ConfirmDialog, DataTable, EmptyState, FileUploadZone (the only drag-and-drop implementation), StatusBadge, RoleBadge, ComingSoonPage.
- `layout/`: AppShell, Sidebar, Header, Breadcrumbs, PageHeader, NotificationBell.

**Capability logic today:**

- **Server-derived (good):** `can_act` (the parties the user may act as), `can_request_document`, `workflow_state(_label)`, `current_holders`.
- **Client-derived (to remove):**
  - `isOwner(record, user.id)` (acceptable input to the adapter);
  - `canComplete` compares `ROLES.RDCO` / `ROLES.ADVISER` + `record.adviser`;
  - `canTag(role)`;
  - `HomePage`'s `isStudent`;
  - `ApprovedProposalsPage`'s role checks.
- **Screen access:** `lib/access.ts` (keep).

**Duplication found:**

- **Records rendered four ways:** Discover card, library table row, workspace case card, queue row.
- **Two `EmptyState`s.**
- **Two headers:** the shared one and Discover's.
- **Metadata edited in two places:** the wizard steps and `EditRecordPage`.
- **Status wording partly client-mapped:** `PIPELINE_LABELS`, which IR-342/IR-274 already target.

## Appendix B — Current backend/API relevant to the redesign

| Capability | Endpoint / model | State |
|---|---|---|
| Record list (Discover) | `GET /records/` (list serializer, published-only via `visible_to` + list narrowing) | EXISTS |
| My records | `GET /records/mine/` (detail serializer, `?status=`) | EXISTS |
| Record detail + workflow fields | `GET /records/<id>/` → `workflow_state`, `workflow_state_label`, `current_holders`, `can_act`, `can_request_document`, `clearances`, `resubmission`, `files` | EXISTS |
| Create draft (authors only) | `POST /records/` with `IsAuthor`; `title` is the only required field; `abstract_file` accepted | EXISTS |
| Manuscript upload → extraction | saving `abstract_file` queues `extract_manuscript_text` (Docling, `extraction` queue) on commit | EXISTS |
| Extraction status / structure for the manuscript | not exposed | **NEEDS BACKEND** (B1) |
| Metadata suggestions | none | **NEEDS BACKEND** (B1, Docling-only) |
| Submit | `POST /records/<id>/submit/` with DPA flag; no slot-completeness check | EXISTS |
| Advisers list | `GET /users/advisers/` | EXISTS |
| Tracker (timeline source) | `GET /records/<id>/tracker/` | EXISTS |
| Document requests | `GET/POST /records/<id>/document-requests/`, `/document-requests/<id>/`, `/document-request-items/<id>/`, slots picklist | EXISTS (IR-262/263; IR-346, IR-349 pending) |
| Supporting files | `/documents/submit/`, `/documents/uploads/…`, `/documents/files/…` | EXISTS |
| Review decisions (current pipeline) | `POST /reviews/submit/`, `/reviews/resubmit/`, `GET /reviews/pending|approved|declined/` | EXISTS (legacy; ADR-032 tickets replace) |
| AI overview | `GET /ai/records/<id>/overview/` (cached) | EXISTS |
| Paper Chat | `/ai/ask/stream/`, `/ai/conversations/` | EXISTS |
| Capabilities list | — | **NEEDS BACKEND** (ADR-032 ticket; phase 2) |
| Seats / pools / claim / My Reviews tabs | — | **NEEDS BACKEND** (ADR-032 seats ticket; IR-268) |
| Versions | `RecordUpload.version` per slot only; no `RecordVersion` | **NEEDS BACKEND** (ADR-032 versions ticket) |
| Lineage | — | **NEEDS BACKEND** (ADR-032) |
| Review comments / public discussion | no model anywhere | **NEEDS BACKEND** (ADR-032) |
| Discoverable Proposals | — | **NEEDS BACKEND** (ADR-032; IR-310 re-scope) |
| Whether the user has review work (My Reviews gate) | none; the frontend gates by role via `lib/access.ts` | **NEEDS BACKEND** (B3) |
| Sidebar "needs action" signal | `/dashboard/stats/` has `pending_mine`, which counts in-review records, not records waiting on the owner | **NEEDS BACKEND** (B2) |
| Audit of UI actions | `AuditEvent` has no workflow events | out of scope (IR-144) |

## Appendix C — View-by-view audit

**Classifications:**

1. Keep
2. Minor refactor
3. Major redesign
4. Merge
5. Remove
6. Backend first
7. Covered by existing Jira

| View | Class | Primary task → verdict |
|---|---|---|
| Sidebar / navigation | 3 | Wayfinding. Five sections → one short list and Administration; Tools to the header |
| Header | 2 | One header everywhere; drop the inert search |
| Discover | 3 | Find research. Dissolve the saved views, add Publish, the Research/Proposals split, `ResearchCard`, the shared empty state |
| Discover Proposals tab | 6 | Blocked on the Discoverable backend |
| Submit Disclosure wizard | 5 → Publish dialog (3) | Start a submission. Replaced |
| Publish prefill | 6 (small) | B1 endpoint |
| My Workspace | 4 → My Library | Track my submissions. Merged; counters and stage tabs removed |
| My Library | 3 | My research + Saved; a rail of sections, a card list |
| Paper View | 3 | Read/act on a record. Four sections, the capabilities adapter, a header rebuild |
| Paper tab reader + chat | 7 (IR-350 subtasks) | Reuse unchanged |
| EvaluationPage | 7 (IR-274) | Decide. Kept, untouched, until IR-260; its actions reappear one by one in the Review section's bar as IR-261/269–273 land; IR-274 deletes it |
| Review timeline | 3 | Tracker history → `ReviewTimeline`; comments are 6 |
| Workflow tracker status strip | 2 | Keep the data; restyle to ui-ux/16's strip; drop the Intake row (ADR-032) |
| Review queue → My Reviews | 3 + 6 | Tabs over seats need the seats backend (IR-268); the rename now |
| Approved Proposals | 5 | Retired by ADR-032 |
| DocumentsPage | 4 → Files section | Manage files. Merged |
| Action Required panel | 2 | Restyle to a banner; one status vocabulary |
| Request document dialog | 1 | Launched from the action bar |
| Reviewer document requests | 2 | Moves into the Files section |
| EditRecordPage | 4 → Edit details dialog | Shares `MetadataForm` |
| Version history | 6 | ADR-032 versions |
| Review / public discussion | 6 | ADR-032 §7 |
| Lineage | 6 | ADR-032 §6 |
| Notifications page | 1 (+ palette via IR-362) | Reached from the bell only |
| Settings / profile | 1 | Moves to the account menu |
| Calls & Conferences | 1 (+ IR-362) | Unaffected |
| Ask IRIS page | 7 (IR-365 etc.) | Unaffected |
| Admin pages | 7 (IR-363) | Unaffected |
| Auth screens | 7 (IR-203/209 family) | Unaffected |
| Responsive / mobile | 3 | §4.13 per ticket + F12 |

## Appendix D — Backend changes required

**The only new backend this spec itself requires is B1, B2 and B3.** All three are small, with no migration. Everything else is an existing ADR-032 ticket that the redesign consumes.

**B1 · Metadata suggestions from the manuscript's Docling structure (§4.5).**

- **Why the frontend requires it:** the prefill cannot be done client-side, because the structure is server-only.
- **Reuse:** `PdfExtraction(kind=MANUSCRIPT)` and the existing structure serializer.
- **Serializer/API only; no migration; no model change.**
- **Permission:** the owner through `visible_to()`, with a 404 otherwise.
- **Audit:** none (a read).
- **Tests:** the Seam 2 list in §5.

**B1b (optional, same ticket).** Record detail gains `manuscript_extraction: { status }`, so Paper View's Files section can say "Processing…" honestly. It is additive.

**B2 · `needs_action_mine` on `/dashboard/stats/`.**

- **Why:** the My Library dot (§4.2) must mean "something is waiting on you". Today's `pending_mine` means "in review".
- **The change:** count the user's owned records whose derived `workflow_state` is `awaiting_resubmission` or `awaiting_document`, using the tracker's existing derivation rather than a new rule.
- **Scope:** serializer/view only; no migration; same permission as the endpoint today.
- **Tests:** a record with an open resubmission request or document request counts, and one that is only in review does not.
- It ships inside F1. **Agent-ready.**

**B3 · `review_access` on `GET /users/me/` (reconciliation pass).**

- **Why:** My Reviews must appear only when the server says the user has review work or capability (§4.2), not for every reviewer role.
- **Reuse:** `MeView` / `UserSerializer` (exists), plus the tracker's `staffable_parties` and the existing `Review`/`RecordAssignment` rows. No new model.
- **Contract:** `review_access: { my_reviews, offices, is_coordinator }`.
  - **Phase 1:** `my_reviews` means adviser of a submitted record, **or** staffs an office party, **or** has authored a review. `is_coordinator` is `false` until seats exist.
  - **Phase 2:** the ADR-032 seats ticket re-points it at seats and `User.is_office_coordinator`, without changing the field.
- **Scope:** serializer only; no migration; the user sees only their own flag.
- **Tests:** an Adviser with no advisees gets `false`; an Adviser of a submitted record gets `true`; an ITSO member with no records gets `true` (pool); a Student gets `false`.
- It ships inside F1. **Agent-ready.**

**Verification items, not changes (checked inside F3):**

- **The server's upload validation.** Confirm the size and type limits for `abstract_file` are enforced server-side. If they are not, add them in F3's backend part: a serializer validator, no migration.
- **The advisers endpoint.** Confirm `GET /users/advisers/` excludes the requesting user, or leave the exclusion to the client, since IR-260 enforces adviser ≠ owner server-side.

**Not required, deliberately:**

- a Publish endpoint (the draft create + submit flow already works);
- a My Library endpoint (`/records/mine/` suffices);
- a discussion model beyond ADR-032's;
- any change to `apps/ai`.

## Appendix E — Jira conflict and overlap analysis

**Verdicts:**

- **K** keep as is
- **U** update/re-scope
- **M** merge into this epic
- **C** close as superseded or duplicate
- **D** dependency only

| Ticket | Status | Current scope | Overlap / conflict | Verdict | Relationship |
|---|---|---|---|---|---|
| IR-149 | In Progress | Frontend foundation and pilot surface (parent) | Its remaining children are superseded here | U | Close once IR-161/162 are resolved; this epic succeeds it |
| IR-161 | In Progress | Submission wizard: type first, route preview | Replaced by the Publish dialog | **C** | Superseded by F3; close when F3 merges |
| IR-162 | To Do | Search screen shape | Unrelated (Ask IRIS) | K | — |
| IR-360 | In Review (merged, #132) | Wizard palette | The screen it recoloured is deleted by F3 | K → Done | — |
| IR-361 | To Do | Palette for My Workspace, the review and clearance screens, Approved Proposals | Most of its screens are deleted (Workspace, Evaluation, Approved Proposals) | **U** | Re-scope to what survives (the status strip, `PeerClearanceStrip` if kept); the deleted files leave the palette allowlist in the ticket that deletes them |
| IR-362 | To Do | Palette for Discover, Library, Calls, Notifications | Discover and Library are redesigned here | **U** | Re-scope to Calls & Conferences and Notifications; Discover and Library come off the allowlist in F2/F4 |
| IR-363 | To Do | Palette for Documents and admin | DocumentsPage is deleted | **U** | Admin only |
| IR-357 / IR-366 | To Do | Palette rollout / close the guard | Must accept files deleted by this epic | D | F-tickets delete their own allowlist lines; IR-366 last |
| IR-141 | In Progress | ClearanceTrack states and semantics | The status strip and timeline replace ClearanceTrack's role | **U** | Re-scope to the status strip's states (ADR-032 vocabulary), delivered in F5/F6, or close as superseded. **PRODUCT** |
| IR-142 | In Progress | Record detail decline banner, block order | Replaced by the Overview banner and sections | **C** | Superseded by F5 (banner from `workflow_state`) |
| IR-143 | In Review | Merged queues, a self-sufficient decision screen | The decision screen becomes the Review section | U | Close on its current PR. Its remaining criteria (stale-submit notice, typed comment kept) become criteria of the ADR-032 action dialogs (IR-269–272) in the Review action bar |
| IR-119 | To Do | RDCO office-amend at intake | Intake retired (ADR-032) | **C** | Superseded by ADR-032 |
| IR-118 | In Progress | Document requirements (FR-M2-01) | Submission-time requirements already removed by its own migration `documents/0005`; what remains fits ADR-022 | **U** | Re-scope to **request templates**: office preset slot lists sent as one ADR-022 `DocumentRequest` (§7.1 item 2) |
| IR-96 | To Do | NFR evidence (U1/U2/U3) | The redesign changes what gets measured | D | F12 feeds it; NFR-U2 is timed on Publish |
| IR-350 / 351 / 352 / 354 / 356 / 372 | In Review (code merged) | Reader and Paper Chat mechanics and visual | Reused unchanged; see Appendix K for the exact split | D | F5 depends on them; IR-372's description ("left") should be corrected to "right" |
| IR-353 | Done | Find in paper | — | K | — |
| IR-355 | To Do | Cross-paper citation keeps the conversation | Independent of sections | K | — |
| IR-255 | To Do | ADR-032 implementation parent | The backend of every blocked slot | D | ADR-032's seven new tickets are created there as vertical slices whose UI uses this epic's slots |
| IR-261, 269, 270, 271, 272, 273 | To Do | ADR-032 actions (held frontend) | Their UI is the Review action bar | **U** | Replace each "held frontend" section with "UI: add the action to F6's action bar / F5's slots" |
| IR-268 | To Do | My Reviews over seats | Its UI section matches §3 stories 68–73 | U | Keep the whole ticket; its UI uses `ResearchCard` (F0) |
| IR-260 | To Do | Cutover (adviser ≠ owner) | F3 shows the rule | D | F3 client rule; IR-260 server rule |
| IR-274 | To Do | Delete the old pipeline and screens | EvaluationPage deletion | K (as re-planned) | **Reconciliation pass reverses the first draft:** F6 does not port or delete EvaluationPage. IR-274 deletes it after IR-260, as planned |
| IR-262 / 263 | Done | Document requests | Reused | K | — |
| IR-346 | To Do | Normal upload fulfils the request | Needed for the Files section's single upload path | D | F5 depends on it |
| IR-349 | In Review | Document-request data restricted to participants | Files section visibility | D | — |
| IR-336 → IR-340…345 | To Do | Post-IR-259 cleanup | IR-344 (workspace office line) dies with Workspace; IR-345's workspace rule dies; IR-342 (server wording) matches §4.12 | U | Close IR-344 as superseded by F4; IR-345 keeps its Paper View rule only; IR-340/341/342/343 keep |
| IR-307 / 309 / 310 / 311 / 312 | To Do | Proposal similarity | IR-310's opt-in *is* ADR-032's Discoverable setting; IR-309 says "at intake" | **U** | IR-310 → the Discoverable ticket; IR-309 → "the Adviser sees overlapping Proposals" |
| IR-203…214 | mixed | Auth screens and a11y | No overlap | K | — |
| IR-368 / 369 / 370 | To Do | Rate-limit message, view counting, a single unread fetch | IR-370 matters when the bell is the only notification entry | D | — |
| IR-86, IR-88 | not found open | Pilot surface / wizard (folded into IR-149) | — | — | — |

## Appendix F — Proposed ticket architecture

**Parent Story (new, under IR-53):**

- **Title:** *Frontend redesign for the settled workflow*.
- **Spec:** this document.
- **Labels:** `area-frontend`, `area-uiux`, `mvp-required`, `thesis-critical` on F3/F5/F6 only.

**Subtasks.** Each keeps the §4.13 responsive/a11y bar and the §5 seams. Each deletes its own palette-allowlist lines and states in its PR which old files it deletes.

### F0 · Shared primitives and the design language

- **Build:**
  - `ResearchCard` (grid + list, slots);
  - `EmptyState` with an action slot (remove Discover's copy);
  - `UploadDropzone` (upgrade `FileUploadZone`: progress, error, retry, keyboard);
  - the type scale and spacing tokens;
  - `PageHeader` updated;
  - the doc 01 amendment.
- **AC:**
  - each component has a Vitest test through roles, and axe is clean;
  - `UploadDropzone` rejects a wrong type/size before upload, with the limit in the message, and exposes progress to assistive tech;
  - no screen changes behaviour;
  - doc 01 records every token change;
  - the palette guard is green.
- **Backend:** none. **Agent-ready.**

### F1 · Navigation and information architecture

- **Build:**
  - the §4.1 sidebar;
  - Notifications and Settings to the header / account menu;
  - removal of the header search;
  - Discover under the shared header;
  - the `HomePage` branch removed;
  - access-map changes;
  - the redirect table;
  - "Review Queue" renamed to "My Reviews", gated by B3's `review_access.my_reviews` (in both the sidebar and the route guard), with the post-login landing following the same flag;
  - B2 and B3 (backend).
- **AC:**
  - `access.test.ts` asserts the new nav per role;
  - My Reviews is absent for a user whose `my_reviews` is false, even with the Adviser role, and present for an office member with no seats; `/review` redirects such a user to Discover;
  - each of the six old URLs redirects (test per URL);
  - no nav item leads to a route its role cannot open;
  - the My Library dot appears only when B2's `needs_action_mine > 0` (B2 ships in this ticket);
  - verified at the four viewports, with the drawer keyboard-operable.
- **Depends:** F3 and F4 must exist before `/records/add` and `/workspace` redirect. Land F1 **after** them, or ship the redirects in F3/F4 and the sidebar in F1.
- **Agent-ready** once F3/F4 are merged.

### F2 · Discover redesign (Research tab)

- **Build:** §4.3 except the Proposals tab.
- **AC:**
  - the saved views are gone;
  - Sort Newest / Most viewed maps to `ordering`;
  - each filter maps to the existing query params and shows as a removable chip;
  - empty, no-results and error states match §4.3;
  - Publish is rendered for authors only and opens the dialog (stub until F3);
  - below `md` the filters open in a sheet with a focus trap;
  - no horizontal scroll at 360;
  - Discover's files come off the palette allowlist.
- **Depends:** F0. **Agent-ready** after F0.

### F3 · Publish dialog (manual metadata; manuscript-only)

- **Build:**
  - §4.4 without the prefill chips;
  - `MetadataForm`;
  - draft resume via `/?publish=<id>`;
  - `/records/add` redirect;
  - deletion of `AddRecordPage`, the steps, and `submissionRoutes`.
  - **No seed change:** slots are already not required (`documents/0005`, §7.1 item 3).
- **AC:**
  - a file drop creates exactly one draft, with the file-name title and type;
  - progress is announced;
  - a failed upload retries without losing the type or the file;
  - Continue is disabled until the upload succeeds;
  - choosing oneself as adviser is impossible, with an explanation;
  - Details patches the draft on Continue;
  - the review summary shows every entered value, and its Edit links return to the step;
  - submit sends the DPA flag;
  - a server 400 keeps step 3 and shows field errors;
  - success names the holder from the re-read record's `current_holders` (never a hard-coded Adviser), with Open paper and Publish another;
  - Thesis/Research and Project remain choosable with no Proposal behind them (invariant 7);
  - closing and reopening from `/?publish=<id>` resumes at the first incomplete step;
  - no upload-slot list appears anywhere in the flow;
  - Vitest covers each state, and axe is clean;
  - verified at the four viewports, including the full-screen sheet at 360;
  - a keyboard-only submission is completed and recorded.
- **Backend:** verify server-side file validation (Appendix D); add it if missing.
- **Depends:** F0. **Agent-ready** after F0.

### B1 · Metadata suggestions endpoint (backend) + F3b · Prefill in Publish

- **B1 AC:** Appendix D and §5 Seam 2. No network call in tests; 404 for non-owners; no migration.
- **F3b AC:**
  - chips appear only for non-null suggestions;
  - Use fills the field, and Dismiss removes the chip;
  - a field the user typed in is never overwritten, and its chip offers *Replace with suggestion* instead;
  - `pending` shows "Reading your PDF…" without disabling fields;
  - polling stops at 90 s or on leaving the step;
  - `failed` / `unsupported` show the neutral line;
  - no confidence value is shown.
- **Depends:** B1 is agent-ready now; F3b depends on B1 + F3.

### F4 · My Library absorbs My Workspace

- **Build:**
  - §4.9;
  - the `/workspace` redirect;
  - deletion of `MyWorkspacePage`, `WorkspaceOfficePills` and `workspaceStages`;
  - the library rail's *My research* section;
  - `ResearchCard` list with status and next-step lines;
  - Continue → Publish;
  - the non-author default.
- **AC:**
  - no numeric counters render;
  - each *My research* filter maps to `/records/mine/?pipeline_status=` or to the returned `workflow_state`, with no client stage derivation;
  - the next-step line appears only when the server's `workflow_state` shows the owner owes something;
  - Continue on a draft opens Publish at that draft;
  - the "this browser only" note stays on Saved;
  - the rail becomes a select below `md`;
  - verified at the four viewports;
  - the old tests for the deleted modules are retired with the reason stated.
- **Depends:** F0; F3 for Continue (or a stub link).

### F5 · Paper View sections and the capabilities adapter

- **Build:**
  - §4.6 and §4.8 (phase 1);
  - the header rebuild with empty lineage/version slots;
  - the Overview / Paper / Review / Files sections in the URL;
  - the Files section replacing `DocumentsPage`;
  - the *Edit details* dialog (`MetadataForm`) replacing `EditRecordPage`;
  - the Action-required banner (§4.10 vocabulary);
  - the adapter;
  - the role-name guard;
  - the redirects for `/records/:id/documents` and `/edit`;
  - removal of *Mark as completed*.
- **AC:**
  - each section renders only under its capability;
  - the redirects work;
  - the adapter table test passes;
  - the source-scan guard fails on a role comparison outside the adapter;
  - the Files section uploads through `UploadDropzone`, and a requested document shows Requested → Uploaded · awaiting review → Accepted / Replacement needed;
  - Edit details is offered only under `edit_details` (draft, or owner while `awaiting_resubmission`), is absent on a rejected, in-review or decided record, and saves and reflects immediately;
  - no author action (*New version*, *Continue*, *Edit details*) renders on a rejected record (invariant 5);
  - a forbidden record shows the not-found state;
  - the Paper section is byte-for-byte IR-352/372 behaviour (the existing reader tests stay green);
  - verified at the four viewports.
- **Depends:** F0, F3 (`MetadataForm`), IR-352/372/351 merged, IR-346.

### F6 · Review section v1 — timeline and action-bar shell

*Revised in the reconciliation pass: F6 no longer ports or deletes `EvaluationPage`.*

- **Build:**
  - §4.7;
  - `ReviewTimeline` from the tracker;
  - the action-bar shell: a `toolbar` landmark, a capability-driven button slot, disabled-with-reason, and `ConfirmDialog` for terminal actions;
  - *Request document* from the bar (ADR-022, already on the new model);
  - the secondary "Record a decision (current form)" link to the untouched `EvaluationPage` until IR-260;
  - the `/review/:id/evaluate` route is **kept**;
  - no Ask IRIS in the Review section (§4.6, decided); a visible *Ask about this paper* link switches to the Paper tab.
- **AC:**
  - the timeline lists routing, reviews and findings, resubmission requests and document requests in order, with actor and party, from the tracker only;
  - no Intake entry is rendered as current, and historical entries show the server's label;
  - the bar renders exactly the adapter's capabilities;
  - an action the server has not granted is absent, and one that is blocked says why;
  - a button slot accepts an action dialog from IR-261/269–273 without F6 changes (demonstrated with *Request document*);
  - below `lg` the paper stacks above the pane with a sticky action bar;
  - verified at the four viewports.
- **Depends:** F5.
- **Not in F6:** every ADR-032 decision action (IR-261, 269, 270, 271, 272, 273 add their own button and dialog into this bar), and deleting `EvaluationPage` (IR-274).

### F12 · Responsive and accessibility verification, and NFR evidence

- **Build:**
  - a recorded pass over every redesigned screen at the four viewports, keyboard-only and at 200 % zoom;
  - the NFR-U2 timed rehearsal on Publish (5 first-time participants, per IR-96's protocol);
  - evidence written to `docs/testing/TRACEABILITY.md` NFR-U1/U3 rows.
- **AC:** each screen × viewport recorded with the device/viewport named; failures filed, not waived.
- **Depends:** F1–F6.

### ADR-032 tickets (created under IR-255, vertical, backend + their UI in these slots)

| ADR-032 ticket | Its UI lands in |
|---|---|
| Seats, pool and coordinator | My Reviews (with IR-268); *Claim* / *Assign* on rows; *Open review* recording; B3's phase-2 definition |
| Record versions | The header version picker; the timeline version tags; *Submit new version* |
| Proposal continuation and lineage | The lineage slot; *Continue as…* on cards and Overview, opening the Publish dialog on the child draft (§4.4) |
| **Capabilities payload** (renamed from ADR-032 §14's "capabilities payload and Paper View modes"; the modes are F5's) | Adapter phase 2 (pass-through) |
| **Review comments** (renamed from "review timeline and `ReviewComment`"; the timeline is F6's) | The timeline composer; comment entries in F6's timeline |
| Public discussion | The bottom of Overview |
| Discoverable Proposals | The Discover Proposals tab, Summary mode, Publish/Edit visibility (absorbs IR-310) |

Each of these depends on F5 (slots) and, where the UI is in Review, on F6.

## Appendix G — Dependency graph and implementation order

```
F0 ──┬── F2 ─────────────────────────────┐
     ├── F3 ──┬── F3b ◄── B1 (parallel)  │
     │        └── F4                      ├── F1 (sidebar + redirects) ── F12
     └── F5 ◄─ IR-352/372/351 merged     │
          ▲    IR-346                     │
          └── F6 ─────────────────────────┘
                 ▲
ADR-032 backend tickets (IR-255) ──► slots in F5/F6/F4 (lineage, versions,
                                     comments, discussion, Discoverable, seats→My Reviews)
```

**Parallel:**

- B1 runs alongside everything.
- F2, F3 and F5 run in parallel after F0. They touch disjoint files, except `MetadataForm`: F3 creates it and F5 consumes it. So F5 either starts after F3 merges, or F3 lands `MetadataForm` first as its own commit.

**Sequential:**

- F0 before any screen;
- F3 before F3b and before F4's Continue;
- F5 before F6;
- F1 after F3 and F4;
- F12 last.
- `EvaluationPage` is untouched by every F ticket and deleted only by IR-274 after IR-260.

**Conflict risks when implemented simultaneously:**

- `lib/access.ts` and `router/index.tsx`: F1 and F3/F4/F5/F6 all add redirects. The rule is that **only F1 edits the sidebar and sections**, and each other ticket adds only its own redirect entry.
- The palette allowlist: each ticket deletes only its own lines.
- `PaperViewPage`: F5 and F6 are sequential, and IR-355 touches chat mounting (coordinate a rebase).

**Recommended order:**

1. **F0**, with **B1** in parallel.
2. **F3**.
3. **F2** and **F5** in parallel.
4. **F4**.
5. **F3b**.
6. **F6**.
7. **F1**.
8. The **ADR-032 slices**, as their backend lands.
9. **F12**.

## Appendix H — Agent-ready work

**Immediately:**

- **F0**: a well-bounded primitives ticket.
- **B1**: a small backend endpoint with a clear contract.
- **B2**: one field on an existing endpoint (it ships inside F1, but could land first).

**After F0 merges:** F2 and F3.

**After their dependencies:** F4, F5, F3b, F6, F1. All of them are agent-ready once their dependencies land, because each has complete acceptance criteria and uses existing endpoints.

**Human-led:** F12 (participants, a real device) and the §7.1 decisions.

The ADR-032 vertical tickets are created later, per the hold recorded on IR-255.

## Appendix I — Explicitly do NOT implement

- A second submission page or an IPAMS-style long form; an upload-slot checklist at submission; a separate "continue as" form (it reuses Publish).
- Porting the legacy decision form into the new Review section (§4.7).
- Role-gated My Reviews (§4.2).
- Any client-side workflow logic: stage derivation, route previews, office selection, or role comparisons for record actions.
- A parallel document-requirement system (ADR-022 is it).
- New reader, find-in-paper, citation-landing or Paper Chat work (IR-350 family).
- Counters, stat cards, analytics or "For you" personalisation without a signal.
- A server-side library, or a Discover-only visibility filter (visibility is one predicate).
- An LLM metadata step or confidence scores in the MVP.
- Any migration. B1, B2 and B3 are serializer/view changes; the seed change first proposed is withdrawn (§7.1 item 3).
- Duplicate Jira tickets: every item in Appendix E marked U/C is updated or closed, never re-created.

## Appendix J — Ticket reconciliation matrix

**Actions:**

- **Reuse:** the existing ticket already does it; use it.
- **Update:** re-scope the ticket's text.
- **Merge:** fold into another ticket.
- **Depend:** a blocking link only.
- **Close:** superseded or duplicate.
- **New:** no ticket covers it.

"T1–T7" are ADR-032 §14's seven tickets, not yet created:

| T | ADR-032 ticket |
|---|---|
| T1 | seats/pool/coordinator |
| T2 | versions |
| T3 | continuation/lineage |
| T4 | capabilities payload |
| T5 | review comments |
| T6 | public discussion |
| T7 | Discoverable Proposals |

| Capability / work | ADR-032 ticket | Existing Jira | Frontend redesign ticket | Backend ticket | Paper Chat / reader ticket | Action |
|---|---|---|---|---|---|---|
| Sidebar / IA, redirects, header, account menu | — | IR-149 (parent), IR-160 (done) | F1 | B2, B3 (inside F1) | IR-351 (AppShell scroll rule must be kept) | **New** F1; IR-149 closed once IR-161/162 are resolved |
| My Reviews gate (capability, not role) | T1 (phase 2) | IR-268 | F1 (nav + guard) | B3 | — | **New** B3 in F1; T1 re-points it |
| My Reviews page (tabs, rows, claim/assign) | T1 | **IR-268** | uses F0 `ResearchCard` | T1 + IR-268 | — | **Reuse** IR-268; no F ticket |
| Every record enters at Adviser | — | IR-261, IR-260 | — | IR-261 / IR-260 | — | **Reuse** |
| Adviser ≠ owner | — | IR-260 | F3 (client guard) | IR-260 | — | **Reuse**; F3 depends softly |
| Publish dialog (manual) | — | IR-161 | F3 | verify upload validation | — | **New** F3; **Close** IR-161 when F3 merges |
| Direct Thesis/Project submission | — | — | F3 | exists | — | **Reuse** (F3 AC) |
| Metadata prefill (Docling) | — | — | F3b | B1 | — | **New** (no existing ticket) |
| Supporting-document requirements | — | IR-118 | — | IR-118 | — | **Update** IR-118 → request templates |
| Document requests (reviewer / owner) | — | IR-262/263 (done), IR-346, IR-349 | F5 (Files, banner) | IR-346 | — | **Reuse** + **Depend** on IR-346 |
| Discover (Research) | — | IR-362 (palette) | F2 | none | — | **New** F2; **Update** IR-362 to Calls & Notifications only |
| Discover Proposals tab + Summary + visibility | T7 | IR-307, **IR-310**, IR-309 | slot in F2/F5 | T7 | — | **Merge** IR-310 into T7; **Update** IR-309 (intake → adviser) |
| My Library + workspace consolidation | — | IR-344, IR-345, IR-361 | F4 | none | — | **New** F4; **Close** IR-344; **Update** IR-345, IR-361 |
| "Needs my action" dot | — | — | F1 / F4 | B2 | — | **New** B2 (in F1) |
| Paper View sections + header + Files + Edit details | ~~T4 "Paper View modes"~~ | IR-141, **IR-142**, IR-363 | F5 | none | IR-352, 356, 372 | **New** F5; **Close** IR-142; **Update** IR-141, IR-363; T4 renamed |
| Capabilities adapter (client) | T4 (server) | IR-345 (Paper View rule) | F5 | T4 (phase 2) | — | **New** F5 phase 1; **Depend** T4 → pass-through |
| Review timeline (tracker-derived) | ~~T5 "review timeline"~~ | IR-258 (done) | F6 | none | — | **New** F6; T5 renamed "review comments" |
| Review comments | T5 | — | slot in F6 | T5 | — | **New** T5 (vertical) |
| Review action bar shell | — | IR-143 | F6 | none | — | **New** F6; **Close** IR-143 on its PR |
| Route / finding / decide / Proposal decision / request revision | — | IR-261, 269, 270, 271, 272 | F6 slot | same tickets | — | **Reuse**; **Update** their "held frontend" → "adds to F6's bar" |
| New version | T2 | IR-273 | F5 slot | T2 + IR-273 | — | **Reuse** IR-273 (resubmit) + T2 (versions); **Depend** |
| Version picker / timeline tags | T2 | — | F5 slot | T2 | — | **New** T2 (vertical) |
| Continue as Thesis/Project + lineage | T3 | — | F3 (reused dialog), F4/F5 slots | T3 | — | **New** T3 (vertical) |
| Public discussion | T6 | — | F5 slot | T6 | — | **New** T6 (vertical) |
| Status strip (party progress) | — | IR-141, IR-258 (done) | F5 | none | IR-356 (rail visuals) | **Update** IR-141 to the strip's states, or close; **PRODUCT** |
| Delete EvaluationPage, pipeline vocabulary | — | **IR-274** | — | IR-274 | — | **Reuse** IR-274 (reverses the first draft) |
| Workflow-display cleanup | — | IR-340, 341, 342, 343 | F0/F5 honour them | — | — | **Reuse** |
| Palette | — | IR-357, 361–366 | each F ticket removes its own allowlist lines | — | — | **Update** 361/362/363 scope; **Depend** IR-366 last |
| Paper reader / find / citations / chat | — | IR-351–356, 372 | reused by F5/F6 | — | yes | **Reuse**; see Appendix K |
| Shared primitives | — | IR-158 (done) | F0 | — | IR-356 (tokens) | **New** F0 |
| Responsive / a11y evidence | — | IR-96, IR-224 | F12 | — | — | **New** F12; **Depend** → IR-96 |
| Office amend at intake | — | IR-119 | — | — | — | **Close** (intake retired) |
| Search screen shape | — | IR-162 | — | — | — | **Reuse** (unrelated) |

**No capability has two tickets building it.** Where a first draft had overlap (F6 vs IR-274 on EvaluationPage, F5 vs T4 on "modes", F6 vs T5 on "timeline"), the matrix assigns one owner.

## Appendix K — IR-350 family: what stays theirs, what the redesign owns

*Code for IR-351, 352, 354, 356 and 372 is merged on `main`, and their cards are In Review. IR-353 is Done. IR-355 is To Do.*

| Ticket | Remains that ticket's responsibility | Belongs to the redesign | Rule for the redesign |
|---|---|---|---|
| **IR-351** Chat and chrome stay available while scrolling | `main` is not a scroll container; sticky offsets clear the header; the rail is capped | F1 changes `AppShell` (Discover under the shared header) | F1 **must not** add `overflow` to `main`, and keeps the sticky offsets. A regression test is added in F1 |
| **IR-352** Contained PDF viewer | The reader, its pane geometry, fit-to-width, the page counter, `readerGeometry` / `paneLayout` | The Review section places the same reader beside the review pane | F6 **reuses** `PaperPdfReader` and the pane helpers unchanged; no second reader |
| **IR-353** Find in paper (Done) | Find UI in the reader chrome | — | It comes free wherever the reader renders; no work |
| **IR-354** Citation lands on the passage | `citationLandingDelta`, first-region landing, the below-`lg` sheet behaviour | Any new pane mode the Review section adds | F6 adds a test that a citation landing in the Review section clears the header and the pane (IR-354's helper, not a new one) |
| **IR-355** Cross-paper citation keeps the conversation (To Do) | Pinning, the header "Chatting about X", release triggers, the ADR-026 §9 amendment (Jive reviews) | F5 restructures `PaperViewPage` sections, which touches the same mount path | **Land IR-355 before F5**, or F5 carries its regression test. F5 must not reintroduce the `LoadingSkeleton` unmount that IR-355 fixes |
| **IR-356** Editorial visual redesign | The Paper View visual language: serif titles, header block, Abstract reading column, chat panel design (AI label, scope toggle in the header, composer, starter questions) | F0 extends the *tokens* app-wide; F5 rebuilds the header *structure* (sections, slots) | F5 keeps IR-356's visual treatment and only adds structure. Ask IRIS stays out of the Review section (§4.6), so IR-356's chat design is untouched |
| **IR-372** Paper tab = reader + Ask IRIS docked right, full width | The Paper tab's layout rule and the dock preference behaviour | Overview (was Abstract), Review and Files sections | The Paper section is unchanged, and the Review section has no chat, so IR-372's rule is not stretched. Correct the card's stale "left" wording |

**Net:** the redesign adds sections and slots *around* the IR-350 family's work and changes none of its behaviour. No reader or chat ticket is duplicated.

## Appendix L — Duplication check: F/B tickets against the seven ADR-032 tickets

| F / B | Overlaps with | Finding | Resolution |
|---|---|---|---|
| F0 primitives | none | — | Keep |
| F1 navigation + B2 + B3 | T1 (seats) defines who has review work | B3's phase-1 definition would be replaced by T1 | Keep. T1's criteria include "re-point `review_access` at seats"; one field, two phases, **not** two implementations |
| F2 Discover | T7 (Discoverable) | F2 builds the tab container but not the Proposals tab | Keep. T7 adds the tab and must use F2's container and `ResearchCard` |
| F3 Publish | T3 (continuation), T7 (visibility) | "Continue as" could have become a second form; visibility is a Publish field | Keep. T3 reuses F3's dialog; T7 adds the visibility control to F3's step 3 |
| B1 / F3b prefill | none | — | Keep |
| F4 My Library | T3 (*Continue as…* on cards) | the card action | Keep. F4 leaves the slot; T3 fills it |
| F5 Paper View | **T4** as named in ADR-032 §14 ("capabilities payload **and Paper View modes**") | **Duplicate on "modes"** | T4 is created as **"capabilities payload"** only (backend + adapter pass-through). F5 owns sections/modes. Record the rename on ADR-032 §14 when T4 is created |
| F5 Paper View | T2 (version picker), T3 (lineage slot), T6 (public discussion slot), T7 (Summary mode) | slots only | Keep. Each T fills its slot and renders nothing until it ships |
| F6 Review | **T5** as named ("review timeline **and ReviewComment**") | **Duplicate on "timeline"** | T5 is created as **"review comments"** (model, API, composer, comment entries). F6 owns the timeline |
| F6 Review | T1 (*Open review* recording) | the button exists in F6 without recording | Keep. T1 makes the button record `opened_at` |
| F12 | none | — | Keep |

**Result:** two naming overlaps (T4, T5), resolved by narrowing those tickets' titles when they are created. No other F/B ticket duplicates an ADR-032 ticket.
