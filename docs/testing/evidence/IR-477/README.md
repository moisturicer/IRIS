# IR-477 browser verification

Checked 2026-11-01 against `4abe60af`, using headless Chromium 156.0.8078.4 at **360 × 740**, with reduced motion. See `browser-check.json` for measured rectangles.

The full `PaperViewPage` rendered the actual author's `ReviewWorkspace`, action bar, `ResizeObserver`, and `PaperPdfReader` with real pdf.js canvas/text rendering. Browser request interception supplied the synthetic author, record, conversation citation (`fixture.json`), and valid three-page PDF (`fixture.pdf`). Authentication was a browser-only fixture; no database records, provider calls, or review decisions were changed. The timeline deliberately returned 503. External icon CSS was blocked after its request stalled. A separate Vite cache avoided stale dependency responses.

## Results

Every Review case loaded the citation address directly, including a fresh PDF load and bar measurement. The action bar measured **112px**, covering y=628–740; the reader toolbar measured **58px**, ending at y=122.

| Case | Observed passage | Result |
| --- | --- | --- |
| 400px passage | y=170.14–570.14 | 48px context retained; entirely above the bar |
| 480px passage | y=148.14–628.14 | Context reduced to end at the bar, within 1px scroll rounding |
| 600px passage | y=122.14–722.14 | Top remains under toolbar; passage exceeds the available 506px |
| Find match initially under bar | y=680.13–690.92 before; y=223.13–235.13 after | Window scrolled from 1520 to 1976; match clears toolbar and bar |
| Paper tab | Existing contained reader; no Review action bar | Paper tab receives no Review obstruction |

The arithmetic tests assume a taller, two-row toolbar; their 450px context-reduction case therefore becomes 480px in this actual browser layout. Both test and browser results follow the same landing rule. Screenshots accompany each case. The Find scenario used the control's DOM click handler because the existing page header overlaps the sticky toolbar at this viewport; this verifies Find's scrolling geometry, not pointer accessibility of that control.

Standards and specification reviews of the implementation reported no confirmed findings. Direct-arrival cases exercise the initial-measurement timing concern raised by review; they passed in this browser. This is verification evidence, not human approval or a deployment record.

## Local checks

`npx tsc --noEmit` passed. The five-file focused Windows run reported four files passing and 234 tests passing before a worker ran out of memory; a one-worker retry also failed during worker startup with an allocation error. A one-worker full-suite attempt was interrupted before a final result. These attempts do not establish a passing full suite. Earlier per-file results are recorded in PR #423; CI reported no checks when inspected.
