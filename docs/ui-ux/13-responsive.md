# 13 — Responsive Behaviour

**Governing requirement — NFR-U3:** the interface must be usable at **360 px** with **no horizontal scrolling**.

That is the constraint. Everything below follows from it.

---

## 1 · Breakpoints

`tailwind.config.js` does not override `screens`, so Tailwind's defaults apply:

| Token | Width | Used for |
|---|---|---|
| `sm` | 640 px | Large phones, landscape |
| `md` | **768 px** | **Sidebar rail appears** |
| `lg` | 1024 px | Two-column content |
| `xl` | **1280 px** | **Sidebar expands to labels** |

### The finding: two competing conventions

Measured across `src/**/*.tsx`:

| Prefix | Uses |
|---|---|
| `sm:` | 47 |
| `md:` | 17 |
| `lg:` | 34 |
| `xl:` | 15 |

**`AppShell` and `Sidebar` switch at `md` and `xl`.** Content screens switch at `sm` and `lg`. The shell and its contents therefore change shape at four different widths, none of which coincide:

```
 360        640        768        1024       1280
  │──────────│──────────│──────────│──────────│
             sm         md         lg         xl
          content    sidebar    content    sidebar
          reflows    → rail     2-col      → labels
```

At 768–1023 px the sidebar has already become a rail while content is still in its single-column phone layout — a 60 px rail beside a full-width mobile column. At 1024–1279 px content is two-column while the sidebar is still an unlabelled rail, which is the widest span where navigation is least legible ([12](12-accessibility.md) §2F).

**Correction: adopt one convention.** The shell's `md` / `xl` are correct — they are tied to real device classes and to the rail's own legibility. Content screens should move to `md` and `xl` so layout changes happen at the same two widths. This is a mechanical change to 81 `sm:` and `lg:` occurrences, and it should happen opportunistically as screens are touched, not as a dedicated pass.

---

## 2 · The three layouts

| Range | Name | Sidebar | Content |
|---|---|---|---|
| **< 768 px** | Phone | Off-canvas drawer, `w-[230px]`, backdrop | Single column, full-bleed |
| **768–1279 px** | Tablet | 60 px icon rail | Single column, `md:ml-[60px]` |
| **≥ 1280 px** | Desktop | 230 px, labelled | Up to two columns, `xl:ml-[230px]` |

`Sidebar.tsx:160` — `w-[230px] md:w-[60px] xl:w-[230px]` — is correct and needs no change.

---

## 3 · Tables are the NFR-U3 risk

**14 files build raw `<table>` elements. `overflow-x-auto` appears 4 times in the entire codebase.**

A five-column table — the audit log has Time / Event / User / Record / Details — cannot fit in 360 px. Without a scroll container it widens its parent, and the **page** scrolls horizontally. That is a direct NFR-U3 failure on at least ten screens.

### The rule

> **Wide content scrolls inside its own container. The page body never scrolls horizontally.**

### Per-table strategy

| Width | Behaviour |
|---|---|
| ≥ 1024 px | Full table |
| 768–1023 px | Drop low-priority columns into a per-row expander |
| **< 768 px** | **Not a table.** Cards: primary field as heading, remaining fields as labelled pairs |

Cards below 768 px, not a scrolling table. A horizontally scrolling table on a phone is technically compliant with "the page doesn't scroll" and practically unusable — the user scrolls a viewport-width window across a five-column grid and loses the row they were reading.

### Which tables survive

Most raw tables are on screens being merged or deferred ([15](15-mvp-ui-scope.md)). After scope reduction the surviving tabular surfaces are:

| Surface | Treatment |
|---|---|
| Audit log | `DataTable` — **fix `DataTable` once**, correct everywhere |
| Review queue | **Becomes a list of links**, not a table ([07](07-review-clearance.md)) — the responsive problem disappears with the markup |
| My submissions | Cards at every width |
| Published records | Cards at every width |

So the table problem is resolved by two things: one `DataTable` fix, and the scope cuts that were happening anyway.

---

## 4 · The Clearance Track at 360 px

The reason [08](08-workflow-resubmission.md) chose a **vertical** track over a horizontal stepper.

A horizontal stepper for a Project — Submitted → RDCO → ITSO → IERC + KTTO → RDCO Final → Published — is six nodes. At 360 px that is ~50 px per node including connectors: enough for an icon, not for a label. The result is either horizontal scroll (NFR-U3 failure) or unlabelled icons ([12](12-accessibility.md) §2B).

Vertical costs nothing horizontally and grows down, which is the axis a phone has.

```
360 px

  WORKFLOW
   ✓ Submitted            12 Sep
   ✓ RDCO Intake          14 Sep
   ● Office Clearance     2 of 3
     ✓🛡 ITSO
        Cleared — preserved
        14 Sep
     ✓  KTTO
        Cleared · 16 Sep
     ↩  IERC
        Revision requested
        18 Sep
   ○ RDCO Final           Not yet
   ○ Published            Not yet
```

Office rows stack label, then status text, then date. **The status text never truncates** — it is the contribution, and `Cleared — preserved` clipped to `Cleared —` is worse than no label at all.

---

## 5 · Per-screen behaviour

| Screen | ≥ 1280 px | 768–1279 px | < 768 px |
|---|---|---|---|
| Home ([04](04-dashboard.md)) | Blocks may sit two-up | Single column | Single column, full-width cards |
| Submission ([05](05-submission.md)) | Single column, max-width | Single column | One field per row; step indicator → *"Step 2 of 3"*; actions full-width stacked |
| Record detail ([06](06-record-detail.md)) | Track + resubmission side by side | Stacked | Stacked; Details collapsed by default |
| Review queue ([07](07-review-clearance.md)) | Rows with inline metadata | Rows | Cards; action full-width |
| Decision ([07](07-review-clearance.md)) | Two columns | Single column, context above form | Clearance panel → *"2 of 3 offices cleared"*, expandable; document opens in a new tab |
| Search ([09](09-search-rag.md)) | Single column, max-width | Single column | Filters → bottom sheet; snippets clamp to 3 lines |
| Audit ([10](10-audit-history.md)) | Full table | Details column → expander | Cards; filters stack |
| Role approvals ([11](11-saas-admin.md)) | List | List | Actions full-width stacked, destructive second |

---

## 6 · Cross-cutting rules

| Rule | Reason |
|---|---|
| **Content is single-column by default**; multi-column is an enhancement above `xl` | Designing up from 360 px means the constrained case is never an afterthought |
| Touch targets ≥ 44 × 44 px below 768 px | [12](12-accessibility.md); `Header`'s `w-[34px]` toggle is under this and needs padding |
| Primary action **last** in a stacked button group | Thumb reach on a phone |
| **Long titles wrap; they do not truncate to a tooltip only** | A `title` attribute is unreachable by touch. Truncation is acceptable only where the full text is reachable another way |
| Modals become full-screen sheets below 768 px | A centred dialog with margins wastes a third of the viewport |
| Fixed pixel widths need a `max-w-full` companion | `NotificationBell`'s `w-[320px]` dropdown at `right-0` is 89 % of a 360 px viewport before page padding |
| No fixed-position element taller than ~60 % of viewport height | The drawer is full-height by design; nothing else should be |
| Images and embeds `max-width: 100%` | |

---

## 7 · Verification

| Check | Method |
|---|---|
| **No horizontal scroll at 360 px** on all 16 MVP screens | DevTools at 360 × 640; `document.body.scrollWidth <= window.innerWidth` |
| Layout integrity at 360 / 768 / 1024 / 1280 | Manual pass, once per screen |
| **200 % zoom at 360 px** | Combined reflow check ([12](12-accessibility.md)) — the hardest case, and the one that finds fixed widths |
| Real device pass | One Android phone, one iPhone, before the pilot |
| Touch target audit below 768 px | Spot-check icon-only controls |

The `scrollWidth` assertion is the one worth automating — it is a single line per screen, it maps directly onto NFR-U3, and it is the check most likely to regress silently when someone adds a table.

**MVP/Post-MVP.** **MVP** — three layouts, tables→cards below 768 px, vertical Clearance Track, no horizontal scroll at 360 px. **Post-MVP** — container queries, a dedicated tablet two-column mode, offline support, an installable PWA shell.

**Backend/API dependencies.** None. Responsive behaviour is entirely a frontend concern — with one exception: labels must be short enough to work at 360 px, and under the label contract ([11](11-saas-admin.md)) those labels come from the server. `W-01`'s configuration should therefore carry a **short form** for each stage and office label, used below 768 px.
