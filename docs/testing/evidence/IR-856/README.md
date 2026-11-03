# IR-856 browser evidence

Captured from the Vite app with Chromium and reduced motion. `capture.cjs` records sign-in and registration at 360 CSS px, 1440 CSS px, and a 720 CSS px viewport rendered at 2× device scale to model a 1440 px display at 200% browser zoom. The captures use the real route components; account API calls were not mocked.

| Page | 360 px | Desktop | 200% zoom |
|---|---|---|---|
| Sign in | [Phone](sign-in-phone.png) | [Desktop](sign-in-desktop.png) | [Zoom](sign-in-zoom-200.png) |
| Registration | [Phone](registration-phone.png) | [Desktop](registration-desktop.png) | [Zoom](registration-zoom-200.png) |

At every size, the label and sheet share the same left coordinate; the label's bottom and sheet's top overlap by 1 CSS px. The document width equals the viewport width in all six captures. Both mastheads have only the Help link. On a phone, Help receives the first keyboard Tab focus; [sign-in](sign-in-focus-phone.png) and [registration](registration-focus-phone.png) captures show that focus. Axe's WCAG 2/2.1 A/AA audit, including contrast, reported no violations on either phone page. The public `/entry/help` route rendered its heading in the same browser run.

Run `capture.cjs` from the repository root with the frontend Vite server on `127.0.0.1:5173` and Playwright installed locally. The script prints its geometry and audit results.
