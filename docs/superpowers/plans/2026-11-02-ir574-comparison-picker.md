# IR-574: Comparison picker implementation plan

**Goal:** Readers select 2 to the server-configured maximum catalogue Records and ask the existing comparison path about them.
**Spec:** IR-574 and its IR-553 amendment; accepted ADR-026 scope guarantees and ADR-046 declared origin metadata.
**Architecture:** A composer control opens the existing Modal with catalogue search and an Area filter. Selection is kept in the existing per-Conversation client and submitted as comparison_record_ids through aiApi.askStream. The comparison engine and its output components stay unchanged.
**Stack:** React, TypeScript, existing Modal/Input/Select/Button and Tailwind tokens.

## Design and constraints

- Reuse the authenticated /records/ catalogue and classification filter; no private-record lookup or new endpoint.
- Display every declared origin explicitly, including unknown; do not infer it from authors.
- No fixed maximum: status.comparison_max_records governs selection and sending; unknown capacity disables picking. Existing backend validation remains authoritative.
- Per-Conversation chips inherit the composer surface, wrap on phones and have labelled removal buttons.
- A record-scoped Conversation never admits comparison selections. Switching and deletion retain the client's isolation guarantees.
- Search loading, empty, failure/retry, pagination, limit, disabled and scoped states have text. Ignore stale search responses.
- Use GitHub CI for lint, typecheck/build and automated tests; browser-check responsive layout, keyboard focus and contrast locally.

## Tasks

- [x] Add page regression tests for catalogue-only requests/origins, title + Area filters, 2..N, removal, per-Conversation selections and scoped refusal.
- [x] Add ComparisonPicker.tsx, extending the composer with a children slot and a separate send-disabled state.
- [x] Extend useConversationClient.ts with per-thread selections/scope and optional comparison IDs in send, without new planner or scope protocol.
- [x] Connect the page's status limit and picker to the composer. Verify changes in Chromium at desktop/360 px, including focus return, stale responses and errors.
- [x] Add per-ticket traceability and honest evidence. Run Standards and Spec review; commit, push, open PR and inspect GitHub CI.

## Review focus

Late search replies; removed chips leaking into requests; scoped Conversations; a lowered/unknown server limit; switching while a comparison is streaming.

## User-added scope

On 2026-11-02 the user requested a confirmation dialog before deleting a Conversation in this same PR. Reuse ConfirmDialog, name the target, initially focus Cancel, block duplicate/pending actions, retain failure/retry, and close the phone history drawer before opening the confirmation. Add page regressions and real-browser verification. The old immediate-delete regression is deliberately updated to require explicit confirmation.

CI evidence is collected from GitHub; no local automated suite/build/lint run duplicates it.
