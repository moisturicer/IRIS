# Redesign recommendations: before and after

Each section pairs **ORIGINAL** screenshots of the deployed IRIS (`screenshots/original/`, captured 12–13 Nov 2026 on `https://iris-citu.duckdns.org/`) with **PROTOTYPE** screenshots of the redesign (`screenshots/redesigned/`, file names start with `R`, captured from `prototype/index.html`).

- **Original** screenshots show real IRIS with the demo accounts and the records the deployed database held.
- **Prototype** screenshots use invented sample papers, people and numbers. Nothing in them is a measurement of IRIS.
- Finding ids (NAV-01, WF-06 …) point to `audit-report.md`.
- Token and component names point to `design-system.md`.

The redesign is a **refinement, not a rebrand**:

- **Kept:** maroon `#6B0F12`, EB Garamond titles, Inter body text, the stone surfaces, the folder-tab sign-in frame, and every route, role and action that exists today.
- **Changed:** hierarchy, density, labelling, state wording, and how phones and tablets lay the app out.

Contents:
1. [Sign-in](#1-sign-in)
2. [Discover](#2-discover)
3. [Record overview](#3-record-overview)
4. [Ask IRIS beside a paper](#4-ask-iris-beside-a-paper)
5. [Paper reader](#5-paper-reader)
6. [Review and clearance (student view)](#6-review-and-clearance-student-view)
7. [Ask IRIS page](#7-ask-iris-page)
8. [My Library](#8-my-library)
9. [Publish a paper](#9-publish-a-paper)
10. [Notifications](#10-notifications)
11. [Settings](#11-settings)
12. [Adviser: My Reviews and routing](#12-adviser-my-reviews-and-routing)
13. [Office coordinator: queue, console, analytics](#13-office-coordinator-queue-console-analytics)
14. [RDCO tools](#14-rdco-tools)
15. [Tablet and phone](#15-tablet-and-phone)
16. [Changes made across the whole app](#16-changes-made-across-the-whole-app)
17. [Review workspace (reviewer view)](#17-review-workspace-reviewer-view)

---

## 1. Sign-in

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original sign-in at 1440](screenshots/original/01-login-1440.jpg) | ![Prototype sign-in with validation](screenshots/redesigned/R01-login-validation-1440.jpg) |
| ![Original sign-in at 360](screenshots/original/05-login-360.jpg) | ![Prototype sign-up, step 1](screenshots/redesigned/R02-signup-1440.jpg) |

**Problems in the original**
- The password field shows `••••••••` as placeholder text, so it looks already filled (US-07).
- "Email Address" and "Sign In" are Title Case, while the rest of the app uses sentence case (VIS-03).
- The visible headline is not a heading; the logo is the h1 (A11Y-08).
- Field outlines are about 1.3:1 against white (A11Y-01).
- At 360 px the CIT-U wordmark is about 10 px tall (RES-05).

**Changes in the prototype**
- Kept the folder-tab frame and the maroon index tabs, because they are distinctive.
- **No institution name in the copy** (live IR-768: the name lives in `config/institution.ts`, and the logo carries it). IRIS is not for CIT-U only.
  - Sign-in: the headline is "Your research has *a place.*" and the field is labelled "Email address", with no placeholder.
  - Sign-up: the headline is "Begin with your *research identity.*" and the field is labelled "Institutional email", with the hint "Use the email your institution gave you."
  - The validation message still names the allowed domain ("ending in @cit.edu"), because the server enforces it. That text should come from the institution config, not be hard-coded.
  - The footer reads "© 2026 IRIS · Research and IP disclosure".
- The password field has no placeholder and a "Show" toggle. "Forgot password?" sits beside its label.
- Validation messages appear in text under each field, and focus moves to the first error (screenshot R01).
- Fields use the new `field` outline token `#8f8884` (3.49:1 against white).
- The CIT-U seal is 40 px tall.
- The page is titled "Sign in · IRIS".

**Why.** Sign-in is the one Persuade surface, so it keeps its character. The fixes remove the three things that make people fail at the first attempt: an apparently filled password, the wrong email domain, and fields they cannot see.

---

## 2. Discover

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original Discover](screenshots/original/10-discover-1440.jpg) | ![Prototype Discover](screenshots/redesigned/R10-discover-1440.jpg) |
| ![Original filters popover](screenshots/original/11-discover-filters.jpg) | ![Prototype filter panel](screenshots/redesigned/R11-discover-filters-1440.jpg) |
| | ![Prototype: a search that looks like a question offers Ask IRIS](screenshots/redesigned/R13-discover-question-suggest-1440.jpg) |
| ![Original Areas modal](screenshots/original/12-discover-areas-modal.jpg) ![Original search error](screenshots/original/16-discover-search-error.jpg) | |

**Problems in the original**
- Three filled maroon controls (Papers, Latest, + Publish) in one toolbar break the Binding Rule (VIS-01).
- The toolbar mixes four control heights (LAY-02).
- About 1.5 results fit on a 1440 × 900 screen, because each card spends half its height on a grey "Preparing first page…" placeholder plus an "AT A GLANCE" block (LAY-01, VIS-02).
- The search placeholder cycles questions, but it runs a keyword search (US-01).
- Filter selects have no labels, and Sort is hidden inside Filters (US-03).
- People results appear inside a Papers search, and their failure offers no retry (US-04).
- The Areas modal says "No Areas available." and still offers Save (US-02).
- Errors say "Check your connection" when the server was slow (US-05).
- The layout toggle is an unlabeled square (CMP-04).

**Changes in the prototype**
- The page header has a title, a one-line description and one filled action, **Publish a paper**.
  - The description is "Research, projects and reference papers in IRIS." An earlier draft said "Theses and research published at CIT-U"; that is gone, because IRIS is not for one school.
  - **Publish appears only for Student and Adviser**, the two roles live IRIS lets author a paper (`lib/access.ts`, `AUTHORS`). Offices and RDCO do not see it, here or in the top bar.
- Search sits inside the header. Its placeholder reads "Search titles, authors and keywords".
- **Ask IRIS is offered only when a search looks like a question** (screenshots R13, R78). The search must start with who, what, when, where, why, how, which, does, is, can and similar words, or end with "?". One quiet line then appears above the results: *"This looks like a question. Ask IRIS answers it from the papers, with page numbers."* The link carries the search to Ask IRIS, which asks it at once. An ordinary title or keyword search never shows it, and a question that finds nothing gets the empty state's **Ask IRIS instead** button.
  - An earlier draft showed a permanent line under the search box (*"Have a question rather than a title?…"*). It was removed: Ask IRIS is already in the sidebar and the floating button, and a line shown on every visit soon goes unread.
  - Cost: it is a guess. A title that starts "How…" shows the line too, which adds one line above correct results.
  - The prototype's search now matches every word, ignoring common words and punctuation, as keyword search does. It used to match the whole phrase, so no question could ever return results.
- **One toolbar, one control height:**
  - **Papers | People** and **Latest | For you | Most viewed** are segmented controls. Their selected state is a white raised segment with Ink text, never maroon (§18).
  - **Filters** shows its active count as a badge. **My feeds** is a menu.
  - The prototype labels the Trending feed "Most viewed". Keep "Trending" unless that feed really is ranked by views.
- Filters open as an inline panel with visible labels ("Area", "College or office", "Year completed", "Record type"), plus "Clear all" and "Done".
- **Sort** moved to the results header next to the live result count ("6 papers for …").
- Results are list rows:
  - **Text:** type · year, a Garamond title, authors, a two-line abstract and keywords, with the search term highlighted.
  - **Actions:** Save, Cite and Share on one line, with views in tabular figures.
  - **Thumbnail:** a 96 px first-page thumbnail drawn as a neutral page outline, never placeholder text.
- **The whole card opens the paper**, not only its title. The title stays the one real link (one link per card for screen readers; middle-click and "open in new tab" still work) and stretches over the card. Authors, Save and other buttons keep their own targets above it. Keyboard focus outlines the whole card. The same applies to My Library, profile and My Reviews rows. Cost: dragging to select abstract text starts on the link, so copying text from a card is harder.
- With these changes, four to five results fit on the first screen.
- An empty result offers **Ask IRIS instead** and **Clear search**.
- People results live only on the People tab.
- The Areas control is left out of the prototype. The live build has no areas yet, so the recommendation is to hide it until areas exist (US-02).
- The layout toggle is gone, because one good list replaces two weak layouts.

**Why.** Discover is the front door for every role. The changes target scanning speed (more results, one reading order per row) and honesty (a keyword box that says it is one, and a route to Ask IRIS for questions).

---

## 3. Record overview

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original record overview](screenshots/original/20-record-overview.jpg) | ![Prototype record overview](screenshots/redesigned/R20-record-overview-1440.jpg) |
| ![Original AI overview headings](screenshots/original/21-record-ai-overview.jpg) | |
| ![Original cite dialog](screenshots/original/22-record-cite-dialog.jpg) | ![Prototype cite dialog](screenshots/redesigned/R24-record-cite-dialog-1440.jpg) |
| ![Original notes panel](screenshots/original/23-record-notes-panel.jpg) | ![Prototype notes panel](screenshots/redesigned/RD3-record-notes-panel-1440.jpg) |
| | ![Prototype related works and comments](screenshots/redesigned/RD1-record-related-comments-1440.jpg) |
| | ![Prototype comments at 390](screenshots/redesigned/RD4-record-comments-390.jpg) |

**Problems in the original**
- Author chips wrap one per line.
- Four dates compete: Added, Published, Completed, and Year Accomplished (LAY-03).
- Inside the AI Overview, the subheads are larger than the section heads (VIS-06).
- The status chip is a solid ink pill (VIS-07).
- Uppercase eyebrows such as "INSTITUTIONAL GOVERNANCE" and "DOCUMENTS" appear (VIS-02).
- A floating **Notes** button sits above the floating **Ask IRIS** button and can cover text on a phone (CMP-02). The pair is kept by the owner's decision; see below.
- The page title is "IRIS" (NAV-01).

**Changes in the prototype**
- **Record bar:** a sticky bar holds Back, the paper title (once the page has scrolled past it), an **Overview | Paper | Review** control and an **Ask IRIS** toggle. Review appears only for people in the workflow.
- **Action row under the title:** one filled **Read paper**, then Save, Cite and Copy link.
- **Notes and Ask IRIS stay where they are today:** a small white **Notes** button just above the maroon **Ask IRIS** button, on Overview and Paper. Each opens the same side panel, and each panel has a button that switches to the other.
  - **Notes (RD3)** is private, as today: "only you can read your notes. Not staff, the paper's authors or Ask IRIS." It saves as you type and says so.
  - The page keeps space at the bottom so the last lines can scroll clear of the two buttons.
- **Byline:** the authors on one wrapping line, followed by "Adviser *name*".
- **Dates:** the line above the title reads "type · college · Completed 2026". Record details lists Completed and Published once each.
- **PDF copy:** **Request a PDF copy** sits in a "Full text" card in the side column. It explains that reading needs no approval and that a copy does.
- **Headings:** a fixed ladder of 22 px section heads, with 17 px Garamond subheads inside the AI Overview. The AI Overview is labelled as generated and cites pages.
- **Status:** shown as tone + word + icon (for example `Published ✓`), outlined rather than solid.
- **Related works (RD1)** keeps the live cards: three across, title in Garamond, then year and area, and **Explore all papers →**. The "Record #" line is dropped, because a record number means nothing to a reader.
- **Comments (RD1, RD4)** keep the live threads, like a social feed:
  - Each comment is a grey bubble with the name and an "Author" tag, and under it **Reply** · time · Edited.
  - Replies sit under their comment, joined by a thread line. A reply to a reply starts with "@name", which jumps to the comment it answers.
  - Threads with more than two replies start folded ("View 3 replies").
  - The reply box sits in the thread, with "Replying to *name* · Cancel reply · Ctrl+Enter to post".
  - Your own comments can be edited or deleted from "⋯", and others can be reported. Sort by Oldest or Newest.
- Record details gains a Contact row.
- **Cite:** the dialog keeps the original's good shape — APA, MLA and BibTeX with one filled **Copy** — and confirms the copy with a toast.
- **Title:** the browser tab reads "*Paper title* · IRIS".

**Why.** The record page is where reading, citing and review meet. Removing duplicate dates lets the abstract lead. One action bar gives every action a predictable home on every width.

---

## 4. Ask IRIS beside a paper

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original Ask IRIS panel](screenshots/original/24-record-ask-iris-panel.jpg) | ![Prototype Ask IRIS panel at 1440](screenshots/redesigned/R21-record-ask-iris-1440.jpg) |
| | ![Prototype Ask IRIS panel at 1280](screenshots/redesigned/R26-record-ask-iris-1280.jpg) |
| | ![Prototype scope widened mid-chat](screenshots/redesigned/RD5-ask-scope-widened-1440.jpg) |
| | ![Prototype chat locked to all papers](screenshots/redesigned/RD6-ask-scope-locked-1440.jpg) |

**Problems in the original**
- The empty panel asks "What would you like to investigate?" and offers no starter questions, which DESIGN.md specifies (US-16).
- Help calls this panel "Paper Chat" while the UI calls it "Ask IRIS" (US-12).
- The scope pill's label is the current scope, but it reads just as well as the thing a click switches to.
- A chat that started on all papers can't narrow back to this paper. The pill simply stops working, and only a hover tooltip says why.
- After a mid-chat switch, nothing shows which answers came from this paper and which from all papers.

**Changes in the prototype**
- The panel opens from the **Ask IRIS** corner button, as today. Its header has New chat, a Notes button that switches the panel to your notes, and Close.
- **One scope control, in the message box** (R21), where the live pill is. It opens a two-item menu:
  - **This paper**: "Only this paper, with pages".
  - **All papers**: "Can cite other CIT-U papers".
  - It is outlined for This paper and filled maroon for All papers, so the state shows at a glance. The placeholder says it too: "Ask about this paper" or "Ask across all papers".
- **The live rules are kept.** Each scope is its own chat, and one that started on all papers can't narrow. Instead of a dead button, one line explains it: "This chat covers all papers. **New chat on this paper**" (RD6).
- **A switch mid-chat leaves a divider**, "All papers from here". A citation from another paper names it ("Perceived Usability…, p. 18"), so it's clear the answer left this paper (RD5).
- Starter questions follow the scope.
- The panel opens beside the paper rather than over it. Below 1280 px the overview collapses to one column, so the abstract stays readable (container query).
- Answers cite page numbers, and each citation jumps to the Paper tab.
- The composer states the model's limits in one line.
- Help now uses the UI's name, "Asking IRIS".

---

## 5. Paper reader

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original paper view](screenshots/original/25-record-paper-view.jpg) | ![Prototype paper reader](screenshots/redesigned/R23-record-paper-1440.jpg) |
| ![Original focus ring at 1280](screenshots/original/26-record-1280-focus-ring.jpg) | ![Prototype sidebar collapsed by hand](screenshots/redesigned/R12-discover-sidebar-collapsed-1440.jpg) |

**Problems in the original**
- The collapsed sidebar rail has bare icons with no labels (NAV-07).
- "Request pending · Cancel request" sits inside the zoom toolbar (CMP-06).
- The loading copy says "Loading Paper View…", which is an internal name (US-09).

**Changes in the prototype**
- At tablet width the sidebar becomes a 76 px rail, and every rail item has a tooltip and an `aria-label` (§15).
- **The sidebar collapses, as in live IRIS (kept, not new).** On a desktop-width screen the IRIS mark is a button, "Collapse sidebar" / "Open sidebar", that folds the sidebar to the same rail and opens it again; the choice is remembered. Opening the Paper tab collapses it for that visit only, and leaving the tab restores your choice (live IRIS, IR-569). **Review collapses it too (a change from live, frontend owner, 13 Nov)**, because the paper is open there as well: at 1440 the workspace gains about 170 px, which keeps the paper readable when a tab is open on the right (RB7). The IRIS mark opens it again for that visit. Read from `Sidebar.tsx` and `ui.store.ts` on `main`; the live session had expired, so it was not seen on the deployed site.
- The reader toolbar holds page navigation, zoom and one **Request PDF** action. The action opens a dialog that asks for a reason and says RDCO approves copies.
- The request's state is tracked in My Library › Download requests, not shown as "pending / cancel" text in the toolbar.
- The mock PDF page uses the app's own serif and sans faces.
- **Not prototyped:** find-in-paper and the section outline that IRIS already has (`PaperFind.tsx`, `headings.tsx`). Keep both.

---

## 6. Review and clearance (student view)

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original review workspace, ITSO view](screenshots/original/B0-review-workspace-conversation-1440.jpg) Captured as an ITSO reviewer. The demo student's records had no multi-office review in progress, so the student view was not captured. Its labels were read from `frontend/src/features/records/paper-view/ReviewRoutingTracker.tsx` ("Cleared on v1, preserved", "Reset by v2"). | ![Prototype review tab](screenshots/redesigned/R22-record-review-student-1440.jpg) |
| | ![Prototype send version 2](screenshots/redesigned/RB5-send-version-dialog-1440.jpg) |

**Problem.** Clearance-aware resubmission is the thesis contribution, and it is the least visible thing in the product (WF-06). It appears only deep in the Review tab. Queue rows and My Library rows show none of it.

**Changes in the prototype**
- **The Review tab keeps the live workspace** (paper, review pane, details) and says what is waiting on whom at both ends of the pane:
  - At the top, where the paper is: *"With the authors · IERC asked for changes"*, and *"Adviser keeps its clearance. Only IERC reviews the next version."*
  - In the footer, your part and one action: *"Your part: send version 2 for IERC. 2 open threads to answer."* with **Send version 2…**.
- **Clearance strip** with one cell per party. Each cell shows its state in words plus an icon:
  - Adviser · cleared
  - ITSO · kept from v1
  - IERC · reviewing
  - KTTO · kept from v1
  - RDCO · publishes last
- Where the strip has room, as in the office console's status column, the label is the fuller "Cleared on v1 · kept".
- **No new colours.** "Kept" uses the settled tone with a shield icon, so status stays tone + word + icon, as DESIGN.md requires.
- **The same strip is reused** on My Library rows, adviser queue rows and the office console (§8, §12, §13).
- **Conversation** tab: versions, decisions and reviewers' comments in one timeline.
- **Send version 2 dialog (RB5):** it says which clearances are kept before you send, takes the revised PDF, and asks for a response under each open thread. After sending, IERC shows "Reviewing v2" and the other offices are unchanged.
- The reviewer's side of the same workspace is in §17.

**Why.** If a student can see at a glance that only IERC is re-reviewing, the thesis claim becomes something users notice rather than something the team explains.

---

## 7. Ask IRIS page

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original new conversation](screenshots/original/40-ask-iris-new.jpg) | ![Prototype answer](screenshots/redesigned/R40-ask-iris-answer-1440.jpg) |
| ![Original depth menu](screenshots/original/41-ask-iris-depth-menu.jpg) | ![Prototype delete conversation dialog](screenshots/redesigned/RD7-ask-delete-conversation-1440.jpg) |
| ![Original answer](screenshots/original/42-ask-iris-answer.jpg) | |
| ![Original sources](screenshots/original/43-ask-iris-sources.jpg) | |

**Problems in the original**
- Answers run about 110 characters a line at 1440 (LAY-04).
- Sources show raw chunk text with Markdown debris and cut off mid-sentence (US-15).
- An empty conversation offers no starter questions (US-16).

**Changes in the prototype**
- The thread and composer are capped at about 68 characters a line and centred. Recent conversations sit in a left column; on phones they open as a list.
- The **depth menu** keeps the real wording: "Standard" (*A shorter search for a quicker answer*) and "Thorough research" (*Searches and reads more before answering*).
- The **sources** list shows paper title, section and page plus a clean snippet, and each source opens the paper at that page.
- While waiting, the message says what is happening: *"Reading the papers. This can take a few seconds…"*.
- Starter questions appear on a new conversation.
- **Delete a conversation (kept from live IRIS, not new).** Each conversation in the list has a trash button, shown on hover or keyboard focus and always shown, at 44 px, on touch screens. It is named "Delete <title>" for screen readers. It opens **Delete conversation?** with live's wording ("Delete “…” and its messages? This cannot be undone."), focus on **Cancel**, and **Delete conversation** as the dark-maroon danger button. Deleting the open conversation returns to a new one; focus moves to the next conversation, or to New conversation when none is left. Read from `ConversationSidebar.tsx` and `RAGChatPage.tsx` on `main`. In the prototype a delete lasts until the page reloads.

---

## 8. My Library

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original overview](screenshots/original/30-library-overview.jpg) | ![Prototype overview](screenshots/redesigned/R30-library-overview-1440.jpg) |
| ![Original submissions](screenshots/original/31-library-submissions.jpg) | |
| ![Original saved empty](screenshots/original/32-library-saved-empty.jpg) | |
| ![Original downloads skeleton](screenshots/original/33-library-downloads-skeleton.jpg) | ![Prototype office My Library: Saved papers and Download requests only](screenshots/redesigned/R31-office-library-1440.jpg) |

**Problems in the original**
- A draft on the Overview has no "continue" action. Continue appears only on My submissions (WF-03).
- Titles carry the uploaded file name, for example *"…Metro Cebu.docx"* (WF-04).
- **Delete** has the same weight as **Continue** (US-06).
- Download requests show an unlabeled skeleton for 7 s or more (FB-02).

**Changes in the prototype**
- **"Your papers" next-step list.** Each paper gets one row stating what is waiting on whom:
  - The draft row: *"Draft · step 2 of 3, Details. Saved 11 Nov."* with a filled **Continue draft** button.
  - Papers in review: *"IERC is reviewing your version 2. Nothing to do yet."* with the clearance strip.
- **My research:**
  - **Continue draft** is the filled button.
  - **Delete draft** is a ghost button with a trash icon. It opens a confirmation dialog that names the paper.
  - Titles have no file extension.
- **Tabs carry counts and are addressable** (`#/library?tab=saved`).
- **Empty states** name the next action, for example *"Nothing saved yet"* with **Go to Discover**.
- **Who gets which tabs (kept from live).** Only authors (Student, Adviser) have Overview and My research, and a Publish button. Office reviewers and RDCO still have My Library, with **Saved papers** and **Download requests** only, because they save and request papers like any reader (live `READER_TABS`; screenshot R31). The System Admin has no My Library or Ask IRIS in the sidebar (live `onlyFor: RESEARCH_ROLES`).

---

## 9. Publish a paper

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original publish dialog](screenshots/original/60-publish-dialog.jpg) | ![Prototype step 1 validation](screenshots/redesigned/R60-publish-step1-validation-1440.jpg) |
| | ![Prototype step 2 validation](screenshots/redesigned/R61-publish-step2-validation-1440.jpg) |
| | ![Prototype review step](screenshots/redesigned/R62-publish-review-1440.jpg) |

**Problems in the original**
- **Continue** is disabled at 50 % opacity (about 3:1, white on pink), and nothing says why (CMP-05).
- The disabled dropzone's helper text is 2.5:1 (A11Y-02).
- The title is pre-filled with the file extension (WF-04).

**Changes in the prototype**
- The three real steps — **Your manuscript**, **Details**, **Review & submit** — appear as a numbered stepper.
- **Continue is always enabled.** Pressing it with something missing shows a text error and moves focus to the first problem. A permanently disabled button tells the user nothing.
- Details pre-fills the title without the extension. A notice says *"IRIS filled the title and abstract from your PDF. Check them before you continue"*, with **Undo**.
- The Adviser is required.
- Review & submit lists every field and adds a "What happens next" notice. The submit button names the adviser ("Submit to Ana").
- Success says what happens next: the Adviser reviews first.
- Resuming a draft (from My Library) opens at the saved step.

---

## 10. Notifications

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original notifications popover](screenshots/original/51-notifications-popover.jpg) | ![Prototype notifications](screenshots/redesigned/R51-notifications-1440.jpg) |
| ![Original adviser notifications](screenshots/original/85-adviser-notifications.jpg) | |
| ![Original stale ITSO notification](screenshots/original/90-office-notification-stale.jpg) | |

**Problems in the original**
- A coordinator's unread notification says a record is waiting while their queue shows zero to review, and it never resolves. Its copy also has a joining error: "please check It is…" (WF-01).
- Type tags are system names, such as "New Record (Proposal / Thesis)" (US-10).
- Unread rows are marked only by a 6 px dot (A11Y-07).
- "NOTIFICATIONS" is set in uppercase (VIS-02).

**Changes in the prototype**
- **Notifications whose task is closed show a resolved line,** for example `✓ Cleared by you on 20 Oct` or `✓ You sent version 2 on 7 Oct`. They drop out of the unread count.
- **Rows are grouped** Today / This week / Earlier.
- **Unread rows are bolder,** with a dot and a hidden "Unread." prefix for screen readers.
- **The text is a full sentence that names the party.** For example: *"Sam Student sent version 2 of … Your clearance from version 1 is kept; only IERC reviews again."*
- **All | Unread (n)** filter and **Mark all as read**.
- **The bell popover** uses compact rows that are links in their own right.

---

## 11. Settings

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original account settings](screenshots/original/54-settings-account.jpg) | ![Prototype privacy settings](screenshots/redesigned/R54-settings-privacy-1440.jpg) |
| ![Original privacy settings](screenshots/original/55-settings-privacy.jpg) | |
| ![Original role settings](screenshots/original/56-settings-role.jpg) | |

**Problems in the original**
- Labels such as "SIGN-IN EMAIL" are uppercase (VIS-02).
- The rectangular "CHANGE PASSWORD" button differs from every other button (VIS-04).
- Tabs are not addressable (NAV-08).
- The privacy copy has a grammar error: "papers you're Contact person of" (US-11).

**Changes in the prototype**
- Settings sections sit in a vertical tab list, and each has a URL (`?tab=privacy`).
- Sentence-case labels; one pill button style.
- **Ask to delete my account…** is a ghost button that opens a confirmation dialog explaining that a System Admin reviews it and that published papers stay.
- **Download my data** keeps the real feature (IR-369 now includes the papers you viewed).
- **Caveat:** the consent checkboxes in the prototype are illustrative. Copy them from the live consent model, not from the prototype.

---

## 12. Adviser: My Reviews and routing

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original adviser empty queue](screenshots/original/80-adviser-my-reviews-empty.jpg) | ![Prototype adviser My Reviews](screenshots/redesigned/R80-adviser-my-reviews-1440.jpg) |
| ![Original adviser done tab](screenshots/original/81-adviser-my-reviews-done.jpg) | ![Prototype adviser review workspace](screenshots/redesigned/R81-adviser-review-your-turn-1440.jpg) |
| ![Original route error](screenshots/original/83-route-error-details.jpg) | ![Prototype finish review dialog](screenshots/redesigned/R82-adviser-route-dialog-1440.jpg) |

**Problems in the original**
- Queue rows show only "Adviser · You · Accepted". No row shows where the paper is with the offices (WF-06).
- Theses read **Accepted**, a term PRODUCT.md reserves for Proposals. This is a server vocabulary decision (WF-05).
- The route error screen itself is good and is kept (§11 of the audit).

**Changes in the prototype**
- **Queue rows** show due date, version, how long the paper has waited, the clearance strip and one action that says what you will do: **Start review**, or **Open**.
- **To review** sorts by **Soonest due**, **Longest waiting** or **Overdue only**. **Done** keeps the live outcome filters (All, Cleared, Finding recorded, Accepted, Rejected, Published), each with its count (R80).
- **Your part, in the pane footer.** The Review workspace ends with one line stating the decision you owe and one action, **Finish review…** (R81).
- **Finish review dialog (R82):** choose **Clear and route**, **Request a revision** or **Reject**, and write a summary for the authors. Clearing lists the offices that review it next (ITSO, IERC, KTTO), each with what it checks. A revision or rejection needs a summary, and your draft comments are sent with the decision.
- **Labels** keep the server's words. The prototype does not rename workflow states.

---

## 13. Office coordinator: queue, console, analytics

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original office My Reviews](screenshots/original/91-office-my-reviews.jpg) | ![Prototype office My Reviews](screenshots/redesigned/R90-office-my-reviews-1440.jpg) |
| ![Original office console error](screenshots/original/92-office-console-error.jpg) | ![Prototype office console](screenshots/redesigned/R91-office-console-1440.jpg) |
| ![Original workflow analytics](screenshots/original/93-workflow-analytics.jpg) | ![Prototype analytics](screenshots/redesigned/R92-office-analytics-1440.jpg) |
| | ![Prototype unclaimed review](screenshots/redesigned/R93-office-review-unclaimed-1440.jpg) |

**Problems in the original**
- Office console and Workflow analytics exist only as links at the top of My Reviews. No sidebar item is active on those pages (NAV-02).
- Two different "selected" colours appear: maroon and solid black (VIS-05).
- The console's error blames the user's connection (US-05).
- Analytics leads every table with paragraphs, and its numbers are left-aligned in proportional figures (LAY-05).

**Changes in the prototype**
- **Sidebar.** My Reviews has nested **Office console** and **Workflow analytics** items for coordinators, and the parent stays active. Breadcrumbs read "My Reviews › Office console".
- **Console table:**
  - Columns: paper, reviewer ("Nobody yet" when unclaimed), due date in tabular figures, and status as tone + word ("Overdue by 1 day", "Due in 2 days", "Unassigned", "Cleared on v1 · kept").
  - Unclaimed rows offer **Assign…**. Other rows put Reassign / Extend due date in a "⋯" menu.
- **Unclaimed review (R93).** The workspace footer says *"Nobody has claimed this yet"* and offers **Assign…** and **Claim review**. After claiming, it offers **Finish review…** (Clear for ITSO, or Record a finding) with rarer actions under "⋯".
- **Analytics:**
  - Three summary figures, then one "By party" table with right-aligned tabular numbers.
  - Your own office's row is marked "You".
  - The method is moved into a "How these numbers are counted" disclosure.
  - **Every number in this screenshot is invented sample data.** The "Clearances kept across a revision" figure is a *proposal* for a metric that would make WF-06 measurable. It does not exist in IRIS today.
- **One selected style everywhere:** an Ink outline or a white raised segment (§18).

---

## 14. RDCO tools

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original import records](screenshots/original/A1-rdco-import-records.jpg) | ![Prototype import check](screenshots/redesigned/RA1-rdco-import-check-1440.jpg) |
| ![Original users](screenshots/original/A2-rdco-users.jpg) | ![Prototype users](screenshots/redesigned/RA2-rdco-users-1440.jpg) |
| ![Original delete requests](screenshots/original/A5-rdco-delete-requests.jpg) | ![Prototype delete requests](screenshots/redesigned/RA5-rdco-delete-requests-1440.jpg) |
| ![Original notices](screenshots/original/A6-rdco-notices.jpg) | ![Prototype notices](screenshots/redesigned/RA6-rdco-notices-1440.jpg) |
| | ![Prototype embargo card](screenshots/redesigned/RD2-rdco-record-embargo-1440.jpg) |
| Not inspected: no System Admin account was used. | ![Prototype audit log](screenshots/redesigned/RC1-admin-audit-log-1440.jpg) |
| | ![Prototype account deletions](screenshots/redesigned/RC2-admin-account-deletions-1440.jpg) |

**Problems in the original**
- **Users:** a filled **Lock** button on every row, including the signed-in RDCO's own (CMP-01).
- **Delete requests:** the **Pending** tab lists a *Declined* request, and its Action column holds a date (WF-02).
- **Import:** "download template here" is a link inside a sentence with a double hyphen, and an empty Import Log is shown (US-14).
- **Notices:** a 50 %-opacity disabled publish button (CMP-05), and textarea outlines at about 1.25:1 (A11Y-01).

**Changes in the prototype**
- **Users:**
  - Name first, with email under it. Your own row is marked "You" and has no actions.
  - Every other row's actions sit in a "⋯" menu. **Lock account…** opens a confirmation dialog that names the person.
- **Record deletion requests (RA5):**
  - Tabs **Pending · Approved · Declined · All**, each with its count. A request appears only under its own state, which is the WF-02 fix.
  - Pending rows offer **Decline…** and **Approve…**. Each opens a dialog that names the record; declining needs a reason the author sees. Decided rows show the outcome and the reason, with no action.
- **Embargo card (RD2):** on a record, RDCO sees whether it is under embargo and until when, with **Release…** and **Change review date…**.
- **System Admin pages (RC1, RC2):** Users, Audit log, Account deletions, Retention and Notices, from the router's admin routes. Account deletions use the same four tabs as record deletions. These are designs only: the live pages were not seen.
- **Import:** three numbered steps (get the template, fill it in, upload), with **Download template** as a real button.
  - After files are chosen, IRIS checks every row and shows problems before **Import records** is enabled (RA1).
  - Imported papers arrive embargoed, as they do today.
  - The prototype labels the template as CSV. Confirm the real format (the live page offers a spreadsheet) before copying that label.
- **Notices:** the live version is shown beside the draft, and **Publish version 4…** asks for confirmation.

**Why.** These screens hold irreversible actions. The pattern throughout: the action is never the loudest thing on the row, the list never contradicts its filter, and a confirmation names its target.

---

## 15. Tablet and phone

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original Discover 768](screenshots/original/70-discover-768.jpg) | ![Prototype Discover 768](screenshots/redesigned/R70-discover-768.jpg) |
| | ![Prototype record review 768](screenshots/redesigned/R71-record-review-768.jpg) |
| ![Original Discover 390](screenshots/original/71-discover-390.jpg) | ![Prototype Discover 390](screenshots/redesigned/R72-discover-390.jpg) |
| ![Original drawer 390](screenshots/original/72-mobile-drawer-390.jpg) | ![Prototype drawer 390](screenshots/redesigned/R73-drawer-390.jpg) |
| ![Original Discover 360](screenshots/original/73-discover-360.jpg) | ![Prototype Discover 360](screenshots/redesigned/R77-discover-360.jpg) |
| ![Original record 390](screenshots/original/74-record-390.jpg) | ![Prototype record 390](screenshots/redesigned/R74-record-390.jpg) |
| ![Original FAB overlap 390](screenshots/original/75-record-390-fab-overlap.jpg) | ![Prototype review drawer 390](screenshots/redesigned/R75-record-review-390-drawer.jpg) |
| | ![Prototype Ask IRIS 390](screenshots/redesigned/R76-ask-iris-390.jpg) |
| | ![Prototype paper 360](screenshots/redesigned/R79-record-paper-360.jpg) |

**Problems in the original**
- At 768 px the full 200 px sidebar stays open, and the Discover toolbar wraps to three rows (NAV-06).
- On phones, four rows of controls push the first result about 400 px down. Publish, Areas and Filters become unlabeled icons (RES-01).
- Many touch targets are 34–38 px (RES-02).
- The record chrome takes about 180 px before the title (RES-03).
- The phone top bar shows no brand (RES-04).
- Two floating buttons can cover text (CMP-02). They are kept by the owner's decision, with space reserved at the bottom of the page.
- Discover's segmented text drops to 12 px (A11Y-09).

**Changes in the prototype**
- **Three layouts:**
  - Desktop (1024 px and up): a 248 px sidebar.
  - Tablet (768–1023 px): a 76 px icon rail with tooltips.
  - Phone (below 768 px): a top bar with the IRIS mark, the bell and a menu button that opens a drawer. The drawer traps focus, closes on Escape and returns focus.
- **Phone Discover:**
  - Search first, then one horizontally scrolling control row with a fade edge.
  - Publish stays a labelled action in the page.
  - The first result appears within the first screen.
- **Phone record:**
  - Back and the section control merge into one record bar.
  - Tables on Review and the RDCO screens stack into labelled rows.
- **Review workspace** lays itself out by its own width: paper and pane from 740 px (RB4), plus an optional right column from 1180 px (RB7), and below that a drawer with "Back to paper" (R71 at 768, R75 at 390). Its footer action stays in reach at every width.
- **Corner buttons.** On a record's Overview and Paper: Notes above Ask IRIS, as today. Elsewhere: Ask IRIS alone. None on the Ask IRIS page or the Review tab.
- **Touch targets** are 44 px or larger, and no text is below 12 px.
- **Overflow check:** every route was checked for all four roles at 360, 390 and 768 px. None scrolls horizontally.

---

## 16. Changes made across the whole app

| Change | Findings | Where to see it |
|---|---|---|
| Each page sets its own `document.title` ("Discover · IRIS") | NAV-01 | Every prototype route; check the browser tab |
| Field outlines at 3.49:1 (`field` token), placeholders at 4.5:1 or more | A11Y-01, A11Y-02 | Sign-in, Publish, Notices |
| One filled maroon action per row; one look per kind of highlight (§18) | VIS-01, VIS-05 | Discover, My Reviews, Review |
| Sentence case and no uppercase eyebrows | VIS-02, VIS-03 | Everywhere |
| One button shape (pill) and one control height per input mode (36 px pointer, 44 px touch) | VIS-04, LAY-02, RES-02 | Everywhere |
| Status as tone + word + icon; no new hues; solid fills reserved for attention | VIS-07 | Records, tables, notifications |
| One stroked icon set (Lucide-style, 1.75 px); the speech-bubble brand glyph only for Ask IRIS | VIS-08 | Sidebar, toolbars |
| Help in the sidebar footer; "Discover", not "Home", in breadcrumbs | NAV-03, NAV-04 | Sidebar |
| Errors say what happened ("IRIS took too long to answer") and offer Try again | US-05, FB-02 | Recommended copy, in `audit-report.md` |
| Destructive actions in menus and confirm dialogs that name the target | CMP-01, US-06 | Users, My research, Settings |
| Empty states name the next action; no zero counters | LAY-06, US-13 | Calls, Saved papers, Role requests |
| No institution name in interface copy ("papers in IRIS", "institutional email"); the logo and sample data keep it | IR-768 (live) | Sign-in, sign-up, Discover, Ask IRIS, Settings |
| Publish only for Student and Adviser; readers' My Library has Saved papers and Download requests | Live `AUTHORS`, `READER_TABS` | Top bar, Discover, My Library |

**Not shown in the prototype.** These recommendations stay in the audit:
- Session-ended messaging after a reload (FB-01, needs reproducing first).
- The long-wait copy (FB-02).
- The Areas modal (US-02).
- The register stepper (US-08).

The prototype has no server, so it cannot honestly simulate slow responses.

**Still in live IRIS.** Two Ask IRIS strings name the institution, against IR-768: `AssistantMessageSkeleton.tsx` ("Searching the CIT-U repository…") and `ChatMessageList.tsx` ("Every answer is grounded in published CIT-U records"). Both should read from the institution config or say "IRIS".

---

## 17. Review workspace (reviewer view)

Inspected live on 13 Nov 2026 as an ITSO reviewer whose review was complete. Nothing was claimed, commented or cleared, and the tour was not started.

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original workspace, conversation](screenshots/original/B0-review-workspace-conversation-1440.jpg) | ![Prototype office workspace, Threads tab](screenshots/redesigned/RB1-office-threads-draft-1440.jpg) |
| ![Original workspace, threads](screenshots/original/B1-review-workspace-threads-1440.jpg) | ![Prototype adviser workspace](screenshots/redesigned/R81-adviser-review-your-turn-1440.jpg) |
| ![Original workspace, changes](screenshots/original/B2-review-workspace-changes-1440.jpg) | ![Prototype changes](screenshots/redesigned/RB2-review-changes-1440.jpg) |
| ![Original scroll gap](screenshots/original/B3-review-changes-page-scroll-gap-1440.jpg) | ![Prototype tour](screenshots/redesigned/RB3-review-tour-1440.jpg) |
| ![Original 1024, pane closed](screenshots/original/B4-review-workspace-1024-pane-closed.jpg) | ![Prototype 1024, Details tab](screenshots/redesigned/RB4-review-details-folded-1024.jpg) |
| ![Original 1024, pane open](screenshots/original/B5-review-workspace-1024-pane-open.jpg) | ![Prototype unclaimed review](screenshots/redesigned/R93-office-review-unclaimed-1440.jpg) |
| | ![Prototype student workspace](screenshots/redesigned/R22-record-review-student-1440.jpg) |
| | ![Prototype RDCO workspace, ready to publish](screenshots/redesigned/RB6-rdco-review-ready-1440.jpg) |
| | ![Prototype workspace at 390](screenshots/redesigned/R75-record-review-390-drawer.jpg) |
| | ![Prototype, Threads opened on the right beside Conversation](screenshots/redesigned/RB7-review-threads-on-right-1440.jpg) |

**What the live workspace gets right, and the prototype keeps**
- Paper and review pane side by side, so a reviewer reads and decides on one screen.
- The pane's **Conversation · Threads · Changes · Details** sections.
- Changes per section, each with a **Viewed** checkbox and a "Show in v1, p. 1" link back to the paper.
- The version picker, **Take a tour**, **Back to paper**, zoom, Download and commenting from the paper.

**Problems in the original**
- Scrolling the page leaves a blank band under the columns (LAY-07, `B3`).
- At 1024 px the open pane lies over the paper, which then scrolls sideways (RES-06, `B5`).
- "YOUR READINESS: This record is not in review." reads as a warning on a finished review, with a red side stripe (WF-07, VIS-09).
- Uppercase eyebrows: "REVIEW WORKSPACE / CURRENT RECORD", "YOUR READINESS", "RECORD CONTEXT", "TIMELINE" (VIS-02).
- Each reviewer's status is said twice (US-17).
- The version picker and title are cut off, and "Take a tour" and "Back to paper" wrap (US-18).

**Changes in the prototype**
- **Layout:**
  - The workspace fills the viewport under the record bar. Only the columns scroll, so the blank band cannot happen.
  - The left sidebar collapses to its icon rail while you are on Review, as it does on Paper in live IRIS (§5). The IRIS mark opens it again.
  - The column edges can be dragged, or moved with the arrow keys, and the widths are remembered.
  - It lays itself out by its own width: paper and pane side by side, then a drawer (§15).
- **Laid out like a GitHub pull request (13 Nov 2026).** The team likes the live workspace, which already works like GitHub's pull request page, so the prototype borrows GitHub's quieter details instead of adding new parts:
  - **Top of the pane:** where the paper is, in tone + word + icon, then who sent this version and when ("Sam Student submitted v1 · 6 Nov 2026"), like GitHub's "opened this pull request". One line under it says which clearances are kept. The row of clearance pills is gone from here; the sidebar and the box at the end of the timeline carry it.
  - **Tabs with counts:** Conversation (comments), Threads, Changes (sections changed) and Details, as GitHub shows Conversation 4 · Commits 3 · Files changed 6. **Changes is always there**, as in live IRIS; with one version it says "Only one version so far" and what will appear once version 2 arrives.
  - **No People & details column (frontend owner, 13 Nov).** The live third column repeated the Details tab, so it is gone. The workspace is two columns by default, and the pane gets the room (520 px).
  - **Open a tab beside (RB7).** A reviewer can open Conversation, Threads, Changes or Details in a right column, for example reading Threads while writing in Conversation. One quiet columns button at the end of the tab row opens a short menu ("Threads on the right"); right-clicking a tab opens the same menu for that tab. The column has its name and a close button, and the choice is remembered. It is offered only when the workspace is at least 1180 px wide, so the paper keeps room; narrower, the tab simply returns to the row. Tabs open on the right only: the paper stays fixed on the left because comments anchor to its passages.
    - *Why not a "⋯" on every tab:* four extra buttons in a row of four tabs is the clutter this pass removed. *Why not right-click alone:* nobody finds it. One visible button plus right-click plus a line in the tour covers both.
  - **The record bar shows only Overview and Review here.** The Paper tab is hidden on Review, because the paper is already open in the first column.
  - **Quieter controls (frontend owner, 13 Nov):** segmented controls are a flat grey track with a white selected segment and ink text; tab counts are neutral grey; secondary buttons stay grey-outlined on hover; fields focus with a plain maroon edge. No pink rings or highlighted borders.
  - **Timeline:** one rail with small icon badges for events (submitted, routed, cleared, asked for changes), and each comment in a box with a grey header: avatar, name, "commented 11 Nov 2026 · on v1" and a role label (Author, Adviser, IERC). Replies sit inside the box, with a "Reply to …" field at its foot. The first box is the submission itself, with the first lines of the abstract, as a pull request opens with its description.
  - **Clearance box** at the end of the timeline, like GitHub's merge box: one icon and one heading ("IERC asked for changes", "2 of 4 cleared", "Every office has cleared"), one line under it, and the offices folded under **Show all clearances**.
  - **Comment box:** your avatar, "Add a comment · the authors and every reviewer can read it", then Saved replies and Mention as icons and **Comment** on the right.
  - **Threads** use the same box: who and which office in the header, the page link on the right, then severity and state, the quoted passage and the comment.
  - Below 360 px of pane width the avatars drop and the boxes take the full width, as GitHub does on a phone.
- **Footer, "Your part",** shaped like GitHub's merge box: a status icon, one heading ("IERC asked for changes", "Your ITSO review is in progress", "Nobody has claimed this for ITSO"), one line under it, and one action that moves the paper on (**Finish review…**, **Claim review**, **Send version 2…**, or RDCO's **Accept & publish…**). Rarer actions sit under "⋯". A finished review shows its verdict there instead.
- **Threads (RB1):**
  - Filters **Open · Yours · Resolved · All**, with counts.
  - Each thread quotes its passage and page, and can be addressed, declined, resolved or reopened.
  - A new comment is a draft until **Finish review…** sends it with the decision.
  - **Saved replies** and **Mention** in the composer.
- **Changes (RB2):** the two versions on one row (v1 → v2), then the counts ("3 changed +29 −22") with **Inline | Side by side** on the same row; changed sections first, each with **Viewed**, and a count of how many you have viewed. Unchanged sections fold into "Show 8 unchanged sections".
- **Reader toolbar:** **Contents** (the paper's outline) and **Find** are added beside zoom, Fit, Comment and Download. Reading an older version shows "Reading v1 · not current".
- **Tour (RB3):** four steps (the paper, the review pane, its sections, your part). The sections step names each tab and points at the columns button. It is offered once and stays out of the way afterwards.
- **Details tab, like GitHub's sidebar:** small headed sections divided by rules.
  - **Reviewers:** each person's avatar and name, with their status on the right as an icon and a short word (Cleared, Kept, Reviewing, Changes asked, Unclaimed, Waiting), and their office and date under the name. An office nobody has claimed shows an empty avatar.
  - A **gear** beside Reviewers appears only for someone who can change it: an Adviser or RDCO can request a review, and an office reviewer can add a colleague.
  - Then Researcher(s), Adviser, Classification as labels, Version, Due dates, Documents and participants.
  - At the bottom, quiet links: **Copy link to this review**, and for the author while the paper is in review, **Withdraw paper…** (moved here from the footer's "⋯").

**Why.** The workspace is where clearance-aware resubmission actually happens. A reviewer should be able to read, comment, see what changed since the last version, and know their own part, without the page fighting them.

---

## 18. Colour and highlights

| ORIGINAL (live IRIS) | PROTOTYPE (redesign) |
|---|---|
| ![Original Discover](screenshots/original/10-discover-1440.jpg) | ![Prototype: matches in the highlighter, Filters on in an Ink outline](screenshots/redesigned/R13-discover-question-suggest-1440.jpg) |
| | ![Prototype: a reviewer's passage marks, the open one matching its thread](screenshots/redesigned/RB8-review-passage-marks-1440.jpg) |
| | ![Prototype: passage marks on a phone](screenshots/redesigned/RB9-review-passage-marks-390.jpg) |

**Problems found in the prototype's earlier pass** (which followed DESIGN.md):
- **Search matches were nearly invisible.** Maroon Wash on a white card is 1.10:1. Matches in the abstract also turned maroon, so they read as links.
- **One pale pink meant about fifteen things:** the current page, the current Settings tab, the open conversation, Filters when on, a chosen record type, the Active and Reviewing statuses, page citations, the scope chip, search matches, step numbers, comment badges, timeline badges, the large avatar and warnings. On one card, a match, a citation and a "Reviewing" status looked the same.
- **Two "selected" looks in one toolbar:** white raised segments beside a pink Filters chip.
- **Card hover differed:** a stone border and lift on results, a pink border on sources and related papers.
- **Off-palette colours:** a gold ring on every thumbnail, `#fbe4e4`, `#fcfcfb`, `#5a0c0f`.
- **No passage marks in the paper.** Live IRIS marks each commented passage (IR-875); the prototype's paper had none, so the review workspace's main highlight was missing.

**Changes.** Each kind of highlight now has one look, and no look has two meanings (full table in `design-system.md` §1, Highlight roles). In short:
- **Action:** maroon fill, one per row.
- **Here:** a stone fill with a maroon icon (sidebar, Settings tab, open conversation).
- **Selected:** white raised or an Ink outline, never maroon.
- **Reference:** maroon text on white (page citations, source numbers).
- **Match:** a yellow highlighter, for search and Find. It is the one hue nothing else uses, live IRIS already uses yellow for Find, and every browser does.
- **Pen:** a reviewer's mark in rose with a 2 px underline and a numbered pin. Open threads are filled; answered and resolved ones keep only the underline. Clicking a mark opens its thread, and the thread's quote turns the same rose. On a phone it opens the review pane on that thread.
- **Status:** white chips with the tone in the text and outline; only Attention is filled.

**This departs from DESIGN.md**, at the frontend owner's direction (13 Nov 2026): DESIGN.md's Four Inks Rule allows no yellow, and it makes Maroon Wash the "on" tint for every state above. If the team adopts this, DESIGN.md and live's `palette.test.ts` need changing first. That is a design decision for the team, not something this audit can settle.

**Captures. The HTML prototype is the source of truth, not the screenshots.** Taken after this change (current): R10–R13, R20–R24, R30, R40, R51, R54, R60–R62, R70, R80, R82, R90, R93, RB1, RB2, RB6–RB9, RD1 and RD3. The rest predate it and still show the pink current-page fill in the sidebar and pink selected chips; they were not re-taken, to save effort. Where an image and the prototype disagree, open the prototype at that route.
