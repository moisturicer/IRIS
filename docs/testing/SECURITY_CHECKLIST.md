# Security checklist: OWASP ASVS 4.0.3 Level 1

**Purpose.** Every ASVS Level 1 requirement, with its status and evidence. Threats are in [ADR-053](../adr/053-threat-model.md), and open risks are in [`SECURITY.md`](../security/SECURITY.md) §11.
**Checked against.** `main` on 2026-11-02, by an AI agent reading the code. No item was tested on a deployed instance. The 21 items marked "Needs manual check" were run on 2026-11-05 under IR-829, on a local production-settings stack, by an AI agent at Ashlee Sean's direction, with her decisions; the agent's results await her confirmation ([IR-829 worksheet](ASVS_MANUAL_CHECKS.md)). Five wait for IR-806's server or the DPO. **Ashlee Sean reviews it; it is a draft until then.**
**Source.** The requirement text is from [OWASP ASVS 4.0.3](https://github.com/OWASP/ASVS/tree/v4.0.3) (CC BY-SA 3.0), with its links removed.

| Status | Meaning | Items |
|---|---|---|
| Pass | Evidence named in the row | 84 |
| Partial | Met in part, and the row says which part | 12 |
| Gap | Not met; the row names the ticket | 14 |
| Deferred | Deliberately deferred | 3 |
| N/A | Does not apply, for the reason given | 10 |
| Needs manual check | Reading the code can't settle it, or a person must judge it | 5 |
| **Total** | | **128** |

## V2 · Authentication

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1.1 | user set passwords are at least 12 characters in length (after multiple spaces are combined). | Gap | Minimum is 8, `AUTH_PASSWORD_VALIDATORS`. [IR-819](https://citiris.atlassian.net/browse/IR-819) |
| 2.1.2 | passwords of at least 64 characters are permitted, and that passwords of more than 128 characters are denied. | Gap | No maximum is enforced. [IR-819](https://citiris.atlassian.net/browse/IR-819) |
| 2.1.3 | password truncation is not performed. However, consecutive multiple spaces may be replaced by a single space. | Pass | Django hashes the whole password |
| 2.1.4 | any printable Unicode character, including language neutral characters such as spaces and Emojis are permitted in passwords. | Pass | No validator limits characters |
| 2.1.5 | users can change their password. | Pass | `ChangePasswordView`; `apps/accounts/test_credential_invalidation.py` |
| 2.1.6 | password change functionality requires the user's current and new password. | Pass | `ChangePasswordSerializer` checks `old_password` |
| 2.1.7 | passwords submitted during account registration, login, and password change are checked against a set of breached passwords either locally (such as the top 1,000 or 10,000 most common passwords which match the system's password policy) or using an external API. If using an API a zero knowledge proof or other mechanism should be used to ensure that the plain text password is not sent or used in verifying the breach status of the password. If the password is breached, the application must require the user to set a new non-breached password. | Gap | Only `CommonPasswordValidator`. [IR-819](https://citiris.atlassian.net/browse/IR-819) |
| 2.1.8 | a password strength meter is provided to help users set a stronger password. | Gap | No meter found in `frontend/src`. [IR-819](https://citiris.atlassian.net/browse/IR-819) |
| 2.1.9 | there are no password composition rules limiting the type of characters permitted. There should be no requirement for upper or lower case or numbers or special characters. | Pass | No composition validator |
| 2.1.10 | there are no periodic credential rotation or password history requirements. | Pass | No rotation or history rule |
| 2.1.11 | "paste" functionality, browser password helpers, and external password managers are permitted. | Pass | No paste handler in `frontend/src` |
| 2.1.12 | the user can choose to either temporarily view the entire masked password, or temporarily view the last typed character of the password on platforms that do not have this as built-in functionality. | Pass | Reveal control in `LoginForm.tsx` |
| 2.2.1 | anti-automation controls are effective at mitigating breached credential testing, brute force, and account lockout attacks. Such controls include blocking the most common breached passwords, soft lockouts, rate limiting, CAPTCHA, ever increasing delays between attempts, IP address restrictions, or risk-based restrictions such as location, first login on a device, recent attempts to unlock the account, or similar. Verify that no more than 100 failed attempts per hour is possible on a single account. | Gap | The lockout is switched off by default for now ([IR-865](https://citiris.atlassian.net/browse/IR-865)), leaving only the 300-an-hour per-address throttle. With `AXES_ENABLED=True` it passes: `AXES_*`, `apps/accounts/test_lockout.py`, `test_auth_throttles.py` ([IR-656](https://citiris.atlassian.net/browse/IR-656), [IR-661](https://citiris.atlassian.net/browse/IR-661)) |
| 2.2.2 | the use of weak authenticators (such as SMS and email) is limited to secondary verification and transaction approval and not as a replacement for more secure authentication methods. Verify that stronger methods are offered before weak methods, users are aware of the risks, or that proper measures are in place to limit the risks of account compromise. | Pass | Email is used only for recovery and verification (ADR-045) |
| 2.2.3 | secure notifications are sent to users after updates to authentication details, such as credential resets, email or address changes, logging in from unknown or risky locations. The use of push notifications - rather than SMS or email - is preferred, but in the absence of push notifications, SMS or email is acceptable as long as no sensitive information is disclosed in the notification. | Partial | A reset sends a notice, a signed-in change does not. [IR-820](https://citiris.atlassian.net/browse/IR-820) |
| 2.3.1 | system generated initial passwords or activation codes SHOULD be securely randomly generated, SHOULD be at least 6 characters long, and MAY contain letters and numbers, and expire after a short period of time. These initial secrets must not be permitted to become the long term password. | Pass | `secrets.token_bytes(32)`, `apps/accounts/recovery/crypto.py`; 30-minute reset TTL |
| 2.5.1 | a system generated initial activation or recovery secret is not sent in clear text to the user. | Needs manual check | Links are sent by email and stored hashed. Mail transport is a deployment fact, so this waits for IR-806's server. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 2.5.2 | password hints or knowledge-based authentication (so-called "secret questions") are not present. | Pass | None exist |
| 2.5.3 | password credential recovery does not reveal the current password in any way. | Pass | Hashed passwords, reset by link |
| 2.5.4 | shared or default accounts are not present (e.g. "root", "admin", or "sa"). | Needs manual check | `seed_demo` makes shared logins and refuses with `DEBUG` off unless `--force`. Waits for IR-806's server. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 2.5.5 | if an authentication factor is changed or replaced, that the user is notified of this event. | Partial | As 2.2.3. [IR-820](https://citiris.atlassian.net/browse/IR-820) |
| 2.5.6 | forgotten password, and other recovery paths use a secure recovery mechanism, such as time-based OTP (TOTP) or other soft token, mobile push, or another offline recovery mechanism. | Pass | [IR-642](https://citiris.atlassian.net/browse/IR-642), ADR-045; `apps/accounts/test_password_recovery.py` |
| 2.7.1 | clear text out of band (NIST "restricted") authenticators, such as SMS or PSTN, are not offered by default, and stronger alternatives such as push notifications are offered first. | N/A | IRIS has no out-of-band authenticator: no SMS or phone sign-in |
| 2.7.2 | the out of band verifier expires out of band authentication requests, codes, or tokens after 10 minutes. | N/A | As 2.7.1. Recovery links are not authenticators, and 2.5.6 covers them |
| 2.7.3 | the out of band verifier authentication requests, codes, or tokens are only usable once, and only for the original authentication request. | N/A | As 2.7.1 |
| 2.7.4 | the out of band authenticator and verifier communicates over a secure independent channel. | N/A | As 2.7.1 |
| 2.8.1 | time-based OTPs have a defined lifetime before expiring. | N/A | No one-time password exists. MFA is deferred ([IR-652](https://citiris.atlassian.net/browse/IR-652)) |

## V3 · Session Management

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1.1 | the application never reveals session tokens in URL parameters. | Pass | No token query parameter in `frontend/src`; Bearer header |
| 3.2.1 | the application generates a new session token on user authentication. | Pass | `start_session` at sign-in, `apps/accounts/test_sessions.py` |
| 3.2.2 | session tokens possess at least 64 bits of entropy. | Pass | SimpleJWT, signed with the required `SECRET_KEY` |
| 3.2.3 | the application only stores session tokens in the browser using secure methods such as appropriately secured cookies (see section 3.4) or HTML 5 session storage. | Pass | Refresh token in `sessionStorage` only, `frontend/src/lib/authStorage.ts` |
| 3.3.1 | logout and expiration invalidate the session token, such that the back button or a downstream relying party does not resume an authenticated session, including across relying parties. | Pass | [IR-166](https://citiris.atlassian.net/browse/IR-166), [IR-657](https://citiris.atlassian.net/browse/IR-657); `apps/accounts/test_session_revoke.py` |
| 3.3.2 | If authenticators permit users to remain logged in, verify that re-authentication occurs periodically both when actively used or after an idle period. | Pass | Refresh limit of 7 days by default, inside Level 1's 30 |
| 3.4.1 | cookie-based session tokens have the 'Secure' attribute set. | Pass | API uses no cookie. Django admin: `SESSION_COOKIE_SECURE` in `production.py` |
| 3.4.2 | cookie-based session tokens have the 'HttpOnly' attribute set. | Pass | API uses no cookie. Django admin: Django's default |
| 3.4.3 | cookie-based session tokens utilize the 'SameSite' attribute to limit exposure to cross-site request forgery attacks. | Pass | API uses no cookie. Django admin: Django's default of Lax |
| 3.4.4 | cookie-based session tokens use the "__Host-" prefix so cookies are only sent to the host that initially set the cookie. | Deferred | API uses no cookie. Decided 2026-11-05 by Ashlee Sean not to add `__Host-` to Django admin's cookie: the admin is behind IR-668's allowlist. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 3.4.5 | if the application is published under a domain name with other applications that set or use session cookies that might disclose the session cookies, set the path attribute in cookie-based session tokens using the most precise path possible. | Needs manual check | Depends on IR-806's domain. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 3.7.1 | the application ensures a full, valid login session or requires re-authentication or secondary verification before allowing any sensitive transactions or account modifications. | Deferred | A password change needs the current password. Decided 2026-11-05 by Ashlee Sean not to add re-authentication to administrator acts now; deferred with MFA ([IR-652](https://citiris.atlassian.net/browse/IR-652)). [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |

## V4 · Access Control

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1.1 | the application enforces access control rules on a trusted service layer, especially if client-side access control is present and could be bypassed. | Pass | Server-side permission classes and `visible_to`; `apps/tests/test_access_matrix.py` |
| 4.1.2 | all user and data attributes and policy information used by access controls cannot be manipulated by end users unless specifically authorized. | Pass | Consent stamps and roles are not writable through serializers; `test_authorization_matrix.py` |
| 4.1.3 | the principle of least privilege exists - users should only be able to access functions, data files, URLs, controllers, services, and other resources, for which they possess specific authorization. This implies protection against spoofing and elevation of privilege. | Pass | Route matrix ([IR-667](https://citiris.atlassian.net/browse/IR-667)). Workflow and system administration are split: RDCO keeps accounts, locks, sessions and role requests, and the System Admin, with no workflow access, holds the Audit Log, settings and office roles (`core/permissions.py`, `test_system_admin.py`, [IR-781](https://citiris.atlassian.net/browse/IR-781)) |
| 4.1.5 | access controls fail securely including when an exception occurs. | Pass | A refused record is a 404; the matrix asserts refusals |
| 4.2.1 | sensitive data and APIs are protected against Insecure Direct Object Reference (IDOR) attacks targeting creation, reading, updating and deletion of records, such as creating or updating someone else's record, viewing everyone's records, or deleting all records. | Pass | [IR-153](https://citiris.atlassian.net/browse/IR-153), `apps/documents/tests/test_document_access_control.py`, route matrix |
| 4.2.2 | the application or framework enforces a strong anti-CSRF mechanism to protect authenticated functionality, and effective anti-automation or anti-CSRF protects unauthenticated functionality. | Pass | API uses Bearer tokens, which browsers do not attach. Django admin uses Django's CSRF middleware |
| 4.3.1 | administrative interfaces use appropriate multi-factor authentication to prevent unauthorized use. | Deferred | MFA needs an identity provider from CIT-U IT ([IR-652](https://citiris.atlassian.net/browse/IR-652)). [IR-668](https://citiris.atlassian.net/browse/IR-668) is the compensating control, on `/django-admin/`, the only address Django serves its admin at since [IR-782](https://citiris.atlassian.net/browse/IR-782) |
| 4.3.2 | directory browsing is disabled unless deliberately desired. Additionally, applications should not allow discovery or disclosure of file or directory metadata, such as Thumbs.db, .DS_Store, .git or .svn folders. | Pass | nginx has no `autoindex`; the image serves the built bundle |

## V5 · Validation, Sanitization and Encoding

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 5.1.1 | the application has defenses against HTTP parameter pollution attacks, particularly if the application framework makes no distinction about the source of request parameters (GET, POST, cookies, headers, or environment variables). | Pass | A repeated parameter uses its last value, consistently, with no 500. Tested 2026-11-05 on a production-settings stack. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.1.2 | frameworks protect against mass parameter assignment attacks, or that the application has countermeasures to protect against unsafe parameter assignment, such as marking fields private or similar. | Pass | No `fields = "__all__"` in app serializers |
| 5.1.3 | all input (HTML form fields, REST requests, URL parameters, HTTP headers, cookies, batch files, RSS feeds, etc) is validated using positive validation (allow lists). | Pass | Of the 74 raw reads IR-829 listed, these three answered 500 to malformed input: the department and course filters and login with non-text fields. They now answer 400, with the ids allow-listed to 1–18 digits (`apps/accounts/test_malformed_input.py`). IR-829 found the other reads re-checked downstream. [IR-923](traceability/IR-923.md) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.1.4 | structured data is strongly typed and validated against a defined schema including allowed characters, length and pattern (e.g. credit card numbers, e-mail addresses, telephone numbers, or validating that two related fields are reasonable, such as checking that suburb and zip/postcode match). | Pass | The department and course filters accept only a whole-number id and answer 400 to anything else; login accepts only text fields. `apps/accounts/test_malformed_input.py`. [IR-923](traceability/IR-923.md) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.1.5 | URL redirects and forwards only allow destinations which appear on an allow list, or show a warning when redirecting to potentially untrusted content. | Pass | The one client redirect goes to the app's own `/login`, `authSession.ts` |
| 5.2.1 | all untrusted HTML input from WYSIWYG editors or similar is properly sanitized with an HTML sanitizer library or framework feature. | Pass | No WYSIWYG input; `react-markdown` sanitizes link schemes |
| 5.2.2 | unstructured data is sanitized to enforce safety measures such as allowed characters and length. | Gap | An abstract of 2,000,000 characters is accepted; reasons, decision comments and request messages have no limit either. Questions, review comments and notes are limited. [IR-926](https://citiris.atlassian.net/browse/IR-926) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.2.3 | the application sanitizes user input before passing to mail systems to protect against SMTP or IMAP injection. | Pass | Django's mail API refuses newlines in headers |
| 5.2.4 | the application avoids the use of eval() or other dynamic code execution features. Where there is no alternative, any user input being included must be sanitized or sandboxed before being executed. | Pass | No `eval` or `exec` in `backend/apps` or `frontend/src`; semgrep in CI |
| 5.2.5 | the application protects against template injection attacks by ensuring that any user input being included is sanitized or sandboxed. | Pass | No user input reaches a server-side template; React renders the interface |
| 5.2.6 | the application protects against SSRF attacks, by validating or sanitizing untrusted data or HTTP file metadata, such as filenames and URL input fields, and uses allow lists of protocols, domains, paths and ports. | Partial | Every outbound base URL comes from settings; eval `--base-url` is management-command only. LlamaParse `presigned_url`s are fetched with no host allow list. [IR-929](https://citiris.atlassian.net/browse/IR-929) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.2.7 | the application sanitizes, disables, or sandboxes user-supplied Scalable Vector Graphics (SVG) scriptable content, especially as they relate to XSS resulting from inline scripts, and foreignObject. | Pass | Manuscript and slot uploads refuse SVG, even renamed `.pdf`. An office's supplementary SVG downloads as `application/octet-stream` with `nosniff` and `CSP default-src 'none'`, tested 2026-11-05. Recheck with [IR-695](https://citiris.atlassian.net/browse/IR-695)'s photos. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 5.2.8 | the application sanitizes, disables, or sandboxes user-supplied scriptable or expression template language content, such as Markdown, CSS or XSL stylesheets, BBCode, or similar. | Pass | KaTeX runs with `trust` off, `PassageQuote.tsx`; Markdown has no raw HTML |
| 5.3.1 | output encoding is relevant for the interpreter and context required. For example, use encoders specifically for HTML values, HTML attributes, JavaScript, URL parameters, HTTP headers, SMTP, and others as the context requires, especially from untrusted inputs (e.g. names with Unicode or apostrophes, such as ねこ or O'Hara). | Pass | React escapes by default; the one `dangerouslySetInnerHTML` holds KaTeX output |
| 5.3.2 | output encoding preserves the user's chosen character set and locale, such that any Unicode character point is valid and safely handled. | Pass | UTF-8 throughout; JSON API |
| 5.3.3 | context-aware, preferably automated - or at worst, manual - output escaping protects against reflected, stored, and DOM based XSS. | Pass | As 5.3.1 |
| 5.3.4 | data selection or database queries (e.g. SQL, HQL, ORM, NoSQL) use parameterized queries, ORMs, entity frameworks, or are otherwise protected from database injection attacks. | Pass | ORM and parameterized `cursor.execute`; semgrep rule in `security/semgrep.yml` ([IR-614](https://citiris.atlassian.net/browse/IR-614)) |
| 5.3.5 | where parameterized or safer mechanisms are not present, context-specific output encoding is used to protect against injection attacks, such as the use of SQL escaping to protect against SQL injection. (C3, C4) | Pass | As 5.3.4. String-built SQL uses constants, such as `keyword_index.py` and `index_health.py` |
| 5.3.6 | the application protects against JSON injection attacks, JSON eval attacks, and JavaScript expression evaluation. | Pass | DRF renderers and browser JSON parsing |
| 5.3.7 | the application protects against LDAP injection vulnerabilities, or that specific security controls to prevent LDAP injection have been implemented. | N/A | IRIS uses no LDAP |
| 5.3.8 | the application protects against OS command injection and that operating system calls use parameterized OS queries or use contextual command line output encoding. | Pass | `subprocess` only in management commands, with fixed arguments; bandit in CI |
| 5.3.9 | the application protects against Local File Inclusion (LFI) or Remote File Inclusion (RFI) attacks. | Pass | No dynamic include; files go through Django storage |
| 5.3.10 | the application protects against XPath injection or XML injection attacks. | Pass | No XML input path in the API. `defusedxml` where evaluation code parses XML |
| 5.5.1 | serialized objects use integrity checks or are encrypted to prevent hostile object creation or data tampering. | Pass | JWTs are signed; Celery accepts JSON only |
| 5.5.2 | the application correctly restricts XML parsers to only use the most restrictive configuration possible and to ensure that unsafe features such as resolving external entities are disabled to prevent XML eXternal Entity (XXE) attacks. | Pass | `defusedxml`, `apps/ai/evaluation/scenarios.py` |
| 5.5.3 | deserialization of untrusted data is avoided or is protected in both custom code and third-party libraries (such as JSON, XML and YAML parsers). | Pass | No `pickle` or `yaml.load` in `backend/apps`; `CELERY_ACCEPT_CONTENT = ["json"]` |
| 5.5.4 | when parsing JSON in browsers or JavaScript-based backends, JSON.parse is used to parse the JSON document. Do not use eval() to parse JSON. | Pass | No `eval` in `frontend/src` |

## V6 · Stored Cryptography

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 6.2.1 | all cryptographic modules fail securely, and errors are handled in a way that does not enable Padding Oracle attacks. | Pass | Tokens are looked up by digest, never decrypted from input; every bad reset token gets the same 400 `invalid_link`, tested 2026-11-05. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |

## V7 · Error Handling and Logging

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 7.1.1 | the application does not log credentials or payment details. Session tokens should only be stored in logs in an irreversible, hashed form. (C9, C10) | Pass | On 2026-11-05 marker passwords, the demo password, reset and activation tokens and bearer tokens appeared in no container log, after sign-in, reset, registration and activation; `/activate/` lines are redacted. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 7.1.2 | the application does not log other sensitive data as defined under local privacy laws or relevant security policy. | Needs manual check | What counts as sensitive under RA 10173 is the DPO's decision, with [IR-123](https://citiris.atlassian.net/browse/IR-123). `FAILED_LOGIN` stores the email in audit metadata. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 7.4.1 | a generic message is shown when an unexpected or security sensitive error occurs, potentially with a unique ID which support personnel can use to investigate. | Pass | Production refuses `DEBUG`, so unexpected errors get Django's generic 500 |

## V8 · Data Protection

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 8.2.1 | the application sets sufficient anti-caching headers so that sensitive data is not cached in modern browsers. | Gap | `no-store` on a few views only. [IR-821](https://citiris.atlassian.net/browse/IR-821) |
| 8.2.2 | data stored in browser storage (such as localStorage, sessionStorage, IndexedDB, or cookies) does not contain sensitive data. | Partial | The refresh token is in `sessionStorage`, as 3.2.3 permits. No other sensitive data was found in the auth store |
| 8.2.3 | authenticated data is cleared from client storage, such as the browser DOM, after the client or session is terminated. | Pass | `clearTokens` and `authStorage` clear on sign-out |
| 8.3.1 | sensitive data is sent to the server in the HTTP message body or headers, and that query string parameters from any HTTP verb do not contain sensitive data. | Partial | Credentials go in the body and tokens in a header; reset links keep the token in a fragment. Verification links are single-use tokens in the fragment (`/verify-email#token=…`), posted to `POST /auth/verification/confirm/` in a body ([IR-643](https://citiris.atlassian.net/browse/IR-643)). Links emailed earlier, with `uid` and token in the path (before IR-928) or the fragment (IR-928), verify no one: both old routes answer only "invalid link". An old path link can still appear in a request line while inboxes hold it, which the redaction covers. Ready for a person to re-check and move to Pass. Log redaction (`core/logging.py`, nginx) stays as the backstop. [IR-928](https://citiris.atlassian.net/browse/IR-928) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 8.3.2 | users have a method to remove or export their data on demand. | Gap | ADR-051 accepted, not built. [IR-785](https://citiris.atlassian.net/browse/IR-785), [IR-786](https://citiris.atlassian.net/browse/IR-786) |
| 8.3.3 | users are provided clear language regarding collection and use of supplied personal information and that users have provided opt-in consent for the use of that data before it is used in any way. | Partial | Consent is collected. Notice needs DPO review ([IR-123](https://citiris.atlassian.net/browse/IR-123)), and version and withdrawal are not built ([IR-789](https://citiris.atlassian.net/browse/IR-789), [IR-791](https://citiris.atlassian.net/browse/IR-791)) |
| 8.3.4 | all sensitive data created and processed by the application has been identified, and ensure that a policy is in place on how to deal with sensitive data. | Gap | No inventory. [IR-824](https://citiris.atlassian.net/browse/IR-824) |

## V9 · Communication

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 9.1.1 | TLS is used for all client connectivity, and does not fall back to insecure or unencrypted communications. | Pass | Caddy serves HTTPS and redirects plain HTTP, and nginx isn't published ([IR-847](https://citiris.atlassian.net/browse/IR-847), ADR-057). CI shows this on the real Caddy with a local certificate. On iris-demo 2026-11-11, plain HTTP answered `308` to `https://iris-citu.duckdns.org/` (IR-806) |
| 9.1.2 | using up to date TLS testing tools that only strong cipher suites are enabled, with the strongest cipher suites set as preferred. | Partial | CI's OpenSSL probe refuses weak ciphers on the real Caddy (IR-847). On iris-demo 2026-11-11, TLS 1.2 negotiated `ECDHE-ECDSA-AES128-GCM-SHA256` and TLS 1.3 `TLS_AES_128_GCM_SHA256` (IR-806). A full scan on the deployed domain is still owed |
| 9.1.3 | only the latest recommended versions of the TLS protocol are enabled, such as TLS 1.2 and TLS 1.3. The latest version of the TLS protocol should be the preferred option. | Pass | The Caddyfile allows only 1.2 and 1.3, and CI's probe confirms it (IR-847). On iris-demo 2026-11-11, TLS 1.2 and 1.3 connected and TLS 1.1 was refused with `alert protocol version`; TLS 1.0 was checked in CI only (IR-806) |

## V10 · Malicious Code

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 10.3.1 | if the application has a client or server auto-update feature, updates should be obtained over secure channels and digitally signed. The update code must validate the digital signature of the update before installing or executing the update. | N/A | A web application with no auto-update feature |
| 10.3.2 | the application employs integrity protections, such as code signing or subresource integrity. The application must not load or execute code from untrusted sources, such as loading includes, modules, plugins, code, or libraries from untrusted sources or the Internet. | Gap | One SRI-pinned Font Awesome 6.5.1 stylesheet remains; built-page icon check pending. [IR-822 evidence](traceability/IR-822.md) |
| 10.3.3 | the application has protection from subdomain takeovers if the application relies upon DNS entries or DNS subdomains, such as expired domain names, out of date DNS pointers or CNAMEs, expired projects at public source code repos, or transient cloud APIs, serverless functions, or storage buckets (*autogen-bucket-id*.cloud.example.com) or similar. Protections can include ensuring that DNS names used by applications are regularly checked for expiry or change. | Needs manual check | Depends on IR-806's DNS. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |

## V11 · Business Logic

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 11.1.1 | the application will only process business logic flows for the same user in sequential step order and without skipping steps. | Pass | Workflow services refuse illegal transitions; `InvalidPipelineTransition` |
| 11.1.2 | the application will only process business logic flows with all steps being processed in realistic human time, i.e. transactions are not submitted too quickly. | N/A | Decided 2026-11-05 by Ashlee Sean: every act needs a signed-in account and throttles apply; a minimum-time rule would be a guess. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 11.1.3 | the application has appropriate limits for specific business actions or transactions which are correctly enforced on a per user basis. | Pass | DRF throttles, per-reader run caps, provider admission |
| 11.1.4 | the application has anti-automation controls to protect against excessive calls such as mass data exfiltration, business logic requests, file uploads or denial of service attacks. | Pass | `DEFAULT_THROTTLE_RATES`, `ai_query`, `apps/tests/test_throttle_configuration.py` |
| 11.1.5 | the application has business logic limits or validation to protect against likely business risks or threats, identified using threat modeling or similar methodologies. | Partial | ADR-053 names the risks and is **Accepted** |

## V12 · Files and Resources

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 12.1.1 | the application will not accept large files that could fill up storage or cause a denial of service. | Pass | `MAX_PDF_SIZE_BYTES` of 50 MB; nginx `client_max_body_size 55m` |
| 12.3.1 | user-submitted filename metadata is not used directly by system or framework filesystems and that a URL API is used to protect against path traversal. | Pass | Stored through Django `FileField`, which cleans the name |
| 12.3.2 | user-submitted filename metadata is validated or ignored to prevent the disclosure, creation, updating or removal of local files (LFI). | Pass | As 12.3.1 |
| 12.3.3 | user-submitted filename metadata is validated or ignored to prevent the disclosure or execution of remote files via Remote File Inclusion (RFI) or Server-side Request Forgery (SSRF) attacks. | Pass | As 12.3.1; IRIS never fetches a file from a supplied name |
| 12.3.4 | the application protects against Reflective File Download (RFD) by validating or ignoring user-submitted filenames in a JSON, JSONP, or URL parameter, the response Content-Type header should be set to text/plain, and the Content-Disposition header should have a fixed filename. | Pass | `FileResponse` with a fixed content type on manuscripts, and nosniff |
| 12.3.5 | untrusted file metadata is not used directly with system API or libraries, to protect against OS command injection. | Pass | No file metadata reaches a shell |
| 12.4.1 | files obtained from untrusted sources are stored outside the web root, with limited permissions. | Pass | The media volume is not mounted into the web container ([IR-152](https://citiris.atlassian.net/browse/IR-152)) |
| 12.4.2 | files obtained from untrusted sources are scanned by antivirus scanners to prevent upload and serving of known malicious content. | Gap | No scanning. [IR-666](https://citiris.atlassian.net/browse/IR-666) |
| 12.5.1 | the web tier is configured to serve only files with specific file extensions to prevent unintentional information and source code leakage. For example, backup files (e.g. .bak), temporary working files (e.g. .swp), compressed files (.zip, .tar.gz, etc) and other extensions commonly used by editors should be blocked unless required. | Pass | nginx serves the built bundle and named asset types; `/api/` and `/admin/` are proxied |
| 12.5.2 | direct requests to uploaded files will never be executed as HTML/JavaScript content. | Pass | Files go through Django views with nosniff ([IR-152](https://citiris.atlassian.net/browse/IR-152)) |
| 12.6.1 | the web or application server is configured with an allow list of resources or systems to which the server can send requests or load data/files from. | Partial | Docling, `db`, `redis` and other internal services have no route out, shown by CI ([IR-825](https://citiris.atlassian.net/browse/IR-825)). Services that call vendors can reach any host, and `SECURITY.md` §7 says why |

## V13 · API and Web Service

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 13.1.1 | all application components use the same encodings and parsers to avoid parsing attacks that exploit different URI or file parsing behavior that could be used in SSRF and RFI attacks. | Pass | Ten encoded and dot-segment forms of `/django-admin/` all get the allowlist's 403 through nginx, tested 2026-11-05. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 13.1.3 | API URLs do not expose sensitive information, such as the API key, session tokens etc. | Pass | Tokens travel in headers; keys are server-side |
| 13.2.1 | enabled RESTful HTTP methods are a valid choice for the user or action, such as preventing normal users using DELETE or PUT on protected API or resources. | Pass | Route matrix declares method by method (`apps/tests/access/routes.py`) |
| 13.2.2 | JSON schema validation is in place and verified before accepting input. | Partial | DRF serializers validate input. There is no JSON schema as such |
| 13.2.3 | RESTful web services that utilize cookies are protected from Cross-Site Request Forgery via the use of at least one or more of the following: double submit cookie pattern, CSRF nonces, or Origin request header checks. | N/A | The API authenticates with Bearer tokens, not cookies |
| 13.3.1 | XSD schema validation takes place to ensure a properly formed XML document, followed by validation of each input field before any processing of that data takes place. | N/A | The API accepts no XML |

## V14 · Configuration

| Item | Requirement | Status | Evidence |
|---|---|---|---|
| 14.2.1 | all components are up to date, preferably using a dependency checker during build or compile time. | Pass | `pip-audit` and `npm audit` gate in CI ([IR-613](https://citiris.atlassian.net/browse/IR-613), [IR-633](https://citiris.atlassian.net/browse/IR-633)) |
| 14.2.2 | all unneeded features, documentation, sample applications and configurations are removed. | Pass | No debug app in production, test-data commands refuse without `--force`, and production renders JSON only, so DRF's browsable API is off (`apps/tests/test_production_renderers.py`). [IR-925](traceability/IR-925.md) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 14.2.3 | if application assets, such as JavaScript libraries, CSS or web fonts, are hosted externally on a Content Delivery Network (CDN) or external provider, Subresource Integrity (SRI) is used to validate the integrity of the asset. | Gap | As 10.3.2. [IR-822](https://citiris.atlassian.net/browse/IR-822) |
| 14.3.2 | web or application server and application framework debug modes are disabled in production to eliminate debug features, developer consoles, and unintended security disclosures. | Pass | `production_problems()` refuses `DEBUG`; `apps/tests/test_settings_validation.py` |
| 14.3.3 | the HTTP headers or any part of the HTTP response do not expose detailed version information of system components. | Gap | No `server_tokens off`. [IR-821](https://citiris.atlassian.net/browse/IR-821) |
| 14.4.1 | every HTTP response contains a Content-Type header. Also specify a safe character set (e.g., UTF-8, ISO-8859-1) if the content types are text/*, /+xml and application/xml. Content must match with the provided Content-Type header. | Partial | Every response has a Content-Type and `nosniff`; nginx's own `text/html` responses name no charset. [IR-924](https://citiris.atlassian.net/browse/IR-924) · [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 14.4.2 | all API responses contain a Content-Disposition: attachment; filename="api.json" header (or other appropriate filename for the content type). | Gap | API responses have no `Content-Disposition`. [IR-821](https://citiris.atlassian.net/browse/IR-821) records whether it applies |
| 14.4.3 | a Content Security Policy (CSP) response header is in place that helps mitigate impact for XSS attacks like HTML, DOM, JSON, and JavaScript injection vulnerabilities. | Partial | Report-only, so it blocks nothing. [IR-823](https://citiris.atlassian.net/browse/IR-823) |
| 14.4.4 | all responses contain a X-Content-Type-Options: nosniff header. | Pass | `SECURE_CONTENT_TYPE_NOSNIFF`, `security-headers.conf`; `test_security_headers.py` |
| 14.4.5 | a Strict-Transport-Security header is included on all responses and for all subdomains, such as Strict-Transport-Security: max-age=15724800; includeSubdomains. | Pass | Caddy adds `max-age=31536000; includeSubDomains; preload` to every HTTPS response, nginx's included, once; CI checks it (IR-806). Checked on iris-demo 2026-11-11 after the deploy: the home page carries it, and `/api/v1/colleges/` carries exactly one |
| 14.4.6 | a suitable Referrer-Policy header is included to avoid exposing sensitive information in the URL through the Referer header to untrusted parties. | Pass | `same-origin` in both places ([IR-663](https://citiris.atlassian.net/browse/IR-663)) |
| 14.4.7 | the content of a web application cannot be embedded in a third-party site by default and that embedding of the exact resources is only allowed where necessary by using suitable Content-Security-Policy: frame-ancestors and X-Frame-Options response headers. | Pass | `X-Frame-Options: DENY` in both places, until CSP enforces frame-ancestors ([IR-823](https://citiris.atlassian.net/browse/IR-823)) |
| 14.5.1 | the application server only accepts the HTTP methods in use by the application/API, including pre-flight OPTIONS, and logs/alerts on any requests that are not valid for the application context. | Pass | nginx and DRF answer 405 to unused methods, CORS pre-flight answers only IRIS's origin, and nginx's access log records refusals. Tested 2026-11-05. [IR-829 worksheet](ASVS_MANUAL_CHECKS.md) |
| 14.5.2 | the supplied Origin header is not used for authentication or access control decisions, as the Origin header can easily be changed by an attacker. | Pass | Authorization reads the token and role, never `Origin` |
| 14.5.3 | the Cross-Origin Resource Sharing (CORS) Access-Control-Allow-Origin header uses a strict allow list of trusted domains and subdomains to match against and does not support the "null" origin. | Pass | `CORS_ALLOWED_ORIGINS` allowlist required in production; `validation.py` ([IR-154](https://citiris.atlassian.net/browse/IR-154)) |
