# IRIS design system — proposed refinement

**Brief.** `PRODUCT.md` pins the direction: *refine the existing IRIS interface within its fixed tokens; do not replace its visual identity or introduce a new palette, type scale or webfont.* So this is not a new look. It keeps the Bound Volume (maroon binding, Garamond titles, stone pages) and fixes where the shipped app drifts from it or fails accessibility. Every change below is tagged:

- **KEEP** — already in `DESIGN.md` / `tailwind.config.js`, used as is.
- **FIX** — an existing token whose use must change (usually for contrast).
- **ADD** — a new token or rule, inside the four-ink palette, filling a gap the audit found.

The prototype's `prototype/styles.css` implements exactly these tokens in its `:root` block.

---

## 1. Colour

The palette is **white, black, stone and maroon, plus one yellow highlighter** for matched words. No green or blue status colours: status is carried by four tones **plus a word and an icon**.

### Highlight roles (changed 13 Nov 2026)

**This departs from DESIGN.md on purpose**, at the frontend owner's request. DESIGN.md gives one pale pink, Maroon Wash, about fifteen jobs: the current page, a selected option, an active status, a page citation, a search match, a badge and a warning all looked alike, and a search match was nearly invisible (1.10:1 on white). The prototype gives each kind of highlight one treatment, and no treatment two meanings.

| Role | Treatment | Where | Token |
|---|---|---|---|
| **Action** | Maroon fill, white text. One per row | Publish, Search, Continue, Send | `--maroon` |
| **Here** (where you are) | Desk Stone fill, Ink text, maroon icon. No coloured stripe | Current sidebar page, current Settings tab, the open conversation, a comment you jumped to | `--here` |
| **Selected** (an option you chose) | White raised on stone (segments), or an Ink outline (chips, option cards). Never maroon | Papers / People, Latest / For you, Filters when on, Soonest due, a chosen record type | `--ink`, `--page` |
| **Reference** (IRIS points at a source) | Maroon text on white with a Rule Stone hairline; maroon fill on hover | Page citations (p. 27), source numbers in Ask IRIS | `--maroon` |
| **Match** (the highlighter) | A yellow highlighter, Ink text on it (14:1). The current Find match is stronger | Words a Discover search matched, Find in the paper | `--hl`, `--hl-now` |
| **Pen** (a reviewer's mark) | Rose fill with a 2 px pen underline and a numbered pin. Answered or resolved threads keep only the underline. The open thread's passage and its card quote share a stronger rose | Commented passages in the review paper, as in live IRIS (IR-875) | `--pen`, `--pen-wash`, `--pen-now` |
| **Status** | Tone + word + icon on white: Quiet (Rule outline), Active (maroon text, Rule outline), Settled (Ink outline), Kept (Ink outline on Bar Stone), Attention (maroon fill) | Review states, office clearances | — |

Why yellow for matches: it is the one hue nothing else in IRIS uses, so a match can never be mistaken for a selection or a status. Live IRIS already uses yellow for Find in the PDF reader, and every browser does. The pen keeps maroon's family because a reviewer's comment is the institution's red pen on the manuscript.

Badges and decoration (step numbers, the "Author" tag on a comment, timeline dots, the scope chip) are neutral: white or Bar Stone with Body or maroon text, never a pink fill. Every card has the same hover: a Rule Stone border and a soft lift. Gold, `#fbe4e4`, `#fcfcfb` and `#5a0c0f` are gone or tokenised (`--maroon-press` for a pressed filled button).

### Brand

| Token | Hex | Use | Contrast on white | Tag |
|---|---|---|---|---|
| `--maroon` Binding Maroon | `#6B0F12` | The one filled action per row, current nav item text, citations, focus ring | 12.34:1 | KEEP |
| `--maroon-light` | `#8B1316` | Hover on maroon fills only | 9.53:1 | KEEP |
| `--maroon-dark` | `#4A0A0C` | Destructive confirm buttons (always with a warning glyph) | — | KEEP |
| `--maroon-wash` | `#FDF2F2` | Retired from the interface (see Highlight roles) | — | **FIX** |
| `--maroon-thread` | `#F9B8B9` | Text selection, the toast icon on the dark toast | — | FIX (narrower) |
| `--pen` / `--pen-wash` / `--pen-now` | `#B4474B` / `#FBEAEA` / `#F5D5D6` | A reviewer's passage mark: underline (5.33:1 on white), fill, and the open one | — | **ADD** |
| `--hl` / `--hl-now` | `#F7E08F` / `#F2C94C` | Matched words; the current Find match | Ink on it 14.15:1 | **ADD** |
| Gold | (existing) | Removed from the paper thumbnails | — | **CUT** |

### Surfaces

| Token | Hex | Use | Tag |
|---|---|---|---|
| `--endpaper` | `#FAFAF9` | Page ground under every screen | KEEP |
| `--page` | `#FFFFFF` | Fields, cards that hold records, dialogs, menus, PDF pages | KEEP |
| `--bar` Bar Stone | `#F5F5F4` | Record bar, reader toolbar, Ask IRIS header, table headers | KEEP |
| `--desk` Desk Stone | `#E7E5E4` | Hairlines between regions, the recessed track, disabled fills | KEEP |
| `--rule` Rule Stone | `#D6D3D1` | Outlines on **decorative** chips and cards only | FIX — no longer used for fields |
| `--field` Field Stone | `#8F8884` | **Outline of every input, select, textarea and checkbox** — 3.49:1 on white, 3.34:1 on Endpaper (WCAG 1.4.11) | **ADD** |

### Text

| Token | Hex | Use | On white | On Bar Stone | Tag |
|---|---|---|---|---|---|
| `--ink` | `#1C1917` | Titles, headings, the *settled* status | 17.5:1 | — | KEEP |
| `--body` | `#44403C` | Running text, outlined control labels | 10.3:1 | 9.4:1 | KEEP |
| `--quiet` | `#57534E` | Secondary lines, inactive tabs, **any small text on a stone surface** | 7.6:1 | 6.99:1 | FIX (wider use) |
| `--faint` | `#78716C` | Metadata and timestamps **on white or Endpaper only** | 4.8:1 | **4.40:1 ✗** | FIX (never on stone) |
| Placeholder | `#78716C` | Placeholders are Faint Ink, never stone-400 (`#A8A29E` is 2.5:1) | 4.8:1 | — | FIX |

### Status tones (four tones + word + icon)

| Tone | Look | Examples | Tag |
|---|---|---|---|
| *Quiet* | Unfilled, Rule Stone outline, Body Ink text | Draft, Not started, Not open yet | KEEP |
| *Active* | White, Rule Stone outline, maroon text, eye icon | In review, Reviewing, Open | **FIX** — the pink fill looked like a search match |
| *Attention* | Solid maroon, white text, alert icon | Changes requested, Overdue, Finding recorded | KEEP |
| *Settled* | **Outlined Ink** with a check icon (was solid Ink) | Published, Cleared, Accepted, Active | **FIX** — solid ink chips out-shouted titles (VIS-07) |
| *Preserved* | Settled + a "kept" glyph (↺ crossed) and the word "kept" | "ITSO cleared on v1 · kept" | **ADD** — makes clearance-aware resubmission visible (WF-06) |

Errors use maroon text with an alert icon and the word "Error" in the accessible name; success messages use Ink with a check icon. Neither introduces a new hue.

---

## 2. Typography

Fonts are unchanged: **EB Garamond 600** for what you read the title of; **Inter** for everything you operate. The scale is the existing `tailwind.config.js` roles, with two fixes.

| Role | Font | Size / line | Weight | Use | Tag |
|---|---|---|---|---|---|
| `display` | Garamond | 40/44 (phone 32/36) | 600 | Record title on Overview; sign-in headline | KEEP (sizes from DESIGN.md, capped at 40 inside the app) |
| `page-title` | Garamond | 28/34 | 600 | Page title ("My Library") | KEEP (`text-display` 28/34) |
| `section` | Garamond | 22/28 | 600 | Section heads (Abstract, AI Overview, Review & routing) | **FIX** — was 20, smaller than subheads inside it (VIS-06) |
| `title` | Garamond | 20/28 | 600 | Record titles in lists, dialog titles | KEEP |
| `subsection` | Garamond | 17/24 | 600 | Markdown headings inside the AI Overview | **ADD** — subheads must be smaller than their section |
| `heading` | Inter | 16/24 | 600 | Card headings, table group labels | KEEP |
| `body` | Inter | 15/24 | 400 | Interface text | KEEP |
| `reading` | Inter | 16/28 | 400 | Abstract, AI Overview, Ask IRIS answers — **max 68ch** | FIX (measure cap, LAY-04) |
| `small` | Inter | 13/20 | 400 | Metadata | KEEP |
| `control` | Inter | 14/20 | 500–600 | Buttons, navigation items, menu items, table cells, notices | **ADD** — the step `text-sm` already gives most controls in the codebase; DESIGN.md's ramp does not list it, so adopting this proposal means adding it there |
| `label` | Inter | 13/20 | 600 | Field labels, chips with text, small buttons | KEEP |
| `micro` | Inter | 12/16 | 500 | Status pills, counts, table captions — the floor; nothing smaller | KEEP |

**Rules (all KEEP, now enforced):** sentence case for every label, button, tab and heading; **no uppercase tracked eyebrows** (VIS-02); a size is a role, never a pixel value; numbers in tables use `tabular-nums` and are right-aligned.

---

## 3. Spacing

A 4 px base, used as named steps.

| Token | px | Typical use |
|---|---|---|
| `--s-1` | 4 | Icon-to-label gap inside chips |
| `--s-2` | 8 | Between related controls in a group |
| `--s-3` | 12 | Field label to field; list row inner gap |
| `--s-4` | 16 | Card padding (compact); gutter on phones |
| `--s-5` | 20 | Card padding |
| `--s-6` | 24 | Between page sections; gutter on tablets |
| `--s-8` | 32 | Above a section heading (more above than below) |
| `--s-10` | 40 | Page top padding on desktop |
| `--s-12` | 48 | Between major regions on wide screens |

Containers: page content max **1120 px** (operate pages), reading column max **68ch**, tables may go full width (`width: "full"` in the route handle — KEEP).

---

## 4. Shape and elevation

| Token | Value | Use | Tag |
|---|---|---|---|
| `--r-thumb` | 6 px | Inner thumb of a segmented control, citation chip | KEEP |
| `--r-control` | 12 px | Fields, selects, menus, toolbar controls | KEEP |
| `--r-sheet` | 16 px | Dialogs, popovers, the entry sheet | KEEP |
| `--r-card` | 20 px | Cards that hold a record | KEEP |
| `--r-pill` | 999 px | **Every button**, chips, Ask IRIS button | FIX — Settings and Users used square buttons (VIS-04) |
| `--lift` | `0 4px 12px rgb(0 0 0 / .08)` | Record row hover, Ask IRIS button | KEEP |
| `--float` | `0 12px 32px rgb(41 37 36 / .16)` | Popovers, menus, dialogs | KEEP (drawer edge) |
| `--recess` | inset track shadow | Retired 13 Nov: the segmented track is flat, with a hairline | DROP |

Regions are separated by **one hairline**, never a card plus a gap plus a shadow (Hairline Rule — KEEP).

---

## 5. Components

### Buttons
| Variant | Look | Rule |
|---|---|---|
| Primary | Maroon fill, white label, pill, 44 px (touch) / 40 px (pointer); hover darkens it | **One per row**, the viewer's next step |
| Secondary | White, Rule Stone outline, Ink label → Bar Stone fill on hover (the outline never turns maroon) | Everything else in the row |
| Ghost | No outline, Quiet Ink, Bar Stone wash on hover | Close, Copy, low-stakes actions |
| Danger | Maroon Dark fill **only inside a confirm dialog**; in rows it is a ghost button with a trash/lock icon | CMP-01, US-06 |
| Disabled | Desk Stone fill, Faint Ink label, `cursor: not-allowed`, with a reason line beside it | CMP-05 |

All buttons: sentence case, icon 18 px at 1.75 stroke on the left, focus ring 2 px maroon with 2 px offset.

### Segmented control (tabs within a page)
Flat Bar Stone track with a Desk Stone hairline. The selected segment is **white with a Rule Stone hairline and Ink text**, like GitHub's segmented control; no maroon, no pink ring, no inset shadow (changed 13 Nov at the frontend owner's request: the maroon thumb with a pink ring read as AI-generated). 32 px pointer / 40 px touch. One selected style across the app (VIS-01, VIS-05).

**Tabs** (underlined, e.g. the review pane): the selected tab is Ink text over a 2 px maroon underline; counts sit in a neutral Desk Stone pill that stays neutral when selected.

**Pressed chips** (Filters on, Soonest due) take an Ink outline, like a chosen option card. Status chips are white with their tone in the text and outline.

### Fields
White, **Field Stone outline** (3.49:1), 12 px radius, 44 px tall. Visible label above (13/20 semibold, sentence case), hint below in Quiet Ink, error below in maroon with an alert icon. Focus: maroon outline thickened to 2 px (an inset 1 px maroon ring); no pink halo. Placeholder only shows an example, never the label, never "••••".

### Cards and record rows
A record in a list is a **row**, not a tall card: type · year line, Garamond title, byline, two-line abstract, a 1-line meta/action bar, and an optional 88 × 116 px first-page thumbnail. White, 1 px Desk Stone border, 20 px radius, lift on hover.

### Tables
Bar Stone header row, 13 px semibold Quiet Ink header text, 52 px rows, hairline separators, numbers right-aligned in tabular figures, row actions in a "More actions" menu, first column is the human name. On phones a table becomes a stacked list with the same fields.

### Dialogs
White sheet, 16 px radius, `--float` shadow, Garamond 20 px title, close button top right, primary action bottom right. Escape closes; focus is trapped and returns to the trigger.

### Navigation
- **Sidebar** (≥1024 px): IRIS mark (also the Collapse sidebar / Open sidebar button, as in live IRIS), primary items, a role section with a sentence-case label ("RDCO tools"), Help, then the account button. Current item: Desk Stone fill, Ink semibold text, maroon icon. No left notch: a coloured stripe on a list item is decoration, and the fill already says where you are.
- **Rail** (768–1023 px, and on the Paper view): icons with tooltips that appear on hover **and** keyboard focus.
- **Phone** (<768 px): top bar with the IRIS mark, Publish (labelled, students/advisers), bell, and menu button; the drawer holds the same sections.
- Nested items (My Reviews › Office console, Analytics) indent under their parent, which stays current.

### Status chip
Pill, 12 px semibold, icon + word, one of the four tones (+ Preserved).

### Clearance strip (ADD)
A one-line row of office chips for a record: `Adviser ✓ cleared · ITSO ✓ kept from v1 · IERC ↺ revision requested · KTTO … waiting`. It appears on My Reviews rows, the author's My Library row and the record's Review tab, so clearance-aware resubmission is visible everywhere the record is.

---

## 6. Iconography

One stroked set (Lucide geometry), 1.75 px stroke, 20 px in navigation, 18 px in buttons, 16 px in chips, `currentColor`. Filled icons are reserved for the brand marks (IRIS mark, Ask IRIS bubble). Icon-only buttons always carry an `aria-label` **and** a visible tooltip; primary actions are never icon-only on any breakpoint.

| Concept | Icon |
|---|---|
| Discover | compass |
| Ask IRIS | Ask IRIS brand bubble (not a brain) |
| My Library | bookmark-stack |
| My Reviews | clipboard-check |
| Calls & Conferences | megaphone |
| Publish | plus |
| Save | bookmark |
| Cite | quote |
| Share | link |
| Notes | sticky-note (as the live Notes button) |
| Cleared | check |
| Kept (preserved clearance) | shield-check |
| Revision requested | rotate-ccw |
| Waiting | clock |
| Lock account | lock |

---

## 7. Breakpoints and layout modes

| Name | Width | Layout |
|---|---|---|
| Phone | < 768 | Top bar + drawer; 16 px gutter; one column; tables become lists; 44 px controls |
| Tablet | 768 – 1023 | Icon rail with tooltips; 24 px gutter; two-column forms |
| Laptop | 1024 – 1439 | Full sidebar (240 px); content max 1120 px |
| Wide | ≥ 1440 | Same, with the record page's details column and Ask IRIS column side by side |

The record page keeps its container queries (`reading`, `overview`) — DESIGN.md's Container Rule is unchanged.

---

## 8. Motion

150 ms colour fades; 240 ms for menus and drawers on `cubic-bezier(0.22, 1, 0.36, 1)`; opacity and transform only; nothing moves under `prefers-reduced-motion`. Loading states gain words after 2 s and a Try again after 10 s (FB-02).

---

## 9. Writing rules

- Sentence case everywhere. "Sign in", "Email address", "Change password".
- Say what waits on whom: "Waiting for ITSO", "Your turn: upload the revised manuscript".
- Errors name the problem and the recovery, and never blame the connection unless the browser is offline.
- Loading copy names the thing in the user's words ("Opening the paper…"), never a component name.
- Counts appear only when something is actionable.
