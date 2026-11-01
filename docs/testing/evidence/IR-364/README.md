# IR-364 palette verification

Screenshots compare the components at base `7b5f7447` with this change, using
Chromium at 1440 × 900 and 360 × 900. Each image is a full-page capture.
The harness mounted the real SettingsPage inside a padded page container and
BrowserRouter, with a synthetic Student account and a deterministic successful
profile-save response. It mounted the real AuthBootstrap with hydration held
pending for the loading state. No live account or server data was used.
The app shell is outside these component captures.

The existing Font Awesome 6.5.2 CSS and solid font were served locally for the
captures because the browser could not load the CDN. Application assets and
loading behavior are unchanged. Temporary capture files are not shipped.

| State | Before desktop | After desktop | Before 360 px | After 360 px |
| --- | --- | --- | --- | --- |
| Saved profile | [Before](before-saved-1440.png) | [After](after-saved-1440.png) | [Before](before-saved-360.png) | [After](after-saved-360.png) |
| Required-name error | [Before](before-error-1440.png) | [After](after-error-1440.png) | [Before](before-error-360.png) | [After](after-error-360.png) |
| Consent recorded | [Before](before-consent-1440.png) | [After](after-consent-1440.png) | [Before](before-consent-360.png) | [After](after-consent-360.png) |
| No consent recorded | [Before](before-no-consent-1440.png) | [After](after-no-consent-1440.png) | [Before](before-no-consent-360.png) | [After](after-no-consent-360.png) |
| Session bootstrap | [Before](before-bootstrap-1440.png) | [After](after-bootstrap-1440.png) | [Before](before-bootstrap-360.png) | [After](after-bootstrap-360.png) |

All 20 states reported document width equal to viewport width: no horizontal
page overflow. The settings section navigation retains its horizontal scroll.
The [focused field](after-focus-360.png) has a solid 2 px maroon ring with a
2 px white offset (verified through computed box-shadow).

Browser axe color-contrast checks reported no violations in Profile, Privacy,
or the bootstrap status. Shared tone contrast is 17.49:1 for white on
stone-900 (success) and 11.26:1 for brand on brand-50 (recoverable error).
Consent icons use stone-900 or stone-600 on white. Error announcements retain
the existing polite `role="status"`; added icons are hidden from assistive
technology, leaving the message unchanged.

The existing SettingsPage, SettingsProfileFields, AuthBootstrap and palette
test files pass: 4 files, 37 tests. TypeScript `tsc --noEmit` passes.
Only the two palette allowlist entries were removed; no behavioral test or
assertion was changed. The full frontend suite (`npm test -- --maxWorkers=4`)
reports 126 files and 1,607 tests passing (332.04 s). Its stderr includes
expected error-boundary fixtures and jsdom's unimplemented `scrollBy` warning.
CI results are recorded in the PR.

`npm run build` also completes (`tsc && vite build`), with the existing large
chunk warning. AI-assisted review against base `7b5f7447` found zero Spec
findings and one Standards finding (a contrast-ratio typo), corrected above.
This is supporting review evidence; human approval remains outstanding.
