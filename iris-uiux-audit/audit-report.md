# IRIS UI/UX audit report

**Scope.** The deployed IRIS at `https://iris-citu.duckdns.org/`, inspected on 12–13 Nov 2026 as a Student, an Adviser, an ITSO office coordinator and RDCO, at 1440, 1280, 768, 390 and 360 px. The record's Review workspace was inspected live on 13 Nov 2026 as an ITSO reviewer, at 1440 and 1024 px, without claiming, commenting or clearing anything (`B0`–`B5`). Frontend source in this repository was read to confirm routes, labels and the screens the audit browser could not load. See `page-inventory.md` for coverage and environment limits.

**Benchmarks.** Nielsen's 10 heuristics; WCAG 2.2 AA; and IRIS's own written rules in `DESIGN.md` and `PRODUCT.md` ("The Binding Rule", "The Named Size Rule", 44 px touch controls, "Say what is waiting on whom", "Show no counters where nothing is actionable"). Several findings are places where the shipped UI breaks the team's own design system rather than a taste call of mine.

**Priorities.** *Critical* blocks a task or fails WCAG level A on every page. *High* misleads users about state, risks a destructive mistake, or blocks phone use. *Medium* slows people down or breaks consistency in a visible way. *Low* is polish.

---

## 1. Executive summary

IRIS already has a real identity — the maroon binding, Garamond titles, calm stone surfaces — and several things are done well (see §11). The problems are not the palette. They are:

1. **The workflow does not always say what is waiting on whom.** A notification tells an ITSO coordinator a record is waiting while their queue shows zero; a Pending tab lists a Declined deletion; a draft in My Library has no "continue" action. For a product whose thesis is the workflow, these are the most important fixes.
2. **Accessibility basics are missing site-wide.** Every page is titled "IRIS"; field outlines are ~1.3:1 against white; phone controls are 34–38 px.
3. **Too many controls compete.** Discover's toolbar carries 11 controls in four heights and three filled maroon buttons; on a phone, four rows of controls push the first result 400 px down, and three of them collapse to unlabeled icons.
4. **The design system's own rules are broken in many small places** — uppercase tracked labels, Title Case labels, square vs pill buttons, two "selected" colours — which is why the app feels assembled rather than designed.
5. **Slow responses are blamed on the user.** Errors say "Check your connection" when the server was slow; loaders say "Loading Paper View…".

| Priority | Count |
|---|---|
| Critical | 2 |
| High | 9 |
| Medium | 31 |
| Low | 28 |

---

## 2. Nielsen heuristic scores (0 = absent, 4 = excellent)

| # | Heuristic | Score | Main evidence |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Good: status chips, autosave lines. Bad: stale ITSO notification (WF-01), 12–17 s waits with unlabeled loaders (FB-02), skeleton-only Download requests |
| 2 | Match with the real world | 2 | "Loading Paper View…", "New Record (Proposal / Thesis)", "Paper Chat" in Help vs "Ask IRIS" in UI, three different dates on a record |
| 3 | User control and freedom | 3 | Dialogs close on Escape, drawer returns focus; Back is always present on records. Delete sits beside Continue with equal weight |
| 4 | Consistency and standards | 1 | Four control heights in one toolbar, Title Case vs sentence case, uppercase eyebrows, pill vs square buttons, maroon vs black "selected" |
| 5 | Error prevention | 2 | Lock buttons filled on every user row including your own; Pending tab shows Declined; password placeholder looks like a saved password |
| 6 | Recognition rather than recall | 2 | Icon-only Publish/Areas/Filters on phones; Office console and Analytics only reachable from links inside My Reviews; Help only inside the account menu |
| 7 | Flexibility and efficiency | 2 | No keyboard search shortcut, filters hidden in a popover with unlabeled selects, ~1.5 results per screen on desktop |
| 8 | Aesthetic and minimalist design | 2 | Discover card spends half its area on a grey preview placeholder; Calls page shows six "0" counters; Analytics leads every table with a paragraph |
| 9 | Help users recover from errors | 3 | Route error screen with Try again, Reload and copyable details is excellent; but list errors say "Check your connection" for server faults |
| 10 | Help and documentation | 3 | Help page is clear and honest; hidden behind the account menu; contents grid reads in the wrong order |

**Total: 22 / 40.** A solid base with fixable, specific problems.

---

## 3. Workflow and system status (thesis-critical)

### WF-01 · Notification contradicts the review queue — **High**
- **Where:** ITSO coordinator, `/notifications` and `/review` (`90`, `91`).
- **Current:** Unread notification: *"RDCO Final sent 'Activity Preference…' to your office for review: please check It is in your office's pool until someone claims it."* My Reviews shows **To review 0**, and the record sits under **Done 1**.
- **Problem:** The notification is never resolved when the work is done, so it keeps asking for action that is no longer possible. The copy also has a sentence-joining error ("please check It is").
- **Impact:** Coordinators lose trust in the queue; on a busy week they cannot tell which notifications still need them. Directly undermines PRODUCT principle 1, "Say what is waiting on whom".
- **Recommendation:** Show a resolved state on notifications whose task is closed ("Cleared by ITSO · no action needed"), drop them from the unread count, and fix the template to two sentences: "RDCO sent *Title* to ITSO. It waits in ITSO's pool until a reviewer claims it."

### WF-02 · Delete Requests "Pending" tab lists a Declined request — **High**
- **Where:** RDCO, `/rdco/delete-requests` (`A5`).
- **Current:** With **Pending** selected, the table shows *Predicting Student Absenteeism · Declined*, and the **Action** column shows a date instead of an action.
- **Problem:** The filter and the row disagree on a permanent-deletion queue.
- **Impact:** An approver cannot trust what is actionable; a mismatched list is how a wrong record gets approved.
- **Recommendation:** Pending shows only requests awaiting a decision; decided rows move to Approved/All. Rename the last column "Decided" when it holds a date, or show Approve/Decline only on pending rows.

### WF-03 · A draft has no next step on My Library's Overview — **Medium**
- **Where:** `/records/mine` Overview (`30`).
- **Current:** "Draft: not yet submitted" with a chevron. Continue/Delete appear only on the My submissions tab (`31`).
- **Impact:** The one thing a student needs to do next is one tab away. **Recommendation:** Put "Continue draft" on the Overview row; state the next step in words ("Finish the details and upload your manuscript").

### WF-04 · Titles carry the uploaded file name — **Medium**
- **Where:** My Library (`30`, `31`): *"Quantitative Forecasting of Land Suitability in Metro Cebu.docx"*.
- **Impact:** The extension leaks into the record title and later into citations. **Recommendation:** Strip the extension when the Publish dialog pre-fills the title from the file name, and flag it in the Details step for confirmation.

### WF-05 · Review vocabulary mixes "Accepted" for Theses — **Low**
- **Where:** Adviser My Reviews → Done (`81`). Every Thesis reads **Accepted**, though `PRODUCT.md` fixes *Accepted* as "a Proposal its Adviser accepted".
- **Recommendation:** Confirm with the server-side label owner; the UI must keep rendering the server's words (`workflow_state_label`), so this is a vocabulary fix on the server, recorded in the relevant ADR.

### WF-06 · Clearance-aware resubmission is invisible outside the record — **Medium**
- **Where:** My Reviews rows, notifications, record page.
- **Current:** The tracker's best labels ("Cleared on v1, preserved", "Reset by v2", found in `ReviewRoutingTracker.tsx`) only appear deep in the Review tab. Queue rows show only "Adviser · You · Accepted".
- **Impact:** The thesis contribution is the least visible thing in the product. **Recommendation:** Show a compact per-office clearance strip (Adviser ✓ · ITSO ✓ kept · IERC ↺ revising) on queue rows and on the author's My Library row. Prototype: *My Reviews* and *Record → Review*.

### WF-07 · The review workspace's readiness card reads as a warning on a finished review — **Medium**
- **Where:** Record → Review, signed in as an ITSO reviewer whose review is complete (`B0`).
- **Current:** A card headed "YOUR READINESS", with a red side stripe and an info icon, says "This record is not in review." and offers "View why →". The footer of the same pane says "Your review: Cleared", and the side column shows ITSO as "Completed · Cleared".
- **Problem:** The card states a system fact in warning dress. It does not say what happens next or who is waiting, so the reviewer has to reconcile three places to learn that their part is done.
- **Impact:** "Say what is waiting on whom" (PRODUCT.md) fails on the screen built for the review.
- **Recommendation:** Replace the card with one line in the pane footer that names the reader's part and the next party, for example "Your part is done: ITSO cleared v1. RDCO publishes last." Prototype: *Record → Review*, footer.

---

## 4. Navigation and information architecture

### NAV-01 · Every page is titled "IRIS" — **Critical** (WCAG 2.4.2, level A)
- **Where:** All routes (`document.title` checked on `/login`, `/signup`, `/`, `/records/1`, `/records/mine`, `/settings`, `/help`, `/notices`).
- **Impact:** Screen-reader users hear "IRIS" on every navigation; everyone with several tabs open sees identical tabs; browser history is unreadable.
- **Recommendation:** "Discover · IRIS", "Predicting Student Absenteeism · IRIS", "My Reviews (2) · IRIS". The route table already has `handle.crumb` for every page — set the title from it.

### NAV-02 · Office console and Workflow analytics are hidden — **Medium**
- **Where:** ITSO/RDCO `/review` (`91`, `A0`). They exist only as links at the top right of My Reviews. On those pages no sidebar item is active and the breadcrumb reads "Home / Office console", skipping My Reviews.
- **Recommendation:** Nest them under My Reviews in the sidebar (My Reviews › Queue, Office console, Analytics) for the roles that have them, and keep the parent active.

### NAV-03 · "Home" vs "Discover" — **Low**
- Breadcrumbs start with **Home**, the sidebar calls the same page **Discover** (`30`, `50`, `53`). Use "Discover" in both.

### NAV-04 · Help lives only in the account menu — **Medium**
- `52`. New users do not look for help under their own name. Put Help in the sidebar footer, next to the account button.

### NAV-05 · Discover has no breadcrumb or page header pattern the other pages use — **Low**
- Discover puts a search bar above the page title; every other page uses breadcrumb → title → description. Pick one page-header pattern; the prototype keeps search inside Discover's header.

### NAV-06 · Sidebar persists at tablet width — **Medium**
- At 768 px the 200 px sidebar stays open and the toolbar wraps to three rows (`70`). Collapse to the icon rail (which already exists for the Paper view) with tooltips below 1024 px.

### NAV-07 · The collapsed icon rail has no labels — **Medium**
- Paper view (`25`): Discover, Ask IRIS, My Library and Calls become bare icons. Add tooltips on hover/focus and `aria-label`s visible to sighted keyboard users.

### NAV-08 · Settings tabs are not addressable — **Low**
- `/settings` stays `/settings` for all three tabs (`54`–`56`). Use `?tab=privacy` like My Library and My Reviews already do.

---

## 5. Visual design

### VIS-01 · Three filled maroon controls in Discover's toolbar — **Medium**
- `10`: **Papers**, **Latest** and **+ Publish** are all solid maroon, breaking DESIGN.md's Binding Rule ("one filled maroon action per row").
- **Recommendation:** Selected segments use Maroon Wash with maroon text; only Publish is filled.

### VIS-02 · Uppercase tracked labels everywhere — **Medium**
- "AT A GLANCE", "FROM THE ABSTRACT" (`10`), "INSTITUTIONAL GOVERNANCE", "DOCUMENTS" (`20`), "NOTIFICATIONS" (`51`), "ASK IRIS" (`40`), "CONTENTS" (`57`), "SIGN-IN EMAIL", "CHANGE PASSWORD" (`54`), "STUDENT" (`56`), "RDCO" sidebar group (`A0`), "REVIEW WORKSPACE / CURRENT RECORD", "YOUR READINESS", "RECORD CONTEXT", "TIMELINE" (`B0`). DESIGN.md: "labels are sentence case, never small tracked capitals".
- **Recommendation:** Sentence-case 12–13 px semibold labels; delete eyebrows that sit above a heading (the heading already says it).

### VIS-03 · Title Case and sentence case mixed — **Low**
- "Email Address", "Sign In", "Create an Account", "First Name" vs "Institutional email", "Sign in" (`01`, `02`); "Workflow Analytics" page vs "Workflow analytics" link (`93`); "Upload Spreadsheet", "Import Log" (`A1`). Use sentence case throughout.

### VIS-04 · Two shapes for the same button — **Medium**
- Pills on most pages; Settings' **CHANGE PASSWORD** is a rounded rectangle in caps (`54`); Users' **Lock** is a small square-cornered filled button (`A2`). One button component, one radius (pill), sentence case.

### VIS-05 · Two colours for "selected" — **Low**
- My Reviews: **To review** selected is maroon, **All of ITSO** selected is solid black (`91`). Choose one selected style (Maroon Wash) for all segmented controls.

### VIS-06 · Heading sizes invert inside the AI Overview — **Medium**
- `21`: the subheads *Objectives*, *Methodology* (~24 px) are larger than the section heads *Abstract*, *AI Overview* (20 px). Readers lose the outline. Section heads 22 px; Markdown subheads inside the AI Overview 17 px Garamond.

### VIS-07 · Status chips are heavy — **Low**
- "Published", "Active", "Accepted" use solid ink pills (`20`, `A2`, `81`) that out-shout titles. Reserve solid fills for *attention*; use outlined/tinted chips with an icon for settled states.

### VIS-08 · Icons are mixed in weight and meaning — **Low**
- Filled sidebar icons beside stroked toolbar icons; the Ask IRIS nav icon is a brain-like glyph while the Ask IRIS mark elsewhere is the speech bubble (`10`, `24`); "Cite" uses a quote mark, "Notes" a filled square. Use one stroked set (1.75 px, 20 px) and the brand glyph only for Ask IRIS.

### VIS-09 · A coloured side stripe carries the readiness card's state — **Low**
- `B0`: apart from its words, the readiness card's only state signal is a red left border. Status in IRIS is tone + word + icon; a stripe is decoration that reads as an alert.
- **Recommendation:** Drop the stripe and show the state as a status chip.

---

## 6. Layout and spacing

### LAY-01 · Discover cards show ~1.5 results per screen — **Medium**
- `10`: each card is ~380 px tall at 1440; half is a grey first-page preview that reads "Preparing first page…" while it loads, plus an "AT A GLANCE" block repeating the abstract.
- **Recommendation:** A list row: type · year, Garamond title, authors, two-line abstract, then views/save/cite on one line, with a 96 px first-page thumbnail at the right that shows a neutral page outline (not a text placeholder) while it renders. 4–5 results per screen.

### LAY-02 · Four toolbar control heights — **Medium**
- `10`: 34 px (Papers/People), 38 px (For you/Latest/Trending), 44 px (Areas, My feeds, layout, Filters, Publish). DESIGN.md: 36 px beside a pointer, 44 px on touch. One height per input mode.

### LAY-03 · The record's metadata block — **Medium**
- `20`: author chips wrap one per line ("Ana Adviser" alone on the second row) and four dates appear: *Added Nov 11, 2026*, *Published 2025*, *Completed 2026*, and *Year Accomplished 2026* in Record details.
- **Recommendation:** One byline line ("Hermoine Joyce Zozobrado and Ashlee Sean Abac · Adviser Ana Adviser"), one date line ("Completed 2026 · added to IRIS 11 Nov 2026"); Record details keeps governance fields only.

### LAY-04 · Ask IRIS answers run ~110 characters a line — **Medium**
- `42`: at 1440 the answer column is ~900 px. Cap the answer at 68ch and centre the thread; keep the composer at the same width.

### LAY-05 · Workflow analytics leads with paragraphs, numbers left-aligned — **Medium**
- `93`: every table is preceded by 3–4 lines of methodology; columns of numbers are left-aligned in proportional figures. Put methodology in a "How these are counted" disclosure; right-align numbers with `font-variant-numeric: tabular-nums`.

### LAY-06 · Empty pages leave the content floating — **Low**
- Role Requests, Calls, Saved papers (`A3`, `50`, `32`): one card centred in a sea of endpaper. Acceptable, but pair the empty state with the next useful action (e.g. "Browse Discover" on Saved papers).

### LAY-07 · The review workspace leaves a blank band when the page scrolls — **Medium**
- **Where:** Record → Review at 1440 (`B3`).
- **Current:** The workspace's columns scroll inside a fixed height, but the page around them scrolls as well. Scrolled to the end, the columns stop about two thirds of the way down and an empty band fills the rest of the screen, with only the sidebar beside it.
- **Impact:** It looks broken, and a reviewer reading Changes loses the paper and the pane at the same moment.
- **Recommendation:** Size the workspace to the viewport under the record bar, so that only the columns scroll and the page never does. Prototype: the workspace is a fixed-height grid with columns that scroll and resize independently.

---

## 7. Usability and microcopy

### US-01 · Search placeholder reads like an Ask IRIS question — **Medium**
- Discover's search cycles questions ("What research explores flood resilience in Cebu?", `10`) but runs a keyword search. Users will type questions and get keyword matches. Placeholder: "Search titles, authors, keywords"; add a secondary "Ask IRIS instead" link carrying the query.

### US-02 · Areas modal is a dead end — **Medium**
- `12`: both lists say "No Areas available." yet the modal offers **Save Areas**, **Clear Areas** and **Reset my interests**. Hide the Areas control until areas exist, or say why there are none and disable Save.

### US-03 · Filters use selects without labels; Sort hides inside Filters — **Medium**
- `11`: the six selects show only placeholder text ("Type", "College") and lose it once chosen. Sort is not a filter. Visible labels above each select; Sort as its own control in the result header.

### US-04 · People section appears inside Papers search, and its failure has no retry — **Medium**
- `15`–`17`: while on **Papers**, a "People — Searching people…" block appears above results, then "People could not be loaded." with no way to retry. Keep People results in the People tab (show a one-line "3 people match — show" link), and give every failure a Try again.

### US-05 · Errors blame the user's connection — **High**
- `16`, `92`: "We couldn't load research. Check your connection, then try again." appeared after a slow server response, and the Office console says the same. The user cannot fix the server.
- **Recommendation:** "IRIS took too long to answer. Try again — if it keeps happening, the server may be busy." Reserve "check your connection" for `navigator.onLine === false`.

### US-06 · Delete has the same weight as Continue — **Medium**
- `31`: two equal outlined pills. Continue filled (it is the next step); Delete as a ghost button with the trash icon, behind a confirm dialog that names the record.

### US-07 · Password placeholder looks like a saved password — **Medium**
- `01`: the empty password field shows "••••••••" as placeholder text. Users think the browser filled it, press Sign In, and fail. Remove the placeholder. *(Amended 2026-11-13: an earlier draft also asked for a `yourname@cit.edu` email placeholder. That is withdrawn. IRIS is not for CIT-U only, and live IR-768 keeps the institution's name in `config/institution.ts`, out of the copy. The email field needs a clear label, not a domain.)*

### US-08 · Register repeats its own stepper — **Low**
- `02`: index tabs say "1 Identity · 2 Affiliation · 3 Security & agreement", and the sheet repeats "Step 1 of 3 · Identity". Keep the tabs.

### US-09 · Internal names in loading copy — **Low**
- "Loading Paper View…" (`82`), "Loading Download Requests…" (`A4`). Say what is loading in user terms: "Opening the paper…", "Loading download requests…".

### US-10 · Notification type labels are system names — **Low**
- "New Record (Proposal / Thesis)", "Record Routed", "New Version Submitted" (`85`). Use plain verbs and sentence case, or drop the tag (the sentence already says it).

### US-11 · Settings copy error — **Low**
- `55`: "Your answer covers the papers you're Contact person of." → "Your answer covers every paper you are the contact person for."

### US-12 · Help says "Paper Chat", the UI says "Ask IRIS" — **Low**
- `57`. Use the UI's name, or label the record panel "Ask IRIS about this paper" and say so in Help.

### US-13 · Calls & Conferences shows six zero counters — **Low**
- `50`: All 0, Internal call 0, Conference deadline 0, Funding window 0, Institutional grant 0, Saved 0, plus "0 open calls." PRODUCT principle 3: no counters where nothing is actionable. Hide the type filters until there is at least one call.

### US-14 · Import Records instructions — **Low**
- `A1`: "Follow the data entry format -- download template here." Make the template a real button ("Download the template (.xlsx)"), drop the double hyphen, and hide the empty Import Log until there is a log.

### US-15 · Ask IRIS sources show raw chunk text — **Medium**
- `43`: source rows contain Markdown debris ("**", "* ++Small sample size:**") and truncate mid-sentence. Strip Markdown, show section heading + page + a clean snippet, and make each row open the paper at that page.

### US-16 · Empty Ask IRIS has no starters — **Low**
- `40`, `24`: "What would you like to investigate?" with an empty composer. DESIGN.md specifies three starter questions (`StarterQuestions`); they are not visible on the deployed build.

### US-17 · Each reviewer's status is said twice — **Low**
- `B0`: the side column shows "ITSO ✓ Completed · Cleared" and then "✓ Cleared" again beside the reviewer's name. The Adviser row says "Completed · Approved" and then "Approved".
- **Recommendation:** One status per party, beside the party, with the person's name under it.

### US-18 · The version picker and title are cut off in the record bar — **Low**
- `B0`, `B5`: the version select reads "v2 · Revi…", and at 1024 the title is cut to "Activity Preference and Level of Physica…". "Take a tour" and "Back to paper" wrap onto two lines each.
- **Recommendation:** A short version label ("v2 · 13 Nov"), the full title in the page title and a tooltip, and a compact record bar below 1280 px.

---

## 8. Interaction and components

### CMP-01 · Destructive Lock button on every user row — **High**
- `A2`: a filled dark-maroon **Lock** button on every row of Users, including the signed-in RDCO's own account (Rita Cruz). The most visually prominent element on the page is the most destructive one.
- **Recommendation:** Row actions in a "⋯" menu (Change role, Lock account…), confirm dialog naming the person, and no Lock on your own row. Name first, then email.

### CMP-02 · Two floating buttons over reading content — **High** (phone) / Medium (desktop)
- `20`, `75`: a **Notes** button (44 px, icon only) floats above the **Ask IRIS** button. On a 390 px phone both cover the AI Overview text. DESIGN.md: "Don't float controls over content… Ask IRIS is the one corner icon."
- **Decision, 13 Nov 2026:** the frontend owner keeps both buttons as they are today: Notes is easy to find just above Ask IRIS, and the two open the same side panel.
- **Recommendation:** Keep the pair, and reserve bottom padding on Overview and Paper so the last lines can always scroll clear of them. DESIGN.md's line "Ask IRIS is the one corner icon" then needs to name Notes as the second, so the rule and the product agree.

### CMP-03 · Double focus ring on search — **Low**
- `15`: the field's container and the inner input both draw a maroon outline. One ring on the container (`:focus-within`).

### CMP-04 · Layout toggle is an unlabeled square — **Low**
- `10`: the "1 column; switch to 2" control is a bare square icon. Use a two-state segmented "List | Grid" with icons and visible tooltips, or drop it (one good list layout).

### CMP-05 · Disabled buttons are illegible — **Low**
- Continue (Publish), Generate (Import), Publish version 2 (Notices) at 50 % opacity ≈ 3:1 white-on-pink (`60`, `A1`, `A6`). Disabled controls are exempt from WCAG contrast, but users must still read them. Use Desk Stone fill with Faint Ink text, plus a reason line ("Choose what you're publishing first").

### CMP-06 · Paper toolbar mixes a request state with zoom — **Low**
- `25`: "Request pending · Cancel request" sits in the zoom toolbar. Move download-request state to the record bar's action area.

---

## 9. Responsiveness

| Width | Result |
|---|---|
| 1440 / 1280 | No overflow. Discover shows ~1.5 results; Ask IRIS lines too long (LAY-01, LAY-04) |
| 768 | Sidebar stays expanded; Discover toolbar wraps to 3 rows; no overflow (NAV-06) |
| 390 / 360 | **No horizontal scroll anywhere checked** ✓. Problems below |

### RES-01 · Phone Discover: four rows of controls, three icon-only — **High**
- `71`, `73`: search, title, Papers/People, For you/Latest/Trending + Areas (icon) + My feeds, then Filters (icon) + Publish (a bare "+"). The first result starts ~400 px down; Publish, Areas and Filters lose their names.
- **Recommendation:** Search, then one horizontally scrollable chip row (Latest · For you · Trending · Filters (n)), Papers/People in the page header, and Publish as a labelled button in the top bar ("Publish").

### RES-02 · Touch targets below 44 px — **Medium**
- Measured at 360: Notifications 34×34, Papers/People 76×34, sidebar links 215×38, For you/Latest/Trending 38 tall, Close menu 36×36. They pass WCAG 2.5.8's 24 px minimum but fail the project's own 44 px touch rule.

### RES-03 · Phone record chrome takes a fifth of the screen — **Medium**
- `74`: top bar (57 px) + Back row + full-width Overview/Paper segmented control ≈ 180 px before the title. Merge Back and the section control into one 56 px record bar.

### RES-04 · Phone top bar has no brand — **Low**
- `71`: hamburger and bell only. Add the IRIS mark (links to Discover).

### RES-05 · CIT-U logo illegible on phones — **Low**
- `04`, `05`: the CIT-U wordmark is ~10 px tall at 360–390. Show the seal only below 480 px.

### RES-06 · At 1024 px the review pane covers the paper — **Medium**
- `B4`, `B5`: with the pane closed the paper fills the space. Opened, the pane lies over the right half of the paper, which keeps its zoom and gains a horizontal scrollbar, so the page cannot be read beside the pane.
- **Recommendation:** Lay the workspace out by its own width. Where it is narrower than about 1100 px, fold the side column into a Details tab and keep paper and pane side by side. Below about 740 px, open the pane as a drawer with "Back to paper". Prototype: `RB4`, `R71`, `R75`.

---

## 10. Accessibility (WCAG 2.2 AA)

| ID | Criterion | Finding | Priority |
|---|---|---|---|
| NAV-01 | 2.4.2 Page Titled (A) | Every page titled "IRIS" | **Critical** |
| A11Y-01 | 1.4.11 Non-text Contrast (AA) | Field outlines `#e7e5e4` on white ≈ **1.25:1** (Notices textarea, measured); Rule Stone `#d6d3d1` ≈ **1.49:1**. Users with low vision cannot find the fields. Use `#a8a29e`-or-darker outlines (≥3:1: `#8a8380` = 3.6:1) | **Critical** |
| A11Y-02 | 1.4.3 Contrast (AA) | Disabled-dropzone helper and some placeholder text use stone-400 `#a8a29e` = **2.5:1** on white (`60`). Placeholders must be ≥4.5:1 if they carry information | High |
| A11Y-03 | 1.3.1 Info and Relationships | Filter selects have no visible label (US-03); Help contents grid is row-ordered in DOM but read as two columns visually, so reading order differs from visual order (`57`) | Medium |
| A11Y-04 | 2.5.8 Target Size (AA) | Passes (smallest 34 px) — but see RES-02 for the project's 44 px rule | — |
| A11Y-05 | 2.4.7 Focus Visible | **Passes**: 1.6 px maroon outline with offset on every control tested (`26`) | ✓ |
| A11Y-06 | 3.3.1 Error Identification | **Passes**: register validation shows text errors and moves focus to the first (`03`) | ✓ |
| A11Y-07 | 1.4.1 Use of Colour | Unread notifications marked by a 6 px maroon dot (with hidden "Unread:" text) — sighted users with colour-vision deficiency get only a small dot. Add weight change to the unread row | Low |
| A11Y-08 | 2.4.6 Headings and Labels | Sign-in's visible headline "Your research has a place." is not a heading; the h1 is the logo. Make the headline the h1 | Low |
| A11Y-10 | 1.4.3 Contrast (AA) | Faint Ink `#78716c` passes on white (4.8:1) and Endpaper (4.59:1) but **fails on Bar Stone `#f5f5f4` (4.40:1)** and Desk Stone (3.82:1), where the record bar, reader toolbar and Ask IRIS header put metadata. Use Quiet Ink `#57534e` on any stone surface | Medium |
| A11Y-09 | 1.4.4 Resize Text | Discover's segmented text drops to 12 px at 360 (`73`); with 200 % zoom the toolbar wraps to five rows | Medium |

---

## 11. What already works (keep it)

- **Identity.** Maroon + Garamond + stone reads as a university press, not a SaaS template. Keep every brand token.
- **Focus ring and keyboard.** Visible maroon focus everywhere; Escape closes the mobile drawer and returns focus to the hamburger.
- **Form validation.** Inline, specific, focus moves to the first error.
- **Route error screen.** "Something went wrong · Nothing you saved has been lost", Try again, a second-failure state offering Reload, and copyable details for RDCO (`83`, `84`) — better than most production apps.
- **Honest copy.** "Saved calls are kept in this browser only", "Figures start on Nov 13… not counted as zero". Keep this voice; just shorten it.
- **No horizontal overflow** at 360 on any screen checked.
- **The entry frame.** The folder-tab metaphor is distinctive and works on phones.
- **Cite dialog.** Clear formats, one filled Copy action.

---

## 12. Finding index

| ID | Title | Priority |
|---|---|---|
| NAV-01 | Every page titled "IRIS" | Critical |
| A11Y-01 | Field outlines ~1.3:1 | Critical |
| WF-01 | Notification contradicts queue | High |
| WF-02 | Pending tab lists Declined deletion | High |
| US-05 | Errors blame user's connection | High |
| CMP-01 | Lock button on every user row | High |
| CMP-02 | Two floating buttons cover text | High |
| RES-01 | Phone Discover control stack | High |
| A11Y-02 | Placeholder/helper 2.5:1 | High |
| FB-01 | Reload ended on sign-in without explanation (needs confirmation) | High |
| FB-02 | 12–17 s waits with unlabeled loaders | High |
| WF-03, WF-04, WF-06 | Draft next step, .docx titles, clearance visibility | Medium |
| NAV-02, NAV-04, NAV-06, NAV-07 | Hidden console, hidden Help, tablet sidebar, unlabeled rail | Medium |
| VIS-01, VIS-02, VIS-04, VIS-06 | Three maroon fills, uppercase labels, button shapes, heading inversion | Medium |
| LAY-01 … LAY-05 | Card density, control heights, record metadata, line length, analytics | Medium |
| US-01 … US-04, US-06, US-07, US-15 | Search placeholder, Areas, filters, People, Delete weight, password placeholder, sources | Medium |
| RES-02, RES-03, A11Y-03, A11Y-09 | Touch targets, phone chrome, reading order, small text | Medium |
| WF-07, LAY-07, RES-06 | Review workspace: readiness card, page scroll gap, pane over the paper at 1024 | Medium |
| remaining | see sections above | Low |

### FB-01 · Reload ended on the sign-in page — **High, needs confirmation**
- `06`, `07`: a reload of `/records/mine` showed only the animated mark for ~17 s, then the sign-in page, with no message. After signing in, IRIS returned to `/records/mine` (good). Blocked requests in the audit browser may have contributed; reproduce on a normal browser. Either way, a session that ends should say so: "Your session ended. Sign in to continue where you were."

### FB-02 · Long waits with no words — **High**
- The full-page loader is an animated mark with no text (`06`); Download requests is a skeleton with no label for 7 s+ (`33`); search showed skeletons for 12 s before failing (`15`). After ~2 s add a line ("Still loading — IRIS is slow to answer right now"); after ~10 s offer Try again.
