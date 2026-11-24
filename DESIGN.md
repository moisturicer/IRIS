---
name: IRIS
description: CIT-U's research and IP disclosure system, read like a bound volume.
colors:
  binding-maroon: "#6B0F12"
  binding-maroon-light: "#8B1316"
  binding-maroon-dark: "#4A0A0C"
  maroon-thread: "#f9b8b9"
  endpaper: "#fafaf9"
  page-white: "#ffffff"
  bar-stone: "#f5f5f4"
  desk-stone: "#e7e5e4"
  rule-stone: "#d6d3d1"
  faint-ink: "#78716c"
  quiet-ink: "#57534e"
  body-ink: "#44403c"
  ink: "#1c1917"
  # Decided 2026-11-14 (IR-1072); field-stone and the control step are built (IR-1074), as are the highlight tokens (IR-1097).
  # Values are the prototype's, iris-uiux-audit/prototype/styles.css. Maroon Wash (#fdf2f2) is retired.
  field-stone: "#8f8884"
  highlight-yellow: "#f7e08f"
  highlight-yellow-now: "#f2c94c"
  pen-rose: "#b4474b"
  pen-wash: "#fbeaea"
  pen-now: "#f5d5d6"
  maroon-press: "#5a0c0f"
typography:
  display:
    fontFamily: "EB Garamond, Georgia, Cambria, serif"
    fontSize: "48px"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "EB Garamond, Georgia, Cambria, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "28px"
  title:
    fontFamily: "EB Garamond, Georgia, Cambria, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "28px"
  body:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "24px"
  reading:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: "20px"
  control:
    # Decided 2026-11-14 (IR-1072), built in IR-1074 as `text-control`: form fields and page buttons only.
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: "20px"
rounded:
  thumb: "0.375rem"
  control: "0.75rem"
  sheet: "1rem"
  card: "1.25rem"
  pill: "9999px"
spacing:
  section-sm: "16px"
  section: "24px"
  section-lg: "32px"
  card: "20px"
  card-compact: "16px"
components:
  button-primary:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.binding-maroon-light}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.body-ink}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  control-outline:
    backgroundColor: "transparent"
    textColor: "{colors.body-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    height: "36px"
  control-on:
    backgroundColor: "{colors.page-white}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    height: "36px"
  control-filled:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.control}"
    size: "36px"
  control-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.faint-ink}"
    rounded: "{rounded.control}"
    height: "36px"
  section-track:
    backgroundColor: "{colors.desk-stone}"
    rounded: "{rounded.control}"
    padding: "2px"
  section-thumb:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.thumb}"
  record-bar:
    backgroundColor: "{colors.bar-stone}"
    height: "56px"
    padding: "0 20px"
  chip-meta:
    backgroundColor: "transparent"
    textColor: "{colors.body-ink}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  citation-page:
    backgroundColor: "{colors.page-white}"
    textColor: "{colors.binding-maroon}"
    rounded: "{rounded.thumb}"
    padding: "0 6px"
  ask-iris-fab:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.pill}"
    size: "56px"
  profile-note:
    backgroundColor: "{colors.bar-stone}"
    textColor: "{colors.body-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sheet}"
    padding: "8px 8px 8px 16px"
  profile-avatar:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.pill}"
    size: "112px"
  entry-masthead:
    backgroundColor: "{colors.page-white}"
    textColor: "{colors.binding-maroon}"
  entry-sheet:
    backgroundColor: "{colors.page-white}"
    rounded: "{rounded.sheet}"
    padding: "40px 44px"
  entry-tab-current:
    backgroundColor: "{colors.page-white}"
    textColor: "{colors.binding-maroon}"
    typography: "{typography.label}"
    height: "44px"
  entry-tab-completed:
    backgroundColor: "{colors.bar-stone}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    height: "44px"
---

# Design System: IRIS

> **Authority.** `docs/adr/` and `docs/ui-ux/01-design-system.md` govern design decisions; `frontend/tailwind.config.js` defines the implemented tokens. This file is a derived summary, mostly of the record page (Paper and Overview, IR-569), plus the entry screens' Dossier frame (IR-704). Correct the design-system document and token source first, then update this summary and `.impeccable/design.json` when they disagree. A redesign refines this system; it does not replace its palette, type scale or webfont.

## Decided changes, not built yet (IR-1072, 2026-11-14)

Decided by **Lee Jasmin Adolfo** (project lead and frontend owner) on 2026-11-14, from the UI/UX audit ([`docs/frontend_ui_audit_spec.md`](docs/frontend_ui_audit_spec.md) §7.1). The authority is [`docs/ui-ux/01-design-system.md`](docs/ui-ux/01-design-system.md) §0, which says the same in full. **Nothing below is built unless its line says so: until the named ticket lands, the sections after this one describe what ships.** Where this section and a rule below disagree, this section wins once its ticket has landed.

- **D1, fields and controls (IR-1074) — built** for text fields, selects and textareas (outline, placeholder and helper colours; native checkboxes keep the browser's own border, about 4.5:1, until a custom box is drawn; the 14/20 `control` step on `Input`, `Select`, `fieldClasses` and `Button` `md`, `lg` and `page`, while hand-built fields keep their own size until they move onto those primitives). Every input, select, textarea and checkbox is outlined in **Field Stone** (#8f8884, 3.49:1 on white, WCAG 1.4.11). Rule Stone stays only on decorative chips and cards. Form fields and page buttons gain a **14/20 `control`** type step; the reader toolbar's reading controls stay 13 px. Placeholders and helper text are Quiet Ink (#57534e).
- **D4, Discover layout (IR-1082).** The **1 / 2 / 3 column toggle stays**, at Jive's preference: one cycling icon button, hidden below `xl`, at the toolbar's one control height. The **96 px outline thumbnail** replaces the abstract-preview panel in 1 column only; the 2 and 3 column cards are text only.
- **D5, navigation (IR-1085) — built.** **Office console and Analytics nest under My Reviews**, only for the roles that already have them. Their current URLs keep working. The sidebar lists them from `SCREEN_ACCESS` (`parent: "reviewQueue"`), the console for a coordinator only.
- **D6, highlight roles (IR-1097) — built.** Each kind of highlight has one look, and no look means two things. Values are the prototype's:

  | Role | Look |
  |---|---|
  | Action | Maroon fill, one per row |
  | Here (current page, tab or conversation) | Desk Stone fill, Ink text, maroon icon, no side stripe |
  | Selected (an option you chose) | White raised segment or an Ink outline, never maroon |
  | Reference (page citation, source number) | Maroon text on white with a Rule Stone hairline |
  | Match (search, Find) | **Highlight Yellow** (#f7e08f); the current match **#f2c94c**; Ink text on it is 14:1 |
  | Pen (a reviewer's mark) | **Pen Rose**: fill #fbeaea, 2 px underline #b4474b, a numbered pin; the open thread's passage #f5d5d6 |
  | Highlight (the reader's own) | Binding Maroon at 15% opacity, multiplied, no edge or underline; a swatch of it names it in the selection menu and Notes (IR-581) |
  | Status | White chip, tone in text and outline; none is filled (IR-1290 reverses "only Attention is filled") |

  **Maroon Wash (#fdf2f2) is retired from the interface** and stops being the "on" tint. **Maroon Press** (#5a0c0f) is the pressed state of a filled button. Yellow is reserved for matches and rose for a reviewer's marks, and nothing else uses either. The **Four Inks Rule** becomes: white, black, stone and maroon, plus one yellow highlighter for matches and one rose pen for a reviewer's marks. The tokens are `hl`, `hl-now`, `pen`, `pen-wash`, `pen-now` and `brand-press` in `tailwind.config.js`, and the roles are class strings in `frontend/src/components/ui/highlightRoles.ts`. `palette.test.ts` keeps `brand-50`, `brand-100`, `brand-200`, gold, cream and the loose hexes out of the source. IR-1097 also edited this file's rules below.
- **D7, status colours (IR-1290) — built.** Part of D6 is reversed, by the project lead. Maroon marked the main action, the overdue warning, "in review", errors and the focus ring, so on the RDCO review card a solid maroon "10 working days overdue" chip sat beside a solid maroon "Claim review" button and looked the same, and the three cleared offices were the quietest text on the card. Two status hues are added, a green and an amber, and **solid maroon is left to the one primary action**:

  | Meaning | Look | Token |
  |---|---|---|
  | Cleared, kept (an office's clearance carried over) | Green text, green outline | `cleared` #1E6B3F (text, 6.5:1 on white), `cleared-line` #3F8A5A (outline, glyph, 4.2:1), `cleared-wash` #EAF3EC |
  | In review, reset (an office that must review the new version) | Amber text, amber outline | `review` #8A5300 (text, 6.3:1), `review-line` #B07A1E (outline, glyph, 3.7:1), `review-wash` #FBF0DA |
  | Attention (overdue, declined, an error) | **Maroon outline on white, with its icon, never filled** | `ring-brand` on `surface` |
  | Quiet, settled | Unchanged | `stone` |

  The clearance strip reads `kept` and `cleared` green, `reviewing` amber, `unclaimed` stone, and `revision` and `not_cleared` maroon, so a resubmission that kept two offices and reset one reads green, amber, green at a glance. Its words still come only from the server (IR-1083). **Amber is only ever an outline, a glyph and a word on white, never a flat fill behind text**, so it cannot be mistaken for the search-match yellow (`hl`). **Gold is not part of this change** and stays out of the interface. Every status keeps an icon plus a word, so in greyscale every state can still be told apart. The tokens are in `tailwind.config.js` and the tones in `frontend/src/components/ui/statusTones.ts`.

## Overview

**Creative North Star: "The Bound Volume"**

IRIS should read like a bound thesis in a university library. The cover is maroon, the titles are set in Garamond, and the pages are typeset with hairline rules. Everything else stays quiet so the work can be read. The paper is the one bright object on screen: on the Paper view, only the PDF pages are white, and the record bar, the toolbar, the Ask IRIS header and the desk behind the pages are stone. On the Overview, the page reads as one typeset column, with a Garamond title sized by its length, a byline of people pills, the actions, and then sections divided by thin rules like the sections of a printed paper.

Maroon is the binding, not the paint. It appears once or twice per view: the filled action, the selected section, the Ask IRIS mark and the page citations. Structure comes from type, space and one-pixel rules, never from boxes. The layout follows the room it has, not the window. The record page measures its own width with container queries, so the sidebar or the Ask IRIS panel beside it changes the layout as surely as a smaller screen does.

Rejected outright: cards wrapped around reading content, controls floating over content, and any colour outside maroon, stone, white and black.

**Key Characteristics:**
- One bright object: the paper (PDF pages, or the Overview column on its endpaper ground).
- Garamond for what you read the title of; Inter for everything you operate.
- Hairlines between regions, never cards, gaps or shadows between them.
- One filled maroon action per row; everything else outlined or ghost.
- One control scale: 44 px on touch, 36 px beside a pointer.
- Width read from the container (`reading`, `overview`), not the viewport.

## Colors

A monochrome stone volume with one maroon binding; no other hue exists in the interface.

### Primary
- **Binding Maroon** (#6B0F12): the institution's identity. The one filled action in a row (View, Continue, Send), the selected section thumb, the Ask IRIS icon, the focus ring, and, as an outline or text only and never a fill, error, rejection and overdue states (IR-1290). 12.3:1 on white.
- **Binding Maroon Light** (#8B1316): hover on maroon fills only.
- **Binding Maroon Dark** (#4A0A0C): destructive actions (with a warning glyph) and dark accents.
- **Maroon Thread** (#f9b8b9): the browser's text selection. **Maroon Wash (#fdf2f2) is retired** (IR-1097): the "on" tint did about fifteen jobs, and each now has its own look (see Decided changes, D6).
- **Maroon Press** (#5a0c0f): the pressed state of a filled maroon button.
- **Highlight Yellow** (#f7e08f, current match #f2c94c): a word a search or Find matched, and nothing else. Ink on it is 14:1.
- **Pen Rose** (underline #b4474b, fill #fbeaea, open thread #f5d5d6): a reviewer's mark on a passage, and nothing else.
- **Cleared Green** (text #1E6B3F, outline #3F8A5A, wash #EAF3EC): an office that cleared a record or whose clearance was kept, and nothing else (IR-1290).
- **Review Amber** (text #8A5300, outline #B07A1E, wash #FBF0DA): a review in progress, or an office reset by a new version. An outline, glyph and word on white, never a flat fill behind text (IR-1290).

### Neutral
- **Endpaper** (#fafaf9): a section fill (`stone-50`) where white on white would lose an edge, such as the Ask IRIS conversation list and table headers. Since IR-1132 the ground under every screen (`canvas`) is white, not Endpaper.
- **Page White** (#ffffff): the PDF pages, fields, cards that hold records, dialogs and menus (`surface`, `overlay`).
- **Bar Stone** (#f5f5f4): the record bar, the reader toolbar, the Ask IRIS header, and the "Not open yet" chip.
- **Desk Stone** (#e7e5e4): the desk behind the PDF pages, the recessed section track, and the hairlines between sections and regions.
- **Rule Stone** (#d6d3d1): resting outlines on controls and chips, and the line between the reader and Ask IRIS.
- **Faint Ink** (#78716c): metadata, timestamps, hints and ghost controls.
- **Quiet Ink** (#57534e): secondary lines and inactive tab labels.
- **Body Ink** (#44403c): running text and outlined control labels.
- **Ink** (#1c1917): titles, section headings and the *settled* status.

### Named Rules
**The Binding Rule.** Maroon marks at most the one filled action, the current section and citations on any screen. If two filled maroon things compete in one row, one of them is wrong. A status is never a solid maroon fill (IR-1290), so nothing that is only a status can look like the action.

**The Four Inks Rule.** The palette is white, black, stone and maroon (light, dark and press), plus one yellow highlighter for matches and one rose pen for a reviewer's marks, plus, for status only, one green and one amber (IR-1290). `brand-400` to `brand-600` are bright reds, not maroon, and are never used. Status is carried by five tones plus an icon and a word, never by any other hue (`palette.test.ts` enforces this).

Gold and cream are gone (IR-1097): the thumbnail ring and the other decoration were off palette, and the Folio Ribbon logo never used them.

**The One Bright Object Rule.** On the reading surfaces, only the thing being read is white. Bars, toolbars and headers around it are stone.

## Typography

**Display Font:** EB Garamond 600 (with Georgia, Cambria)
**Body Font:** Inter Variable (with the system sans stack)

**Character:** Garamond gives the title and section heads the voice of a printed thesis; Inter keeps every control, label and number plain and legible. Only Garamond 600 is loaded, so it never appears at another weight.

### Hierarchy
- **Shared app roles:** `text-display` 28/34, `text-title` 20/28, `text-heading` 16/24, `text-body` 15/24, `text-small` 13/20 and `text-label` 12/16 come from `frontend/tailwind.config.js`. Display and title use EB Garamond 600; the other roles use Inter. The record page below has documented reading-specific sizes.
- **Display** (EB Garamond 600, tight tracking, balanced wrap): a record's title on the Overview. The one line the page exists to name. Its size follows its length (IR-1264), read from the `overview` container, never the window: up to 80 characters 48 px (36 px below 40 rem), up to 160 characters 36 px (28 px), longer 30 px (24 px). It is never cut.
- **Headline** (EB Garamond 600, 20/28 px): section headings on the Overview (Abstract, AI Overview, Related works, Comments) and the Ask IRIS heading. Ink, never maroon.
- **Title** (EB Garamond 600, 20/28 px): the paper's title in the record bar, wrapping onto as many lines as it needs (the Full Text Rule; it was one truncated line before IR-1218); dialog and card titles.
- **Reading** (Inter 400, 16 px, line-height 1.8): the AI Overview's prose, filling the Overview column. Every paragraph reads at 16 px with 1.75 leading, the same as an Ask IRIS answer (IR-1306; the 17 px lead is retired). Markdown section headings inside it are maroon Garamond (21 / 19 / 18 / 17 px, IR-1306) with space above and no rule; list markers are maroon. The Abstract reads at 17 px with 1.75 leading.
- **Body** (Inter 400, 15/24 px): interface text.
- **Label** (Inter 600, 13/20 px): every control's text. Metadata is the 13 px `small` role at weight 400; field labels are 12/16 px.

### Named Rules
**The Typeset Title Rule.** Garamond is for what you read the title of (a paper, a section, a dialog). It never sets a control, a chip or a number.

**The Named Size Rule.** A size is asked for by role (`text-title`, `text-small`), never by pixel (`text-[13px]`). Nothing goes below 11 px, and labels are sentence case, never small tracked capitals.

## Layout

The record page is a container named `reading`, and the Overview column is its own container named `overview`, so the layout reads the width it is given.

- **Paper tiers** (from the `reading` width): below 640 px Ask IRIS fills the workspace and offers Back to paper; from 640 px it is a drawer over the paper (a modal with a stone scrim); from 1000 px it is a column beside the paper, which keeps at least 640 px. The Paper view is full height: the record bar, then the reader beside Ask IRIS.
- **Record bar on a phone** (below 640 px of the `reading` width, so a phone or any narrow workspace, not the window): one 56 px row, never two. Back is its icon, the Overview / Paper / Review control takes the rest of the row, and the title is not drawn (it stays as the page heading for screen readers). The version moves out of the bar to the start of the reader's toolbar, where it is drawn once.
- **Touch size:** every control is 44 px on a touch pointer. The `touch:` variant is the `(pointer: coarse)` media query, not a width: the shared `Button` (`sm`, `md`, `lg`, `icon`) and the app shell's controls use it, so a touch tablet gets 44 px at any window width. The reading surfaces keep their own scale, 44 px below 640 px of the `reading` width and 36 px from it.
- **Ask IRIS width:** 450 px by default, from 320 px to half the workspace, resizable from its left edge and remembered per browser. On the Overview it is a column the page makes room for; it never covers the page. With it open the Record details rail folds away and the Overview column is centred in the room left, not held against its left edge (IR-581).
- **Overview column:** one column up to 60 rem (960 px), set against whatever is beside it (Ask IRIS, or Record details) with the spare room on its left, a 56 px left gutter (16 px on a phone) and a 32 px right one. Record details sit beside the page in a 22 rem sticky column while the Overview container is 64 rem or wider, under it otherwise, and fold away while Ask IRIS is open.
- **Rhythm:** sections inside the Overview are 32 px above and below a Desk Stone hairline. The gaps between a page's sections are 16 / 24 / 32 px; card padding is 20 px (16 compact).
- **Motion:** 150–200 ms colour fades; layout moves (the section thumb, the Record details fold, Ask IRIS arriving from its edge) take 300–320 ms on `cubic-bezier(0.22, 1, 0.36, 1)`. Opacity and transform only for anything that appears, and nothing moves under reduced motion.

### Named Rules
**The Container Rule.** Read the container, never the window. A `lg:` breakpoint on a reading surface is a bug: the sidebar and Ask IRIS change the room without changing the window.

**The Flush Column Rule.** Reading text fills its column and meets what is beside it; the column, not the text, sets the measure.

**The Full Text Rule (IR-1218).** Text is given its whole box, reflows with it, and is never cut. It holds for every paragraph, title, label, name and message, in every surface.

1. **Text fills the width it is given.** It runs to the end of its box (a column, a card, a cell, a dialog) or the screen before it breaks. No width cap narrower than the box (`max-w-*`, a fixed `w-*`, a `ch` measure) stops it early and leaves empty space beside it. A narrow box is fine; a narrow cap inside a wider box is not.
   - Good: a card's title wraps at the card's edge.
   - Bad: an abstract capped at 65 characters in a 900 px column, with the right third empty.
2. **Text re-wraps only when its space changes.** Narrow the window or the box and lines break sooner; widen it and they spread back out. No `<br>`, fixed line count or per-breakpoint text written for one screen size.
   - Good: a heading on two lines at 360 px and one line at 1280 px.
   - Bad: a heading hand-broken after its third word, which leaves a short ragged line on a wide screen.
3. **Text is never cut off or hidden.** No ellipsis (`truncate`, `text-ellipsis`, `line-clamp-*`), and nothing that hides the end of text: a fixed height or `overflow-hidden` on text, or `whitespace-nowrap` on text that can be long. Long unbroken strings (an email, a URL, a file name) break with `break-words`; they do not spill out or get cut.
   - Good: a long paper title wraps onto three lines in the record bar.
   - Bad: `Rainwater Harvesting in Urban Ce…` with the rest unreachable.
4. **Long reading text is justified (IR-1221).** Paragraphs a person reads through take `text-justified` (`index.css`): both edges straight, with automatic hyphenation (it needs the page's `lang="en"`). That means an abstract, the AI Overview's paragraphs, Help, a call's description, the data notice, review comments, thread bodies and replies, timeline entries, the response letter, revision, rejection, routing and document-request reasons, the Publish form's abstract, and reported comments and download-request notes in admin. Titles, headings, labels, buttons, badges, table cells and form fields stay left-aligned, and so does text clamped to a few lines (a list card's abstract preview, a call's description on the board), whose last visible line would be stretched. It holds at every width, phones included (decided by Hermoine Zozobrado, 2026-11-18): a narrow box gets slightly wider word gaps. A paragraph's last line stays left, so a one-line comment reads as before.
   - Good: an abstract whose lines all end at the column's edge, at 360 px and at 1745 px.
   - Bad: a justified button label or table cell, or a heading stretched across its box.

**The seven allowed cuts.** These, and only these, may end in an ellipsis. Anything else needs this rule changed first. The guard test `src/test/fullTextRule.test.ts` fails on any `truncate`, `text-ellipsis` or `line-clamp-*` that is not one of them (IR-1219).
- **A long file name in a table cell** may stay on one line, so one name does not make its row tall. Its full name is shown on hover and on keyboard focus (a `title` alone is not enough: it does not show on focus), and is read in full by screen readers.
  - Good: `Final_Thesis_Manuscript_Revi…` whose cell shows the whole name when hovered or focused, and is announced whole.
- **An abstract's preview in a list card** (Discover, a person's profile) may be clamped to its few lines. The card links to the paper's page, where the whole abstract is shown, never cut.
  - Good: Discover's card ends its abstract in `…`; opening the paper shows all of it.
  - Bad: the same clamp on the paper's own page, in review, or anywhere that is not a preview with a link to the full text.
- **A long review comment's opening** (over 300 characters) may end in `…` with a **See more** button after it, which shows the whole comment in place. The button is reachable by keyboard and says what it does. Added by IR-1219 (decided by Hermoine Zozobrado, 2026-11-19): a thread of long comments stays quick to scan.
  - Good: a reviewer's long comment shows its first lines, and See more shows the rest without leaving the thread.
  - Bad: a comment cut with no See more, or a See more that opens another page.
- **A call's description on the Calls board** may be clamped to two lines, with a **Show more** button on the card that shows the whole description in place and becomes **Show less**. Added by IR-1219 (decided by Hermoine Zozobrado, 2026-11-19): board cards stay even and quick to scan. The board offers no other way to the full description (*View & apply* leaves IRIS, and not every call has it), so the button is what makes this cut allowed.
  - Good: a long call description ends in `…` and Show more beneath it; pressing it shows all of it on the card.
  - Bad: the clamp without Show more.
- **Discover's rotating example search** (the hint in the empty search box) stays on one line and may end in `…`. It is decorative: hidden from screen readers, gone as soon as you type, and no example is needed to search. Added by IR-1219 (decided by Hermoine Zozobrado, 2026-11-19), so the box does not change height as the hints rotate.
  - Bad: the same one-line cut on the search box's label, its help text, or anything a person types.
- **A paper's title in the reading bar** (the 56px row above a paper, from the reading-split width up) stays on one line and may end in `…`. The full title shows on hover and focus, screen readers read it whole, and the Overview tab shows it in full. Added by IR-1219 (decided by Hermoine Zozobrado, 2026-11-19): the bar is one row (IR-1092), and Paper Chat's dock and the reading pane are sized from its fixed height, so a wrapped title would spill over the paper.
  - Good: a long title ends in `…` in the bar; resting on it shows the whole title.
  - Bad: the same cut on the Overview's own title, or a reading-bar title with no full text on hover.
- **A conversation's title in Ask IRIS's list** stays on one line and may end in `…`, with one **⋯** menu (Pin, Rename, Delete) in place of row buttons. While a title is cut, it shows whole in a tooltip on hover and on keyboard focus (a `title` alone is not enough). Screen readers read it whole, and the conversation shows it. Added by IR-1253 (asked for by Hermoine Zozobrado, 2026-11-21, "exactly like a Claude chat"): wrapped, a long title reflowed onto more lines whenever the row's buttons appeared on hover, and the row jumped in height.
  - Good: `Rainwater harvesting in urban ce…` in the list; focusing it shows the whole title, and opening it shows it in the conversation.
  - Bad: the same cut on the conversation's own heading, or a cut title with no tooltip on keyboard focus.

## Elevation & Depth

Flat. Depth comes from tonal layering: Endpaper ground, stone bars, white pages. Reading regions are divided by one-pixel stone hairlines, not by shadow or gaps. Elsewhere, a card is white with a one-pixel `stone-200` border and no resting shadow. Shadow is kept for what floats or is pressed:

- **Card lift** (`box-shadow: 0 4px 12px 0 rgb(0 0 0 / 0.08)`): the Ask IRIS icon, and a record card on hover.
- **Drawer edge** (`box-shadow: -12px 0 32px rgb(41 37 36 / 0.12)`): Ask IRIS as a drawer over the paper, one soft leftward shadow.
- **Recess** (`box-shadow: inset 0 1px 3px rgb(41 37 36 / 0.28), inset 0 0 0 1px rgb(41 37 36 / 0.07)`): the section track, pressed into the record bar.

### Named Rules
**The Hairline Rule.** Two regions are separated by one Desk Stone or Rule Stone line. Never a card, a gap and a shadow at once.

## Shapes

Gently rounded and consistent. Controls and fields take one radius (0.75 rem), and so do section tabs such as My Library's, like the sidebar's highlighted item (IR-1329); page actions, chips and the Ask IRIS icon are full pills; cards that hold a record are 1.25 rem. A concentric inner shape, such as the section thumb inside its track, is one step smaller (0.375 rem), and that is the only use of the smaller radius. A thick accent border never sits on a rounded shape.

## Components

### Buttons
Quiet and exact.
- **Page actions** (View, Save, Cite, Share, Edit details): 44 px full pills, 20 px side padding, 14 px semibold. **One** Binding Maroon fill per row (View where there is a paper, otherwise Save; Continue or Open review when those are the viewer's job); the rest have no fill and a Rule Stone outline that turns maroon on hover.
- The shared implementation is the `Button` component (`frontend/src/components/ui/Button.tsx`, IR-1088): a pill in every text size, with `size="page"` as the 44 px page action, and one disabled look for every variant, Desk Stone with Faint Ink, plus an optional `disabledReason` line beside it. Only the `icon` size keeps the 0.75 rem radius, so a `Button` is a pill wherever it is used, not only for page actions (audit VIS-04; this supersedes the 0.75 rem control radius in Shapes above for labelled buttons). A disabled ghost takes the same Desk Stone fill as the others. Screens not yet moved onto it still use `PILL_PRIMARY` and `PILL_SECONDARY` in `frontend/src/components/ui/pillStyles.ts`, which draw the same pill. Danger uses `brand-dark` with a warning glyph.
- **Reading controls** (record bar, reader toolbar, Ask IRIS): 44 px on touch and 36 px beside a pointer, 0.75 rem radius, 13 px semibold. Three states: outlined at rest, an Ink outline on white when on, and the one filled control (Send).
- **Ghost** (Copy on the AI Overview, Close): no outline, Faint Ink, a Bar Stone wash and Ink text on hover.
- **Focus:** a 2 px Binding Maroon ring with an offset on every interactive element (`FOCUS_RING` in `frontend/src/components/ui/interaction.ts`). That file also defines `COLOUR_TRANSITION` for the 150 ms hover/focus fade.

### Save menu (IR-566)

One bookmark control, an outlined icon on a Discover card and a pill on the Record page, filled once the paper is saved. Its menu has three sections divided by Rule Stone lines: **Reading status** (Want to read, Reading, Completed; choosing the checked one clears it but keeps the save), **Save to My Library / Remove from My Library**, and **Your folders**, which closes with one stone-500 line saying that saves, reading status and folders follow the account (IR-572). Filing a paper in a folder saves it; taking it out of a folder leaves it saved. Once the account holds the most folders it may, the new-folder field is disabled and that line says so instead. A failed save, removal or filing returns the previous state and says so in a `role="alert"` line where the reader acted, never silently. There is no Star: Save covers it.

### Section tabs
The record's sections (Overview, Paper, Review, Files) are a recessed Desk Stone track in the record bar, with a Binding Maroon thumb that slides to the current one over 300 ms. The current label is white; the others are Quiet Ink and turn maroon on hover.

### Chips
- **Meta chips** (record type, classification, flags): full pills, no fill, Rule Stone outline, 13 px semibold Body Ink.
- **People pills** (IR-1264): one per author and one for the Adviser, in one row under the title. A Bar Stone pill, 44 px tall in a reading area narrower than 640 px and 36 px from there (the reading surfaces' control size), holding a 28 px initials disc and the name; an author's disc is maroon, the Adviser's white with a Rule Stone ring, and the Adviser's name is followed by "· Adviser" in Quiet Ink. A pill with a profile is a link (Desk Stone and maroon text on hover); one without is plain text.
- **Status:** `TONES` in `frontend/src/components/ui/statusTones.ts` defines four tones only. *Quiet* is unfilled with a stone outline, *active* is white with maroon text and a Rule Stone outline, *attention* is solid maroon (the only filled tone), and *settled* is an Ink outline on white. Each carries its word, and stopping states also carry an icon.
- **Scope chip** ("This paper" / "All papers") in the composer: white with a Rule Stone outline and a maroon dot; filled maroon when widened to all papers.

### Citations
In the AI Overview a citation is the page it cites: "p8", 12 px semibold maroon on white with a Rule Stone hairline, at the baseline of the text, linking to that page. Chat citations stay small numbered markers: 12 px semibold maroon on a white square with a Rule Stone hairline, and the same numbers appear on the answer's sources button.

### Inputs / Fields
A white field with a Rule Stone outline and the control radius. Focus darkens the outline to maroon with a soft maroon ring. A disabled field sits on Endpaper with a not-allowed cursor and says why beside it. Paper Chat's composer holds the scope chip and Send inside its field. The Ask IRIS page's composer is one line that grows with the question up to a cap, over a row of round icon controls (attach, closed until uploads exist; compare) and a Bar Stone settings pill whose menu offers only what the server supports. Send is Bar Stone until there is something to send.

### Toasts (IR-764)
A toast reports the outcome of something the reader just did, in the bottom-right corner, over the page and never inside it, so nothing on the screen moves. A success leaves after about 4 seconds. An error that offers a way out carries **one action** (such as Try again) beside Dismiss and stays until the reader takes it or dismisses it; taking the action closes the toast. It names what failed ("Could not build the calendar file for ICCE 2027. Try again."). Calls & Conferences reports its calendar failure this way instead of a line that grew inside the row. A decision the reader must make first is a dialog, a field's error stays under its field, and a page that didn't load keeps its own error state.

### Navigation
- **Record bar:** 56 px, Bar Stone, a Desk Stone hairline under it. Back (always labelled), a hairline divider, the paper's title on Paper, then the section tabs.
- **Ask IRIS icon:** a 56 px Binding Maroon circle at the bottom right with the white Folio Ribbon Ask IRIS glyph, shown only while the panel is closed, lifting 2 px on hover.

### Ask IRIS panel (signature)
A column on Endpaper behind one Rule Stone line, never a card. A Bar Stone header with the Garamond heading, an "AI" tag and the paper's title. Below it, the conversation, or a Garamond "Ask about this paper." with three starter questions in a hairline list (`StarterQuestions`, shared with the Ask IRIS page). At the bottom, the composer. It arrives from its edge (320 ms) and has dialog semantics only when it covers the paper.

### Record details (IR-1264)
The rail beside the Overview says what the record is held under and, for those in its review, where it stands. **Status** is drawn here, never under the title: the first line of **Review & routing** for a participant (one line per party with its outcome and the *Preserved* mark, then *See review history*, which opens Review), a *Status* row in **About this record** for anyone outside the review while the record is not published, and nothing on a published paper. **About this record** shows only the rows that say something (no em dash, *Not declared* or *Not flagged*) to anyone outside the review; its owners and reviewers see every row, decided by participation, never by role (IR-411). The owner's waiting work is the revision banner and document requests at the top of the Overview; there is no separate summary card.

### Overview sections (signature)
Abstract, AI Overview, Related works and Comments, each under one Desk Stone hairline, each with a Garamond headline. The AI Overview is the one exception to no cards (IR-1306): a `rounded-card` with a white header (maroon mark disc, Garamond heading, a ghost Copy), a `stone-50` body and a footer line saying AI wrote it, so a reader never mistakes it for the authors' text. Comments are drawn and plainly closed (disabled field and Post, "Not open yet") until the feature exists.

### Entry frame: the Dossier Folder (signature)
Sign in, register, email verification and the pending and declined screens share one frame (`EntryFrame`, IR-704), read like a file handed across a registry desk.
- **Masthead:** a white bar with a Desk Stone hairline under it, the page's one visible h1: the IRIS mark and maroon wordmark, a hairline divider and the CIT-U logo, both at their natural proportions. Sign in and register carry the link to each other here, at least 44 px, at every width.
- **Lede** (sign in and register only): a Garamond 600 headline, 36 px on a phone to 60 px from `lg`, Ink with its last words in Binding Maroon, and one plain Body Ink sentence. Below `md` it is left-aligned and the sentence follows the folder, so the first field stays in the first screenful.
- **Folder:** index tabs on the top edge of one Page White sheet (1 rem radius, `stone-200` border, card lift; the tabs' top corners are 0.75 rem), with a Bar Stone sheet offset behind it. The tab joined to the sheet is white with a 2 px maroon top edge and maroon label text. Sign in, verification and the pending screen have one tab that only labels the sheet.
- **Register stepper:** completed tabs carry an Ink check and a solid Rule Stone outline on Bar Stone and link back; the current tab is joined to the sheet with a maroon number; tabs not started are dashed and cannot be reached. Below 390 px only the current tab shows its name, the others their mark.
- **Footer:** CIT-U identity in 13 px Quiet Ink under a hairline, and no policy link until the policies exist.
- **Motion:** the sheet settles once (280 ms, 0.5 rem rise and fade, a recorded exception to the 150–200 ms rule because it runs once on load) and register's steps cross-fade (150 ms), both only when motion is welcome.

Replaced the split screen with its "shelf of bound work" brand panel (IR-535, IR-586), deleted in IR-711.

### Profile and Settings (IR-933)
Two pages. **Profile** reads like a short typeset entry: an initials avatar (112 px, maroon with white Garamond initials) or the person's photo beside a Garamond name, the role and the affiliation, then About and Research interests, each under one hairline. A field left empty is left out. On your own profile a Bar Stone **note** strip says this is how others see you and that it is changed in Settings; it holds no control (IR-1304). **Settings** opens on its **Profile** section, the same sections as fields (photo and name, About you), closed by Discard changes and Save; Save stays on the section with a "Profile saved." line and a link to the Profile. The other Settings sections hold the account: sign-in and password, consent, and role.

### Another person's Profile (IR-700)
The same typeset entry as your own, at `/people/:id`, with a second column. **Collaborators** (a 40 px avatar, a name link and "N shared papers") sit beside the sections once the page's own width reaches 48rem, behind one vertical hairline, and fall under them behind the same hairline laid flat; the layout reads the `profile` container, never the window. Research and Advised are compact `ResearchCard`s with only their own views, ten at a time with Show more, and Collaborators load twelve at a time. There are no totals, no citation counts and no email; a section with nothing in it is left out. A name with no visible Profile is plain text, and a hidden person is the standard not-found screen.

### Handbook pages (2026-11-23)
Setup and Workflow analytics share one layout (`Handbook`): a Contents rail beside one typeset column, read from the page's own `handbook` container (52rem), never the window. Below that the rail becomes a wrapping row of pills. The item being read or edited takes the Here look. Setup's requirement rows are numbered in RDCO's order with their controls and Template slot. **Guidelines shows one record type at a time**, chosen from a segmented control (the choice is the address's `#type`), and answers in reading order: What you submit (the Manuscript), Have these ready (Required), Only if they apply (Optional, folded away); the group names Required or Optional once, so rows carry no badge or number. Sections are Garamond headings over one hairline, never cards; analytics tables are ruled with hairlines, zeros step back to Faint Ink, and time in stage draws a thin decorative bar beside each figure. Full detail: `docs/ui-ux/01-design-system.md`, Handbook amendment.

### Identity (IR-744)
**Folio Ribbon.** The mark is a serif I standing in the gutter of an open folio: four maroon pieces (two leaves, two ribbons), with the I as the white space between them. `IrisMark`, `IrisWordmark`, `IrisLoader`, `SearchGlyph` and `AskIrisGlyph` (`frontend/src/components/brand/IrisBrand.tsx`) fill with `currentColor`: maroon on white, white only on maroon. The loader replays the concept's storyboard (one leaf, its partner, the ribbons, then the I) on a 2 s loop; Ask IRIS is a speech bubble with the mark's serif I cut out of it; answering sets that I in type (top serif, stem, bottom serif). Both fade instead under reduced motion. Assets and their build: `docs/brand/folio-ribbon/final/`.

## Do's and Don'ts

### Do:
- **Do** keep exactly one filled Binding Maroon action per row, and make it the viewer's next step.
- **Do** separate regions with one Desk Stone (#e7e5e4) or Rule Stone (#d6d3d1) hairline.
- **Do** keep the paper the only white thing on the Paper view; bars and headers are Bar Stone (#f5f5f4).
- **Do** take control sizes from the reading scale (44 px touch, 36 px pointer) and read the `reading` or `overview` container for every layout change.
- **Do** set titles and section headings in EB Garamond 600 and everything operable in Inter.
- **Do** show unbuilt features as visibly closed (disabled, with a line saying so), never as working and never filled with invented content.
- **Do** keep motion to opacity and transform, 150–320 ms, and none under reduced motion.

### Don't:
- **Don't** wrap reading content (the Abstract, the reader, Ask IRIS) in a card. The AI Overview is the one exception, so its provenance is unmistakable (IR-1306).
- **Don't** float controls over content. Controls live in a bar or toolbar. The two corner icons are Notes, above Ask IRIS, and both keep clear of the reading text: Overview and Paper reserve bottom padding so the last line scrolls past them.
- **Don't** use any colour outside maroon, stone, white and black: no green, amber, blue, gradients or glows, and no `brand-400` to `brand-600`.
- **Don't** use a `lg:` (window) breakpoint to size or arrange anything on the record page.
- **Don't** give reading text its own narrow measure inside the Overview column, or leave a gap between it and the Ask IRIS panel.
- **Don't** cut text off with an ellipsis, a line clamp or a fixed height, or cap it narrower than its box. The seven allowed cuts are named in the Full Text Rule.
- **Don't** add an outlined button where a ghost one is enough. The AI Overview does say it is AI-generated (IR-1306).
- **Don't** put a thick accent border on a rounded shape. The one recorded exception is the entry folder's tab joined to the sheet (`EntryTab`, and register's current step), whose 2 px maroon top edge is the approved Dossier direction (the `border-accent-on-rounded` exception in `.impeccable/config.json`).
