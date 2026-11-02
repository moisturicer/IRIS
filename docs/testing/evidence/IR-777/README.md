# IR-777 â€” notification bell Label in Name

IR-777 fixes a WCAG 2.1 2.5.3 Label in Name defect reported by IR-631's
real-browser axe run. Above nine unread notifications, the bell visibly showed
`9+` while its `aria-label` exposed the uncapped raw count, for example
`Notifications, 20 unread`.

## Implementation

`NotificationBell` derives one `unreadBadge` string:

- `0` unread: no visible badge; button name is `Notifications`.
- `1`â€“`9` unread: the visible number is also the count in the accessible name.
- More than `9`: the visible badge and accessible name both use `9+`.

The same value now drives both surfaces, so display formatting and accessible
name formatting cannot silently diverge.

## Red-first evidence â€” 2026-11-02

Before the implementation change:

```text
NotificationBell.test.tsx

12 tests
11 passed
1 failed

visible badge: 9+
accessible name: Notifications, 20 unread

Unable to find role="button" with name "Notifications, 9+ unread"
```

The `0` and `7` unread cases already passed; only the capped count reproduced
the defect.

## Green evidence â€” 2026-11-02

Focused regression suite:

```text
npx vitest run src/components/layout/NotificationBell.test.tsx

Test Files  1 passed (1)
Tests       12 passed (12)
```

Full frontend suite:

```text
npm test

Test Files  129 passed (129)
Tests       1655 passed (1655)
Duration    108.05s
```

Lint:

```text
npm run lint

0 errors
3 warnings
```

The three warnings pre-date IR-777:

- `src/api/ai.test.ts:137` â€” unused `_`.
- `src/features/accounts/UserListPage.tsx:68` â€” existing `useEffect` dependency warning.
- `src/features/records/paper-view/PaperViewPage.tsx:571` â€” unused eslint-disable directive.

Build:

```text
npm run build

tsc && vite build
1355 modules transformed
built successfully
```

The existing Vite native-config, Tailwind screen, and chunk-size messages remain
warnings; IR-777 changes no build configuration or warning threshold.

## Browser evidence still required

The original defect is axe-core's real-browser `label-content-name-mismatch`.
jsdom verifies the accessible-name contract but cannot replace that browser
check. IR-777 therefore remains partial until IR-631's Chromium accessibility
checks for journeys 04 and 05 are re-run against this change and no longer list
the notification bell.

This file records implementation and automated regression evidence; it is not a
claim of whole-application WCAG conformance.
