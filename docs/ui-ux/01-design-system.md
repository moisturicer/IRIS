# 01 — Design System

A system exists. It is systematically bypassed. **The recommendation is adoption, not replacement.**

---

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

Semantic colours come from Tailwind defaults — green/amber/red/blue for status. That is fine and worth keeping; inventing a parallel semantic ramp would be cost without benefit.

### Type

`Inter` with a system fallback stack. Scale defined as `2xs` 11px · `xs` 12px · `sm` 13px · `base` 14px · `md` 15px · `lg` 16px.

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
| `Button` | 5 variants × 3 sizes, `loading`, forwardRef | **Add `aria-label` requirement when children are icon-only** ([12](12-accessibility.md)) · use tokens |
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

`StatusBadge` maps pipeline statuses to Tailwind colour families. The mapping is reasonable; the **contrast is not verified**. All are `-100` background with `-700` text, which typically passes AA, but `amber-100/amber-700` and `yellow-100/yellow-700` should be checked ([12](12-accessibility.md)).

**A semantic problem worth fixing:** `declined` (amber) and `rejected` (red) are visually adjacent but semantically opposite — one is recoverable, one is terminal. Given that resubmission is the thesis contribution, the difference must be unmissable.

**Recommendation:** keep the colours, but never rely on colour alone. `declined` reads **"Revision requested"** with a return-arrow icon; `rejected` reads **"Rejected"** with a stop icon. Colour plus label plus shape — WCAG 1.4.1 requires colour not be the sole carrier of meaning, and here the distinction is load-bearing for the research.

---

## 8 · Proposed additions for the Clearance Track

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
