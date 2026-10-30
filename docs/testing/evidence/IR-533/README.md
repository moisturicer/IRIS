# IR-533 entry-flow verification

Implementation scope confirmed by the project lead in the 2026-10-30 grilling:
complete IR-538, IR-555 and IR-207; check sign-in, registration, verification,
pending/declined access and the lock dialog. WCAG 2.1 AA remains the baseline.
The project's 44×44 targets and 4.5:1 disabled-text requirement also apply.
Unsupported statistics stay removed; restoring one requires a verifiable source.

## Executed checks

- Entry-page/primitives/palette suite: **13 files, 191 tests passed**.
- Added lock-dialog keyboard and axe tests: **2 passed**. The fixture supplies
  client rectangles because jsdom does not implement layout; the real browser
  separately checks focus containment.
- After the final registration/link changes: sign-in, registration and lock-dialog
  regression suite: **3 files, 71 tests passed**.
- After fixing focus return from a disabled sign-in trigger: **43 tests passed**,
  lint passed and TypeScript passed again.
- Production TypeScript/Vite build passed. Existing configuration, Tailwind screen
  and bundle-size warnings remain.
- Frontend lint passed with **0 errors, 6 existing warnings**. The deliberate
  `src/ir207-probe.tsx` reintroduction of `text-gold hover:bg-gold-dark` failed with
  `no-restricted-syntax` and exit 1; the file was then removed and lint passed.
  Existing gold borders/rings pass. The library star icon has one documented
  exception: its accessible name, `aria-pressed` and filled/outline shape carry
  the state independently of gold. Guard fixtures are excluded from lint.
- Accounts REST regression suite: **64 passed**, including six lockout tests,
  the current-user role-request seam, password policy and sessions. Executed in
  the existing backend image using a temporary source copy and a separate
  `test_iris_ir533` PostgreSQL database. No live account state was changed.
- Backend flake8 passed on the four changed Python files.

Commands were run from the isolated `fix/IR-533-entry-accessibility` worktree.
The accounts command was `python -m pytest apps/accounts -q --tb=short
--reuse-db -p no:cacheprovider`, with `IRIS_REQUIRE_DB=1` and
`DB_NAME=iris_ir533`. Missing staticfiles warnings are from that temporary copy.

## Browser evidence

Headless installed Google Chrome, reduced motion, real application routes and
styles; API responses intercepted with synthetic fixtures. These browser checks
do not establish integration with a live registration or approval service; the
REST suite above tests the backend separately.

[`browser-audit.json`](browser-audit.json) records **36 state/width combinations**:
login; signup error and success; verification success and failure; pending and
declined; manual and timed lock dialogs, each at 360, 768, 1280 and 1745 pixels.
All have one h1, no horizontal overflow, no measured target below 44×44, and no
reported WCAG A/AA axe violation. Text/placeholder/disabled-select foregrounds
and effective backgrounds were sampled from computed browser styles; the
minimum recorded ratio is **4.59:1**.

**Limits:** axe recorded incomplete contrast checks in 11 combinations,
including clipped/off-viewport shelf labels and content obscured by a dialog.
Those are not counted as passes. Computed color samples and screenshots provide
additional evidence, not a full accessibility conformance audit. Decorative
shelf titles use the existing verified pairs: white/brand 12.34:1,
white/brand-light 9.53:1, brand-100/brand-dark approximately 13:1,
stone-900/white 17.49:1.

[`keyboard-reflow-contrast.json`](keyboard-reflow-contrast.json) records the
additional 320px reflow and keyboard checks. Sign-in had six stops,
registration had fourteen, verification had one/two named links, and pending
and declined each had the sign-out action. All reached controls had a visible
focus indicator; no horizontal overflow or undersized measured target was
found. The lock dialog retained Tab/Shift+Tab focus, closed with Escape, and
returned focus to Sign In after that button was enabled again.

Primary action pairs were **12.34:1 resting, 9.53:1 hovering**. Full-width
disabled actions were **9.42:1** (stone-700 on stone-100, opacity 1). Outline
actions were **10.27:1 resting, 9.83:1 hovering**. Placeholders were **4.80:1**,
or **4.59:1** on disabled input/select backgrounds. This is measured browser
style evidence, not an actual assistive-technology session or browser-zoom test.

Screenshots are named `<state>-<width>.jpg`; for example
[verification on a phone](verify-success-360.jpg),
[verification failure](verify-failure-360.jpg),
[signup errors](signup-error-360.jpg),
[signup success](signup-success-360.jpg),
[pending access](pending-360.jpg),
[declined access](declined-360.jpg), and
[desktop verification](verify-success-1745.jpg).

## Human review still required

Run an actual screen reader through loading → verified/failed announcements,
registration errors/confirmation, pending/declined access and both lock dialogs.
Record the assistive technology/browser versions, the spoken results, and the
reviewer's name. Also confirm browser zoom/text resizing with the real browser
controls. DOM assertions, axe and 320px reflow do not prove either check.

This evidence is not human approval, full WCAG certification, or permission to
mark the parent tickets Done. IR-203 and IR-209 remain open until IR-533 is
reviewed, approved and merged under the repository Definition of Done.
