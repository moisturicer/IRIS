# ADR-073: Pages update live, by server-sent hints that make them refetch

## Status

**Accepted**, 2026-11-19, by Lee Jasmin Adolfo ([IR-1213](https://citiris.atlassian.net/browse/IR-1213)). Accepted verbally, and recorded here by Ashlee Sean the same day; there is no written approval on the PR.
- **Already decided:** Ashlee Sean chose live push over timed polling on 2026-11-17.
- **Drafted** by an AI agent (Claude Code) at Ashlee's request. AI does not make architecture decisions (CLAUDE.md), so the design below was a proposal until accepted. The three questions the first draft left open were settled by Ashlee on 2026-11-19 (§Questions settled while drafting); Lee Jasmin Adolfo then accepted the design.
- **Built by IR-1213.** Measured before merge, as settled question 3 asked (§Consequences). Two build notes: an office's pool channel is its role's channel (`live:role:<office>`), since IRIS's offices are roles; and the stream view is a class-based async view, so the route matrix can read its method.

## Context

**What people see today.** Team testing (2026-11-17): new submissions, reviews, routing and requests appear only after a manual browser refresh.

**How pages load data today** (`main` at `cf97aec0`):
- Every page fetches with its own `useEffect` through `apiClient`. There is no shared query cache.
- A few re-read on events within the same tab:
  - the sidebar's queue counts after a decision on a queue page (`lib/queueCounts.ts`, IR-1138);
  - its My Library dot and My Reviews count on every address change (IR-1208).
- Nothing re-reads when another person acts.

**What the stack already offers:**
- **ASGI.** `backend` runs gunicorn with `UvicornWorker` (ADR-017), so an async view can hold many open connections cheaply.
- **SSE through the edge.** Ask IRIS already streams server-sent events from Django through nginx and Caddy (`apps/ai/streaming.py`, IR-504). The response sets `X-Accel-Buffering: no` and nginx passes it through.
  - That class pumps a *sync* generator on a thread per stream. That suits an answer that lasts a minute, but not a connection held open all day: it would hold one thread per open tab.
- **Redis** (`redis>=5`, which includes `redis.asyncio`) is already running for Celery and the cache.
- **Notifications** (`apps/notifications/services.py`) are created inside the workflow services for every act that reaches a person: routed, sent back, completed, revision asked, new version, and the request decisions. Each one already knows exactly who should hear about the change.

**Constraints from other ADRs:**
- **Access is one predicate (`visible_to`, IR-153)**, so a live message must never tell someone that a record they can't open exists.
- **The inactivity rule (IR-166, ADR-072)** must not count an open stream as activity.
- **The access token lasts 30 minutes** and the refresh token is cookie-only (ADR-072), so a long-lived connection has to outlive token expiry.

## Decision

1. **Hints, never data.**
   - The server sends a short message naming *what changed*, such as `{"topics": ["reviews", "record:42"]}`. The page then refetches what it already shows, through the normal API with its normal permission checks.
   - A hint carries no titles, names or states.
   - Everything a person sees after a hint is exactly what a manual refresh would have shown.

2. **One stream per tab, over `fetch`, not `EventSource`.**
   - `GET /api/v1/live/` is an async Django view answering `text/event-stream`.
   - The browser reads it with `fetch` and a stream reader, the way Ask IRIS's runtime reader does (IR-634). `EventSource` can't send the `Authorization` header, and the refresh cookie is scoped to `/api/v1/auth/` (ADR-072).
   - The view is fully async: an async generator over `redis.asyncio`, with no thread and no database connection held while idle. It authenticates once, inside `sync_to_async`, then closes its database connection.

3. **Who receives a hint: channels the server picks, never ones the browser asks for.**
   - `live:user:<id>`, the person's own channel. A hint is published here for every `Notification` created for them, with topics derived from its kind and record: `notifications`, plus `reviews`, `library` or `record:<id>` as applicable. The recipients are exactly the notification's, and a record id goes only to someone already notified about that record, who may see it.
   - `live:office:<party>`. A pool change (routed, claimed, assigned, returned) publishes `{"topics": ["reviews"]}` to that office, with no record id, so its members' To review lists and counts refresh.
   - `live:role:rdco`. A request created or decided (role, download, delete, call) publishes `{"topics": ["queues"]}`, so RDCO's queue pages and sidebar counts refresh.
   - The view subscribes a connection to its user's channel, their offices' channels and their role channel, all decided by the server from the account.
   - Publishing happens in `transaction.on_commit`, so a hint never arrives before the change it announces is readable. If Redis is down, the publish failure is logged and swallowed, and the act still succeeds.

4. **One Redis subscription per server process, not per tab.**
   - Each ASGI worker keeps a single `PSUBSCRIBE live:*` connection and fans messages out to its open streams through in-process queues.
   - Redis connections then grow with the number of server processes, not with tabs.
   - A stream's queue is bounded. A stream that falls behind is closed, and its tab reconnects and refetches (decision 6).

5. **Token expiry and the inactivity rule.**
   - The stream ends when the access token it was opened with expires, so at most 30 minutes after that. The browser then reconnects through the normal refresh path (ADR-072), so a signed-out or revoked session can't keep a stream for longer than that.
   - Opening the stream sends the idle header like any request. The open stream itself records no activity, so a tab left open still reaches the 30-minute idle sign-out.

6. **Hints are a nudge, never the source of truth.**
   - On every (re)connect, and whenever the tab regains focus, the page refetches what it shows. A missed hint therefore costs at most a delayed update, never a wrong page.
   - This also covers IR-1033: notifications refetch on focus.
   - Reconnects back off exponentially (1 s doubling to 60 s, with jitter).

7. **Keepalive.** A comment line (`: ping`) every 25 seconds keeps nginx's default 60-second `proxy_read_timeout`, and any idle proxy, from closing the stream. No nginx change is needed beyond the existing per-response `X-Accel-Buffering: no`.

8. **Frontend shape.**
   - `lib/live.ts` owns the one connection per tab.
   - Pages call `useLiveRefresh(["reviews"], reload)`. The hook runs `reload` when a matching hint arrives, after a reconnect, or when focus returns, coalescing bursts within about 500 ms.
   - **Wired in the build:**
     - the sidebar counts (queues, My Reviews, My Library) and the notification bell;
     - My Reviews and the Office console;
     - My Library;
     - the review page (`record:<id>`);
     - RDCO's request queues.
   - Discover, the public catalogue, is not live: it refetches on focus.

## Questions settled while drafting

All three were left open in the first draft and decided by Ashlee Sean on 2026-11-19:
1. **The first build wires the pages in decision 8.** Discover refetches on focus only.
2. **Live updates pause silently when Redis is down.** Pages fall back to refetching on focus, with no notice: nothing shown is wrong, only later.
3. **Capacity is measured before merge.** About 100 simulated open tabs on the Docker stack. Memory per backend process, open connections and Redis connections are recorded in the build PR, and a problem found there blocks the merge.

## Alternatives Considered

### A. Timed polling (every ~30 s) plus refetch on focus
- **Gains:** smallest build, no new endpoint, no Redis fan-out.
- **Costs:** up to 30 s late. Polling also adds steady load that grows with open tabs, whether or not anything changed.
- **Not chosen:** Ashlee chose live push on 2026-11-17. Refetch on focus is kept anyway (decision 6).

### B. WebSockets (Django Channels)
- **Gains:** two-way, and a well-known library.
- **Costs:** a new dependency, a channel layer, and a second routing stack beside Django's. Nothing here needs browser-to-server messages.
- **Not recommended.**

### C. Push the changed data itself, not a hint
- **Gains:** one fewer round trip per update.
- **Costs:** every message would need its own permission filtering and serialization, duplicating each endpoint's `visible_to` and serializer. A slip leaks data.
- **Not recommended:** hints keep the existing API as the only reader (decision 1).

### D. `EventSource` with the token in the query string
- **Gains:** the browser's built-in reconnect.
- **Costs:** the access token would end up in server and proxy logs.
- **Not recommended:** `fetch` streaming is already used by Ask IRIS.

### E. One Redis subscription per tab
- **Gains:** simplest code.
- **Costs:** Redis connections grow with every open tab.
- **Not recommended:** decision 4 keeps them per process.

## Consequences

- **Pages refresh themselves** for the events in decision 3 within about a second, and on focus for everything else.
- **One long-lived HTTP connection per open tab** on the backend, with no thread or database connection while idle.
  - **Measured 2026-11-19 on the Docker stack** (uvicorn, 2 workers, the branch's code, a throwaway database):
    - **Memory:** a warmed-up server went from 222.6 MiB to 234.7 MiB with 100 open streams, about **120 KB per tab**. That is more than the "tens of KB" first estimated, and still about 12 MB per 100 tabs.
    - **CPU:** 0.5% with all of them idle.
    - **Opening:** 100 streams opened in 1.0 s.
    - **Redis:** 2 pattern subscriptions, one per worker, not one per tab.
    - **Delivery:** a published hint reached 100 of 100 streams, median 32.5 ms and slowest 41.5 ms.
  - **End to end:** a real `Notification` created in another process reached an open stream with its topics.
- **Every refetch is an ordinary API call,** so a burst of activity becomes a burst of reads. Decision 8 coalesces them per tab.
- **Workflow services gain `publish_live(...)` calls** next to their notifications, inside `on_commit`. A future act that forgets to publish still shows up on focus.
- **Redis becomes part of the browser experience,** though not of correctness (decision 6).

## Security Impact

- **No new data path.** Hints carry topics and, on a person's own channel, record ids they were already notified about. Everything shown is fetched through the existing permission-checked API.
- **Channels are server-assigned.** The browser can't subscribe to another person's, office's or role's channel.
- **No token in a URL** (decision 2). Streams end with their access token (decision 5).
- **CORS is unchanged.** The stream is same-origin through nginx.

## Deployment Impact

- **No new service, no new port and no migration.** It needs Redis, which is already running.
- **nginx:** none beyond the existing response header. Caddy already streams Ask IRIS.

## Amendment 2026-11-23 (b): the person who asked (IR-1289)

**Status: Proposed.** Drafted by an AI agent at Lee Jasmin Adolfo's request; it is a proposal until a person accepts it.

**Why.** Decision 3 tells RDCO's queues when a role or call request changes, but not the person who made it. An approved user's open app kept its old role, and the pending-approval screen stayed up. Because the server picks a stream's role channel when the stream opens, a new role was not heard until a reload. A Call's poster didn't see RDCO's decision either.

**Two new topics, each on one person's own channel only:**
- **`account`.** A saved `RoleRequest` (asked, approved or declined) and any role change through `User.assign_role` tell that user. Their tabs read `/auth/me` again, on the hint and when the tab is shown. When the role has changed, the tab reopens its stream (`restartLive`), so the new role's channel is heard. A generation counter stops the replaced loop from reconnecting.
- **`calls`.** A saved or deleted `Opportunity` tells its poster. **My Calls** and **Calls and conferences** refetch quietly on it and when the tab is shown.

**Not covered.** A newly confirmed Call has no reader list to tell, so other people's boards catch up when their tab is shown again.

## Amendment 2026-11-23: the review discussion (IR-1284)

**Status: Proposed.** Drafted by an AI agent at Lee Jasmin Adolfo's request; it is a proposal until a person accepts it.

**Why.** Decision 3 publishes `record:<id>` only beside a `Notification`. Most review-discussion acts create none -- replies, Conversation comments, resolve, reopen, severity changes, answers, edits -- so an Adviser's reply on one screen never reached the student's open paper. The threads panel also never refetched, not even on focus.

**Change to decision 3.**
- A saved or deleted `ReviewComment` publishes `record:<id>` on commit to the **own channel** (`live:user:<id>`) of every active account `may_read_review` admits: owners, anyone who held a seat, and members of an office with an active assignment (`apps.reviews.mentions.candidates`). Never a role channel, so an office member with no part in the record hears nothing.
- Readers are worked out after commit, from committed state.
- A draft is its writer's alone, so a draft's save or delete is published to its writer only.
- *Finish review* and a Decision closing threads change comments with `update()`, which sends no signal; both call `apps.live.signals.review_changed` themselves.
- The paper page's threads panel (`useReviewThreads`) refetches quietly on `record:<id>`, on reconnect and on focus. A failed quiet read keeps the shown list.

**What this widens.** Decision 3 said a record id goes "only to someone already notified about that record". Now it also goes to someone who may read that record's review. They can already open the record and its discussion, so no hint reaches anyone who can't.

**Cost.** One `may_read_review` check per candidate per committed comment write. Bursts are coalesced per tab (decision 8).

## Related Requirements

NFR labels only: none. Relates to IR-1033 (refetch on focus), IR-1138 (queue counts), IR-1208 (My Reviews count), IR-166 and ADR-072 (sessions), ADR-017 (ASGI), and IR-504 and IR-634 (streaming).

## Related Tasks

- IR-1213: the spec, which builds this after acceptance.
- IR-1284: the review discussion (Amendment 2026-11-23).
- IR-1033.
