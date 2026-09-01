# 00 — Design Direction

UI/UX direction for the final validated MVP. **Exploration and documentation only — no implementation.**

**Source note.** `docs/architecture-grill/` does not exist; by agreement the design-interview conclusions were recorded as ADRs. Governing sources are `docs/adr/`, `docs/architecture-tasks/`, `docs/mvp-validation/`, the SRS/SDD, and direct inspection of `frontend/src/` on `refactor/docker-service` @ `0b85ab2`.

---

## 1 · The central design problem

**The thesis contribution is invisible in the interface.**

`RecordClearance` — the model holding per-office clearance state — is never serialized into any API response. `grep -rn "clearance" frontend/src` returns nothing outside a code comment. `StatusBadge` renders `Record.pipeline_status` and nothing else.

Measured against what the interface is required to communicate:

| Must communicate | Status today |
|---|---|
| Current workflow state | ✅ `StatusBadge`, 13 statuses |
| Office clearance status | ❌ **Absent** |
| Pending offices | ❌ **Absent** |
| Approved offices | ❌ **Absent** |
| Declining office | ❌ **Absent** — only inferable from the review comment list |
| Preserved clearances | ❌ **Absent** |
| Resubmission requirements | ⚠️ Partial — a button and a sentence, no specifics |
| Final completion | ✅ `published` / `completed` |

**Five of eight are missing.** A user looking at a Thesis/Research record in `parallel_review` sees a single amber pill reading *"Parallel Office Review"*. They cannot tell that IERC has cleared and KTTO has not, and after a decline-and-resubmit they cannot tell that IERC's clearance was preserved.

This is not a polish problem. It is the difference between a product that demonstrates the research contribution and one that merely contains it. Everything in this document set proceeds from it.

**The design answer is one new pattern — the Clearance Track (§[08](08-workflow-resubmission.md)) — plus the API work to feed it (`W-07`).**

---

## 2 · Design principles

Five, in priority order. When they conflict, the earlier wins.

**1 · Make the workflow legible without explaining the implementation.**
A student should understand *"IERC has cleared this; KTTO is still reviewing; you only need to address ITSO's comments"* without knowing what a `RecordClearance` row is. Status names in the UI are institutional language, not enum values.

**2 · State before action.**
Every workflow screen answers *"where is this, and what happens next"* before it offers a button. Users of institutional workflow systems are usually checking status, not acting.

**3 · Show the whole track, not just the current step.**
Parallel clearance is the point. A single status badge collapses a four-office picture into one word and destroys the information the contribution creates.

**4 · Degrade visibly, never silently.**
When AI is unavailable, say so and fall back to keyword search ([ADR-008](../adr/008-ai-degradation-to-fts.md)). A silent fallback that returns worse results while looking identical is worse than an error — and it would contaminate the usability evaluation.

**5 · Configuration over branching.**
Office names, stage labels and terminology are data, not code ([ADR-002](../adr/002-workflow-transition-table.md)). The UI renders what the API describes; it does not hardcode "IERC".

---

## 3 · What exists — an honest assessment

The frontend is further along than the backend. This is a **refinement** exercise, not a redesign.

### What holds up

| | Evidence |
|---|---|
| **Real design tokens** | `tailwind.config.js` defines a brand ramp (`#6B0F12` + 50–900), gold, cream, Inter, a 6-step font scale, radii, two card shadows |
| **A primitive layer** | `ui/` — Button (5 variants × 3 sizes), Input (label/error/hint/leading), Card, Badge, Modal, Spinner, Toast |
| **Shared components** | `DataTable` (wraps `@tanstack/react-table`, paginated), `EmptyState`, `StatusBadge`, `RoleBadge`, `ConfirmDialog`, `FileUploadZone` |
| **A responsive shell** | Sidebar as drawer < 768 px, icon rail 768–1279, full ≥ 1280; `AppShell` handles all three |
| **Global focus styling** | `index.css` sets a 2 px brand `:focus-visible` ring with offset — better than most projects this size |
| **Modal semantics** | `role="dialog"`, `aria-modal`, `aria-labelledby`, Escape-to-close, `aria-hidden` backdrop, labelled close button |
| **Feature coverage** | ~37 page components; the workflow path is complete end to end |

### What has drifted — measured, not impressionistic

| Finding | Count |
|---|---|
| `[#6B0F12]` arbitrary value vs `brand` token | **134 vs 61** — 69% bypass the token |
| `text-[13px]` arbitrary vs `text-sm` token | **182 vs 7** — the font scale is 96% unused |
| Font Awesome loaded **twice** in `index.html` | 6.5.1 **and** 6.5.2 — two full stylesheets |
| Icons without `aria-hidden` | ~72 of 95 announced as meaningless to screen readers |
| `text-gray-400` on white — **≈2.8:1, fails WCAG AA** | 77 occurrences |
| Identical loading markup duplicated | 10 files, while `Spinner` exists and is used in 5 |
| Raw `<table>` instead of `DataTable` | 14 files vs 2 using the shared component |
| `StatusBadge` contains a stale `ktto_review` key | Not in `PIPELINE_STATUS` |

**The pattern is consistent:** the system was designed, then bypassed under delivery pressure. The fix is adoption, not redesign — which is cheap, and is why §[01](01-design-system.md) recommends codifying rather than replacing.

---

## 4 · Brand

Keep the existing identity. It is CIT-U-appropriate and already implemented.

| Token | Value | Contrast on white | Use |
|---|---|---|---|
| `brand.DEFAULT` | `#6B0F12` | **12.3:1** ✅ AAA | Primary actions, active nav, focus ring, headings |
| `brand.light` | `#8B1316` | 9.8:1 ✅ | Hover states |
| `gold.DEFAULT` | `#C59334` | **≈2.8:1** ❌ **fails AA** | **Decorative only** — never text or icons conveying meaning |
| `cream` | `#F5F0E8` | — | Backgrounds |
| `gray-400` | `#9ca3af` | **≈2.8:1** ❌ **fails AA** | **Stop using for text** — minimum `gray-500` (4.8:1) |

**Two accessibility corrections are needed at token level**, and both are cheap: gold is not a text colour, and `gray-400` is not a text colour. Together they account for the majority of the contrast failures in §[12](12-accessibility.md).

**SaaS note.** Brand colour becomes per-institution configuration post-MVP ([11](11-saas-admin.md)). The token indirection already supports it — which is another reason to stop hardcoding `#6B0F12`.

---

## 5 · Voice

Institutional, plain, specific. The audience is university staff and students, not software users.

| Instead of | Write |
|---|---|
| "Record is in `parallel_review`" | "With IERC and KTTO for review" |
| "Clearance reset" | "IERC needs to review this again" |
| "Preserved clearances: 2" | "KTTO and ITSO already cleared this — they won't need to review again" |
| "Submission failed" | "Your file is 62 MB. The limit is 50 MB." |
| "AI unavailable" | "AI search is offline. Showing keyword results instead." |

**Rule:** name the office, name the action, name what the reader must do. Never surface an enum value.

---

## 6 · Scope discipline

Bounded by [ADR-001](../adr/001-mvp-scope-boundary.md): **~27 dev-days for the entire semester**, of which the frontend gets roughly 3.

**In:** `W-07` clearance visibility · pilot-surface reduction · token adoption on touched components · the accessibility corrections in §[12](12-accessibility.md).

**Out:** any redesign · new component libraries · TanStack Query · shared table modules · form-stack consolidation · component splitting · animation. All are `DO NOT BUILD YET` under ADR-001.

**The only new UI work that earns its place is the Clearance Track**, because it is the interface to the thesis contribution and without it the contribution cannot be evaluated ([`docs/mvp-validation/00-validation-strategy.md`](../mvp-validation/00-validation-strategy.md)).

---

## 7 · Document map

| Doc | Covers |
|---|---|
| [01](01-design-system.md) | Tokens, drift, primitives, what to codify |
| [02](02-information-architecture.md) | Content model, screen map, role→screen matrix |
| [03](03-navigation.md) | Sidebar, breadcrumbs, role-based navigation |
| [04](04-dashboard.md) | Dashboard / home screen spec |
| [05](05-submission.md) | Submission wizard spec |
| [06](06-record-detail.md) | Record detail — **the workflow's home** |
| [07](07-review-clearance.md) | Reviewer queue and decision spec |
| [08](08-workflow-resubmission.md) | **Clearance Track patterns** and resubmission |
| [09](09-search-rag.md) | Search, AI answers, degradation |
| [10](10-audit-history.md) | Audit and history |
| [11](11-saas-admin.md) | What is configurable, MVP vs post-MVP |
| [12](12-accessibility.md) | Keyboard, labels, focus, contrast, semantics |
| [13](13-responsive.md) | Breakpoints, 360 px, table strategy |
| [14](14-component-inventory.md) | What exists, what is needed, what to delete |
| [15](15-mvp-ui-scope.md) | KEEP / REDUCE / DEFER / REMOVE per screen |
