# ASVS manual checks worksheet (IR-829)

**Purpose.** A person records a result for the 21 items that [`SECURITY_CHECKLIST.md`](SECURITY_CHECKLIST.md) marks "Needs manual check". An AI agent drafted these steps from the code on 2026-11-02 and ran none of them, so a step may need adjusting.

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

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 5.2.7 Scriptable SVG uploads
**Requirement:** user-supplied SVG can't run scripts.

The code has no `ImageField`, and no profile photo in `apps/accounts`, so the checklist's question about profile photos may not apply. `RecordFile` (`apps/documents/models.py`) does store supplementary files, and this draft did not confirm which file types it accepts.

1. Make a test file called `test.svg` containing `<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>`.
2. Try uploading it through every upload the app offers, including supplementary files.
3. If an upload is accepted, open the file through the app's own link.

**Pass:** the upload is refused, or the file downloads without running. No alert box appears.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 8.3.1 Sensitive data in URLs
**Requirement:** sensitive data travels in the body or headers, not the query string.

1. With the Network tab open, register, sign in, change a password, and request a password reset.
2. Read each request's URL.
3. Use a current activation or reset link, and see whether it carries a secret in its URL.

**Pass:** no password or token appears in a query string. Legacy activation links carry a token in the path (`/api/v1/auth/activate/<uid>/<token>/`), and nginx keeps it out of its logs. Record whether you accept that, or raise a ticket to retire them.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

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

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

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

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

## B. Read the code

### 5.1.3 Input is allow-listed
**Requirement:** all input is validated against allow lists.

Go through the app URL files that `backend/config/urls.py` includes. For each view that takes input, confirm that it validates through a serializer or an explicit check. Look hardest for `request.data.get`, `request.query_params` and `request.POST`, which skip serializers.

**Pass:** each read value is validated before use. List any that aren't.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 5.1.4 Structured data has a defined format
**Requirement:** structured data is typed, with its allowed characters, length and pattern defined.

Using the same list as 5.1.3, check that emails, identifiers, dates and choice fields have proper types and limits. Check that related fields are compared where it matters, such as a course belonging to its department.

**Pass:** no structured field is accepted as free text with no limit.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 5.2.2 Free text is limited
**Requirement:** unstructured data has safety limits such as length.

List free-text inputs: abstracts, comments, Ask IRIS questions and notes. For each, find its maximum length. A Django `TextField` has none unless the serializer sets one.

**Pass:** each one has a limit, or a written reason it doesn't need one.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 5.2.6 Server-side request forgery
**Requirement:** untrusted data can't steer where the server sends requests.

Trace where each outbound URL comes from. These files make direct HTTP calls: `apps/ai/providers/voyage.py`, `apps/ai/providers/openrouter_decisions.py`, `apps/ai/extraction/docling_client.py`. Also check the LLM client in `apps/ai/providers/openai_compatible.py`, and the `ai/` gateway. The evaluation files `replay.py` and `http_driver.py` should be reachable only from management commands, so confirm that too.

**Pass:** no URL, host or port comes from a request or a stored user value.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 6.2.1 Crypto fails safely
**Requirement:** crypto errors don't reveal anything useful, which rules out padding oracle attacks.

Read `apps/accounts/recovery/crypto.py` and every other Fernet or HMAC use. Check how a bad token is handled, then send a tampered reset token to `/api/v1/auth/password/reset/confirm/`.

**Pass:** every kind of bad token gets the same response, with no crypto detail in it.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 7.1.1 Credentials stay out of logs
**Requirement:** logs hold no credentials, and session tokens only in hashed form.

1. Read `core/logging.py` and search for `logger.` calls near passwords, tokens and emails.
2. If you can run the stack, sign in, fail a sign-in, reset a password and activate an account.
3. Search the logs of `backend`, `frontend` and the workers for your test password and for tokens.

**Pass:** none appears in the logs.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 13.1.1 Components parse the same way
**Requirement:** components use the same encodings and parsers, so a URL can't mean one thing to nginx and another to Django.

Read how `frontend/nginx.conf` handles `/api/`, `/admin/` and `/django-admin/`. Then, on a stack served through nginx, try encoded forms such as `/%61dmin/`, `/api/../admin/`, `/django-admin%2f` and `//admin/`, adding `--path-as-is` to curl so it doesn't tidy them. nginx treats `/django-admin/` specially, so compare what each form reaches.

**Pass:** no encoded form gets past the admin allowlist or reaches a path it shouldn't.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 14.2.2 Unneeded features removed
**Requirement:** unneeded features, documentation, samples and configuration are removed.

Check what production includes: `INSTALLED_APPS` in `config/settings/production.py`, the production image's contents, and any debug or sample routes. Check that `seed_demo` and other test-data commands can't run by accident in production.

**Pass:** you can give a reason for everything you find. List anything to remove.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

## C. Make a decision

Each of these is a judgement, so record who decided and why. A "no" here is a valid result if the reason is written down.

### 3.4.4 `__Host-` prefix on the admin cookie
**Question:** should the Django admin's session cookie use the `__Host-` prefix? The API uses no cookies, so only the admin is affected.

- **Change it:** the cookie is locked to the exact host and can't be set by a subdomain. It's one or two settings, and it stops working if the admin is ever served over plain HTTP, including local development unless development is exempted.
- **Leave it:** nothing changes, but the item stays unmet, and the risk depends on what else runs on the same domain.

`Record` Decision: ____ Date: ____ Person: ____ Reason: ____

### 3.7.1 Re-authentication for sensitive acts
**Question:** should administrator acts ask for the password again? A password change already needs the current password. Other administrator acts need nothing further.

- **Add it:** a stolen or unattended session can do less damage. It takes new work on each sensitive act and adds a step for administrators.
- **Leave it:** no extra work, but a live session is enough to perform those acts. MFA is already deferred (IR-652).

`Record` Decision: ____ Date: ____ Person: ____ Reason: ____

### 7.1.2 Sensitive data under RA 10173
**Question:** what counts as sensitive in logs under the Data Privacy Act? `FAILED_LOGIN` stores the email address in audit metadata, and an email is personal data. This is best answered by, or with, the DPO.

- **Keep the email:** failed sign-ins are easier to investigate, but the audit log holds personal data, including addresses people mistyped, and needs a retention rule.
- **Remove or hash it:** less personal data is stored, but investigating an attack on one account gets harder.

`Record` Decision: ____ Date: ____ Person: ____ Reason: ____

### 11.1.2 Realistic human speed
**Question:** should the app refuse workflow steps completed too quickly for a person? No such rule exists. Throttles limit the rate of requests, which isn't the same thing.

- **Add it:** it stops scripted submissions, but legitimate fast users and any automation could be refused, and the time limit would be a guess.
- **Mark it N/A with a reason:** no work. It's defensible because users sign in with accounts and throttles already apply, but a signed-in script could still move quickly.

`Record` Decision: ____ Date: ____ Person: ____ Reason: ____

## D. Check the deployment

These can't be answered until IR-806's server and domain exist.

### 2.5.1 Recovery secrets aren't sent in clear text
**Requirement:** activation and recovery secrets aren't sent unprotected.

Links are stored hashed and sent by email. `EMAIL_USE_TLS` defaults to true in `config/settings/base.py`.

1. Confirm `EMAIL_USE_TLS` is true, and not overridden, on the server.
2. Confirm which mail provider is used and that it requires TLS.
3. Send a reset to a test mailbox, and read the message's `Received` headers for TLS.

**Pass:** the connection from the app to the mail provider uses TLS. Email beyond that provider can't be guaranteed, so note that the links are short-lived: reset links last 30 minutes.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 2.5.4 No shared or default accounts
**Requirement:** no shared or default accounts exist, such as `admin`.

`seed_demo` creates shared logins such as `admin@cit.edu` with a known password, and refuses with `DEBUG` off unless `--force` is used.

1. On the server, try signing in with `admin@cit.edu` / `IrisDemo123!` and with one `<role>@cit.edu` account.
2. Have an administrator list the accounts, and look for shared addresses.

**Pass:** the demo logins fail, and each account belongs to one named person.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 3.4.5 Cookie path
**Requirement:** if the domain is shared with other apps, cookies use the most precise path.

`SESSION_COOKIE_PATH` isn't set in the settings, so Django's default of `/` applies.

1. Find out what else runs on the chosen domain.
2. If it's a separate subdomain with nothing else on it, record N/A and why.
3. If other apps share the host, set the cookie path to the admin path, or raise a ticket.

**Pass:** no other app on the host can receive the admin cookie.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____

### 10.3.3 Subdomain takeover
**Requirement:** DNS entries can't be taken over.

1. With whoever manages the DNS (probably CIT-U IT), list every record pointing at IRIS.
2. Check each one points at a server the team still controls, with no leftover `CNAME` to a removed service.
3. Find out who is responsible for renewal and for removing records when the temporary server goes away.

**Pass:** every record has a live target and a named owner, including a plan for retiring the temporary server.

`Record` Result: ____ Date: ____ Person: ____ Evidence: ____
