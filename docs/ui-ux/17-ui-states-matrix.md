# 17 — UI states matrix

**IR-906** (child of IR-895). One row per surface, one column per state a read can leave a screen in. Every cell is **implemented**, **added by IR-906**, or **N/A with the reason**. No cell is left "missing".

## The five states

| State | What the reader sees | Shared piece |
|---|---|---|
| **Loading** | A placeholder in the shape of the content, announced once | `Skeleton`, or the surface's own placeholder |
| **Empty** | The read worked and there is nothing: "no research matches", "nothing here yet" | `EmptyState` |
| **Error** | The read failed outright (network, server). Says nothing was changed and offers **Try again** | `EmptyState tone="error"`, `ReadFailedState` |
| **Interrupted** | The read got no answer within its timeout (ADR-061). Nothing is known about the server, so only **Retry**, chosen by the reader | `InterruptedState` |
| **Access revoked** | The server answered 403 or 404. **One screen for a hidden Record and a missing id**, with the same words, so the page never confirms that something exists (IR-153) | `NotFoundScreen`, `EmptyState` |

`readFailureKind(err)` (`src/lib/readFailure.ts`) is the one place a failed read is sorted into `interrupted`, `unavailable` (403 or 404, alike) or `failed`. Where a surface must tell a refusal from a failure, use it; where only the timeout matters, `isRequestTimeout` is enough.

Legend: **✓** already implemented · **●** added by IR-906 · **N/A** with the reason. "Missing" was the third state in the ticket; every cell found missing was implemented in this change, and what is left is named in the cell or under "Not in this matrix".

## The matrix

| Surface | Loading | Empty | Error | Interrupted | Access revoked |
|---|---|---|---|---|---|
| **Discover** (`DiscoverPage`) | ✓ `ResultsSkeleton` | ✓ no results with filters (Clear filters); nothing published yet | ✓ "We couldn't load research" + Try again; a failed Load more keeps the list and retries | ● `InterruptedState` + Retry for the first load. A timed-out **Load more** keeps the list and shows the ordinary "didn't load" line with Try again, which is a retry too | N/A — the list is read under the visibility predicate every time, so a Record that stops being readable is absent on the next read. A card opened afterwards lands on Paper View, which has this cell |
| **Paper View** (`PaperViewPage`) | ✓ `LoadingSkeleton` on first load; moving between Records keeps the page | N/A — the page is one Record that exists; its sections carry their own empty copy | ✓ "We couldn't load this record" + Try again | ● `InterruptedState` + Retry | ● `NotFoundScreen subject="Record"` for 404 **and 403**; ● also when a re-read after an act (download request, document request, embargo) finds access gone |
| **My Library** (`MyLibraryPage`, its four views) | ✓ placeholders in Overview, My research, Saved, Download requests | ✓ each view has its own copy and next step | ✓ "Could not load …" + Try again | ● all four views, through `ReadFailedState` (Saved reads its account saves from the library store, which gained an `interrupted` flag) | ✓ Saved reports papers it can no longer read as "no longer available" instead of hiding them. N/A for My research and Download requests — both endpoints are scoped to the signed-in reader, a lapsed session is the session layer's, and any other refusal reads as an error with Try again |
| **Ask IRIS** (`RAGChatPage`, Django path) | ● "Loading this conversation…" while one is opened (before, the opening screen showed starter questions); ✓ an answer streams or shows `AssistantMessageSkeleton` | ✓ starter questions; ✓ no sources | ● an address or list that fails to load shows an in-place state with Try again (before, a toast over an empty screen); ✓ a failed answer still toasts and keeps the question | ● `InterruptedState` + Retry | ✓ "This conversation is not available" for 404; ● 403 now reads the same |
| **Review** — My Reviews (`MyReviewsPage`) | ✓ `Skeleton` | ✓ per-tab copy | ● a first-load failure had **no way out**; now Try again | ● `InterruptedState` + Retry | ● a refusal says My Reviews isn't available to the reader and offers no retry (access may have changed) |
| **Review** — Office console (`OfficeConsolePage`) | ✓ `Skeleton` | ✓ "no open reviews" | ✓ + Try again | ● `InterruptedState` + Retry | ✓ "This console is for coordinators" for 403 (now sorted by `readFailureKind`) |
| **Review** — workspace panels in Paper View (`ReviewTimeline`, `ReviewRoutingTracker`) | ✓ skeleton rows | ✓ timeline and tracker empty copy | ● the tracker panel told the reader to "reload the page"; it now offers Try again, as the timeline does | ● both say it took too long and offer Retry | N/A, with a known gap — both show their own "could not load" with Try again for a 403 or 404 and do not tell Paper View, so the page stays open. Paper View drops to Not available only on the re-reads that follow a download request, a document request or an embargo change; other re-reads still swallow the error |

## Not in this matrix, and why

- **The runtime reader** (`RuntimeReader`, behind `AI_RUNTIME_READER`, off by default) has its own run states from IR-726 (queued, running, interrupted, retry). It is a different protocol, not a read.
- **Writes.** A timed-out write is never retried by the client and may have been applied (ADR-061). Each form owns how it says so; this matrix covers reads.
- **Review analytics** (`ReviewAnalyticsPage`) was not audited: it is a coordinator report rather than a work surface, and its states are a follow-up.
- **Admin, Publish, Settings and the other surfaces.** The ticket names five. IR-895's other children own the rest.
- **Cancellation.** These surfaces still fetch in their own `useEffect`, so a slow earlier response can still overwrite a later one there. ADR-061 plans moving them onto `useApiRead`; this ticket only makes their failures read consistently.
- **Colour contrast** of the new states is not checked under jsdom, where axe cannot do it (see `docs/ui-ux/12-accessibility.md`). It is checked in a real browser by the smoke tier's `axe-states.spec.ts` (IR-908), on mocked data, for the cells that tier can reach; the cells it does not scan are listed in `docs/testing/traceability/IR-908.md`.

## How it is proved

Each ● cell has a test that queries by role and accessible name. They are listed in [`docs/testing/traceability/IR-906.md`](../testing/traceability/IR-906.md).
