# ASVS manual checks worksheet (IR-829)

**Purpose.** A person records a result for the 21 items that [`SECURITY_CHECKLIST.md`](SECURITY_CHECKLIST.md) marks "Needs manual check". An AI agent drafted these steps from the code on 2026-11-02.

**Run on 2026-11-05 (IR-829).** Groups A and B ran on a local Core journeys stack: production settings, served through nginx, synthetic accounts and data only, `main` at `14768455`. **An AI agent ran them and wrote each Pass or Fail, at Ashlee Sean's direction. They are the agent's results until she confirms them below.** Ashlee made the group C decisions as owner of S2 Epic QA & Security (IR-687), except 7.1.2, which is the DPO's. Group D waits for IR-806's server.

Results: 6 Pass, 7 Fail, 2 Deferred and 1 N/A by decision, 5 not yet runnable. Every Fail has an `area-security` ticket: IR-923 (5.1.3 and 5.1.4, one defect), IR-924, IR-925, IR-926, IR-928 and IR-929. In `SECURITY_CHECKLIST.md` a Fail is a Gap, or Partial where the row says which part holds.

`Confirmed` by Ashlee Sean that the group A and B results stand: ____ Date: ____

**How to fill it in.** Replace each blank on an item's `Record` line.

- **Result:** Pass, Fail, or N/A with the reason. Leave it blank if the check can't be run yet.
- **Date and Person:** when you ran the check, and your name. Decision items need the name of whoever is entitled to decide.
- **Evidence:** the command output, a screenshot, or the files you read.

**When you're finished.**

1. Raise an `area-security` ticket for each Fail, and put its key in Evidence.
2. Copy each result into the item's row in `SECURITY_CHECKLIST.md`, and update the counts at the top.

**Where to run the commands.** Set `BASE` to the address of the stack you're testing. Use `curl.exe` in PowerShell, because plain `curl` runs a different command there. Never use real accounts or real papers.

| Group | Items | What you need |
|---|---|---|
| A. Try it in the running app | 5 | Docker running, or the first server for two items |
| B. Read the code | 8 | The repository |
| C. Make a decision | 4 | The right person to decide |
| D. Check the deployment | 4 | The first real server (IR-806) |

## A. Try it in the running app

### 5.1.1 Repeated parameters
**Requirement:** the app defends against HTTP parameter pollution.

1. Sign in with a test account and open the browser's Network tab.
2. Use a filter on Discover, then copy that request.
3. Send it again with the filter parameter repeated with two different values, such as `?status=a&status=b`.

**Pass:** the response follows one predictable rule, shows no extra records, and has no 500 error.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`. A repeated parameter uses its last value, consistently: `/courses/?department=1&department=2` returns department 2's course, `?department=2&department=1` department 1's. Repeated Discover filters follow the same rule with no 500: `?record_type=1&record_type=2` 200; `?year_from=2020&year_from=abc` 400; `?college=1&college=2&college=x` 400; `?is_ip=true&is_ip=false` 200.

### 5.2.7 Scriptable SVG uploads
**Requirement:** user-supplied SVG can't run scripts.

The code has no `ImageField`, and no profile photo in `apps/accounts`, so the checklist's question about profile photos may not apply. `RecordFile` (`apps/documents/models.py`) does store supplementary files, and this draft did not confirm which file types it accepts.

1. Make a test file called `test.svg` containing `<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>`.
2. Try uploading it through every upload the app offers, including supplementary files.
3. If an upload is accepted, open the file through the app's own link.

**Pass:** the upload is refused, or the file downloads without running. No alert box appears.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`. A scripted `test.svg`, and the same bytes renamed `test.pdf`, were refused by the manuscript (`PATCH /records/<id>/`) and slot (`/documents/submit/`) uploads: "Only PDF files are accepted." Supplementary files are office-only and accept any type: a seated ITSO reviewer's `test.svg` upload answered 201. Opening it through the app's own link (`/documents/files/<id>/download/`, plain and `?inline=1`, as ITSO and as the owner) returned `application/octet-stream`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'`, so it can't run. The upload response also names the storage URL (`/media/documents/<uuid>.svg`), which nginx answers 404, so it reveals a filename but serves nothing. Recheck when IR-695 adds profile photos.

### 8.3.1 Sensitive data in URLs
**Requirement:** sensitive data travels in the body or headers, not the query string.

1. With the Network tab open, register, sign in, change a password, and request a password reset.
2. Read each request's URL.
3. Use a current activation or reset link, and see whether it carries a secret in its URL.

**Pass:** no password or token appears in a query string. Legacy activation links carry a token in the path (`/api/v1/auth/activate/<uid>/<token>/`), and nginx keeps it out of its logs. Record whether you accept that, or raise a ticket to retire them.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending); decision by Ashlee Sean, as owner of S2 Epic QA & Security (IR-687) Evidence: credentials are posted in the body and the API takes a bearer header. Reset links carry the token in a fragment (`/password/reset#token=…`), which the browser never sends. Verification emails put it in the path (`/activate/<uid>/<token>/`). Registering and activating an account on the local Core journeys stack, production settings through nginx, `main` at `14768455` worked, and every `/activate/` line in the logs reads `[redacted]`, but the token still reaches browser history and `Referer`. Ashlee decided this is not accepted: [IR-928](https://citiris.atlassian.net/browse/IR-928). **Update 2026-11-06 (IR-928, not a re-run on the stack):** new verification emails carry `uid` and token in the fragment and the page posts them in a body; the old path link stays until its token expires (3 days). The change is covered by `test_activation_fragment.py` and the page tests; re-run this item on the stack after it deploys.

### 14.4.1 Content-Type on every response
**Requirement:** every response has a correct Content-Type, with a character set on text types.

**Needs nginx:** run it on the first server, or another stack that serves through nginx.

```
curl.exe -sI $BASE/
curl.exe -sI $BASE/api/v1/ai/status/
curl.exe -sI $BASE/api/v1/does-not-exist/
curl.exe -sI $BASE/admin/
curl.exe -sI $BASE/assets/does-not-exist.js
```

Also check a PDF download and a streamed Ask IRIS answer in the Network tab.

**Pass:** every response has a `Content-Type` that matches its content, and `text/*` types name a character set.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`. Every response has a Content-Type and `nosniff`, and Django's are right (`application/json`; `text/html; charset=utf-8` on the API 404). Responses nginx answers itself send `text/html` with no charset (`/` 200, `/admin/` 200, `/assets/does-not-exist.js` 404, `/django-admin/` 403, `/activate/x/y/` 200), so the `text/*` charset requirement fails there. [IR-924](https://citiris.atlassian.net/browse/IR-924). Supplementary file downloads answered `application/octet-stream` (see 5.2.7). Manuscript PDF downloads and the Ask IRIS stream were not exercised.

### 14.5.1 Only the HTTP methods in use
**Requirement:** the server accepts only the methods the app uses, and logs or alerts on the rest.

**Needs nginx:** run it on the first server, or another stack that serves through nginx.

```
curl.exe -s -o NUL -w "%{http_code}\n" -X TRACE  $BASE/
curl.exe -s -o NUL -w "%{http_code}\n" -X DELETE $BASE/
curl.exe -s -o NUL -w "%{http_code}\n" -X PUT    $BASE/index.html
curl.exe -s -o NUL -w "%{http_code}\n" -X TRACE  $BASE/api/v1/auth/login/
curl.exe -s -o NUL -w "%{http_code}\n" -X DELETE $BASE/api/v1/auth/login/
```

`frontend/nginx.conf` has no `limit_except` rule, so nginx alone decides how it answers on static paths.

**Pass:** each returns 401, 403, 405 or 501, and none changes anything. Then check whether these requests can be found in the logs: the requirement also asks for logging or alerts.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`. TRACE, DELETE, PATCH and CONNECT on `/`, PUT on `/index.html`, and TRACE on `/api/v1/auth/login/` all answered 405. DELETE on login answered 405 with `Allow: POST, OPTIONS`, and PUT on `/api/v1/courses/` answered 405 with `Allow: GET, HEAD, OPTIONS`. A CORS pre-flight from IRIS's origin got its allow headers, and one from `https://evil.example` got none. Refused requests are logged by nginx (`"TRACE /probe-829-trace HTTP/1.1" 405`). There is no alerting; ASVS asks for logs or alerts, and the access log is the record.

## B. Read the code

### 5.1.3 Input is allow-listed
**Requirement:** all input is validated against allow lists.

Go through the app URL files that `backend/config/urls.py` includes. For each view that takes input, confirm that it validates through a serializer or an explicit check. Look hardest for `request.data.get`, `request.query_params` and `request.POST`, which skip serializers.

**Pass:** each read value is validated before use. List any that aren't.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: 74 raw reads (`request.data.get`, `query_params`) found by `git grep` across 13 view modules. Most are re-checked downstream (routing, decisions, seats and documents resolve ids through permission helpers; Discover uses a filter form). On the local Core journeys stack, production settings through nginx, `main` at `14768455`, three public routes answer 500 to malformed input: `/departments/?college=abc`, `/courses/?department=abc`, and `POST /auth/login/` with non-text fields. [IR-923](https://citiris.atlassian.net/browse/IR-923).

### 5.1.4 Structured data has a defined format
**Requirement:** structured data is typed, with its allowed characters, length and pattern defined.

Using the same list as 5.1.3, check that emails, identifiers, dates and choice fields have proper types and limits. Check that related fields are compared where it matters, such as a course belonging to its department.

**Pass:** no structured field is accepted as free text with no limit.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: the same defect as 5.1.3, so it shares [IR-923](https://citiris.atlassian.net/browse/IR-923). The department and course filters accept an untyped id that reaches an integer lookup. Discover's typed filters answer 400 (`year_from=abc` gives "Enter a number."), and email is validated on reset (a 300-character address gives 400).

### 5.2.2 Free text is limited
**Requirement:** unstructured data has safety limits such as length.

List free-text inputs: abstracts, comments, Ask IRIS questions and notes. For each, find its maximum length. A Django `TextField` has none unless the serializer sets one.

**Pass:** each one has a limit, or a written reason it doesn't need one.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`. An abstract of 2,000,000 characters was accepted (`PATCH /records/<id>/` 200). Limited: Ask IRIS questions (2,000), review comments (10,000), download notes (500), reset passwords (128), names (100). No field limit, only Django's 2.5 MB body default: abstracts, routing and revision reasons, decision comments, document-request messages and rejection reasons, opportunity descriptions. [IR-926](https://citiris.atlassian.net/browse/IR-926).

### 5.2.6 Server-side request forgery
**Requirement:** untrusted data can't steer where the server sends requests.

Trace where each outbound URL comes from. These files make direct HTTP calls: `apps/ai/providers/voyage.py`, `apps/ai/providers/openrouter_decisions.py`, `apps/ai/extraction/llamaparse_client.py` (Docling was retired by IR-843). Also check the LLM client in `apps/ai/providers/openai_compatible.py`, and the `ai/` gateway. The evaluation files `replay.py` and `http_driver.py` should be reachable only from management commands, so confirm that too.

**Pass:** no URL, host or port comes from a request or a stored user value.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: Voyage, the LLM routes (`inference/profiles.py`), LlamaParse and LlamaExtract (`extraction/selection.py`) and the gateway's adapter all take their base URL from settings. Docling is retired (IR-843), and the eval drivers' `--base-url` is reachable only from management commands. But `llamaparse_client._download` fetches the `presigned_url`s in LlamaParse's response with no host, scheme or port check, and ASVS asks for allow lists. The vendor's authenticated response is the only source, and IR-825's egress limit is the backstop. [IR-929](https://citiris.atlassian.net/browse/IR-929).

### 6.2.1 Crypto fails safely
**Requirement:** crypto errors don't reveal anything useful, which rules out padding oracle attacks.

Read `apps/accounts/recovery/crypto.py` and every other Fernet or HMAC use. Check how a bad token is handled, then send a tampered reset token to `/api/v1/auth/password/reset/confirm/`.

**Pass:** every kind of bad token gets the same response, with no crypto detail in it.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: reset tokens are random values looked up by SHA-256 digest (`recovery/crypto.py`), so nothing user-supplied is decrypted. Fernet decrypts only ciphertext the server stored. Grant HMACs are verified in PostgreSQL (IR-722), and the Discover cursor catches `BadSignature`. On the local Core journeys stack, production settings through nginx, `main` at `14768455`, random, empty, non-base64 and Fernet-shaped tokens to `/auth/password/reset/confirm/` all got the same 400 `invalid_link` body. A 5,000-character token got 413 `payload_too_large`, the body cap, before any token handling.

### 7.1.1 Credentials stay out of logs
**Requirement:** logs hold no credentials, and session tokens only in hashed form.

1. Read `core/logging.py` and search for `logger.` calls near passwords, tokens and emails.
2. If you can run the stack, sign in, fail a sign-in, reset a password and activate an account.
3. Search the logs of `backend`, `frontend` and the workers for your test password and for tokens.

**Pass:** none appears in the logs.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: `core/logging.py` redacts activation paths, and the only `logger` call near a credential logs a user id (`recovery/service.py:192`). On the local Core journeys stack, production settings through nginx, `main` at `14768455` the run did: a failed sign-in with a marker password, a password reset (token read from Mailpit), and a registration with a second marker password followed by activation from the emailed link. It then searched every container's logs (1,557 lines) and found 0 of either marker password, 0 of the demo password, 0 of the reset token, 0 of the activation token and 0 bearer tokens. All 5 `/activate/` lines read `[redacted]`.

### 13.1.1 Components parse the same way
**Requirement:** components use the same encodings and parsers, so a URL can't mean one thing to nginx and another to Django.

Read how `frontend/nginx.conf` handles `/api/`, `/admin/` and `/django-admin/`. Then, on a stack served through nginx, try encoded forms such as `/%61dmin/`, `/api/../admin/`, `/django-admin%2f` and `//admin/`, adding `--path-as-is` to curl so it doesn't tidy them. nginx treats `/django-admin/` specially, so compare what each form reaches.

**Pass:** no encoded form gets past the admin allowlist or reaches a path it shouldn't.

`Record` Result: **Pass** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: local Core journeys stack, production settings through nginx, `main` at `14768455`, sent unnormalized. `/django-admin/`, `/%64jango-admin/`, `/django-admin%2f`, `//django-admin/`, `/api/../django-admin/`, `/api/%2e%2e/django-admin/`, `/api/..%2fdjango-admin/`, `/./django-admin/`, `/static/../django-admin/` and `/api/v1/../../django-admin/` all got the allowlist's 403. `/DJANGO-ADMIN/` got the SPA's `index.html`, not Django, whose URLs are case-sensitive.

### 14.2.2 Unneeded features removed
**Requirement:** unneeded features, documentation, samples and configuration are removed.

Check what production includes: `INSTALLED_APPS` in `config/settings/production.py`, the production image's contents, and any debug or sample routes. Check that `seed_demo` and other test-data commands can't run by accident in production.

**Pass:** you can give a reason for everything you find. List anything to remove.

`Record` Result: **Fail** Date: 2026-11-05 Person: AI agent, at Ashlee Sean's direction (her confirmation pending) Evidence: production `INSTALLED_APPS` holds no debug app (the debug toolbar is development only), and every test-data command (`seed_demo`, `load_corpus`, `reset_demo_records`, `review_clock_for_testing`, `backfill_abstracts`) refuses with `DEBUG` off unless `--force`. But DRF's browsable API is on in production: on the local Core journeys stack, production settings through nginx, `main` at `14768455`, `GET /api/v1/courses/` with `Accept: text/html` returned DRF's HTML page. [IR-925](https://citiris.atlassian.net/browse/IR-925).

## C. Make a decision

Each of these is a judgement, so record who decided and why. A "no" here is a valid result if the reason is written down.

### 3.4.4 `__Host-` prefix on the admin cookie
**Question:** should the Django admin's session cookie use the `__Host-` prefix? The API uses no cookies, so only the admin is affected.

- **Change it:** the cookie is locked to the exact host and can't be set by a subdomain. It's one or two settings, and it stops working if the admin is ever served over plain HTTP, including local development unless development is exempted.
- **Leave it:** nothing changes, but the item stays unmet, and the risk depends on what else runs on the same domain.

`Record` Decision: **Leave it** Date: 2026-11-05 Person: Ashlee Sean, as owner of S2 Epic QA & Security (IR-687) Reason: only Django's admin uses a cookie; the API uses bearer tokens. The admin is on its own path behind IR-668's network allowlist, which already narrows who can reach the cookie. Recorded as deferred, not met.

### 3.7.1 Re-authentication for sensitive acts
**Question:** should administrator acts ask for the password again? A password change already needs the current password. Other administrator acts need nothing further.

- **Add it:** a stolen or unattended session can do less damage. It takes new work on each sensitive act and adds a step for administrators.
- **Leave it:** no extra work, but a live session is enough to perform those acts. MFA is already deferred (IR-652).

`Record` Decision: **Leave it** Date: 2026-11-05 Person: Ashlee Sean, as owner of S2 Epic QA & Security (IR-687) Reason: password change already requires the current password, sessions expire when idle, and administrator acts are audited. Re-authentication stays deferred with MFA (IR-652). Recorded as deferred, not met.

### 7.1.2 Sensitive data under RA 10173
**Question:** what counts as sensitive in logs under the Data Privacy Act? `FAILED_LOGIN` stores the email address in audit metadata, and an email is personal data. This is best answered by, or with, the DPO.

- **Keep the email:** failed sign-ins are easier to investigate, but the audit log holds personal data, including addresses people mistyped, and needs a retention rule.
- **Remove or hash it:** less personal data is stored, but investigating an attack on one account gets harder.

`Record` Decision: blank, the data protection officer's to make (with IR-123's DPO review) Date: — Person: —

### 11.1.2 Realistic human speed
**Question:** should the app refuse workflow steps completed too quickly for a person? No such rule exists. Throttles limit the rate of requests, which isn't the same thing.

- **Add it:** it stops scripted submissions, but legitimate fast users and any automation could be refused, and the time limit would be a guess.
- **Mark it N/A with a reason:** no work. It's defensible because users sign in with accounts and throttles already apply, but a signed-in script could still move quickly.

`Record` Decision: **N/A** Date: 2026-11-05 Person: Ashlee Sean, as owner of S2 Epic QA & Security (IR-687) Reason: every workflow act needs a signed-in account and request throttles apply. A minimum-time rule would be a guess and could refuse legitimate fast users.

## D. Check the deployment

These can't be answered until IR-806's server and domain exist.

### 2.5.1 Recovery secrets aren't sent in clear text
**Requirement:** activation and recovery secrets aren't sent unprotected.

Links are stored hashed and sent by email. `EMAIL_USE_TLS` defaults to true in `config/settings/base.py`.

1. Confirm `EMAIL_USE_TLS` is true, and not overridden, on the server.
2. Confirm which mail provider is used and that it requires TLS.
3. Send a reset to a test mailbox, and read the message's `Received` headers for TLS.

**Pass:** the connection from the app to the mail provider uses TLS. Email beyond that provider can't be guaranteed, so note that the links are short-lived: reset links last 30 minutes.

`Record` Result: blank, can't run yet (needs IR-806's server and mail provider) Date: — Person: —

### 2.5.4 No shared or default accounts
**Requirement:** no shared or default accounts exist, such as `admin`.

`seed_demo` creates shared logins such as `admin@cit.edu` with a known password, and refuses with `DEBUG` off unless `--force` is used.

1. On the server, try signing in with `admin@cit.edu` / `IrisDemo123!` and with one `<role>@cit.edu` account.
2. Have an administrator list the accounts, and look for shared addresses.

**Pass:** the demo logins fail, and each account belongs to one named person.

`Record` Result: blank, can't run yet (needs IR-806's server; on a development or Core journeys stack the demo logins exist by design) Date: — Person: —

### 3.4.5 Cookie path
**Requirement:** if the domain is shared with other apps, cookies use the most precise path.

`SESSION_COOKIE_PATH` isn't set in the settings, so Django's default of `/` applies.

1. Find out what else runs on the chosen domain.
2. If it's a separate subdomain with nothing else on it, record N/A and why.
3. If other apps share the host, set the cookie path to the admin path, or raise a ticket.

**Pass:** no other app on the host can receive the admin cookie.

`Record` Result: blank, can't run yet (depends on IR-806's domain) Date: — Person: —

### 10.3.3 Subdomain takeover
**Requirement:** DNS entries can't be taken over.

1. With whoever manages the DNS (probably CIT-U IT), list every record pointing at IRIS.
2. Check each one points at a server the team still controls, with no leftover `CNAME` to a removed service.
3. Find out who is responsible for renewal and for removing records when the temporary server goes away.

**Pass:** every record has a live target and a named owner, including a plan for retiring the temporary server.

`Record` Result: blank, can't run yet (depends on IR-806's DNS and its owner) Date: — Person: —
