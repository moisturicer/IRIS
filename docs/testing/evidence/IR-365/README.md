# IR-365 — Ask IRIS palette rollout evidence

**Ticket:** IR-365 — The Ask IRIS hub and chat page use only white, black, grey and maroon

## Implementation

IR-365 removes the Ask IRIS files from the palette guard's shrinking exceptions and converts their remaining off-palette utilities:

- `AIHubPage.tsx`: gray/slate/amber → stone and shared maroon status tones.
- `RAGChatPage.tsx`: retrieval-only → `TONES.active`; unavailable → `TONES.attention`.
- `ConversationSidebar.tsx`: destructive hover red → maroon; selected conversation remains soft maroon.
- `answerLayout.ts`: gray code-block tones → stone.
- `ChatInput.tsx`: removes the persistent `Enter to send · Shift+Enter for new line` helper; Enter/Shift+Enter behaviour is unchanged.
- `palette.test.ts`: Ask IRIS files removed from both IR-365 exception sets.
- `RAGChatPage.test.tsx`: deliberate assertions for selected conversation, retrieval-only state, unavailable state, and absence of the persistent keyboard hint.

No Ask IRIS behaviour was intentionally changed.

## TDD evidence

### RED

Focused run after removing the IR-365 allowlist entries and adding the semantic-state assertions:

- `src/test/palette.test.ts`: 2 expected failures.
- `src/features/ai/RAGChatPage.test.tsx`: 2 expected failures.
- Total: **4 failed, 60 passed**.

The guard named the expected remaining violations:

- `AIHubPage.tsx`: amber plus gray/slate.
- `RAGChatPage.tsx`: amber.
- `ConversationSidebar.tsx`: red.
- `answerLayout.ts`: gray.

The retrieval-only assertion saw the old amber banner, and the unavailable assertion saw the old neutral wrapper.

### GREEN

Focused run:

```text
Test Files  2 passed (2)
Tests       64 passed (64)
```

Additional validation:

- `npx tsc --noEmit` — passed.
- `npm run lint` — 0 errors, 3 pre-existing warnings.
- `npm run build` — passed.
- Full frontend suite — **130 files, 1,706 tests passed**.
- `git diff --check` — no whitespace errors; Windows LF→CRLF notices only.

After the keyboard-hint cleanup, the focused/full/browser checks were rerun successfully before PR preparation.

## Browser evidence

IR-414 Ask-IRIS-only headless Chromium pre-pass against frontend/backend `0158d80b`:

| Viewport | Overflow | axe serious/critical | axe other | Keyboard |
|---|---|---:|---:|---|
| 360 | none | 0 | 0 | 7 stops; 0 no-indicator; 0 covered |
| 768 | none | 0 | 0 | — |
| 1280 | none | 0 | 0 | 16 stops; 0 no-indicator; 0 covered |
| 1745 | none | 0 | 0 | — |
| 1280@200% | none | 0 | 0 | — |

Generated after-change screenshots:

- `Ask_IRIS__360.jpg`
- `Ask_IRIS__768.jpg`
- `Ask_IRIS__1280.jpg`
- `Ask_IRIS__1745.jpg`
- `Ask_IRIS__1280_200pct.jpg`

## Visual-evidence limitation

Jira asks for before/after screenshots of the hub, a cited conversation, retrieval-only/degraded mode, and the selected-conversation sidebar at desktop and 360 px.

The current router no longer mounts `AIHubPage`; `/ai` and `/ai/conversations/:conversationId` both mount `RAGChatPage`. Therefore the hub conversion is enforced by the source-tree palette guard but cannot honestly be represented as a normal routed-app screenshot.

The automated pre-pass captures the routed Ask IRIS screen, not all four named semantic states. Those exact named before/after screenshots remain manual evidence to attach if the acceptance criterion is to be closed literally.

## Review status

- Standards review: **PASS**
- Spec/code review: **PASS**
- Jira visual-evidence criterion: **PARTIAL — named before/after screenshots still outstanding**
- Human approval: outstanding
- CI: outstanding until PR
