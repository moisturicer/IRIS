# IR-574: Pick papers to compare; confirm Conversation deletion

Executed 2026-11-02. Vite served this task's modified frontend based on `8a0b7d0a`. The running Docker backend bound the main checkout's `backend/` at `c764c3c6` (no tracked backend edits). This is not a same-build release verification.

## Browser checks

Chromium 156.0.8078.4 used actual demo-account authentication, owned Conversations and the authenticated catalogue API. The comparison answer SSE was intercepted with deterministic output: no provider was called and no generated-comparison quality claim is made.

The existing server reported a maximum of **6**. The picker blocked sending with one selection, disabled additional choices at six, kept selected chips removable and sent five remaining IDs through the existing `comparison_record_ids` field after removal. It sent no scope-widening flag.

The picker rendered without horizontal page overflow at **360 x 740** and **1440 x 1000**. Tab remained inside the dialog for twenty steps; Escape closed it; closing returned focus to its trigger. Search, Area, Close, Done and pagination targets measured at least 44 px high. Search uses the existing catalogue search over titles, abstracts and authors, narrowed by the selected Area.

The dialog is portalled outside the composer's native form. Enter on a checkbox and the Close button did not submit the drafted comparison. The selected-chip list wraps and scrolls within a bounded, keyboard-focusable region on a phone.

**Picker-only axe WCAG A/AA: no violations.** A whole-page scan recorded the existing IR-771 low-contrast toolbar/hint/history text behind the picker. Those baseline findings are retained in [browser.json](browser.json); no full-page conformance pass is claimed. The new picker uses stone-600 secondary text and the existing brand controls.

## User-requested deletion confirmation

At 360 px, opening confirmation closed the history drawer so only one focus trap was active. Cancel received initial focus. Opening and Escape sent no DELETE. An injected 503 left the confirmation visible with an error and retry; the next explicit confirmation used the real DELETE endpoint on a Conversation created by this script. The UI navigated away from the deleted address. Cleanup removed only script-created Conversations.

## Evidence

- [Raw browser observations](browser.json)
- [Desktop picker](desktop-picker.png)
- [Phone picker](phone-picker.png)
- [Phone selections](phone-chips.png)
- [Phone delete confirmation](delete-confirm-phone.png)

## Automated checks and review

Per the user's standing instruction, **GitHub CI supplies lint, TypeScript/build and automated test evidence**. No local pass is claimed. The page regression additions cover catalogue-vs-private-history choices, declared origins, search/Area requests, configured bounds, removed IDs, unknown capacity, scoped refusal, Conversation switching, stale replies, search retry and accidental submission. The existing deletion test is deliberately changed to require confirmation; new tests cover Cancel, Escape and failure recovery.

Server-side catalogue authorization remains enforced by the unchanged `RecordViewSet.get_queryset()`. Existing backend tests in `apps/records/tests.py` (`test_list_still_excludes_drafts_for_the_owner`, `test_list_still_excludes_drafts_for_staff`, stranger draft refusal) exercise that boundary in CI; the mocked page test does not establish server authorization by itself.

Standards and Spec agent reviews are recorded in the PR. Human approval remains outstanding.
