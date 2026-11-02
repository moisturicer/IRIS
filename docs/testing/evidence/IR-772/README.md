# IR-772 — Download Requests 360 px reflow

Executed 2026-11-02 against the IR-772 working tree based on `c764c3c6`.

## Change

The Download Requests filter toolbar lets **Refresh** take a full-width row below
the `sm` breakpoint, then restores the existing compact right-aligned placement
from `sm` upward. The data table keeps its own intentional horizontal scrolling.

## Component regression

`frontend/src/features/admin/DownloadRequestsPage.test.tsx`

- focused file: 1 passed
- tests: 6 passed
- IR-772 regression verifies `w-full`, `justify-center`, `sm:ml-auto`, `sm:w-auto`

## Frontend verification

- TypeScript: pass
- ESLint: 0 errors, 3 pre-existing warnings
- production build: pass
- full frontend suite: 129 files passed, 1,658 tests passed
- `git diff --check`: clean

## Browser acceptance

IR-414 Download-only pre-pass in headless Chromium 156.0.8078.4:

| Viewport | Overflow | axe serious/critical | axe other | Keyboard |
| --- | --- | ---: | ---: | --- |
| 360 | none | 0 | 0 | 9 stops; 0 no-indicator; 0 covered |
| 768 | none | 0 | 0 | — |
| 1280 | none | 0 | 0 | 21 stops; 0 no-indicator; 0 covered |
| 1745 | none | 0 | 0 | — |
| 1280@200% | none | 0 | 0 | — |

The pre-pass implementation reports `overflow: null` when
`document.documentElement.scrollWidth - clientWidth <= 1`, so the 360 px result
meets the ticket's no-page-overflow acceptance criterion.

The generated report labels the frontend ref `c764c3c6` because the IR-772
changes were still uncommitted when the browser run executed. Vite served the
modified IR-772 working tree. The backend was `c764c3c6`; IR-772 changes no
backend behavior.

Human review remains the merge gate.
