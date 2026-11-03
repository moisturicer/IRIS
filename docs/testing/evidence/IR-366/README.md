# IR-366 — Close the palette guard evidence

**Ticket:** IR-366 — Close the palette guard: the whole frontend is white, black, grey and maroon

## What changed

IR-366 closes the staged palette rollout.

- Removed the staged palette exception lists from `frontend/src/test/palette.test.ts`.
- The guard now scans every frontend `.ts`, `.tsx`, and `.css` source file, excluding only the guard file's own deliberate fixtures.
- Converted the six remaining shared `gray` / `slate` stragglers to `stone`:
  - `components/compliance/DpaConsentModal.tsx`
  - `components/layout/Breadcrumbs.tsx`
  - `components/layout/NotificationBell.tsx`
  - `components/records/DownloadRequestModal.tsx`
  - `components/shared/DataTable.tsx`
  - `features/discover/PaperCiteModal.tsx`
- Replaced touched hand-written maroon values with established `brand` tokens.
- Updated `docs/ui-ux/01-design-system.md` so the palette rule applies to the whole interface and the guard is the enforcement mechanism.
- Updated `docs/ui-ux/14-component-inventory.md` to state that the staged exception lists are gone.

## TDD evidence

### RED — removing the allowlists first

The guard was changed before the six source files were converted.

Result:

```text
Test Files  1 failed (1)
Tests       1 failed | 11 passed (12)
```

The failing whole-tree second-grey guard named exactly the remaining six files:

- `src/components/compliance/DpaConsentModal.tsx`
- `src/components/layout/Breadcrumbs.tsx`
- `src/components/layout/NotificationBell.tsx`
- `src/components/records/DownloadRequestModal.tsx`
- `src/components/shared/DataTable.tsx`
- `src/features/discover/PaperCiteModal.tsx`

### GREEN

After conversion:

```text
src/test/palette.test.ts
12 passed / 12
```

TypeScript, lint, and production build were run successfully. The build emitted only the existing Vite chunk-size warning.

### Guard regression proof

A deliberate throwaway edit added:

```text
bg-red-500
```

to `src/components/shared/StatusBadge.tsx`.

The guard failed exactly as required:

```text
src/components/shared/StatusBadge.tsx:
  bg-red-500
```

The probe was then reverted and the palette guard returned to green.

## Full frontend suite

```text
Test Files  130 passed (130)
Tests       1703 passed (1703)
```

The suite emitted known jsdom / React Router / `act(...)` diagnostic noise, but no test failures.

## Visual pass

A routed-screen headless Chromium pre-pass was run against the IR-366 worktree after GREEN. Generated screenshots should be attached to the PR to satisfy the ticket's "one screenshot per screen area" review evidence.

## Baseline drift check

IR-366 started from `9dfe169e`.

Before commit, `main` advanced to `11056fad` by four commits. GitHub comparison showed that none of the nine IR-366 scoped files changed between those refs; the intervening work is backend/extraction and repository metadata. The branch should therefore be rebased onto current `main`, followed by a focused palette + TypeScript sanity check. The full frontend suite and visual pre-pass do not need to be repeated solely for that baseline movement.

## Review status

- Standards review: pending final post-rebase diff
- Spec review: pending final post-rebase diff
- Full suite: green
- Palette guard: green after deliberate regression proof
- Human approval: outstanding
- CI: outstanding until PR
