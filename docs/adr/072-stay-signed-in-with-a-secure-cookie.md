# ADR-072: Staying signed in across tabs and browser restarts, with the refresh token in a secure cookie

## Status

**Accepted**, 2026-11-18, by Lee Jasmin Adolfo ([IR-1222](https://citiris.atlassian.net/browse/IR-1222)).
- **How it was accepted:** verbally, to Ashlee Sean, who recorded it here the same day. There is no written approval on the PR.
- **Who decided what.** The choices in §Decision were made by Ashlee Sean on 2026-11-18: storage, the "Keep me signed in" checkbox and the 30-day limit. The ADR was drafted by an AI agent (Claude Code) at Ashlee's request. AI does not make architecture decisions (CLAUDE.md). The two questions the first draft left open were settled by Ashlee (§Questions settled while drafting).
- **Built by IR-1222** (PR to follow on the card). Two implementation notes: refresh answers a refused session `401` (it declares a `WWW-Authenticate` header, as simplejwt's own view did); and refresh refuses inside one transaction, as the idle rule always has, so an expired session's `ended_reason` is recorded by the next authenticated request rather than by the refused refresh.

Amends [IR-166](https://citiris.atlassian.net/browse/IR-166)'s inactivity rule for remembered sessions only. Corrects `docs/security/SECURITY.md` §2 (see §Context, "The 7-day limit is not absolute").

## Context

**What a person sees today.** Hermoine Zozobrado, in team testing (2026-11-17):

> "basta dapat if mo duplicate tab gana japon signed in already (currently works) and if itype ang domain name sa search discover page dapat (currently lets users sign in and I feel like if imo iusab ang url sa taas kay mo sign in siya which is bad)"

In other words:
- **Duplicating a tab:** you stay signed in. This already works.
- **Typing the site's address:** you should land on Discover. Today you get the sign-in form.
- **Editing the address in the address bar:** today this can ask you to sign in again, which feels wrong.

IR-1215 (PR #869, merged) sends a signed-in person past `/login` within a tab. It can't fix a new tab, because of where the token is kept.

**How sign-in works today** (`main` at `616f0c7d`):

| Piece | Today |
|---|---|
| Access token | 30 minutes, held in memory only (`store/auth.store.ts`) |
| Refresh token | Returned in the login response body, kept by the browser in `sessionStorage["iris_refresh_token"]` (`frontend/src/lib/authStorage.ts`), sent in the body of `POST /api/v1/auth/token/refresh/` and `POST /api/v1/auth/logout/` |
| Rotation | `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION`: each refresh returns a new refresh token and blacklists the one presented |
| Session | `UserSession` (IR-166). Its id is the `sid` claim in every token of a sign-in. A session idle past `SESSION_IDLE_TIMEOUT_MINUTES` (30) is ended for good (`apps/accounts/sessions.py` `touch`), and the browser signs out at the same moment (`frontend/src/lib/activity.ts`, `IDLE_TIMEOUT_MS`) |
| Ending a session | Logout, a password change or reset (ADR-045), an administrator's revoke (IR-657) or lock (IR-644), and account deletion end it on the server at once |

`sessionStorage` belongs to one tab. A duplicated tab copies it, which is why that case works. A new tab, or a link opened in one, starts with none and shows the sign-in form.

That was deliberate: closing the tab ends the session on a shared lab machine (`docs/security/SECURITY.md` §2). An earlier review also flagged a token kept in durable storage, readable by any script on the page, as a finding (`docs/architecture-review/05-security-architecture.md`).

**The 7-day limit is not absolute.** `SECURITY.md` §2 calls the refresh token's 7 days "the absolute limit on a session". It isn't: simplejwt 5.5.1's `TokenRefreshSerializer` calls `set_exp()` on every rotation, so each refresh moves the expiry to 7 days from that moment. Today the 30-minute idle rule ends a session long before that matters. Once the idle rule no longer applies to remembered sessions, it does matter, so this ADR gives them a fixed end, 30 days from sign-in (decision 4), and corrects `SECURITY.md`.

**Same-origin.** In production the browser reaches the API on the site's own origin: Caddy terminates TLS (ADR-057) and nginx serves the app and proxies `/api/` (`frontend/nginx.conf`). In development it goes through Vite's `/api` proxy. A cookie scoped to the API path is therefore a first-party, same-site cookie in both.

## Decision

1. **The refresh token moves to a cookie that page scripts can't read.**
   - The login and refresh responses set it as `iris_refresh`, with `HttpOnly`, `Secure` (except with `DEBUG` on plain-`http` localhost), `SameSite=Strict` and `Path=/api/v1/auth/`.
   - It no longer appears in any response body, and the browser no longer stores it anywhere: `authStorage.ts`'s `sessionStorage` key is removed, and a leftover one is cleared on load.
   - The access token stays in memory, as now.
   - Refresh and logout read the token from the cookie only. Neither accepts one in the body.
2. **A new tab finds the session by asking for one.**
   - On load, the browser always calls refresh. The cookie goes with the request automatically, because the browser sends it, not the page.
   - With no cookie, the server answers `401` with `code: "no_session"`. The browser treats that as signed out and shows no "session ended" message. The session-ended codes (`session_idle`, `session_ended_*`) keep their meaning and their message (IR-645, IR-1081).
3. **"Keep me signed in" is a checkbox on the sign-in form, off by default.**
   - **Off:** the cookie has no `Max-Age`, so it lives until the browser session ends. Every tab shares it. The session's only limit is the 30-minute idle rule, unchanged: it ends 30 minutes after the person was last active, and not before. *(Ashlee, 2026-11-18.)* The refresh token's own 7-day expiry (`REFRESH_TOKEN_LIFETIME`) is not a limit a person meets: every refresh renews it, and an idle session ends at 30 minutes, long before it (§Context).
   - **On:** the cookie gets `Max-Age` of 30 days and survives a browser restart. The session is marked remembered (`UserSession.remembered`, a migration). The idle rule doesn't end it, on the server (`touch`) or in the browser (the idle watch reads `remembered` from the login and refresh responses).
4. **A remembered session lasts 30 days from sign-in, however much it is used.** *(Ashlee, 2026-11-18.)*
   - **Why from sign-in:** a forgotten, remembered session on a lab PC ends on a known date.
   - **How:** the session stores its end (`UserSession.expires_at`, sign-in + `REMEMBERED_SESSION_DAYS`, default 30). Every rotated refresh token keeps that same expiry instead of a fresh `REFRESH_TOKEN_LIFETIME`, the cookie's `Max-Age` is the time left, and refresh refuses the session after it with `session_expired`, which shows the existing "session ended" message.
5. **Refresh and logout are protected against cross-site requests.** `SameSite=Strict` already stops a browser from sending the cookie with a request another site starts. As a second layer, both endpoints refuse a request whose `Origin` is not one of `CORS_ALLOWED_ORIGINS`. They also require an `X-IRIS-Auth: 1` header: a cross-origin page can't add a custom header without a CORS preflight, which `CORS_ALLOWED_ORIGINS` refuses. Login sets the cookie but doesn't read one, so it needs neither check.
6. **Tabs take turns to refresh.** Rotation blacklists the token presented, so two tabs refreshing at the same moment would leave the slower one holding a blacklisted token, and that tab would be signed out. Within a browser, the refresh runs inside `navigator.locks.request("iris-refresh", …)`. A tab that waited then sends the cookie the first tab's refresh just replaced. `refreshOnce` still shares one refresh between the requests of one tab. No grace window is added on the server: reusing a rotated token stays refused, so a stolen old token is still useless.
7. **Ending a session clears the cookie.**
   - Logout blacklists the cookie's token, ends the session and answers with an expired `iris_refresh`.
   - A password change, reset, revoke, lock or deletion already ends the session on the server; that browser's next refresh is refused and clears the cookie.
   - Nothing about who may end a session changes.

## Questions settled while drafting

Both were left open in the first draft and decided by Ashlee Sean on 2026-11-18:
1. **Remembered sessions count 30 days from sign-in**, not from the last use (decision 4). Counting from the last use is closer to Facebook, but a session used once a month would never end.
2. **Sessions without the box have no limit but the 30-minute idle rule** (decision 3). The refresh token's sliding 7-day expiry is left as it is and isn't treated as a session limit.

## Alternatives Considered

### A. `localStorage` instead of a cookie
- **Gains:** frontend-only; the smallest change.
- **Costs:** any script that runs on the page can read the token and use it from anywhere until it expires. It reverses the finding that removed durable token storage. Not chosen (Ashlee, 2026-11-18).

### B. Always remembered, no checkbox
- **Gains:** simplest for people on their own laptop.
- **Costs:** a lab PC someone walks away from stays signed in for up to 30 days. Not chosen (Ashlee, 2026-11-18).

### C. Drop the idle rule for everyone
- **Gains:** the most like Facebook.
- **Costs:** the same lab-PC exposure as B, for every sign-in. Not chosen (Ashlee, 2026-11-18).

### D. A server-side grace window for a just-rotated token, instead of decision 6
- **Gains:** no browser coordination.
- **Costs:** an old token works again for that window, weakening rotation for everyone. Not recommended.

## Consequences

- **New tabs and typed addresses stay signed in.** A duplicated tab still works. Hermoine's three cases are met with the box off.
- **"Closing the browser signs out" is not guaranteed with the box off.** Browsers that restore the previous session (Chrome's "Continue where you left off", for example) also restore session cookies. The 30-minute idle rule stays the real protection on a shared PC.
- **A script injected into the page can no longer read the refresh token,** but it can still act as the signed-in person while the page is open, as it can today. Cookies don't replace the CSP work (IR-823).
- **Everyone signs in once more after the deploy,** because a token held in `sessionStorage` is no longer read.
- **Tools that called refresh with a body token stop working.** None was found outside the browser client; the evaluation commands mint their own tokens (`eval_answer_quality`).
- **The browser's idle watch has to know whether the session is remembered,** so the login and refresh responses gain `remembered`.

## Security Impact

- **Better:** the refresh token is out of reach of page scripts.
- **Worse, by choice, for remembered sessions:** a remembered session survives without activity until 30 days after sign-in, on a device someone chose to trust.
- **Unchanged:** CORS isn't widened. `CORS_ALLOW_CREDENTIALS` is already on for `CORS_ALLOWED_ORIGINS` only.
- **Docs to update:** `SECURITY.md` §2 (storage, the 7-day correction, remembered sessions) and `DATA_INVENTORY.md`, which list where the token lives.

## Deployment Impact

- One migration: `UserSession.remembered` (default false) and `UserSession.expires_at` (null for sessions without the box).
- One setting: `REMEMBERED_SESSION_DAYS`, default 30.
- nginx already proxies `/api/` on the same origin, so no change there.
- The deploy signs everyone out once.

## Related Requirements

NFR-S2 (session management, as a label only). IR-166, IR-645, IR-1081, IR-1197, IR-1215.

## Related Tasks

- IR-1222: builds this, after acceptance.
- IR-1215: PR #869, merged.
- IR-823: CSP.
