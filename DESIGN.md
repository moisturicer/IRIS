---
name: IRIS
description: CIT-U's research and IP disclosure system, read like a bound volume.
colors:
  binding-maroon: "#6B0F12"
  binding-maroon-light: "#8B1316"
  binding-maroon-dark: "#4A0A0C"
  maroon-wash: "#fdf2f2"
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
    backgroundColor: "{colors.maroon-wash}"
    textColor: "{colors.binding-maroon}"
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
    backgroundColor: "{colors.maroon-wash}"
    textColor: "{colors.binding-maroon}"
    rounded: "{rounded.thumb}"
    padding: "0 6px"
  ask-iris-fab:
    backgroundColor: "{colors.binding-maroon}"
    textColor: "{colors.page-white}"
    rounded: "{rounded.pill}"
    size: "56px"
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

## Overview

**Creative North Star: "The Bound Volume"**

IRIS should read like a bound thesis in a university library. The cover is maroon, the titles are set in Garamond, and the pages are typeset with hairline rules. Everything else stays quiet so the work can be read. The paper is the one bright object on screen: on the Paper view, only the PDF pages are white, and the record bar, the toolbar, the Ask IRIS header and the desk behind the pages are stone. On the Overview, the page reads as one typeset column, with a large Garamond title, a byline of chips, the actions, and then sections divided by thin rules like the sections of a printed paper.

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
- **Binding Maroon** (#6B0F12): the institution's identity. The one filled action in a row (View, Continue, Send), the selected section thumb, the Ask IRIS icon, error and rejection states, and the focus ring. 12.3:1 on white.
- **Binding Maroon Light** (#8B1316): hover on maroon fills only.
- **Binding Maroon Dark** (#4A0A0C): destructive actions (with a warning glyph) and dark accents.
- **Maroon Wash** (#fdf2f2): the "on" tint. A switched-on control, the scope chip, a page citation, an *active* status chip, a search highlight.
- **Maroon Thread** (#f9b8b9): the outline drawn around a Maroon Wash fill.

### Neutral
- **Endpaper** (#fafaf9): the ground under every screen (`canvas`), and the ground the Overview and the Ask IRIS panel sit on.
- **Page White** (#ffffff): the PDF pages, fields, cards that hold records, dialogs and menus (`surface`, `overlay`).
- **Bar Stone** (#f5f5f4): the record bar, the reader toolbar, the Ask IRIS header, and the "Not open yet" chip.
- **Desk Stone** (#e7e5e4): the desk behind the PDF pages, the recessed section track, and the hairlines between sections and regions.
- **Rule Stone** (#d6d3d1): resting outlines on controls and chips, and the line between the reader and Ask IRIS.
- **Faint Ink** (#78716c): metadata, timestamps, hints and ghost controls.
- **Quiet Ink** (#57534e): secondary lines and inactive tab labels.
- **Body Ink** (#44403c): running text and outlined control labels.
- **Ink** (#1c1917): titles, section headings and the *settled* status.

### Named Rules
**The Binding Rule.** Maroon marks at most the one filled action, the current section and citations on any screen. If two filled maroon things compete in one row, one of them is wrong.

**The Four Inks Rule.** The palette is white, black, stone and maroon (with its tints, light and dark). `brand-400` to `brand-600` are bright reds, not maroon, and are never used. Status is carried by four tones plus a word, never by a new hue (`palette.test.ts` enforces this).

Gold (`gold.DEFAULT`, about 2.8:1 on white) stays decorative, as on the logo. It is never text or the only status signal.

**The One Bright Object Rule.** On the reading surfaces, only the thing being read is white. Bars, toolbars and headers around it are stone.

## Typography

**Display Font:** EB Garamond 600 (with Georgia, Cambria)
**Body Font:** Inter Variable (with the system sans stack)

**Character:** Garamond gives the title and section heads the voice of a printed thesis; Inter keeps every control, label and number plain and legible. Only Garamond 600 is loaded, so it never appears at another weight.

### Hierarchy
- **Shared app roles:** `text-display` 28/34, `text-title` 20/28, `text-heading` 16/24, `text-body` 15/24, `text-small` 13/20 and `text-label` 12/16 come from `frontend/tailwind.config.js`. Display and title use EB Garamond 600; the other roles use Inter. The record page below has documented reading-specific sizes.
- **Display** (EB Garamond 600, 36 px on a phone and 48 px from `sm`, line-height 1.08, tight tracking, balanced wrap): a record's title on the Overview. The one line the page exists to name.
- **Headline** (EB Garamond 600, 20/28 px): section headings on the Overview (Abstract, AI Overview, Related works, Comments) and the Ask IRIS heading. Ink, never maroon.
- **Title** (EB Garamond 600, 20/28 px): the paper's title in the record bar, on one truncated line; dialog and card titles.
- **Reading** (Inter 400, 16 px, line-height 1.8): the AI Overview's prose, filling the Overview column. The first paragraph is the lead at 17 px, darker. Markdown section headings inside it are Ink Garamond with space above and no rule; list markers are maroon. The Abstract reads at 17 px with 1.75 leading.
- **Body** (Inter 400, 15/24 px): interface text.
- **Label** (Inter 600, 13/20 px): every control's text. Metadata is the 13 px `small` role at weight 400; field labels are 12/16 px.

### Named Rules
**The Typeset Title Rule.** Garamond is for what you read the title of (a paper, a section, a dialog). It never sets a control, a chip or a number.

**The Named Size Rule.** A size is asked for by role (`text-title`, `text-small`), never by pixel (`text-[13px]`). Nothing goes below 11 px, and labels are sentence case, never small tracked capitals.

## Layout

The record page is a container named `reading`, and the Overview column is its own container named `overview`, so the layout reads the width it is given.

- **Paper tiers** (from the `reading` width): below 640 px Ask IRIS fills the workspace and offers Back to paper; from 640 px it is a drawer over the paper (a modal with a stone scrim); from 1000 px it is a column beside the paper, which keeps at least 640 px. The Paper view is full height: the record bar, then the reader beside Ask IRIS.
- **Ask IRIS width:** 450 px by default, from 320 px to half the workspace, resizable from its left edge and remembered per browser. On the Overview it is a column the page makes room for; it never covers the page.
- **Overview column:** one column up to 60 rem (960 px), set against whatever is beside it (Ask IRIS, or Record details) with the spare room on its left, a 56 px left gutter (16 px on a phone) and a 32 px right one. Record details sit beside the page in a 22 rem sticky column while the Overview container is 64 rem or wider, under it otherwise, and fold away while Ask IRIS is open.
- **Rhythm:** sections inside the Overview are 32 px above and below a Desk Stone hairline. The gaps between a page's sections are 16 / 24 / 32 px; card padding is 20 px (16 compact).
- **Motion:** 150–200 ms colour fades; layout moves (the section thumb, the Record details fold, Ask IRIS arriving from its edge) take 300–320 ms on `cubic-bezier(0.22, 1, 0.36, 1)`. Opacity and transform only for anything that appears, and nothing moves under reduced motion.

### Named Rules
**The Container Rule.** Read the container, never the window. A `lg:` breakpoint on a reading surface is a bug: the sidebar and Ask IRIS change the room without changing the window.

**The Flush Column Rule.** Reading text fills its column and meets what is beside it; the column, not the text, sets the measure.

## Elevation & Depth

Flat. Depth comes from tonal layering: Endpaper ground, stone bars, white pages. Reading regions are divided by one-pixel stone hairlines, not by shadow or gaps. Elsewhere, a card is white with a one-pixel `stone-200` border and no resting shadow. Shadow is kept for what floats or is pressed:

- **Card lift** (`box-shadow: 0 4px 12px 0 rgb(0 0 0 / 0.08)`): the Ask IRIS icon, and a record card on hover.
- **Drawer edge** (`box-shadow: -12px 0 32px rgb(41 37 36 / 0.12)`): Ask IRIS as a drawer over the paper, one soft leftward shadow.
- **Recess** (`box-shadow: inset 0 1px 3px rgb(41 37 36 / 0.28), inset 0 0 0 1px rgb(41 37 36 / 0.07)`): the section track, pressed into the record bar.

### Named Rules
**The Hairline Rule.** Two regions are separated by one Desk Stone or Rule Stone line. Never a card, a gap and a shadow at once.

## Shapes

Gently rounded and consistent. Controls and fields take one radius (0.75 rem); page actions, chips and the Ask IRIS icon are full pills; cards that hold a record are 1.25 rem. A concentric inner shape, such as the section thumb inside its track, is one step smaller (0.375 rem), and that is the only use of the smaller radius. A thick accent border never sits on a rounded shape.

## Components

### Buttons
Quiet and exact.
- **Page actions** (View, Save, Cite, Share, Edit details): 44 px full pills, 20 px side padding, 14 px semibold. **One** Binding Maroon fill per row (View where there is a paper, otherwise Save; Continue or Open review when those are the viewer's job); the rest have no fill and a Rule Stone outline that turns maroon on hover.
- The shared implementations are `PILL_PRIMARY` and `PILL_SECONDARY` in `frontend/src/components/ui/pillStyles.ts`; Danger uses `brand-dark` with a warning glyph.
- **Reading controls** (record bar, reader toolbar, Ask IRIS): 44 px on touch and 36 px beside a pointer, 0.75 rem radius, 13 px semibold. Three states: outlined at rest, Maroon Wash when on, and the one filled control (Send).
- **Ghost** (Copy on the AI Overview, Close): no outline, Faint Ink, a Bar Stone wash and Ink text on hover.
- **Focus:** a 2 px Binding Maroon ring with an offset on every interactive element (`FOCUS_RING` in `frontend/src/components/ui/interaction.ts`). That file also defines `COLOUR_TRANSITION` for the 150 ms hover/focus fade.

### Section tabs
The record's sections (Overview, Paper, Review, Files) are a recessed Desk Stone track in the record bar, with a Binding Maroon thumb that slides to the current one over 300 ms. The current label is white; the others are Quiet Ink and turn maroon on hover.

### Chips
- **Meta chips** (record type, classification, flags): full pills, no fill, Rule Stone outline, 13 px semibold Body Ink.
- **Author chips:** white pills with a Desk Stone outline and a 24 px maroon initials disc.
- **Status:** `TONES` in `frontend/src/components/ui/statusTones.ts` defines four tones only. *Quiet* is unfilled with a stone outline, *active* uses Maroon Wash, *attention* is solid maroon, and *settled* is solid Ink. Each carries its word, and stopping states also carry an icon.
- **Scope chip** ("This paper" / "All papers") in the composer: Maroon Wash with a maroon dot; filled maroon when widened to all papers.

### Citations
In the AI Overview a citation is the page it cites: "p8", 12 px semibold maroon on a Maroon Wash, at the baseline of the text, linking to that page. Chat citations stay small numbered markers.

### Inputs / Fields
A white field with a Rule Stone outline and the control radius. Focus darkens the outline to maroon with a soft maroon ring. A disabled field sits on Endpaper with a not-allowed cursor and says why beside it. The Ask IRIS composer holds the scope chip and Send inside its field.

### Navigation
- **Record bar:** 56 px, Bar Stone, a Desk Stone hairline under it. Back (always labelled), a hairline divider, the paper's title on Paper, then the section tabs.
- **Ask IRIS icon:** a 56 px Binding Maroon circle at the bottom right with the IRIS mark, shown only while the panel is closed, lifting 2 px on hover.

### Ask IRIS panel (signature)
A column on Endpaper behind one Rule Stone line, never a card. A Bar Stone header with the Garamond heading, an "AI" tag and the paper's title. Below it, the conversation, or a Garamond "Ask about this paper." with three outlined starter questions. At the bottom, the composer. It arrives from its edge (320 ms) and has dialog semantics only when it covers the paper.

### Overview sections (signature)
Abstract, AI Overview, Related works and Comments, each under one Desk Stone hairline, each with a Garamond headline. The AI Overview has no card and no provenance label: just the heading with the IRIS mark, a ghost Copy, and the article. Comments are drawn and plainly closed (disabled field and Post, "Not open yet") until the feature exists.

### Entry frame: the Dossier Folder (signature)
Sign in, register, email verification and the pending and declined screens share one frame (`EntryFrame`, IR-704), read like a file handed across a registry desk.
- **Masthead:** a white bar with a Desk Stone hairline under it, the page's one visible h1: the IRIS mark and maroon wordmark, a hairline divider and the CIT-U logo, both at their natural proportions. Sign in and register carry the link to each other here, at least 44 px, at every width.
- **Lede** (sign in and register only): a Garamond 600 headline, 36 px on a phone to 60 px from `lg`, Ink with its last words in Binding Maroon, and one plain Body Ink sentence. Below `md` it is left-aligned and the sentence follows the folder, so the first field stays in the first screenful.
- **Folder:** index tabs on the top edge of one Page White sheet (1 rem radius, `stone-200` border, card lift; the tabs' top corners are 0.75 rem), with a Bar Stone sheet offset behind it. The tab joined to the sheet is white with a 2 px maroon top edge and maroon label text. Sign in, verification and the pending screen have one tab that only labels the sheet.
- **Register stepper:** completed tabs carry an Ink check and a solid Rule Stone outline on Bar Stone and link back; the current tab is joined to the sheet with a maroon number; tabs not started are dashed and cannot be reached. Below 390 px only the current tab shows its name, the others their mark.
- **Footer:** CIT-U identity in 13 px Quiet Ink under a hairline, and no policy link until the policies exist.
- **Motion:** the sheet settles once (280 ms, 0.5 rem rise and fade, a recorded exception to the 150–200 ms rule because it runs once on load) and register's steps cross-fade (150 ms), both only when motion is welcome.

Replaced the split screen with its "shelf of bound work" brand panel (IR-535, IR-586), deleted in IR-711.

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
- **Don't** wrap reading content (the AI Overview, the Abstract, the reader, Ask IRIS) in a card.
- **Don't** float controls over content. Controls live in a bar or toolbar, and Ask IRIS is the one corner icon.
- **Don't** use any colour outside maroon, stone, white and black: no green, amber, blue, gradients or glows, and no `brand-400` to `brand-600`.
- **Don't** use a `lg:` (window) breakpoint to size or arrange anything on the record page.
- **Don't** give reading text its own narrow measure inside the Overview column, or leave a gap between it and the Ask IRIS panel.
- **Don't** add a label explaining how AI text was made, or an outlined button where a ghost one is enough.
- **Don't** put a thick accent border on a rounded shape. The one recorded exception is the entry folder's tab joined to the sheet (`EntryTab`, and register's current step), whose 2 px maroon top edge is the approved Dossier direction (the `border-accent-on-rounded` exception in `.impeccable/config.json`).
