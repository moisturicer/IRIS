# Page inventory

Inspected on the deployed site `https://iris-citu.duckdns.org/` on 12–13 Nov 2026, signed in as four real roles, with the frontend source (`frontend/src/router/index.tsx`, `lib/access.ts`) used to confirm every route exists and who may reach it.

**Legend.** ✅ inspected live · 🟡 inspected live but the content could not finish loading in the audit browser (see *Environment limits*) · 📄 not reachable with the accounts used, reviewed from source only.

Screenshot ids refer to files in `screenshots/original/`.

## Public (signed out)

| Route | Screen | Status | Evidence |
|---|---|---|---|
| `/login` | Sign in (Dossier entry frame) | ✅ 1440 · 360 | `01`, `05` |
| `/signup` | Register, step 1 of 3 (Identity), empty-submit validation | ✅ 1440 · 390 | `02`, `03`, `04` |
| `/signup` steps 2–3 | Affiliation, Security & agreement | 📄 (not reached: would need real input) | — |
| `/password/forgot`, `/password/reset` | Forgot / reset password | 📄 | — |
| `/verify-email`, `/verify-email/resend`, `/activate/...` | Verification and pending screens | 📄 | — |

## Every signed-in user (Student shown)

| Route | Screen | Status | Evidence |
|---|---|---|---|
| `/` | Discover — Papers (Latest), result cards with first-page preview | ✅ 1440 · 768 · 390 · 360 | `10`, `70`, `71`, `73` |
| `/` popovers | Filters, Areas modal, My feeds menu | ✅ | `11`, `12`, `13` |
| `/` People | People directory filters | ✅ | `14` |
| `/?q=` | Search: loading, error, results | ✅ | `15`, `16`, `17` |
| `/?publish=new` | Publish dialog, step 1 (Your manuscript) | ✅ (opened, nothing saved) | `60` |
| `/records/:id` | Record — Overview (abstract, actions, AI Overview, Record details) | ✅ 1440 · 1280 · 390 | `20`, `21`, `26`, `74` |
| `/records/:id` dialogs | Cite dialog, Notes panel, Ask IRIS (Paper Chat) panel | ✅ | `22`, `23`, `24` |
| `/records/:id?section=paper` | Paper reader with page toolbar and Ask IRIS column | ✅ | `25` |
| `/records/mine` | My Library — Overview, My submissions, Saved papers, Download requests | ✅ (download list stayed skeleton) | `30`–`33` |
| `/ai`, `/ai/conversations/:id` | Ask IRIS — new chat, depth menu, answer with citations, sources list | ✅ | `40`–`43` |
| `/opportunities` | Calls & Conferences (empty) | ✅ | `50` |
| Bell popover, `/notifications` | Notifications | ✅ | `51`, `85`, `90` |
| Account menu | Profile / Settings / Help / Sign out | ✅ | `52` |
| `/profile` | Own profile | ✅ | `53` |
| `/profile/edit` | Edit profile | 📄 | — |
| `/people/:id` | Another person's profile | 📄 | — |
| `/settings` | Account & security, Data privacy & consent, Role & access | ✅ | `54`–`56` |
| `/help` | Help | ✅ | `57` |
| Mobile drawer | Hamburger navigation | ✅ 390 | `72` |
| Any (route crash) | "Something went wrong" route error screen | ✅ (triggered by a blocked chunk) | `83`, `84` |
| Full-page loader | Session restore on reload | ✅ | `06`, `07` |

## Adviser

| Route | Screen | Status | Evidence |
|---|---|---|---|
| `/review` | My Reviews — To review (empty), Done (3) with outcome filters | ✅ | `80`, `81` |
| `/records/:id?section=review` | Record — Review & Routing tracker, ReviewActionBar (Route, Request revision, Accept & publish) | 🟡 chunk blocked → reviewed from `features/records/paper-view/Review*.tsx` | `82`–`84` |
| `/notifications` | 5 unread review notifications | ✅ | `85` |

## Office reviewer / coordinator (ITSO)

| Route | Screen | Status | Evidence |
|---|---|---|---|
| `/review` | My Reviews with Mine / All of ITSO scope, links to console and analytics | ✅ | `91` |
| `/review/office` | Office console (assign, reassign, extend due date) | 🟡 API blocked → reviewed from `features/review/OfficeConsolePage.tsx` | `92` |
| `/review/analytics` | Workflow Analytics | ✅ | `93` |
| `/notifications` | Routed-record notification | ✅ | `90` |
| `/records/:id?section=review` | Review workspace: paper, review pane (Conversation, Threads, Changes, Details), People & details column, tour offer, version picker | ✅ 1440 · 1024, 13 Nov, as an ITSO reviewer whose review was complete | `B0`–`B5` |
| Record dialogs | Clear…, Record finding…, Add reviewer | 📄 (`OfficeReviewDialog.tsx`, `AddReviewerDialog.tsx`) | — |

## RDCO

| Route | Screen | Status | Evidence |
|---|---|---|---|
| Sidebar | RDCO section (6 items) | ✅ | `A0` |
| `/records/import` | Import Records | ✅ | `A1` |
| `/rdco/users` | Users table | ✅ | `A2` |
| `/rdco/role-requests` | Role Requests (empty) | ✅ | `A3` |
| `/rdco/download-requests` | Download Requests | 🟡 chunk blocked | `A4` |
| `/rdco/delete-requests` | Delete Requests | ✅ | `A5` |
| `/notices` | Data notice publishing | ✅ | `A6` |

## System Admin only (not signed in as this role)

`/admin/users`, `/audit` (Audit Log), account deletion requests, `/retention` — 📄 routes confirmed in the router; not inspected visually. They share the table and page-header components seen on the RDCO pages, so the RDCO findings on tables, destructive buttons and page headers apply to them.

The prototype has a System Admin role with these pages (`RC1`, `RC2`). They are designs built from the routes and the RDCO components, not evidence of how the live pages look.

## Environment limits (read before trusting a 🟡)

- The Claude browser pane blocked some static files and one API call with `net::ERR_BLOCKED_BY_CLIENT` (for example `PaperViewPage-*.js` and `ai-*.css` on the Adviser's second tab, `/api/v1/reviews/office/`). That is the audit browser's own filter, **not an IRIS defect**, and the resulting errors are not counted against IRIS. What *is* counted is how IRIS presents those failures (copy, recovery).
- The server was slow throughout (search ~12 s, a full reload ~17 s). Slowness is reported where it changes what the user sees.
- One full-page reload ended on the sign-in page without explanation. Because blocked requests may have contributed, the finding is marked *needs confirmation*.
- The Review workspace was opened read-only: no review was claimed, no comment written, no clearance changed and the tour was not started.
- No record was created, saved, edited, approved or deleted. The Publish dialog was opened and closed at step 1, before any draft exists (`PublishDialog.tsx` creates a draft only after the manuscript step).
