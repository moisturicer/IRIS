# 01 — Design System

A system exists. It is systematically bypassed. **The recommendation is adoption, not replacement.**

> **Amended 2026-09-25 (IR-356).** The project lead authorised redesigning the frontend and changing this system where that serves the product, provided this document records it. The amendments are marked **IR-356** below; they supersede the text they sit beside.

---

## 0 · IR-356 amendments at a glance

| Area | Rule now | Replaces |
|---|---|---|
| **Palette** | **White, black, grey (`stone`) and maroon (`brand`, with its `50`–`200` tints, `light` and `dark`) only.** No green, amber, orange, yellow, red, blue, violet, teal or sky. Errors and rejections use maroon. `brand-400…600` are bright reds, not maroon — do not use them. **Applied so far to the reading surfaces** — Paper View, Paper Chat, and what they render (`StatusBadge`, the document-request panels, the passage notices and the Ask IRIS emblem, which Ask IRIS and the Evaluation page share). **IR-359 converted the shared components and the app shell:** `Button` (`danger` is `brand-dark` with a warning glyph, told from primary by glyph and verb), `Badge` and `Toast` (onto `TONES`; a Toast's kind is also a glyph and a word read to screen readers), `Input`'s error state (maroon, with a glyph), `ConfirmDialog` (now built on `Button`), the auth alert, the account-locked modal, the file upload zone, the Forbidden and coming-soon screens, the DPA consent gate and the sidebar, whose tagline moved from gold to `stone-500` because gold is ≈2.8:1 — gold stays on the logo image only. **IR-360 converted the submission wizard** — Submit Disclosure, Add Record and Edit Record and every step: a field error is maroon with a glyph (`steps/FieldError.tsx`), and hand-built selects and textareas take `Input`'s border (`steps/fieldClasses.ts`); a done step is near-black with a check and says "completed" to a screen reader, the current one is filled maroon and `aria-current`, and an upcoming one is its number in an outline; an uploaded file is near-black with a check and an upload error solid maroon with a glyph, so "Mandatory"/"Required" moved to soft maroon; advisories are soft maroon (Data Privacy) or grey (upload timing). **IR-407 converted Discover** — its result cards (now `ResearchCard`), filter bar, sheet and search highlight (soft maroon, `brand-50`), and the shared record badges in `discoverUtils.ts`, which My Library and My Workspace also draw: IP protection takes the soft maroon tint, and the programme flags (commercialization, community extension, accepted) are grey and told apart by icon and word. **IR-410 converted My Library and deleted My Workspace and `WorkspaceOfficePills`.** **IR-530 converted Calls & Conferences** — the red/amber countdown chips became the four tones by meaning (≤7 days *attention*, ≤21 *active*, otherwise and closed *quiet*), always with words, and the board's urgency now comes mainly from grouping by deadline; the solid per-type badges became a grey glyph and a word. **Not yet converted:** the other files on the guard's `NOT_YET_CONVERTED` list — convert each as it is touched. `gray`/`slate` should also give way to `stone` as files are touched | "Semantic colours come from Tailwind defaults — green/amber/red/blue" (§1) |
| **Status tones** | Four, by meaning: **quiet** `stone-700` text on **no fill**, outlined `stone-300` (not yet with a reviewer; **IR-558** — it inherits the surface it sits on rather than adding a grey of its own, and stays told apart from the other tones by its outline and label) · **active** `brand-50/brand` (with a reviewer, or recoverable) · **attention** solid `brand`, white text (terminal or blocking) · **settled** `stone-900`, white text (finished). Every chip carries its label, and the states that stop a record also carry an icon: **revision requested** is *active* with a return arrow, **rejected** is *attention* with a ban sign — soft versus solid, arrow versus ban, never alike (§7). **IR-358:** defined once as `TONES` in `components/ui/statusTones.ts`; use it rather than restating the classes. The palette itself is enforced by `src/test/palette.test.ts`, which fails on an off-palette colour in any file not on its shrinking `NOT_YET_CONVERTED` list | The per-status colour families in §7–8 |
| **Type** | **Inter** for the interface and **EB Garamond** (`font-display`, weight 600) for titles and section headings on reading surfaces (Paper View, Paper Chat). Both **self-hosted** through `@fontsource` and bundled by Vite — no font CDN. Inter was declared but never loaded before this; every screen had been rendering in the OS fallback face. Display sizes above the 11–16 px body scale: `text-xl` (20 px) section headings, `text-3xl`/`text-4xl` (30/36 px) a paper's title | "`Inter` with a system fallback stack" (§1) |
| **Reading measure** | Long-form text (an abstract) at `text-lg` with `leading-7` (1.75), about 65 characters wide, left-aligned, never justified | — |
| **Actions** | Page actions are 44 px pills from `components/ui/pillStyles.ts`: **one** `PILL_PRIMARY` per row (the most important action for this viewer), the rest `PILL_SECONDARY` (no fill, `stone-300` outline, IR-558), a toggle that is on `PILL_SELECTED` | Mixed 32–36 px rounded-rect buttons |
| **Surface roles** | **IR-558.** Three backgrounds, named in `tailwind.config.js` and used by the shared components: **`canvas`** (`stone-50`) is the one ground under every screen, replacing the cool-grey page body and the warm-grey app frame; **`surface`** (white) is content — a card, a panel, a field; **`overlay`** (white, opaque) is anything that floats over content — a toast, a menu, a dialog, the PDF toolbar and the view switch. Passive chips and secondary pills have no fill, so they take the surface they sit on. A screen may add a different background only for a named functional role (a selected row, a code block, a loading skeleton); "a slightly different white" is not one | The page body in `gray-50`, the app frame in `stone-100`, and see-through white (`bg-white/60`, `bg-white/90`) on cards and reading controls |
| **Reading workspace** | **IR-569.** A record page opens with one **record bar** (Back, sections as tabs in a grey box with the current one filled maroon). Ask IRIS is a 56px round maroon icon at the bottom right, gone while its panel is open. **Paper** is a full-height workspace after the alphaXiv PDF view: the bar, then the reader and Ask IRIS divided by hairlines (`stone-200`/`stone-300`), no cards, gaps or shadows between them; only the PDF pages are white. The record bar, the reader's toolbar and the panel's header are `stone-100`, the desk behind the pages `stone-200`, the section tabs are a recessed `stone-200` track (inset shadow) with a sliding maroon thumb, and the scope chip is a `brand-50` tint: tints of the palette, not new hues. Over the paper (below 1000 px of content) Ask IRIS is a drawer with one soft leftward shadow and a `stone-900/25` scrim. The layout reads the `reading` container's width, not the window's | The floating pill section switch, a floating *Ask about this paper* button, and the reader and chat as rounded cards beside each other |
| **Ask IRIS page** | **IR-570.** The answer column is the page's one `surface`; history and sources beside it are `canvas`, and the transcript, toolbar and composer add no white of their own. The page reads its own width: from **900 px** (`ASK_PANELS_INLINE_PX`, the 640 px reading minimum plus the 260 px history) history and sources sit beside the answer as before; below it they are **closed by default and open one at a time as drawers** (`ChatDrawer`): `overlay`, history from the start edge and sources from the end, one soft shadow towards the answer, a `stone-900/25` scrim, the page behind inert, focus moved in, kept in and returned to the toggle. New chat moves into the history drawer. Toggles take 44 px there. The page is `h-dvh` and the viewport declares `interactive-widget=resizes-content`, so the composer stays above a phone's keyboard; keyboard hints are hidden on coarse pointers. A streaming answer says what it is doing in **one** polite live line under its text, which also carries the screening count | History squeezing the transcript into a strip at 360 px, `#FBFCFD` and white layers inside the chat, and a second status region in the candidate list |
| **Reading controls** | **IR-569.** One scale for every control in the reading surfaces (record bar, reader toolbar, Ask IRIS), in `paper-view/controls.ts`: **44 px on touch, 36 px beside a pointer**, `rounded-lg`, 13 px semibold; an icon-only control is the same size square (so `Button size="icon"` is now **44/36 px**, was 44/32). Three states: outlined at rest (`stone-300`), a `brand-50` tint when on, and the one filled state (Send). **Page actions** (View, Save, Cite, Share) stay 44 px pills, one filled per row. Text controls name their size with the type scale (`text-small`), never `text-[13px]`. Sizes read the `reading` container, never the window (`lg:`), so the sidebar and Ask IRIS beside a paper change them too. **A concentric inner shape** (the section thumb inside its track) is one radius step smaller (`rounded-md`), the only sanctioned use. Held by `readingStandards.test.ts`, with a shrinking allowlist for the older files (the dialogs' pixel text sizes, three `rounded-md`s). | Controls at 32, 34, 36, 40 and 44 px and `rounded-md`, `rounded-lg` and `rounded-full` side by side on one screen |
| **Palette guard** | **IR-558, an amendment to IR-358's rule**, which let `gray` and `slate` pass on purpose. `src/test/palette.test.ts` now also rejects a new `gray`/`slate` colour class and a see-through white background (`bg-white` at any opacity below 100), each with its own allowlist of existing files that **may only shrink**. The Ask IRIS files are on the `gray`/`slate` list until IR-365 lands; IR-366 deletes the lists. IR-538 removed the email-verification screen's decorative circles and its remaining palette allowances | "`gray`/`slate` are greys and pass" |
| **`Button`** | `size="icon"` (44 px below `lg`, 36 px above, as of IR-569; `aria-label` required by the type) and the `aria-pressed:` state on `ghost` — **added by IR-352**, listed here because this section is the one place to find the current system | "5 variants × 3 sizes" (§3) |
| **Header search** | Not shown on Paper View (a reading surface). It is inert on every screen — it has no handler — which is a separate fix | — |

### IR-405 amendments: the design language for the whole redesign

The IR-374 redesign extends the IR-356 direction from Paper View to every screen it rebuilds (`docs/frontend_redesign_spec.md` §4.12). IR-405 (F0) put the tokens and shared components in place. Each later ticket adopts them as it rebuilds its screen.

| Area | Rule now | Replaces |
|---|---|---|
| **Type roles** | Six named sizes in `tailwind.config.js`, picked for what the text *is*: `text-display` 28/34 (page and record titles), `text-title` 20/28 (dialog titles, card titles), `text-heading` 16/24 (section headings), `text-body` 15/24, `text-small` 13/20 (secondary lines, metadata), `text-label` 12/16 (labels). `display` and `title` are set in `font-display` (EB Garamond 600); everything else in Inter. **Labels are sentence case**: no uppercase-and-tracking labels below 12 px. The size ladder `3xs`–`lg` (11–17 px, IR-452) stays for existing code; new and rebuilt screens use the roles. `src/test/typeScale.test.ts` pins every role's size and leading | The scattered 10–11 px uppercase labels, and choosing a size by number |
| **Spacing** | Tailwind's 4 px base, plus named steps: `section-sm` 16, `section` 24, `section-lg` 32 for the gaps between a page's sections; `card` 20 and `card-compact` 16 for card padding (`p-card-compact md:p-card`) | "Spacing is Tailwind default" (§1) |
| **Surfaces** | A `stone-50` canvas. Cards are white with a 1 px `stone-200` border and **no resting shadow**. With no shadow to lift it, a card shows hover and keyboard focus by darkening its border to `stone-400`. That is an IR-405 addition; §4.12 does not specify a hover state. Shadow is kept for things that float: dialogs, menus, the mobile sheet | `shadow-card` on resting cards |
| **Action hierarchy** | One maroon primary pill per region (`pillStyles`), outline pills for the rest, text buttons for tertiary actions. Danger is `brand-dark` with its glyph (IR-359) | — |
| **Focus** | A visible 2 px maroon ring with an offset on every interactive element: `FOCUS_RING` in `components/ui/interaction.ts` | Browser default outlines |
| **Motion** | 150–200 ms, opacity and transform only for anything that moves or appears, and none under `prefers-reduced-motion` (`motion-reduce:transition-none`). A progress bar grows by `scaleX`, not by animating its width. **One deliberate addition to spec §4.12**, whose rule reads "opacity/transform only": hover and focus **colour** changes keep a short transition (`COLOUR_TRANSITION` in `components/ui/interaction.ts`), as every existing pill and link already does. A colour fade moves nothing and causes no reflow, and dropping it would make the rebuilt screens snap where the rest of the app fades. Recorded here under the lead's licence to amend the design system (§0 note), not silently | Spec §4.12 "150–200 ms opacity/transform only" |
| **Dialogs that are tasks** (IR-408) | `Modal` takes three optional props, all off by default: `sheet` (full screen below `md`, a centred dialog from `md` up; spec §4.13, which says `md` where §4.4 says `sm`; §4.13 is followed), `footer` (actions pinned under the scrolling body, so a step's Continue never scrolls away on a phone) and `displayTitle` (the title in `font-display text-title`, as a content title). Publish uses all three. A dialog that asks a question keeps the plain form | `Modal`'s single centred layout at every width |
| **Shared components** | `ResearchCard` (new: one card for a record, `list`/`grid`, with slots; **IR-410 added `compact`**, which keeps a list card's title at `text-title` and its padding compact for a working list, and lets the status row wrap so several chips never overflow a phone), `EmptyState` (action slot, `error` tone, `framed`; Discover's private copy deleted), `UploadDropzone` (replaces `FileUploadZone`: checks before upload when asked to, progress, retry, Enter/Space), `PageHeader` (restyled to the type roles). Details in [14](14-component-inventory.md) §4–5 | §4's "No change for MVP" for these |

### IR-535 amendment: the entry frame

| Area | Rule now | Replaces |
|---|---|---|
| **Entry brand panel** | The sign-in, register, verify and pending screens share `AuthLayout`, whose desktop panel (`AuthBrandPanel`) is a **shelf of bound work**: a `stone-100` ground, a plain statement in `font-display`, one sentence per screen saying what that screen is for, and a row of volumes in `brand`, `brand-dark`, `brand-light` and white whose spines carry only the record types IRIS holds. Chosen by the project lead from an `impeccable` round (2026-10-12). No quotation, figure or claim of prestige. Gold is the two bands at each spine's head and nothing else. **One deliberate exception to the type roles:** the statement is set at `text-4xl` (`2xl:text-5xl`) in `font-display` 600, the size a paper's title takes, rather than at `display` (28px), because it is the one line the screen exists to say. The shelf fades in once (200ms opacity, none under reduced motion) | The cream panel with the design-brief quotation and "a prestigious archive" (signup) and the tagline panel (login) |
| **Shelf entrance** (IR-586) | The volumes on the entry panel's shelf rise 1.5rem and fade in, one after another, 35 ms apart, each over 420 ms (`cubic-bezier(0.22, 1, 0.36, 1)`), so the shelf is full within about a second of load. A spine lifts 6 px under the pointer over 200 ms; it is decoration and opens nothing. Both are opacity and transform only, and neither runs under `prefers-reduced-motion`. **A recorded exception to the Motion row's 150–200 ms:** this runs once, on decoration nobody waits on, and `fade-in-up` already runs 300 ms elsewhere. The stagger is generated by the `shelfRise` plugin in `tailwind.config.js`, because the entry frame takes no inline style. The entrance fills `backwards`, never `both`, so a landed volume's `transform` is free for the hover lift. It replays only if the panel is laid out afresh, as when a window is resized across `lg` | The whole shelf fading in at once over 200 ms (`motion-safe:animate-fade-in`) |
| **`text-spine`** | A utility in `index.css` that sets `writing-mode: vertical-rl` turned to read bottom to top, for spine titles. Tailwind has no writing-mode utility | — |
| **Register finish** (IR-540) | Consent is given against an inline **data notice** opened by "Read the data notice" (a disclosure, 44px tall, as sign-in's "Forgot password?" is), never against a link. Register is never disabled: a submit without consent marks the box invalid with its own error, because a disabled button says nothing about why (and `opacity-50` was 3.09:1). "What happens next" (verify, then RDCO decides) sits above Register in `text-small stone-600`. Success replaces the form with "Check your email": the address in `stone-900` semibold, the two remaining steps, and Go to sign in as a full-width maroon link. Failures are `AuthAlert`s inside the form — a non-field refusal, an unreachable server, options that did not load (with Try again); no toast | Two `#` links to documents that do not exist, a disabled Register, a success toast with a redirect, and "Failed to load form options. Please refresh." |
| **Pending screen** (IR-537) | Rebuilt in the entry frame. Its title is `font-display text-display` 600, as the type roles say; the older sign-in and register titles (Inter 700, 28px) follow under IR-539. The panel gains a fifth variant, **`declined`** ("Your account is registered, but RDCO did not approve it."), so the panel never says the account will open beside a message saying the request was refused. "Registered as" is one square catalogue card on `surface` with a 2px gold head rule — square because a thick rule on rounded corners tapers; gold as a border only. No turnaround time anywhere: nothing on the server backs one | The standalone grey card with the amber hourglass, the inline logo lockup and "typically within 1–2 business days" |
| **Register screen** (IR-539) | Built from the shared primitives: `Input` and the new `Select` at `lg`, the password show/hide toggles in `Input`'s trailing slot (44×44, named "Show password" / "Show confirmed password"), and Register on `Button` `full` in maroon (12.3:1 at rest, 9.5:1 on hover). The role choice is a radio group named "I am registering as", drawn as two tiles: the chosen one `brand-50` with a maroon border and text. A required field shows "(required)" in `stone-600` (7.6:1) beside its label and carries `aria-required`, so the word is seen and the state is announced, and the name stays the label alone. Password feedback is words, "At least 8 characters" and "Passwords match", with a check glyph as decoration. Both entry titles, sign in and register, now use `font-display text-display` 600, as the pending screen does | Nine controls with no accessible name, `bg-[#F3F3F3]` fields with a green "valid" border, two role buttons that announced no state, "Password looks good." in green alone, and Register white on gold (2.76:1) |
| **Entry tokens guard** | `components/auth/entryTokens.test.ts` fails on a hex value, an arbitrary-value class, an inline style, gold as text or fill, or cream in an entry-frame file. IR-537 to IR-540 add their screens to it | — |

## 1 · Tokens as defined

`frontend/tailwind.config.js`:

### Colour

| Token | Value | Contrast on white | Verdict |
|---|---|---|---|
| `brand.DEFAULT` | `#6B0F12` | 12.3:1 | ✅ AAA — primary |
| `brand.light` | `#8B1316` | 9.8:1 | ✅ hover |
| `brand.dark` | `#4A0A0C` | 15.1:1 | ✅ |
| `brand.50…900` | full ramp | — | ✅ tints available and largely unused |
| `gold.DEFAULT` | `#C59334` | **≈2.8:1** | ❌ **decorative only** |
| `gold.dark` | `#A87B2A` | ≈3.9:1 | ❌ still below 4.5:1 for body text |
| `cream` | `#F5F0E8` | — | ✅ background |

~~Semantic colours come from Tailwind defaults — green/amber/red/blue for status.~~ **Superseded by IR-356 (§0): the interface uses white, black, grey and maroon only, and status is carried by four tones plus a label.**

### Type

`Inter` with a system fallback stack — **IR-356: now actually loaded (self-hosted), with `EB Garamond` as `font-display` for reading-surface titles and headings (§0).** Scale defined as `2xs` 11px · `xs` 12px · `sm` 13px · `base` 14px · `md` 15px · `lg` 16px.

**13px base is small** but internally consistent and appropriate for a dense institutional tool. Keep it. Do not go below 11px anywhere.

> **Corrected (IR-405).** The ladder above is stale. IR-452 raised it one step: `3xs` 11 · `2xs` 12 · `xs` 13 · `sm` 14 · `base` 15 · `md` 16 · `lg` 17 px. IR-405 added the six type roles beside it (§0): `display` 28/34 · `title` 20/28 · `heading` 16/24 · `body` 15/24 · `small` 13/20 · `label` 12/16.

### Radius, shadow, spacing

`rounded` 0.5rem · `lg` 0.75rem · `xl` 1rem · `2xl` 1.25rem. Two card shadows (`card`, `card-md`). Spacing is Tailwind default. **IR-405: plus the named steps `section-sm`/`section`/`section-lg` (16/24/32) and `card`/`card-compact` (20/16), and resting cards take no shadow (§0).**

---

## 2 · Drift — measured

The system is defined and then routed around.

| Token | Token usage | Arbitrary usage | Bypass |
|---|---|---|---|
| Brand colour | `bg-brand` etc. **61** | `[#6B0F12]` **134** | **69%** |
| Font size | `text-sm` **7** | `text-[13px]` **182** | **96%** |
| Card shadow | `shadow-card` ~0 | `border border-gray-200` | ~100% |

Even the primitives bypass their own system — `Button` hardcodes `bg-[#6B0F12]`, `Spinner` hardcodes `text-[#6B0F12]`, `Input` hardcodes `border-[#6B0F12]`.

**Why it matters beyond tidiness.** Per-institution branding is a stated post-MVP SaaS capability ([11](11-saas-admin.md)). With 134 hardcoded hex values, rebranding means a find-and-replace across the codebase rather than changing one config. The token indirection is the feature; bypassing it removes it.

### Recommendation

**Do not retrofit all 134.** That is a day of churn with no user-visible change, against a ~3 dev-day frontend budget.

**Do adopt tokens in any component you touch** (`FE-01`, `W-07`, the a11y fixes), and fix the five primitives — Button, Input, Spinner, Badge, Card — because every other component inherits from them. That is under an hour and captures most of the value.

**Add a lint rule** to prevent new arbitrary brand values, once ESLint runs (`FE-04`):

```
no-restricted-syntax on /\[#6B0F12\]/ → "use bg-brand / text-brand"
```

---

## 3 · Primitive layer

`frontend/src/components/ui/`

| Component | State | Change |
|---|---|---|
| `Button` | 5 variants × 5 sizes (`full` from IR-204, `icon` from IR-352), `loading`, forwardRef | ~~Add `aria-label` requirement when children are icon-only~~ **Done for `size="icon"` (IR-352): the type requires it** ([12](12-accessibility.md)) · use tokens |
| `Input` | label, error, hint, leading, trailing, `md`/`lg` sizes, derived `id`, `required` (IR-539: "(required)" beside the label and `aria-required`, not the native attribute, so an empty field is not `:invalid` before anyone types) | ~~Wire `aria-invalid` and `aria-describedby`~~ **Done (IR-158)** |
| `Select` | **New (IR-539).** A native `<select>` with `Input`'s contract: label, hint, error, derived `id`, `aria-invalid`, `aria-describedby`, `required`, and the same `md`/`lg` steps, with a drawn chevron. Native rather than a custom listbox, so the keyboard, the phone picker and `<optgroup>` behave as each platform expects | Adopt wherever a select is hand-rolled with `fieldClasses` |
| `Card` + `CardHeader` | Border, not shadow | Adopt `shadow-card`; keep the border option |
| `Badge` | 6 variants, 11px, rounded-full | Keep |
| `Modal` | `role="dialog"`, `aria-modal`, `aria-labelledby`, Escape, labelled close | **Add focus trap + focus restore** — the only substantive gap |
| `Spinner` | 3 sizes, brand colour | Keep; wrap in the new `LoadingState` |
| `Toast` | Exists | Verify `role="status"` / `aria-live` |

**The primitives are good.** Four small corrections cover most of the accessibility work in this document set, because everything else composes from them.

---

## 4 · Shared components

`frontend/src/components/shared/`

| Component | State | Change |
|---|---|---|
| `DataTable` | Wraps `@tanstack/react-table`, server pagination, empty and loading rows | **Add `scope="col"`, `aria-label` on the icon-only pager, `overflow-x-auto` container.** Sorting is a `TODO` at line 3 |
| `StatusBadge` | Maps 13 statuses → colour + label | **Remove the stale `ktto_review` key** (not in `PIPELINE_STATUS`). Keep otherwise |
| `EmptyState` | Icon + title + message | ~~**`text-gray-400` fails contrast** → `gray-500`; add `aria-hidden` to the icon~~ **Done (IR-405):** `stone-600` message, `aria-hidden` icon, heading title, `action` slot, `error` tone |
| `RoleBadge`, `ConfirmDialog` | Fine | No change for MVP |
| `UploadDropzone` | **IR-405**, replaces `FileUploadZone` | With `validate`, checks type and size before upload; shows progress; retries a failed upload; opens with Enter or Space |
| `ResearchCard` | **IR-405**, new | One card for a record in a list or grid ([14](14-component-inventory.md) §4) |
| `ComingSoonPage` | Placeholder | Used by `/storage`, which is removed (`SC-01`) |

### Two components to add

**`LoadingState`** — the string `p-8 text-center text-gray-400 text-[13px]` is duplicated across **10 files** while `Spinner` exists and is used in 5. One component with `role="status"` fixes duplication, contrast and screen-reader announcement together. **~30 minutes.**

**`ClearanceTrack`** — the interface to the thesis contribution. Full specification in §[08](08-workflow-resubmission.md). **The only genuinely new component the MVP needs.**

---

## 5 · Icons

Font Awesome 6 via CDN, `<i className="fas fa-…" />`, 95 usages.

**Two defects:**

1. **Loaded twice.** `index.html` links **6.5.1 at line 9 and 6.5.2 at line 17** — two full stylesheets, one wasted download. Delete one.
2. **~72 of 95 icons lack `aria-hidden="true"`**, so screen readers announce meaningless font glyphs.

**Recommendation.** Keep Font Awesome — replacing it is churn. Fix both defects (~1 hour), and add `aria-hidden` at the primitive level so composed components inherit it.

**Post-MVP:** a CDN dependency is a runtime dependency on a third party. For an on-premise institutional deployment behind a firewall it should be self-hosted. Not MVP; note it in the deployment runbook.

---

## 6 · Layout

`AppShell` composes Sidebar + Breadcrumbs + main; there has been no Header since IR-519. Its responsive states are in [13](13-responsive.md) §2.

**The sidebar (IR-413, 2026-10-12).** Redesigned with impeccable's *Quiet white* direction, inside these tokens:

- **Brand:** the logo, the **IRIS** wordmark in `font-display` (`text-title`, semibold, `tracking-widest`, `text-brand`) and the bell. The tagline *Research-to-IP Platform* is on its own line under the wordmark at `text-3xs` (11 px) `stone-500`. It was 9 px and wrapped onto three lines beside the bell, below this file's 11 px floor.
- **Nav:** one unlabelled main list, plus RDCO's labelled *Administration* group (`text-3xs`, uppercase, `tracking-wider`, `stone-500`). Rows are `text-sm`, `rounded-lg`, `px-3 py-2`, with a `w-5` icon.
  - **Active** is the brand tint: `bg-brand-50`, `text-brand`, semibold, with the icon in brand. The 4 px maroon left bar is gone.
  - **Hover** is neutral, `bg-stone-100`, so it is never mistaken for the active row.
  - Every row carries `FOCUS_RING`.
- **The account menu** in the user block holds Settings & Profile, Help and Sign out (`AccountMenu.tsx`). It is a disclosure: a button that shows and hides a list of plain links and buttons, not an ARIA `menu`. It opens upward, or to the right of the rail, and uses `shadow-card-md`.
- **Collapse / Expand** is one always-visible control at the bottom. It replaced a toggle that only appeared when you hovered the logo, which a touch tablet could not reach.
- **Widths:** `w-60` / `w-16` instead of `230px` / `60px`.
- **One new token:** `transition-shell` (`transitionProperty.shell`: transform, width, margin) in `tailwind.config.js`. The drawer slides, the rail narrows and the content margin follows. Two separate `transition-*` classes on one element silently override each other, because `cn` does not merge Tailwind classes.
- **The app background is the `canvas` role** (`stone-50`, IR-558), previously `stone-100` and before that `gray-100`; the sidebar and mobile bar are `surface`. The drawer backdrop is `stone-900/40`, previously `black/40`, following the palette rule at the top of this file.

One quirk: the Discover home and Ask IRIS are special-cased full-bleed, with no `PageContainer` or breadcrumbs, and paint their own page.

---

## 7 · Status colour semantics

> **IR-356:** the colour families below are superseded by the four tones in §0. The rule that matters survives unchanged: never colour alone. "Revision requested" (`awaiting_resubmission`, legacy `declined`) is a **soft maroon chip with a return arrow**; "Rejected" is a **solid maroon chip with a ban sign**. Tone, icon and label all differ.

`StatusBadge` maps pipeline statuses to Tailwind colour families. The mapping is reasonable; the **contrast is not verified**. All are `-100` background with `-700` text, which typically passes AA, but `amber-100/amber-700` and `yellow-100/yellow-700` should be checked ([12](12-accessibility.md)).

**A semantic problem worth fixing:** `declined` (amber) and `rejected` (red) are visually adjacent but semantically opposite — one is recoverable, one is terminal. Given that resubmission is the thesis contribution, the difference must be unmissable.

**Recommendation:** keep the colours, but never rely on colour alone. `declined` reads **"Revision requested"** with a return-arrow icon; `rejected` reads **"Rejected"** with a stop icon. Colour plus label plus shape — WCAG 1.4.1 requires colour not be the sole carrier of meaning, and here the distinction is load-bearing for the research.

---

## 8 · Proposed additions for the Clearance Track

> **IR-356:** the *Visual* column is superseded by §0's palette — map cleared/preserved to **settled**, pending/not_started to **quiet**, in_review to **active**, declined/rejected to **attention**. Icons and labels stand as proposed.

New semantic tokens, colour-independent, defined once and reused across every clearance surface:

| State | Meaning | Visual | Icon | Label |
|---|---|---|---|---|
| `cleared` | Office approved | `green-100 / green-800` | check | "Cleared" |
| `pending` | Awaiting this office | `gray-100 / gray-700` | clock | "Awaiting review" |
| `in_review` | Office has opened it | `blue-100 / blue-800` | eye | "In review" |
| `declined` | This office sent it back | `amber-100 / amber-800` | return arrow | "Revision requested" |
| `rejected` | Terminal | `red-100 / red-800` | stop | "Rejected" |
| `preserved` | Cleared and **carried through** a resubmission | `green-100 / green-800` + border | check + shield | "Cleared — preserved" |
| `not_started` | Not yet engaged | `gray-50 / gray-500` dashed | dot | "Not yet required" |

**`preserved` is the contribution made visible.** It must be visually distinct from plain `cleared` — same colour family, added border and shield glyph — and accompanied by explicit text, because that distinction is precisely what the evaluation asks participants to perceive (`M17` in [`docs/mvp-validation/05-gqm.md`](../mvp-validation/05-gqm.md)).

---

## 9 · Effort

| Change | Effort | Priority |
|---|---|---|
| Delete the duplicate Font Awesome link | 5 min | Now |
| `aria-hidden` on decorative icons (primitive level) | 30 min | Now |
| `text-gray-400` → `gray-500` for text | 30 min | Now |
| `LoadingState` component, replacing 10 duplicates | 30 min | Now |
| Fix the five primitives to use tokens | 45 min | Now |
| `Modal` focus trap + restore | 45 min | Now |
| `Input` `aria-invalid` / `aria-describedby` | 20 min | Now |
| `DataTable` scope, pager labels, scroll container | 30 min | Now |
| Remove stale `ktto_review` key | 5 min | Now |
| **Subtotal** | **~4 hours** | |
| **`ClearanceTrack` component** | **~1 day** | **`W-07`** |
| Lint rule against arbitrary brand values | 15 min | With `FE-04` |
| Retrofit all 134 hardcoded values | ~1 day | **Post-MVP** |

**~1.5 dev-days for everything except the retrofit** — which is within the frontend budget and delivers the contribution's interface plus the accessibility corrections.
