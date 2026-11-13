# UI/UX audit of live IRIS and the redesign it proposes — specification (IR-1071)

**Status: PROPOSED (14 Nov 2026).** Nothing here is approved. The project lead, or the team in the Phase 0 meeting (§7.1), approves it. Tracked on [IR-1071](https://citiris.atlassian.net/browse/IR-1071) under the redesign epic [IR-920](https://citiris.atlassian.net/browse/IR-920).

**What this spec is.** It turns the audit in [`iris-uiux-audit/`](../iris-uiux-audit/README.md) into decisions and tickets. That folder holds the evidence:
- [`audit-report.md`](../iris-uiux-audit/audit-report.md): findings with ids, for example `WF-01`, `NAV-01` and `A11Y-01`;
- [`redesign-recommendations.md`](../iris-uiux-audit/redesign-recommendations.md): before and after, page by page;
- [`design-system.md`](../iris-uiux-audit/design-system.md): proposed tokens and components;
- [`implementation-roadmap.md`](../iris-uiux-audit/implementation-roadmap.md): the files each slice touches;
- **`prototype/`**: a standalone HTML prototype of every redesigned page, for five roles. **It is the reference for how a screen should look and behave.** The screenshots the notes link to are a local convenience: the repository ignores `screenshots/` folders, so they are not committed, and some predate the colour change in §4.9 (`redesign-recommendations.md` §18).

**How it relates to other documents.**
- **[`frontend_redesign_spec.md`](frontend_redesign_spec.md) (IR-374) stays the redesign's authority.** This spec amends it only where §4 says *Amends IR-374*.
- **ADR-032's workflow invariants** (IR-374 §0) bind every ticket here. The frontend renders what the server says; it decides no workflow state.
- **Two decisions depart from `DESIGN.md`** (§4.9 and the field token in §4.10). Neither can ship until the team accepts it and `DESIGN.md` and `palette.test.ts` change first.

Sections 1–6 follow the project's `to-spec` template. Appendix A lists the tickets.

---

## 1. Problem statement

The audit inspected live IRIS on 12–13 Nov 2026, read-only, as a student, an adviser, an ITSO coordinator, RDCO and a system admin, at 1440, 1024, 768, 390 and 360 px. It recorded 70 findings (2 Critical, 9 High, 31 Medium, 28 Low). The ones that matter most:

- **The workflow is hard to follow outside the record.** A notification still says "waiting for you" after the review is cleared (WF-01). Delete Requests' *Pending* tab lists a declined request (WF-02). A draft has no next step on My Library (WF-03). Which clearances survived a resubmission, the thesis contribution, is visible only inside the record (WF-06).
- **Accessibility basics fail.** Every page is titled "IRIS" (NAV-01, WCAG 2.4.2, level A). Field outlines and placeholders fall below contrast minimums (A11Y-01, A11Y-02).
- **Errors blame the user.** Server failures say "Check your connection" (US-05), and long waits show no words (FB-02).
- **Destructive actions are loud.** A filled *Lock* button sits on every user row (CMP-01).
- **Phones are crowded.** Discover stacks four rows of controls, three of them icon-only (RES-01). The record chrome takes a fifth of the screen (RES-03). Two floating buttons cover reading text (CMP-02).
- **One pale pink means about fifteen things.** The current page, a selected chip, an active status, a citation and a search match all look alike, and a search match is nearly invisible: 1.10:1 on white (§4.9).
- **Smaller inconsistencies add up.** There are two button shapes, uppercase eyebrows, mixed Title and sentence case, and four toolbar heights.

Section 11 of the audit report lists what already works. The redesign keeps it.

## 2. Solution

Keep IRIS's structure and its GitHub-style review workspace. Fix how each screen reports state, and make the visual language consistent:

- **Say what is waiting on whom, everywhere.** A notification shows when its task has closed. A compact clearance strip appears on My Reviews, the office console and My Library. Draft rows offer *Continue draft*.
- **Meet WCAG 2.2 AA where the audit found gaps.** Page titles come from the route table. Fields and placeholders meet contrast. Touch targets are at least 44 px.
- **Honest feedback.** One helper words every failure, every list offers *Try again*, and slow loads say what is happening.
- **One look per kind of highlight** (§4.9), one button component, sentence case, and no eyebrows.
- **Layouts that fit the device.** A tablet icon rail, a phone Discover with one row of controls, and a review workspace laid out by its own width.

## 3. User stories

### Everyone
1. As a user, I want each browser tab to name its page, so I can find my place among several tabs and screen readers announce where I am.
2. As a user, I want an error to say whether IRIS or my connection failed and to offer *Try again*, so I know what to do.
3. As a user, I want a slow page to tell me it is still working, so I don't reload and lose my place.
4. As a user, I want to click anywhere on a Discover result to open it, so I don't have to aim at the title.
5. As a user who types a question into Discover, I want IRIS to suggest Ask IRIS, so I find the tool that answers questions.
6. As a phone user, I want Discover's controls in one row and every control big enough to tap.
7. As a keyboard or screen-reader user, I want every control labelled and the reading order logical.

### Authors (Student, Adviser)
8. As a student, I want My Library to tell me what each of my papers is waiting on, and to continue a draft from there.
9. As a student, I want to see which clearances were kept when I sent version 2.
10. As an author, I want deleting a draft to be quieter than continuing it, and to name the draft before I confirm.

### Reviewers (Adviser, ITSO, IERC, KTTO, RDCO)
11. As a reviewer, I want a notification to show that its task is closed, so I don't open a finished review.
12. As a reviewer, I want each paper's clearance strip in my queue, so I see who holds it without opening it.
13. As a reviewer, I want the workspace to fit my screen, with only its columns scrolling, and to open a second tab beside the first on a wide screen.
14. As a coordinator, I want Office console and Analytics under My Reviews, and analytics numbers I can compare at a glance.

### RDCO and System Admin
15. As RDCO, I want Delete Requests' *Pending* tab to list only pending requests.
16. As an admin, I want row actions in a menu, with Lock behind a dialog that names the person.

### Readers who don't author (offices, RDCO, admin)
17. As an office reviewer, I don't want a *Publish* button or research tabs I can never use. My Library shows my saved papers and download requests.

## 4. Implementation decisions

### 4.1 Page titles (NAV-01)
The shell sets `document.title` from the deepest route crumb plus " · IRIS". Records use the paper's title and conversations use theirs. My Reviews includes its count.

### 4.2 Notifications know when their task closed (WF-01, US-10, A11Y-07)
**Server first.** A notification whose review step has closed carries `resolved_at` and a `resolved_label` (or `actionable: false`), and leaves the unread count. The client renders a settled line, for example "Cleared by you on 20 Oct". The client never infers it. *Needs Phase 0 decision D2.*

### 4.3 Errors and waiting (US-05, FB-02)
One helper, extending `lib/readFailure.ts`, picks the message: offline → "Check your connection"; timeout or 5xx → "IRIS took too long to answer. Try again." Every list failure has *Try again*. Loaders gain a line of text after 2 s and *Try again* after 10 s.

### 4.4 Clearance strip (WF-06) — thesis-critical
A compact per-party strip extracted from `ReviewRoutingTracker` ("Cleared on v1 · kept", "Reviewing v2"), rendered from server fields only (IR-374 invariant 15). It appears on My Reviews rows, the office console and My Library rows.

### 4.5 Authoring is for authors — *Amends IR-374 §4.9*
*Publish* and My Library's research tabs appear only for users the server says can author (Student, Adviser). Other roles' My Library shows **Saved papers** and **Download requests** only. The capability comes from the server (IR-374 §4.8), never a role-name check. If no such capability exists yet, the ticket adds it first.

### 4.6 Discover
- **One toolbar:** one filled action (Publish), one control height, visible filter labels, Sort in the results header with a live count.
- **List rows** with a 96 px outline thumbnail. People results appear only on the People tab.
- **The whole card opens the paper,** using a stretched link on the title. Other controls on the card stay clickable above it, and keyboard focus outlines the whole card.
- **No permanent Ask IRIS hint.** When a search looks like a question (it ends in "?" or starts with a question word), one line suggests Ask IRIS and carries the question over.
- **Search matches every word.** Words are matched separately, stopwords are dropped, and each match is highlighted (§4.9).
- **Phone:** search first, then one horizontally scrolling row (feed, Filters (n), My feeds).
- **Neutral copy:** Discover, sign-in and sign-up do not say "CIT-U" (IRIS is not only for CIT-U; live IR-768 already did this for part of it).

### 4.7 Navigation and layout
- Office console and Analytics nest under My Reviews (D5). Help moves to the sidebar footer. Breadcrumbs say "Discover", not "Home". Settings tabs are addressable by `?tab=`.
- Below 1024 px the sidebar becomes a 76 px icon rail, with tooltips and accessible names.
- On phones, Back and the section control merge into one 56 px record bar.
- Notes sits above Ask IRIS in the corner (owner's decision, 13 Nov), and pages reserve bottom padding so text scrolls clear of both.

### 4.8 Review workspace — *Amends IR-374 §4.7*
Detailed in `redesign-recommendations.md` §17. In short:
- The workspace fills the viewport; only its columns scroll (LAY-07).
- It lays out by its own width: paper and pane side by side, then a drawer with *Back to paper* (RES-06).
- **No People & details column.** It repeated the Details tab (frontend owner, 13 Nov).
- On a workspace at least 1180 px wide, a reviewer may open one tab in a right column; the choice is remembered.
- A **"Your part" footer** with one heading and one action replaces the readiness card (WF-07, VIS-09).
- One status per party in Details (US-17), sentence-case labels and a short version label (US-18).

IR-870 is building the workspace now; this ticket follows it and must not fight it.

### 4.9 Colour and highlights — *departs from `DESIGN.md`*
Each kind of highlight gets one look, and no look means two things:

| Role | Look |
|---|---|
| Action | Maroon fill, one per row |
| Here (current page or tab) | Desk Stone fill, Ink text, maroon icon; no side stripe |
| Selected (an option you chose) | White raised segment, or an Ink outline; never maroon |
| Reference (citation, source number) | Maroon text on white with a Rule Stone hairline |
| Match (search, Find) | Yellow highlighter `#F7E08F`, current match `#F2C94C`; Ink text on it is 14:1 |
| Pen (a reviewer's passage mark) | Rose fill with a 2 px underline and a numbered pin; the open thread's passage is stronger |
| Status | White chip, tone in text and outline; only Attention is filled |

Gold and stray hexes are removed. The full table is in `design-system.md` §1. **`DESIGN.md`'s Four Inks Rule allows no yellow, and it makes Maroon Wash the "on" tint for all of the above. The team must accept the change, and `DESIGN.md` and `palette.test.ts` must change, before code does.**

### 4.10 Components and type
- **Buttons:** one component with a pill radius and sentence case. The disabled state is Desk Stone with Faint Ink and a reason line. Prefer validation on press to a permanently disabled *Continue*.
- **Fields:** outline `#8f8884` (3.49:1); placeholder and helper text in Quiet Ink `#57534e` (D1).
- **Text:** no uppercase tracked eyebrows, sentence case everywhere, and a fixed heading ladder inside the AI Overview (22 / 17 px).
- **User rows:** actions in a "⋯" menu. Lock is a confirm dialog that names the person, and there are no actions on your own row.

### 4.11 Ask IRIS presentation
The thread is capped at 68ch. Sources show title, section, page and a clean snippet, and open the paper at that page. An empty conversation shows starter questions. **Presentation only:** no retrieval, answer or runtime code changes. The AI area's owner reviews the ticket before work starts.

## 5. Testing decisions

- **Vitest page tests over a mocked API,** querying by role and accessible name (IR-374 §5). Page titles get a router test that asserts `document.title`.
- **axe-core** fails on serious and critical issues. Contrast is a manual check at 1440, 1024, 768, 390 and 360 px, because jsdom cannot measure it.
- **Server tickets** (§4.2, possibly §4.5) ship backend tests and, if they add a field, a migration tested on a realistic database copy.
- **Thesis-critical tickets** (§4.2, §4.4, My Library next steps, §4.8) add `docs/testing/traceability/IR-XXX.md`.
- Each ticket compares its screens with the matching prototype route.

## 6. Out of scope

- Workflow rules, routing, labels and vocabulary. The server owns them (IR-374 §0). WF-05's "Accepted" for theses is a server vocabulary decision (D3).
- Retrieval, answers and anything under `apps/ai` or `ai/`.
- New metrics. A number the prototype shows, for example "Clearances kept across a revision", needs an ADR or ticket that defines how it is counted. The prototype's figures and papers are invented.
- Dark mode, and new features the audit did not find missing.

## 7. Further notes

### 7.1 Phase 0 decisions (one meeting, the team's, not this spec's)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Adopt the `field` outline token `#8f8884` and a 14/20 `control` type step | Yes; add both to `DESIGN.md` |
| D2 | Should a notification carry a *resolved* state from the server? | Yes; the client cannot know reliably |
| D3 | Thesis records reading "Accepted" | A server vocabulary call, recorded in the ADR that owns workflow labels |
| D4 | Keep the Discover layout toggle and the uploaded-cover thumbnail? | One list layout, thumbnail as a 96 px outline |
| D5 | Nest Office console and Analytics under My Reviews | Yes, for the roles that have them |
| D6 | Adopt the highlight roles of §4.9, including yellow for matches | Yes; change `DESIGN.md` and `palette.test.ts` first |

### 7.2 Existing tickets this overlaps
Linked rather than duplicated:
- IR-870: review workspace, in progress.
- IR-896: WCAG acceptance.
- IR-1028: ConfirmDialog for admin actions.
- IR-1038 to IR-1043: type roles and component rules.
- IR-947: Discover year range.
- IR-1048: upload refusal message.

### 7.3 Limits of the audit
Some live requests were blocked by the audit browser, so FB-01 ("reload ended on sign-in") needs reproducing before work. The audit's accessibility checks were manual and axe-based, not a full conformance review.

---

## Appendix A — Tickets

Created 14 Nov 2026. All sit under IR-920 except IR-1075 (under IR-671), unassigned, labelled `s2-active`, `area-frontend` and `area-uiux` plus what is listed. "Done" follows `docs/engineering/DEFINITION_OF_DONE.md` §4. Each ticket's acceptance criteria are summarised here; its Jira description carries them in full.

| # | Key | Ticket | Spec | Priority | Extra labels | Overlaps |
|---|---|---|---|---|---|---|
| A0 | [IR-1071](https://citiris.atlassian.net/browse/IR-1071) | Docs: UI/UX audit, HTML redesign prototype and this spec | all | Medium | `area-documentation` | — |
| A1 | [IR-1072](https://citiris.atlassian.net/browse/IR-1072) | Decide the audit's open design questions (D1–D6) | §7.1 | High | `not-ready` | — |
| 1.1 | [IR-1073](https://citiris.atlassian.net/browse/IR-1073) | Every page has its own browser tab title | §4.1 | Highest | `ready-to-pull` | — |
| 1.2 | [IR-1074](https://citiris.atlassian.net/browse/IR-1074) | Form fields, placeholders and stone-surface metadata meet contrast | §4.10 | High | `not-ready` (D1) | IR-896 |
| 1.3 | [IR-1075](https://citiris.atlassian.net/browse/IR-1075) | Notifications show when their review task has closed — **parent IR-671**, cross-stack | §4.2 | High | `area-backend` `area-workflow` `thesis-critical` `not-ready` (D2) | — |
| 1.4 | [IR-1076](https://citiris.atlassian.net/browse/IR-1076) | Delete Requests: Pending lists only pending requests | — | High | `area-workflow` `ready-to-pull` | — |
| 1.5 | [IR-1077](https://citiris.atlassian.net/browse/IR-1077) | Users: row actions in a menu, Lock behind a named confirm | §4.10 | High | `ready-to-pull` | IR-1028 |
| 1.6 | [IR-1078](https://citiris.atlassian.net/browse/IR-1078) | Errors say who failed and offer Try again; slow loads say they are working | §4.3 | High | `ready-to-pull` | IR-1048 |
| 1.7 | [IR-1079](https://citiris.atlassian.net/browse/IR-1079) | Notes and Ask IRIS corner buttons never cover reading text | §4.7 | High | `ready-to-pull` | — |
| 1.8 | [IR-1080](https://citiris.atlassian.net/browse/IR-1080) | Phone Discover: search, then one row of controls | §4.6 | High | `ready-to-pull` | — |
| 1.9 | [IR-1081](https://citiris.atlassian.net/browse/IR-1081) | Reproduce, then fix, a reload landing on sign-in | — | High | `not-ready` | — |
| 2.1 | [IR-1082](https://citiris.atlassian.net/browse/IR-1082) | Discover toolbar and result rows | §4.6 | Medium | `not-ready` (D4, D6) | IR-947 |
| 2.2 | [IR-1083](https://citiris.atlassian.net/browse/IR-1083) | Clearance strip on My Reviews, the office console and My Library | §4.4 | Medium | `area-workflow` `thesis-critical` `ready-to-pull` | — |
| 2.3 | [IR-1084](https://citiris.atlassian.net/browse/IR-1084) | My Library says what each paper waits on and offers Continue draft | §3.8–10 | Medium | `area-workflow` `thesis-critical` `ready-to-pull` | — |
| 2.4 | [IR-1085](https://citiris.atlassian.net/browse/IR-1085) | Navigation: reviews nesting, Help in the footer, addressable Settings tabs | §4.7 | Medium | `not-ready` (D5) | — |
| 2.5 | [IR-1086](https://citiris.atlassian.net/browse/IR-1086) | Tablet: the sidebar becomes a labelled icon rail below 1024 px | §4.7 | Medium | `ready-to-pull` | — |
| 2.6 | [IR-1087](https://citiris.atlassian.net/browse/IR-1087) | Sentence case and no uppercase eyebrows | §4.10 | Medium | `ready-to-pull` | IR-1039–1042 |
| 2.7 | [IR-1088](https://citiris.atlassian.net/browse/IR-1088) | One button component, with a legible disabled state | §4.10 | Medium | `ready-to-pull` | IR-1043, IR-1038 |
| 2.8 | [IR-1089](https://citiris.atlassian.net/browse/IR-1089) | Record overview: one byline, one date line, a fixed heading ladder | §4.10 | Medium | `ready-to-pull` | — |
| 2.9 | [IR-1090](https://citiris.atlassian.net/browse/IR-1090) | Ask IRIS: reading width, clean sources, starter questions | §4.11 | Medium | `not-ready` (owner review) | — |
| 2.10 | [IR-1091](https://citiris.atlassian.net/browse/IR-1091) | Workflow analytics: method in a disclosure, aligned numbers | — | Medium | `ready-to-pull` | — |
| 2.11 | [IR-1092](https://citiris.atlassian.net/browse/IR-1092) | Phone record bar and 44 px touch targets | §4.7 | Medium | `ready-to-pull` | — |
| 2.12 | [IR-1093](https://citiris.atlassian.net/browse/IR-1093) | Sign-in fields: no misleading placeholders, Show toggle, headline as h1 | — | Medium | `ready-to-pull` | — |
| 2.14 | [IR-1094](https://citiris.atlassian.net/browse/IR-1094) | Review workspace fits the viewport and lays out by its own width | §4.8 | Medium | `area-workflow` `thesis-critical` `not-ready` (after IR-870) | IR-870 |
| 2.15 | [IR-1095](https://citiris.atlassian.net/browse/IR-1095) | Discover: the whole card opens the paper; suggest Ask IRIS for questions | §4.6 | Medium | `ready-to-pull` | — |
| 2.16 | [IR-1096](https://citiris.atlassian.net/browse/IR-1096) | Publish and research tabs only for authors | §4.5 | Medium | `area-workflow` `not-ready` (capability check) | — |
| 2.17 | [IR-1097](https://citiris.atlassian.net/browse/IR-1097) | One look per kind of highlight | §4.9 | Medium | `not-ready` (D6) | — |
| 3.1 | [IR-1098](https://citiris.atlassian.net/browse/IR-1098) | Polish batch: paper toolbar, microcopy, empty states, icons, phone brand, Help reading order | — | Low | `ready-to-pull` | — |

Row 2.13 (Help reading order) is folded into 3.1.
