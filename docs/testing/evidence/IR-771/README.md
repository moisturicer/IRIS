# IR-771: Ask IRIS secondary text contrast

Executed 2026-11-02 against the IR-771 working tree based on `5f024e31`.

The toolbar label, composer keyboard hint and conversation-history timestamp use the existing `text-stone-600` utility instead of `text-stone-400`. No backend or answer-path behavior changes.

## Real-browser measurements

Chromium 156.0.8078.4 rendered the actual application at 1280 x 800. Computed foreground and ancestor background colors were read from the DOM; WCAG relative luminance gives:

| Text | Foreground | Background | Contrast |
| --- | --- | --- | ---: |
| Ask IRIS toolbar label | #57534e | #ffffff | 7.6293:1 |
| Enter to send hint | #57534e | #ffffff | 7.6293:1 |
| Selected conversation timestamp | #57534e | #fdf2f2 | 6.9606:1 |

All exceed WCAG AA's 4.5:1 minimum. Substituting the former #a8a29e into those measured backgrounds gives 2.5220:1 and 2.3009:1 respectively; this is a calculated comparison, not a separate before-build capture. See [raw measurements](contrast.json) and [desktop capture](desktop.png). An axe WCAG A/AA scan of this selected-history state returned no violations.

The unchanged `frontend/scripts/ir414-prepass.mjs` was run from `frontend/`:

```text
node scripts/ir414-prepass.mjs --base http://127.0.0.1:5174 --api http://127.0.0.1:8019 --backend-ref fixture-only-no-live-backend --only "Ask IRIS" --out ../docs/testing/evidence/IR-771/prepass
```

[The report](prepass/prepass.md) and [raw output](prepass/prepass.json) record no color-contrast violation, no other axe violation and no page overflow at 360, 768, 1280, 1745 and 1280@200%. Keyboard walks at 360 and 1280 found no missing focus indicators or covered controls.

## Limits

Docker was stopped and no live backend was listening. Browser checks used a temporary local fixture API with a synthetic Student session, configured AI status and an empty conversation. The selected-history measurement returned one synthetic conversation; the pre-pass returned an empty history to keep `/ai` on its landing route. Both rendered the real frontend source and stylesheet. These are styling checks, not backend integration or human WCAG sign-off. The frontend ref in the report is the base HEAD because the changes were uncommitted while Vite served them. No provider was called and no real account or conversation was changed.

## Local checks

- Focused `RAGChatPage.test.tsx`: 47 passed.
- Production build (`tsc && vite build`): passed.
- ESLint: no errors; 3 existing warnings.
- Full frontend suite: local runs interrupted; GitHub CI is the full-suite evidence, as requested by the user. Check the PR for the result.

## Code review

- Standards: no blocking findings. Changes are localized and follow ADR-055. The inherited class-assertion test checks utilities; browser measurements establish contrast.
- Spec: no findings. All three affected text pairs exceed 4.5:1, and the unchanged pre-pass is clean at all five viewport settings. Fixture-backed rendering limits integration claims.

The first full-suite invocation was interrupted after timeouts while free physical memory was approximately 418 MiB on this 8 GiB machine. The suite was restarted unchanged with `npm test -- --maxWorkers=2` to bound memory use, then stopped at the user's request to push and use GitHub CI as the full-suite evidence. Neither local attempt is reported as passing.

- Traceability shape check: 6 passed (one local pytest configuration warning: pytest-django is not installed).
