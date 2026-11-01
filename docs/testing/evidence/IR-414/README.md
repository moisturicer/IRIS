# IR-414 (F12) automated pre-pass

**This is a pre-pass, not F12's evidence.** It is what a headless browser can
measure. It does not replace the human pass IR-414 requires: a real device,
judging whether a focus order makes sense, and NFR-U2's five timed participants
on Publish. Its job is to point that pass at the right places.

- **Tool:** `frontend/scripts/ir414-prepass.mjs` (how to run it is in its header).
- **Results:** [`prepass.md`](prepass.md) (summary) and
  [`prepass.json`](prepass.json) (every cell, with axe targets and keyboard
  stops). Full-page screenshots at 360 px and at 200 %, where reflow fails,
  are in [`shots/`](shots/). The other viewports' shots were dropped to keep
  the repository small (a rerun regenerates them), so the `shot` paths in
  `prepass.json` for those cells point at nothing.
- **Device:** headless Chromium 156 with emulated viewports of 360×740,
  768×1024, 1280×800 and 1745×982. 200 % zoom is emulated as a 1280-wide window
  at 200 %, which lays out as a 640×360 CSS-pixel viewport at device scale
  factor 2.
- **Stack:** frontend `a9df3d9f` (this branch). The backend is the shared dev
  stack at `0fd6967b` (main checkout, `feature/IR-566-account-saved-records`,
  which contains this branch's base `d01d5de1`). Its AI migrations 0034 and 0035
  were not applied, and the pass never reaches them. Seeded demo data, run
  2026-11-01.

## What it checked

Per screen and viewport:
- horizontal overflow (WCAG 1.4.10);
- axe-core WCAG 2.x A/AA violations, with colour contrast measured in a real
  browser;
- at 360 and 1280, a keyboard walk recording each focus stop's indicator and
  whether another element covers it.

F6's deferred Review-section checks, at 360, 1280 and 200 %, as an adviser on
record 18 and as IERC on record 14: toolbar arrow keys and wrap, the sticky bar
over the timeline's last entry, and the *Request documents* dialog's focus in,
Tab trap, Escape and focus return. All passed for both reviewers. The adviser's
arrow-key check is n/a because only one action is enabled before *Open review*.

## Failures, verified in a second targeted probe

| # | Finding | Measured | Where | WCAG |
|---|---|---|---|---|
| 1 | `stone-500` (#78716c) text on `stone-100` (#f5f5f4) | **4.39 : 1**; 4.5 : 1 needed at 11–13 px | Paper View record bar (*Back*, version, breadcrumb, zoom %), My Reviews tab counts, Review workspace labels, at every viewport | 1.4.3 |
| 2 | `stone-400` (#a8a29e) text on white or `#fdf2f2` | **2.30–2.52 : 1** | Ask IRIS: turn timestamps, the *Ask IRIS* label, the "Enter to send" hint | 1.4.3 |
| 3 | The *Refresh* button runs off the page | **68 px** horizontal scroll at 360 | Download requests (RDCO) | 1.4.10 |
| 4 | A textarea with no accessible name | axe *critical* | Import records, every viewport | 4.1.2 / 1.3.1 |
| 5 | Scrolling regions keyboard users cannot reach | axe *serious* | Workflow analytics' two `overflow-x-auto` tables at 360; the office Review pane (`.review-pane-body`) at 200 % | 2.1.1 |

**Fixed on this branch:** the *Request documents* dialog opened with focus left
on the button behind it, so Tab moved around the page underneath (WCAG 2.4.3).
It now uses the shared `useDialogFocus` hook, and the table above shows it
passing.

**Not reproduced, so not filed:**
- Discover's `.inset-0` contrast hit at 1280 and 1745. The targeted probe found
  no contrast failure on Discover.
- Settings' "covered" input. No visible input is covered; it is most likely the
  visually hidden photo file input under its label.

**For a person to confirm:** at 360 the adviser's comment textarea is reported
under a `<p>` in the sticky footer when it takes focus (WCAG 2.4.11).

**Not measured:**
- The ITSO coordinator screens. `itso.coordinator@cit.edu` is not seeded in this
  dev database, which predates IR-478's coordinators; run
  `manage.py seed_demo --accounts-only` and resume. This run's retries of the
  refused login locked that missing account for 15 minutes. The script no longer
  retries a refusal.

## What this pass cannot see (left to the human pass)

- Overflow inside panes that scroll on their own; only the page is measured.
- Whether a focus indicator is visible: any box-shadow counts, including one
  that is always there.
- The confirmation dialog, *Ask about this paper*, and whether the sticky bar
  traps focus below `lg`.
- Account activation, password reset, lockout states, add/edit routes, and any
  validation or pending/success state. The pass never submits a form or sends a
  question.
- Legibility, a real device, and NFR-U2's timed participants.
