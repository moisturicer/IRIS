# Implementation roadmap

This roadmap orders the audit's findings into shippable slices.
- **Order:** severity first (Critical → High → Medium → Low). Within a severity, items that unblock others come first, and thesis-critical workflow visibility comes before visual polish.
- **Size:** each slice is small enough for one Jira issue and one PR.
- **Paths:** file paths are relative to `frontend/src/` unless they start with `backend/`. They come from reading the code on `main` at commit `957b2783`.

**Jira.** Every row now has an issue (IR-1072 to IR-1098, created 14 Nov 2026); the key for each is in `docs/frontend_ui_audit_spec.md` Appendix A. Name the branch `feature/IR-XXX-…` or `fix/IR-XXX-…`.

**Estimates.** S is under half a day, M is one to two days, and L is three days or more. They are rough, for planning only.

**Ownership.** The frontend rows can start now. Rows marked **server** need a backend change first; get the owner's agreement on that change before frontend work starts.

---

## Phase 0: decisions before code (one meeting)

These choices are the team's, not the audit's. Each one changes several rows below.

| # | Decision | Affects | Recommendation |
|---|---|---|---|
| D1 | Adopt the `field` outline token `#8f8884` (3.49:1) for form fields and the `control` 14/20 type step | A11Y-01, the prototype's whole type scale | Add both to `DESIGN.md` (see `design-system.md`) |
| D2 | Should a notification carry a *resolved* state from the server? | WF-01 | Yes. The client cannot know reliably that a task closed |
| D3 | Thesis records reading "Accepted" | WF-05 | A server vocabulary call, recorded in the ADR that owns workflow labels; the UI keeps rendering `workflow_state_label` |
| D4 | Keep the Discover layout toggle and the uploaded-cover thumbnail? | LAY-01, CMP-04 | One list layout, with the thumbnail as a 96 px outline |
| D5 | Nest Office console and Analytics under My Reviews in the sidebar | NAV-02 | Yes, for the roles that have them |

---

## Phase 1: Critical and High (aim: next sprint)

| # | Slice | Findings | Files | Size | Notes |
|---|---|---|---|---|---|
| 1.1 | **Page titles from the route table.** Add a `useDocumentTitle` effect in the shell that reads the deepest `handle.crumb` and appends " · IRIS". Records and conversations set their own title (paper title, conversation title). My Reviews includes its count | NAV-01 | `components/layout/AppShell.tsx`, `router/index.tsx` (crumbs already exist), `features/records/paper-view/PaperViewPage.tsx`, `features/ai/RAGChatPage.tsx` | S | Test: navigate in a vitest router test and assert `document.title`. Also fix crumbs "Workflow Analytics" → "Workflow analytics", "Import Records" → "Import records" (VIS-03) |
| 1.2 | **Field outline and placeholder contrast.** Fields use `#8f8884` (3:1 or more against white). Placeholder and helper text become Quiet Ink `#57534e`. Metadata on stone surfaces becomes Quiet Ink | A11Y-01, A11Y-02, A11Y-10 | `tailwind.config.js`, `index.css`, `components/ui/fieldClasses.ts`, `Input.tsx`, `Select.tsx` | S | Contrast stays a manual check; jsdom cannot measure it (CLAUDE.md) |
| 1.3 | **Notifications show when their task is closed.** **Server:** expose `resolved_at` + `resolved_label` (or `actionable: false`) on notifications whose review step has closed, and leave them out of the unread count. **Client:** render a settled status line ("Cleared by you on 20 Oct") and fix the template copy | WF-01, US-10, A11Y-07 | `backend/apps/notifications/` (serializer and the workflow hooks that close steps), `features/notifications/NotificationsPage.tsx`, `components/layout/NotificationBell.tsx` | M | Thesis-critical: principle "Say what is waiting on whom" |
| 1.4 | **Delete Requests: Pending shows only pending.** Split Pending and Decided. Show actions only on pending rows. Decided rows show outcome and reason | WF-02 | `features/admin/DeleteRequestsPage.tsx` (+ its test), and the list endpoint's filter if the mismatch is on the server | S | Check first whether the API or the client filter is wrong |
| 1.5 | **Users: no filled Lock on every row.** Put row actions in a "⋯" menu. Lock is a confirm dialog that names the person. No actions on your own row. Name first, email under it | CMP-01 | `features/accounts/UserListPage.tsx`, `features/accounts/accountActions.ts` | S | |
| 1.6 | **Honest error and slow-load copy.** One helper decides the message: offline → "check your connection"; timeout or 5xx → "IRIS took too long to answer. Try again." Every list failure gets **Try again**. After 2 s, loaders gain a line of text; after 10 s, they gain Try again | US-05, FB-02 | `lib/readFailure.ts` (extend it rather than adding another helper), then the about 20 files that hard-code "Check your connection" (`grep -rn "Check your connection" frontend/src`), `components/ui/Spinner.tsx`, `Skeleton.tsx` | M | One helper keeps the copy consistent; the per-file edits are mechanical |
| 1.7 | **Corner buttons clear of text.** Keep Notes above Ask IRIS (owner's decision, 13 Nov). Reserve bottom padding on Overview and Paper so the last lines scroll clear of both, and update DESIGN.md's "one corner icon" line to name Notes | CMP-02 | `features/records/paper-view/NotesPanel.tsx`, `AskIrisFab.tsx`, `ReadingHeader.tsx`, `PaperViewPage.tsx` | S | |
| 1.8 | **Phone Discover control stack.** Search first, then one horizontally scrolling row (feed segments, Filters (n), My feeds). Papers/People in the header. Publish keeps its label | RES-01, RES-02, A11Y-09 | `features/discover/DiscoverPage.tsx`, `DiscoverFilterBar.tsx`, `DiscoverTabs.tsx` | M | Do it together with 2.1, which changes the same toolbar |
| 1.9 | **Session-ended message.** Reproduce FB-01 on a normal browser first. If a reload can land on sign-in, show "Your session ended. Sign in to continue where you were." | FB-01 | `lib/authSession.ts`, `lib/tokenRefresh.ts`, `features/auth/LoginPage.tsx` | S | Needs confirmation; the audit browser blocked some requests |

---

## Phase 2: workflow visibility and consistency (Medium)

| # | Slice | Findings | Files | Size |
|---|---|---|---|---|
| 2.1 | **Discover toolbar and results.** Maroon Wash for selected segments, one filled action (Publish). One control height. Visible filter labels; Sort in the results header with a live count. List rows with a 96 px outline thumbnail. People results only on the People tab. Hide Areas until areas exist | VIS-01, VIS-05, LAY-01, LAY-02, US-01, US-02, US-03, US-04, CMP-03, CMP-04 | `features/discover/*` (`DiscoverResultCard.tsx`, `DiscoverFilterBar.tsx`, `DiscoverFilterDropdown.tsx`, `DiscoverSearchComposer.tsx`, `ManuscriptCover.tsx`, `DiscoverPeopleResults.tsx`), `components/ui/pillStyles.ts` | L |
| 2.2 | **Clearance strip component.** Extract a compact per-party strip from `ReviewRoutingTracker.tsx` ("Cleared on v1 · kept", "Reviewing v2"). Use it on My Reviews rows, the office console and My Library rows | WF-06 | `features/records/paper-view/ReviewRoutingTracker.tsx`, `features/review/MyReviewsPage.tsx`, `features/review/OfficeConsolePage.tsx`, `features/library/SubmissionRow.tsx` | M |
| 2.3 | **My Library next steps.** Overview rows say what is waiting on whom and offer **Continue draft**. Delete draft becomes a ghost button behind a named confirm. Strip the file extension from pre-filled titles | WF-03, WF-04, US-06 | `features/library/LibraryOverview.tsx`, `MyResearchList.tsx`, `DeleteDraft.tsx`, `features/publish/prefill.ts`, `autofill.ts` | M |
| 2.4 | **Navigation.** Nest Office console and Analytics under My Reviews. Move Help to the sidebar footer. "Discover", not "Home", in breadcrumbs. Settings tabs addressable by `?tab=` | NAV-02, NAV-03, NAV-04, NAV-08 | `components/layout/Sidebar.tsx`, `Breadcrumbs.tsx`, `AccountMenu.tsx`, `router/index.tsx`, `features/settings/*` | M |
| 2.5 | **Tablet layout.** Below 1024 px the sidebar becomes the 76 px icon rail, with tooltips and `aria-label`s | NAV-06, NAV-07 | `components/layout/AppShell.tsx`, `Sidebar.tsx`, `lib/layout.ts` | M |
| 2.6 | **Sentence case and no eyebrows.** Remove the uppercase tracked labels, and Title Case labels on sign-in, register and RDCO pages | VIS-02, VIS-03 | Search for `uppercase` and `tracking-` in `features/` and `components/`. Covers about a dozen screens | M |
| 2.7 | **One button component.** Pill radius and sentence case. Disabled state is Desk Stone + Faint Ink with a reason line; prefer validation on press over a permanently disabled Continue | VIS-04, CMP-05 | `components/ui/Button.tsx` (+ test), `features/settings/*` (Change password), `features/publish/PublishDialog.tsx`, `ManuscriptStep.tsx`, `features/records/ImportRecordsPage.tsx`, `features/admin/NoticesPage.tsx` | M |
| 2.8 | **Record overview metadata.** One byline, one date line, governance fields only in Record details. Fixed heading ladder inside the AI Overview (22 / 17 px) | LAY-03, VIS-06, VIS-07 | `features/records/paper-view/PaperAiOverview.tsx`, `ReviewDetails.tsx`, `PaperGovernance.tsx`, `ReadingHeader.tsx`, `headings.tsx`, `components/ui/Badge.tsx`, `statusTones.ts` | M |
| 2.9 | **Ask IRIS reading width and sources.** Cap the thread at 68ch. Sources show title, section, page and a clean snippet (strip Markdown), and open the paper at that page. Show starter questions | LAY-04, US-15, US-16, US-12 | `features/ai/components/ChatMessageList.tsx`, `ChatMessageBubble.tsx`, `ChatInput.tsx`, `features/help/helpSections.tsx` | M |
| 2.10 | **Workflow analytics.** Methodology in a "How these numbers are counted" disclosure. Right-aligned tabular numbers | LAY-05 | `features/review/ReviewAnalyticsPage.tsx` | S |
| 2.11 | **Phone record chrome and touch targets.** Merge Back and the section control into one 56 px record bar. Every control at least 44 px on touch | RES-02, RES-03 | `features/records/paper-view/ReadingHeader.tsx`, `components/layout/*` | M |
| 2.12 | **Sign-in fields.** No password placeholder, no institution-specific email placeholder, Show toggle, headline as the h1 | US-07, A11Y-08 | `features/auth/LoginPage.tsx` (+ `entryHeadings.test.tsx`) | S |
| 2.13 | **Reading order of Help contents** | A11Y-03 | `features/help/HelpPage.tsx` | S |
| 2.14 | **Review workspace layout and status.** Size the workspace to the viewport so only its columns scroll. Lay it out by its own width: paper and pane, then a drawer with "Back to paper". Drop the People & details column (it repeats the Details tab) and let a reviewer open one tab in a right column on wide screens. Replace the readiness card with a "Your part" footer line and one action. One status per party in the Details tab; sentence-case labels; a short version label | LAY-07, RES-06, WF-07, VIS-09, US-17, US-18 | `features/records/paper-view/ReviewWorkspaceLayout.tsx`, `ReadinessPanel.tsx`, `ReviewDetails.tsx`, `tour/GuidedTour.tsx` (+ `ReviewTour.test.tsx`) | L |

---

## Phase 3: polish (Low)

Batch these into one or two PRs once Phase 2 has landed:

- **Paper view:** move "Request pending · Cancel" out of the zoom toolbar (CMP-06). Use plain loading copy, "Opening the paper…" (US-09).
- **Microcopy:**
  - Fix the Settings sentence "papers you're Contact person of" (US-11).
  - Remove the duplicated register stepper (US-08).
  - Add the Import template button and hide the empty Import Log (US-14).
- **Empty states:** no zero counters on Calls & Conferences (US-13); empty states that name the next action (LAY-06).
- **Icons:** one stroked set at 1.75 px; the speech-bubble glyph only for Ask IRIS (VIS-08).
- **Phone brand:** the IRIS mark in the phone top bar (RES-04); the CIT-U seal only below 480 px (RES-05).

---

## How to verify each slice

1. **Tests.**
   - Run `npm run test:changed` before pushing; CI runs the full suite (CLAUDE.md).
   - Query by role and accessible name, never by class.
   - axe-core fails only on serious and critical issues.
2. **Manual checks.**
   - Contrast and focus, at 1440, 1024, 768, 390 and 360 px.
   - Compare against the matching prototype route and the `R*` screenshot in `redesign-recommendations.md`.
3. **Thesis-critical rows** (1.3, 2.2, 2.3, 2.14) need a traceability note (`docs/testing/traceability/IR-XXX.md`), because they change how the workflow reports state.
4. **Server rows** (1.3, possibly 1.4) ship their backend change with tests in `backend/`. They need a migration if a field is added; per CLAUDE.md, test it against a realistic database copy.

## What the prototype does not decide

The prototype is a direction, not a spec. Wording in the workflow follows the server's labels and the ADRs. Analytics figures and sample papers in the prototype are invented. Before any metric is built (for example "Clearances kept across a revision"), it needs an ADR or a ticket that defines how it is counted.
