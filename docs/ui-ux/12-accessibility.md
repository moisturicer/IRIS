# 12 — Accessibility

**Target: WCAG 2.1 Level AA** for the sixteen MVP screens.

Not because a rubric asks for it. Because this is an institutional system that staff are *required* to use — a reviewer cannot opt out of the clearance workflow — and because an evaluation participant who cannot operate the interface produces a data point about the interface, not about the workflow.

---

## 1 · Measured baseline

Counted across `frontend/src/**/*.tsx`:

| Signal | Count | Reading |
|---|---|---|
| `text-gray-400` | **77** | ≈ 2.8:1 on white. **Fails 1.4.3** |
| Font Awesome icons | **110** | |
| `aria-hidden` | 23 | **87 icons announce as unlabelled content** |
| `aria-label` | 22 | |
| **`sr-only` / visually-hidden** | **0** | **No screen-reader-only text exists anywhere in the product** |
| `role="…"` | 4 | |
| `alt=` | 7 | |
| Raw `<table>` | 14 files | vs **2** using `DataTable` |
| `<div onClick>` | 1 | Genuinely low — the codebase mostly uses real elements |

The last row is worth stating plainly: **the codebase's element semantics are better than its ARIA.** Links are links and buttons are buttons. The failures are concentrated in contrast, icon labelling, and a handful of specific components — which makes them cheap to fix.

The `sr-only: 0` result is the structural one. It means the 768–1279 px icon rail ([03](03-navigation.md)) has no accessible names *by construction*: labels are hidden with `hidden xl:block`, which removes them from the accessibility tree as well as the screen. At that width the entire primary navigation is unlabelled to a screen reader.

---

## 2 · Failures, ranked

### A. Colour contrast — 1.4.3 (AA)

| Token | Ratio on white | Verdict |
|---|---|---|
| Brand `#6B0F12` | **12.3 : 1** | ✅ **AAA** |
| Gold `#C59334` | **≈ 2.8 : 1** | ❌ Fails AA for text |
| `text-gray-400` (`#9CA3AF`) | **≈ 2.8 : 1** | ❌ Fails AA — **77 uses** |
| `text-gray-500` (`#6B7280`) | ≈ 4.8 : 1 | ✅ Passes |

**Fix:** replace `text-gray-400` with `text-gray-500` for text. Keep `text-gray-400` only for genuinely decorative glyphs that are `aria-hidden`. **Gold is a decorative and border colour only** — never body text, never a label, never a link ([01](01-design-system.md)).

The brand colour passing at AAA is a real asset: primary actions, links and active states are already well above the threshold. The contrast problem is entirely in the greys.

### B. Icons announce as noise — 1.1.1

87 of 110 icons lack `aria-hidden`. A Font Awesome `<i>` with no text and no `aria-hidden` is announced by some screen readers as an empty element or by its ligature.

**Rule.** Every icon is one of exactly two things:

| Kind | Markup |
|---|---|
| **Decorative** — sits beside text that already says it | `<i className="fas fa-check" aria-hidden="true" />` |
| **Meaningful** — the only carrier of the information | Icon `aria-hidden` **plus** visually-hidden text |

There is no third case. An icon-only button always needs an accessible name.

### C. Status conveyed by colour alone — 1.4.1

`StatusBadge` maps 13 statuses to colours. `EvaluationPage`'s decision options use `text-green-700` / `text-amber-700` / `text-red-700` as the differentiator.

Both already carry text, which saves them — but the **Clearance Track** ([08](08-workflow-resubmission.md)) introduces seven states, and the `preserved` state is distinguished from `cleared` by green-plus-border. That distinction is the thesis contribution and **must not be a colour difference**.

**Rule.** Every clearance state renders **icon + label + colour**, and the label is different text: `"Cleared"` vs **`"Cleared — preserved"`**. A user who sees no colour still reads the contribution.

### D. Modal has no focus management — 2.4.3, 2.1.2

`Modal.tsx` has `role="dialog"`, `aria-modal`, `aria-labelledby`, an Escape handler, an `aria-hidden` backdrop and an `aria-label="Close"` button. It is 80 % correct.

It has **no focus trap and no focus restore**. Tab moves behind the dialog into the page underneath; on close, focus returns to `<body>`.

This blocks two flows that matter: reject confirmation ([07](07-review-clearance.md)) and role approval ([11](11-saas-admin.md)) — both irreversible actions confirmed in a dialog a keyboard user cannot stay inside.

**Fix:** trap Tab within the dialog, focus the first interactive element on open, restore focus to the trigger on close. ~30 lines, one component, every dialog in the product fixed at once.

### E. Form errors are not associated — 3.3.1, 4.1.2

`Input.tsx` renders `label`, `error` and `hint` correctly and derives an `id` — but sets **neither `aria-invalid` nor `aria-describedby`**. A screen reader announces the field name and nothing else; the error is visible text floating near an input it is not connected to.

This is the highest-leverage fix in the document. `Input` is the shared primitive: fixing it corrects the submission wizard, the decision comment, the audit filter and the login form simultaneously. ~10 lines.

### F. Icon rail is unlabelled — 4.1.2

Covered above. **Fix:** add an `sr-only` utility and give every rail item visually-hidden text, or an `aria-label`, independent of the visual label's breakpoint.

### G. Loading states are unannounced — 4.1.3

Ten files duplicate `<div className="p-8 text-gray-400 text-[13px]">Loading...</div>`. Two failures in one string: it fails contrast, and a screen reader user gets no notification that content arrived.

**Fix:** one `<Skeleton>` component with `role="status"` and `aria-live="polite"`, replacing all ten.

### H. Tables

14 files build raw `<table>`s; none has a `<caption>`, and header cells lack `scope`. `DataTable` is used twice.

**MVP position:** most raw tables are on screens being merged or deferred ([15](15-mvp-ui-scope.md)). Fix the ones that survive — the review queue becomes a list of links rather than a table ([07](07-review-clearance.md)), and the audit log already uses `DataTable`. **Fix `DataTable` once**, and the surviving tables are correct.

---

## 3 · Requirements per screen

| Screen | Specific requirement |
|---|---|
| Login / Signup | Errors associated with fields; no CAPTCHA without an alternative; password field labelled and toggle-able |
| Home ([04](04-dashboard.md)) | Attention block `role="status"` **on first render only**, not on every poll |
| Submission ([05](05-submission.md)) | Step change announced; focus to the step heading; type selection a real radio group; upload zone keyboard-operable, not drag-only |
| Record detail ([06](06-record-detail.md)) | `<h1>` = title; sections labelled; track is `<ol>` with `aria-current="step"` |
| Review queue ([07](07-review-clearance.md)) | Rows are links; peer clearance icons carry text; count in `aria-live` |
| Decision ([07](07-review-clearance.md)) | `<fieldset>`/`<legend>` naming the office; reject warning `role="alert"`; **confirmation traps focus** |
| Clearance Track ([08](08-workflow-resubmission.md)) | Icon + label + colour; `preserved` distinguished **by text** |
| Search ([09](09-search-rag.md)) | `role="search"`; results announced once; AI answer in a labelled region; citations are named links |
| Audit ([10](10-audit-history.md)) | Table `<caption>` and `scope`; labelled filters; pagination announced |
| Role approvals ([11](11-saas-admin.md)) | Confirmation names the consequence in full |
| Navigation ([03](03-navigation.md)) | Rail items labelled at every breakpoint; drawer traps focus, returns it to the toggle |

---

## 4 · Cross-cutting rules

| Rule | Criterion |
|---|---|
| Visible focus indicator on every interactive element; never `outline: none` without a replacement | 2.4.7 |
| Touch targets ≥ 44 × 44 px | 2.5.5 (AAA, adopted — the product is used on phones) |
| Page title unique per route, set on navigation | 2.4.2 |
| Focus moves to `<h1>` on route change | 2.4.3 |
| Skip-to-content link as the first focusable element | 2.4.1 |
| Text resizes to 200 % without loss of content | 1.4.4 |
| No information conveyed by colour alone | 1.4.1 |
| Errors identified in text, not only in colour | 3.3.1 |
| `lang` on `<html>` | 3.1.1 |
| Nothing that flashes more than three times per second | 2.3.1 |

**Not adopted for the MVP:** full AAA contrast, sign-language alternatives, context-sensitive help on every field, reading-level constraints. Stated explicitly so the exclusion is a decision rather than an oversight.

---

## 5 · Cost

| Fix | Files | Effort |
|---|---|---|
| `Input` — `aria-invalid` + `aria-describedby` | 1 | **~15 min** |
| `Modal` — focus trap and restore | 1 | **~1 hr** |
| Add `sr-only` utility + label the icon rail | 2 | **~30 min** |
| `text-gray-400` → `text-gray-500` for text | 77 uses | **~45 min** |
| `aria-hidden` on decorative icons | 87 uses | **~1 hr** |
| Shared `Skeleton` with `aria-live` | 10 call sites | **~1 hr** |
| Skip link + focus-on-route-change | 1 | **~30 min** |
| `DataTable` — caption and `scope` | 1 | **~30 min** |
| **Total** | | **≈ 5.5 hours** |

Under one dev-day. Six of the eight are single-component changes that propagate everywhere, which is the only reason the number is this small — and the reason to do them **before** building the Clearance Track rather than after, so the new component inherits correct primitives instead of needing its own retrofit.

Excluded from that figure: the Clearance Track's own accessibility, which is part of building it ([08](08-workflow-resubmission.md)), and per-screen semantic corrections, which happen as each screen is touched.

---

## 6 · Verification

| Method | When | Catches |
|---|---|---|
| **axe-core in CI**, failing the build on serious/critical | Every PR (`T-03`) | Contrast, missing names, ARIA misuse — roughly 40 % of issues |
| **Keyboard-only walkthrough** of the submission → decision → resubmission path | Before the pilot | Focus traps, lost focus, unreachable controls |
| **Screen reader pass** — NVDA on Windows — on the same path | Before the pilot | Unlabelled icons, unannounced state, meaningless reading order |
| **200 % zoom at 360 px** | Before the pilot | Reflow, clipping ([13](13-responsive.md)) |
| **Contrast audit of the token set** | Once, at design-system fix time | The gold and grey problems above |

Automated testing alone is insufficient and should not be presented as coverage. The keyboard walkthrough of the one path that carries the thesis contribution is the single highest-value manual check, and it takes about twenty minutes.

**Honest scope statement.** These measures target WCAG 2.1 AA on the sixteen MVP screens and are verified by the methods above. No formal third-party accessibility audit is planned, and no conformance claim should be made in the thesis beyond *"designed and tested against WCAG 2.1 AA using automated and manual methods."*
