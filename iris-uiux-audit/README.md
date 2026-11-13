# IRIS UI/UX audit and redesign prototype

An independent audit of the deployed IRIS (`https://iris-citu.duckdns.org/`), with a working HTML/CSS/JS prototype of the proposed redesign.

**Nothing here touches the production application.** The audit read the live site and the frontend source. The prototype is a separate static page with invented sample data and no server.

## What is in this folder

| File | What it holds |
|---|---|
| `audit-report.md` | 70 findings (2 Critical, 9 High, 31 Medium, 28 Low), each with where, current behaviour, problem, impact and recommendation. Also Nielsen heuristic scores, a WCAG 2.2 AA table and what already works |
| `page-inventory.md` | Every screen inspected, by role and width, with its screenshot id, plus the screens that could not be reached and why |
| `design-system.md` | The proposed system: colour tokens with hex values and contrast, type scale, spacing, radii, shadows, buttons, inputs, cards, tables, dialogs, navigation, status tones, icons and breakpoints |
| `redesign-recommendations.md` | Before and after for 16 screens and the review workspace: **original** screenshot, problems, **prototype** screenshot, changes, reasoning |
| `implementation-roadmap.md` | Findings ordered into Jira-sized slices, with the frontend files each slice touches |
| `screenshots/original/` | 68 captures of the **live IRIS** (ids `01`–`A6`, and `B0`–`B5` for the review workspace) |
| `screenshots/redesigned/` | 59 captures of the **prototype** (ids start with `R`) |
| `prototype/` | `index.html`, `styles.css`, `script.js`, `assets/` (IRIS mark, wordmark, Ask IRIS glyph, favicon, CIT-U logo) |

Original and prototype screenshots never share a folder, and prototype file names always start with `R`.

**The screenshots are not in git.** The repository ignores every `screenshots/` folder (`.gitignore`: local design captures are not part of the repo), so on GitHub the images in these notes don't render. They exist only on the machine that took them. **The prototype is the reference:** open it at the route a note names. Some prototype captures also predate the colour change (`redesign-recommendations.md` §18).

## How the audit was done

- **When and how.** On 12–13 Nov 2026, in a browser on the live site. One reviewer had the Student, Adviser, ITSO coordinator and RDCO accounts, and signed in to each themself. Pages were inspected at 1440, 1280, 768, 390 and 360 px by resizing the viewport. No action that changes a record was taken. The review workspace was added on 13 Nov, signed in as an ITSO reviewer, at 1440 and 1024 px.
- **Source code.** The frontend source on `main` (commit `957b2783`) was read to confirm routes, labels and states the live data could not show.
- **Benchmarks.** Nielsen's 10 heuristics; WCAG 2.2 AA; and IRIS's own `PRODUCT.md` and `DESIGN.md`. Many findings are places where the shipped UI breaks the team's own written rules.

**Pages inspected**
- **Entry:** sign-in, register (with validation).
- **Discover:** search, filters, the Areas modal, My feeds, People, the loading and error states.
- **Record:** overview, AI Overview, Cite, Notes, the Ask IRIS panel and the paper reader.
- **My Library:** all four tabs.
- **Ask IRIS:** new conversation, the depth menu, an answer and its sources.
- **Account and help:** Calls & Conferences, notifications (popover and page), the account menu, Profile, all three Settings tabs, Help.
- **Review roles:**
  - Adviser: My Reviews and its route error screen.
  - ITSO: My Reviews, the office console, workflow analytics and a record's Review workspace.
  - RDCO: Import records, Users, Role requests, Download requests, Delete requests, Notices.
- **Responsive:** phone and tablet versions of Discover, the drawer and the record.

`page-inventory.md` lists each page with its screenshot and the few screens that could not be reached.

## Major findings

1. **The workflow does not always say what is waiting on whom.**
   - An ITSO notification says a paper is waiting while the queue shows zero (WF-01).
   - A Pending tab lists a Declined deletion (WF-02).
   - A draft on My Library's overview has no "continue" (WF-03).
   - Clearance-aware resubmission, the thesis contribution, is visible only deep in a record's Review tab (WF-06).
2. **Accessibility basics fail on every page.**
   - Every page is titled "IRIS" (NAV-01, WCAG level A).
   - Field outlines are about 1.3:1 against white (A11Y-01).
   - Some helper text is 2.5:1 (A11Y-02).
3. **Too many controls compete.**
   - Discover's toolbar has 11 controls in four heights, three of them filled maroon (VIS-01, LAY-02).
   - On phones, four rows of controls push the first result about 400 px down and lose their labels (RES-01).
4. **Destructive actions are the loudest thing on screen.** A filled Lock button sits on every user row, including your own (CMP-01).
5. **The design system's own rules are broken in small ways.** Uppercase eyebrows, Title Case labels, two button shapes and two "selected" colours make the app feel assembled rather than designed (VIS-02 to VIS-05).
6. **Slow responses are blamed on the user.** Errors say "Check your connection" when the server was slow (US-05), and long waits show loaders with no words (FB-02).

**What already works and is kept:**
- The maroon-and-Garamond identity, the folder-tab sign-in and the visible focus ring.
- Inline form validation, the route error screen, and the honest copy.
- No horizontal overflow at 360 px.

## Design decisions

- **Refine, don't rebrand.** Every brand token stays:
  - Maroon `#6B0F12`, EB Garamond titles, Inter body, stone surfaces.
  - Gold is decoration only.
  - Two tokens are added, the `field` outline `#8f8884` and a `control` 14/20 type step. Both need a line in `DESIGN.md` if adopted.
- **One filled maroon action per row.** Each kind of highlight has one look (recommendations §18): stone for where you are, Ink for what you selected, maroon text for references, a yellow highlighter for matched words and a rose pen for reviewers' marks. This departs from DESIGN.md, at the frontend owner's direction.
- **Status is tone + word + icon, never a new hue.** For example "Cleared" with a check, "Cleared on v1 · kept" with a shield, "Reviewing v2" with an eye, and "Overdue by 1 day" with an alert mark.
- **Make the workflow visible.** A clearance strip on queue rows, My Library rows and the Review tab. "What happens next" text on every record a person is waiting on. Notifications resolve when their task closes.
- **Fewer, clearer controls.** One control height per input mode (36 px with a pointer, 44 px on touch). Labelled filters. Sort beside the result count. Destructive actions in menus and confirm dialogs that name the target.
- **Three layouts:** a 248 px sidebar at 1024 px and up, which the IRIS mark collapses to the icon rail (remembered; the Paper tab collapses it for that visit, as in live IRIS, and so does Review in the prototype); a 76 px icon rail with tooltips from 768 to 1023 px; a top bar and drawer below 768 px. Ask IRIS is the corner button; on a record, Notes sits just above it, as in IRIS today.
- **Honest copy.** It says what is loading, never blames the connection for a server fault, and puts no counters where nothing is actionable.

## Run the prototype

The prototype is plain HTML, CSS and JavaScript. It needs no build step, no install and no server-side code.

**Option 1: a static server (recommended)**

Hash routing and the fonts behave exactly as designed this way. From the repository root:

```bash
python -m http.server 5178 --directory iris-uiux-audit
```

Then open `http://localhost:5178/prototype/`. Opening it from the root rather than from `prototype/` keeps the "Before and after notes" link working.

**Option 2: open the file directly.** Double-click `prototype/index.html`. Everything works except that the browser may block the Markdown link in the prototype bar. Fonts load from Google Fonts when online and fall back to system serif and sans offline.

**Using it**
- **Prototype bar.** The dark bar at the top is not part of IRIS. It switches the role you view as: Student, Adviser, ITSO coordinator, RDCO or System Admin. Each role gets its real sidebar, queue and permissions; a page your role cannot open shows a "no access" state.
- **Persistence.** The chosen role is remembered in this browser. Nothing else is saved; reloading resets sample data.
- **Routes to present.** `#/discover`, `#/records/101`, `#/records/103?tab=review` (Adviser), `#/records/111?tab=review` (ITSO), `#/records/104?tab=review` (Student), `#/library`, `#/ai`, `#/reviews`, `#/reviews/console`, `#/reviews/analytics`, `#/rdco/users`, `#/rdco/delete-requests`, `#/admin/audit`, `#/admin/account-deletion-requests`, `#/login`.
- **Interactions that work:**
  - Navigation, the phone drawer, popovers and dialogs (Escape closes them, and focus is trapped and returned).
  - The three-step Publish wizard with validation, the Ask IRIS panel and page with canned answers and citations.
  - Filters and sort, Cite with copy, claiming a review, and the confirm dialogs on destructive actions.
  - On a record: the Notes and Ask IRIS corner buttons and their shared panel, the This paper / All papers menu, Related works, and comment threads with replies, edit, delete and report.
  - The review workspace, laid out like a GitHub pull request: a timeline of comment boxes, tabs with counts, a status box at the end of the timeline and in the footer, a Details tab with a gear only where you can change something, a tab opened beside the pane on wide screens, resizable columns, threads with draft comments, Changes with Viewed, Finish review, Send version 2, Contents and Find in the reader, and the four-step tour.
- **Responsive testing.** Resize the window or use device emulation: 1440 / 1280 / 1024 / 768 / 390 / 360. The review workspace lays itself out by its own width (paper and pane, an optional right column from 1180 px, or a drawer).

## Honest limits

- **All sample data in the prototype is invented.** That covers papers, people, dates, views and every analytics figure. None of it is a measurement of IRIS or of CIT-U research.
  - The "Clearances kept across a revision" figure is a *proposed* metric that does not exist today.
  - The Settings consent checkboxes are illustrative.
- **Some recommendations are not prototyped**, because a static page cannot honestly simulate them:
  - Slow-server and session-ended states (FB-01, FB-02).
  - The Areas modal (US-02).
- **The review workspace runs on canned data.** Threads, versions, the Changes comparison and saved replies are sample content, and a draft comment lasts only until reload.
- **System Admin pages were not seen live.** The prototype's admin pages follow the router's routes and the RDCO components.
- **FB-01 needs reproducing.** The reload that ended on sign-in may have been caused by requests the audit browser blocked.
- **Contrast was checked by computing ratios,** not with assistive technology. A screen-reader pass on the real app is still owed.
- **The design detector** (Impeccable's `detect`) was run on the prototype and its findings fixed. Advisories left standing, all deliberate:
  - The proposed 14 px `control` step is not yet in `DESIGN.md`'s ramp.
  - A 9 px concentric segment radius and small 2–4 px bars.
  - The decorative gold seal (`#c9a227`), and the grey and black inks of the mock PDF page.
- **Preview config.** `.claude/launch.json` was added to this worktree only so the prototype could be served for screenshots. It is not part of the deliverable.

## Resuming this work

All deliverables listed above exist and the prototype has been browser-tested at every width. To extend it:
1. **Add a screen.** Add a `view…()` function and a `ROUTES` entry in `prototype/script.js`. Reuse the `head()`, `recRow()`, `status()`, `clearStrip()` and `dialog()` helpers, and the classes in `styles.css`.
2. **Capture it.** Save screenshots to `screenshots/redesigned/` with the next `R` id, and add a before/after section to `redesign-recommendations.md`.
3. **Build it in IRIS.** Pick up `implementation-roadmap.md` from Phase 0. Create the Jira issue for each slice before starting.
