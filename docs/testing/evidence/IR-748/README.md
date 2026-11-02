# IR-748 — accessible User List and Audit Log tables

IR-748 addresses the screen-reader table defects found by IR-414's accessibility
pre-pass. The implementation is shared through `DataTable`, with each page
supplying its own table name.

## Behaviour verified

- User List exposes a table named **User accounts**.
- Audit Log exposes a table named **Audit log events**.
- Every column header declares `scope="col"`.
- The User List actions column has the accessible name **Actions**.
- One named `role="status"` / `aria-live="polite"` region announces loading,
  empty results, and completed pagination changes.
- The loading spinner is left unlabelled because the live region owns the
  announcement and should be spoken once.
- The stale sorting TODO is removed; sorting was not added.
- Both page suites retain axe checks for no serious or critical violations.

## Automated verification — 2026-11-02

```text
npm test

Test Files  129 passed (129)
Tests       1652 passed (1652)
Duration    104.46s
```

```text
npm run lint

0 errors
3 warnings
```

The three warnings pre-date IR-748:
`src/api/ai.test.ts:137`, `UserListPage.tsx:68`, and
`PaperViewPage.tsx:571`. IR-748 does not suppress or broaden lint rules.

```text
npm run build

tsc && vite build
1355 modules transformed
built successfully
```

The existing Vite warnings about `configLoader: native`, Tailwind object screen
variants, and chunks over 500 kB remain warnings; IR-748 changes no build or
warning threshold.

## Limits

This evidence verifies the named automated acceptance criteria in the two
screens and shared table component. It is not a claim of whole-application WCAG
2.1 AA conformance or human assistive-technology validation.
