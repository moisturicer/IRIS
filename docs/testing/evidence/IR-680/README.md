# IR-680 visual regression evidence

Captured 2026-10-30 in headless Chromium (Playwright 1.64.1), viewport 1600×1000, reduced motion. Before is `c6b6c1e`; after is the IR-680 workspace extraction. Both use the real app, Review mode, PDF renderer, fonts and existing page-test record data, with synthetic Adviser and ITSO responses. All API traffic is intercepted; no live records or credentials are used.

| Viewer | Before | After | Result |
|---|---|---|---|
| Adviser | [before](adviser-before.png) | [after](adviser-after.png) | Identical PNG SHA-256 |
| ITSO reviewer | [before](itso-before.png) | [after](itso-after.png) | Identical PNG SHA-256 |

`comparison.json` records image hashes and record/manuscript/tracker request parity. The duplicate reads are React development StrictMode's existing behavior, identical in both runs. Fonts were explicitly loaded before capture. The baseline uses a dependency junction, so its unchanged bundled font files were served directly by the capture harness to avoid Vite's filesystem allowlist; the app and styles were unchanged.

This comparison verifies one wide layout for each requested role. Existing page tests cover capability rendering, action refresh, author/read modes and Ask IRIS navigation; these screenshots do not establish every workflow state.
