# ADR-061: Request timeout, cancellation and retry in the API client

## Status

**Proposed** — 2026-11-06 ([IR-914](https://citiris.atlassian.net/browse/IR-914)), awaiting a named approver. Drafted by an AI agent. **The two timeout values are the team's to set**; the ones below are a proposal, held in `frontend/src/api/requestPolicy.ts` so changing one is a one-line edit.

## Context

`apiClient` set no `timeout`, so a request that never answered left a screen loading for ever. Only some calls took an abort signal (manuscript uploads and blobs, Ask IRIS). Screens that read in a `useEffect` could let a slow earlier response overwrite a later one. The only retry was the single replay after a 401 token refresh, and no rule said anything else.

## Decision

**Timeouts.** Chosen per request in `apiClient`'s request interceptor, so a caller cannot leave a file transfer on the short one:

| Request | Timeout (proposed) |
|---|---|
| Ordinary (lists, details, small writes) | 30 seconds |
| Upload (`FormData` body) or blob download (`responseType: "blob"`) | 5 minutes |

A caller that passes its own `timeout` keeps it. Server timeouts and the Ask IRIS stream protocol (which already abort, follow and cancel) are unchanged.

**Typed error.** A request that exceeds its timeout rejects with `RequestTimeoutError` (`timeoutMs`, `method`, `url`, `cause`), recognised by `isRequestTimeout`. It is not a server refusal: nothing is known about whether the server acted.

**Cancellation.** `useApiRead(read, deps)` gives a screen's list or detail read an `AbortSignal`, aborted when the screen unmounts or `deps` change. A response arriving after its read was cancelled is dropped even if the API call ignored the signal, so a stale response never replaces a newer one. API read functions accept `{ signal }` as they are migrated onto the hook.

**Interrupted state.** `useApiRead` reports `interrupted` for a timeout, and `InterruptedState` shows it with a Retry. IR-895's "interrupted" state is not in the repository at this date; `InterruptedState` is the interim, and IR-895 should replace or adopt it.

**Retry rule.**

- Nothing is retried automatically. The one existing exception is the 401 replay: the server refused that request, so nothing ran, and it happens once.
- A **write**, an upload, or anything that could duplicate an act is never sent again without a person asking. A timed-out write may have been applied.
- A **read** is sent again only when the reader chooses Retry.

## Consequences

**Gains:**

- A hung request ends in a message and a Retry within a known time.
- A slow response can no longer overwrite a newer one on a screen that uses the hook.
- No path exists by which a write is silently doubled.

**Costs:**

- 30 seconds may be too short for a slow campus link or a heavy report, and 5 minutes too short for a very large file on a poor one; either shows as a false "interrupted". Retry is one click, but the numbers need the team's judgement.
- Roughly seventy components still fetch in their own `useEffect`. Only `DeleteRequestsPage` uses the hook so far; the rest move over one at a time, and until then keep the old behaviour except that their requests now time out.
- No automatic retry means a brief network blip on a read needs one click to recover.

**Rejected:**

- **Automatic retry of idempotent reads:** hides slowness, multiplies load on a struggling server, and the idempotence of each read is unverified.
- **One timeout for everything:** it cannot suit both a list and a manuscript.
- **A data-fetching library (e.g. TanStack Query):** a larger architectural change than this ticket; revisit with the team.
