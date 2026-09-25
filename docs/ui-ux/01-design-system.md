# 01 — Design System

A system exists. It is systematically bypassed. **The recommendation is adoption, not replacement.**

> **Amended 2026-09-25 (IR-356).** The project lead authorised redesigning the frontend and changing this system where that serves the product, provided this document records it. The amendments are marked **IR-356** below; they supersede the text they sit beside.

---

## 0 · IR-356 amendments at a glance

| Area | Rule now | Replaces |
|---|---|---|
| **Palette** | **White, black, grey (`stone`) and maroon (`brand`, with its `50`–`200` tints, `light` and `dark`) only.** No green, amber, orange, yellow, red, blue, violet, teal or sky. Errors and rejections use maroon. `brand-400…600` are bright reds, not maroon — do not use them. **Applied so far to the reading surfaces** — Paper View, Paper Chat, and what they render (`StatusBadge`, the document-request panels, the passage notices and the Ask IRIS emblem, which Ask IRIS and the Evaluation page share). **IR-359 converted the shared components and the app shell:** `Button` (`danger` is `brand-dark` with a warning glyph, told from primary by glyph and verb), `Badge` and `Toast` (onto `TONES`; a Toast's kind is also a glyph and a word read to screen readers), `Input`'s error state (maroon, with a glyph), `ConfirmDialog` (now built on `Button`), the auth alert, the account-locked modal, the file upload zone, the Forbidden and coming-soon screens, the DPA consent gate and the sidebar, whose tagline moved from gold to `stone-500` because gold is ≈2.8:1 — gold stays on the logo image only. **Not yet converted:** `WorkspaceOfficePills` and My Workspace, and the other files on the guard's `NOT_YET_CONVERTED` list — convert each as it is touched. `gray`/`slate` should also give way to `stone` as files are touched | "Semantic colours come from Tailwind defaults — green/amber/red/blue" (§1) |
| **Status tones** | Four, by meaning: **quiet** `stone-100/stone-700` (not yet with a reviewer) · **active** `brand-50/brand` (with a reviewer, or recoverable) · **attention** solid `brand`, white text (terminal or blocking) · **settled** `stone-900`, white text (finished). Every chip carries its label, and the states that stop a record also carry an icon: **revision requested** is *active* with a return arrow, **rejected** is *attention* with a ban sign — soft versus solid, arrow versus ban, never alike (§7). **IR-358:** defined once as `TONES` in `components/ui/statusTones.ts`; use it rather than restating the classes. The palette itself is enforced by `src/test/palette.test.ts`, which fails on an off-palette colour in any file not on its shrinking `NOT_YET_CONVERTED` list | The per-status colour families in §7–8 |
| **Type** | **Inter** for the interface and **EB Garamond** (`font-display`, weight 600) for titles and section headings on reading surfaces (Paper View, Paper Chat). Both **self-hosted** through `@fontsource` and bundled by Vite — no font CDN. Inter was declared but never loaded before this; every screen had been rendering in the OS fallback face. Display sizes above the 11–16 px body scale: `text-xl` (20 px) section headings, `text-3xl`/`text-4xl` (30/36 px) a paper's title | "`Inter` with a system fallback stack" (§1) |
| **Reading measure** | Long-form text (an abstract) at `text-lg` with `leading-7` (1.75), about 65 characters wide, left-aligned, never justified | — |
| **Actions** | Page actions are 44 px pills from `components/ui/pillStyles.ts`: **one** `PILL_PRIMARY` per row (the most important action for this viewer), the rest `PILL_SECONDARY`, a toggle that is on `PILL_SELECTED` | Mixed 32–36 px rounded-rect buttons |
| **`Button`** | `size="icon"` (44 px below `lg`, 32 px above; `aria-label` required by the type) and the `aria-pressed:` state on `ghost` — **added by IR-352**, listed here because this section is the one place to find the current system | "5 variants × 3 sizes" (§3) |
| **Header search** | Not shown on Paper View (a reading surface). It is inert on every screen — it has no handler — which is a separate fix | — |


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

### Radius, shadow, spacing

`rounded` 0.5rem · `lg` 0.75rem · `xl` 1rem · `2xl` 1.25rem. Two card shadows (`card`, `card-md`). Spacing is Tailwind default.

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
| `Input` | label, error, hint, leading, derived `id` | **Wire `aria-invalid` and `aria-describedby`** to the error/hint |
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
| `EmptyState` | Icon + title + message | **`text-gray-400` fails contrast** → `gray-500`; add `aria-hidden` to the icon |
| `RoleBadge`, `ConfirmDialog`, `FileUploadZone` | Fine | No change for MVP |
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

`AppShell` composes Sidebar + Header + Breadcrumbs + main, with three responsive states ([13](13-responsive.md)). Genuinely good and needs no change.

One quirk: the Discover home is special-cased full-bleed with no Header. Acceptable, but it makes that route inconsistent with every other — worth resolving if Discover survives scope ([15](15-mvp-ui-scope.md)).

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
