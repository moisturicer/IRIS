# ADR-045: Email account recovery and verification resend

## Status and approval

**Proposed — 2026-10-30, IR-641. Not accepted; no runtime change authorized.**
Named human approver: **pending**. Approval date and evidence: **pending**.
Acceptance requires the person's name, explicit approval of this revision and a
durable review/comment link recorded here. AI review and merging a draft do not
constitute architectural approval. IR-642 and IR-643 remain **not-ready** until
that record exists and their readiness is reassessed against the accepted text.

## Context and observed baseline

Forgotten-password guidance currently directs users to RDCO or their department
administrator. `backend/apps/accounts/views.py` offers authenticated password
change, registration and GET activation, but no reset or resend endpoint.
`services.py` uses `default_token_generator` for verification without a distinct
purpose or persisted consumption record. `RegisterView.perform_create` dispatches
mail inside its transaction. `core/utils.py:send_email_async` can fall back to a
synchronous, silently failing send; `accounts/tasks.py` retries mail three times.
These are observations, not the proposed recovery guarantees.

`User` stores verification, active and manual-lock flags separately from role and
`RoleRequest`. `sessions.py` tracks browser sessions; `authentication.py` still
accepts access JWTs without `sid`. Registration and password-change serializers
check length but do not call all configured Django password validators. Recovery
must not inherit these gaps or accidentally become an approval/unlock mechanism.

## Proposed decision

### 1. Account eligibility and effects

The following rules apply at issuance **and again under lock at consumption**.
Restrictions take precedence over all other rows. Unknown, deleted, ambiguous
email matches and unusable-password accounts are ineligible for both purposes.

| Account state | Reset password | Resend/consume verification | Preserved state |
|---|---|---|---|
| Active, unlocked, unverified | Allowed | Allowed | Reset leaves `is_verified=false` |
| Active, unlocked, verified | Allowed | No email; existing verification tokens refused | Verification remains true |
| Pending or declined role request | Same rules as flags above | Same rules as flags above | Role and request decision unchanged |
| Manually locked | Refused | Refused | Lock unchanged |
| Inactive | Refused | Refused | Active flag unchanged |
| Axes login lockout | Allowed if otherwise eligible | Allowed if otherwise eligible | Axes attempts and lockout unchanged |
| Unknown account | No email | No email | No account created |

Reset changes only the password and recovery/security state described below;
verification changes only `is_verified` and its own token state. Neither assigns
a role, modifies consent, approval, coordinator/staff privileges or email address,
unlocks, reactivates or signs the user in. Verification proves mailbox control;
it does not approve a role. Return to ordinary sign-in, which retains existing
authorization and account checks. This ADR does not introduce a new login
approval policy. A verified pending-role account keeps exactly its existing rights.

Email input is stripped and the domain lowercased using the existing account
normalization; local-part case is preserved. Do not silently introduce a new
case-insensitive identity rule. More than one match must fail closed.

### 2. Public HTTP contracts

All paths below are relative to `/api/v1/auth/`. Recovery is anonymous, accepts
JSON only, ignores incidental Authorization headers, and never returns JWTs,
account IDs, recipient addresses or delivery status. Responses have
`Cache-Control: no-store`. Unknown fields and malformed types receive 400.

| POST path | Exact request fields | Success |
|---|---|---|
| `password/reset/request/` | `{"email":"reader@example.edu"}` | 202 generic acknowledgement below |
| `verification/resend/` | `{"email":"reader@example.edu"}` | Same 202 |
| `password/reset/confirm/` | `{"token":"<opaque>","new_password":"<value>","confirm_password":"<value>"}` | 200 `{"code":"password_reset","detail":"Password updated. Sign in with your new password."}` |
| `verification/confirm/` | `{"token":"<opaque>"}` | 200 `{"code":"email_verified","detail":"Email verified. Return to sign-in."}` |

202 is always `{"code":"request_received","detail":"If this address is eligible, an email will arrive shortly. You can try again after 60 seconds.","retry_after":60}`.
It covers eligible, unknown, restricted, already-verified, cooldown-suppressed
and recipient-limited requests identically. It promises neither existence nor
delivery. Syntactically invalid/missing email: 400
`{"code":"validation_error","errors":{"email":["Enter a valid email address."]}}`.
Missing/wrong-type fields use the same envelope with the relevant field and
`"This field is required."` or `"Invalid value."`. Email maximum is 254 characters;
tokens must be the 43-character base64url encoding specified below.

All invalid, expired, revoked, superseded, wrong-purpose, used and newly
ineligible token submissions return identical 400
`{"code":"invalid_link","detail":"This link is invalid or no longer available. Request a new email."}`.
Check token and eligibility before password-policy errors; no distinction between
expiry and use is exposed. Valid-token password errors use 400
`{"code":"validation_error","errors":{"new_password":["<validator message>"],"confirm_password":["Passwords do not match."]}}`,
omitting fields without errors. They do not consume the token.

IP throttling returns 429 `{"code":"rate_limited","detail":"Too many requests. Try again later.","retry_after":N}`
with integer `Retry-After: N` seconds until the limiting window clears (maximum
remaining delay when multiple windows apply). Shared infrastructure outage
preventing durable acceptance or limit enforcement returns 503
`{"code":"temporarily_unavailable","detail":"Unable to process this request. Try again later.","retry_after":60}`
and `Retry-After: 60`, identically for every account. No recipient-specific 5xx.
Unsupported methods return 405 without side effects; wrong media type returns
415. Body limit is 4 KiB (413). Bad tokens count toward IP limits.

### 3. Links, tokens and atomicity

Issue 32 cryptographically random bytes, base64url without padding (43 characters).
Store SHA-256 digest, user, immutable purpose (`password_reset` or
`email_verification`), issuance/expiry timestamps, consumed/revoked timestamps,
email binding and password-security version. No JWT or default Django reset
generator reuse. Reset lifetime is **30 minutes (1800 seconds)**; verification
is **24 hours (86400 seconds)**, measured from issuance, invalid at `now >= expires_at`.
Each purpose has at most one current token per user. A newly accepted issuance
revokes older tokens of that purpose **at commit**, including when delivery later
fails. Suppressed requests and delivery retries do not rotate or extend tokens.
Different purposes do not revoke each other merely on issuance.

Use `/password/reset#token=<opaque>` and `/verify-email#token=<opaque>` on the
configured frontend origin. Read the fragment once into memory and immediately
remove it with `history.replaceState`; never put it in local/session storage.
No token validation or mutation on page GET, preview, scanner or prefetch. Show
the reset form or a deliberate "Verify email" button; POST alone consumes.
Refresh after stripping requires reopening the email. Set Referrer-Policy:
no-referrer; omit analytics/third-party resources on these pages.

Lock the user then token rows in consistent order for issuance, consumption,
password change and credential issuance. Consumption checks purpose, digest,
expiry, current-generation/email binding, security version and eligibility inside
one transaction. Commit password/verification change, consumption and audit
together. Concurrent consumption yields exactly one success; losers get
`invalid_link`. Serialize issuance against consumption: whichever commits first
defines whether the old link is consumed or superseded. Recheck state rather
than trusting the emailed account snapshot. Email changes revoke both purposes.
All password changes revoke reset tokens; verification tokens survive password
changes because only reset tokens bind the password-security version.

### 4. Passwords and existing credentials

Reset requires matching confirmation and `validate_password(new_password, user)`
using all configured `AUTH_PASSWORD_VALIDATORS`: current minimum 8 characters,
common-password rejection and numeric-only rejection. Do not trim passwords.
Maximum 128 characters, enforced before hashing. Reject the current password
with `new_password: ["Choose a different password."]`. The server is authoritative;
client validation may assist but must render server errors verbatim as text.

On reset, atomically increment a persisted per-user credential version, end all
UserSessions and revoke all outstanding refresh credentials. Access and refresh
JWTs carry that version; both authentication and refresh compare against the
current user version on every request. Legacy JWTs with no version are refused
after rollout, including sid-less access tokens. Reset issues no replacement
credentials. Credential issuance and password checking must serialize with reset
so a login using the old password cannot mint the new version. Django-auth
sessions must also become invalid through the changed password hash. An already
authorized in-flight request may finish; every new authenticated request after
reset commit must fail with old credentials. Verification alone revokes no sessions.
Rollout forces existing JWT holders to sign in again; this is a deliberate cost.
Authenticated password change shares the credential-version/token invalidation
primitive so it cannot leave reset links or credentials alive accidentally.

### 5. Abuse controls and privacy

Use atomic shared counters across workers, not DRF's approximate process-local
throttling. Per purpose: request IP limit **10/10 minutes and 50/24 hours**;
confirmation IP limit **30/10 minutes**. Per normalized recipient across both
purposes: **5 issuances/hour and 10/24 hours**, plus **60 seconds between
issuances of either purpose**. Sliding windows use server UTC; attempts exactly
at the cutoff leave the window. Counters count request attempts by IP, and
accepted issuances by recipient; recipient buckets and cooldown timestamps are
maintained for syntactically valid unknown/ineligible addresses too, with the
same suppression decisions, to avoid existence-dependent behavior. Their
"issuance" means admission to the private delivery decision, even without mail.
Do not extend cooldown on suppressed requests. Limits are checked before lookup.
Recipient suppression returns generic 202, never a recipient-dependent 429.

Use keyed HMAC recipient identifiers in counters, not raw email or plain hashes.
Trust forwarded IPs only from the configured reverse proxy. Validation and
throttle decisions must not depend on account existence. Perform delivery lookup
asynchronously for every admitted syntactically valid request, including unknown
addresses; the HTTP path must not wait for SMTP or expose account lookup timing.
Do not offer polling of delivery or account status. If shared counters are down,
fail closed with the generic 503 for all addresses. Captcha is not added here.

### 6. Durable email and retry behavior

Persist a delivery intent in the request transaction; enqueue its ID only in
`transaction.on_commit`. A periodic dispatcher retries unqueued intents after
broker failure, so an on-commit crash cannot lose accepted requests. Worker
rechecks eligibility and issues a token plus its outgoing-mail record atomically;
send only after that commit. Registration verification must use this same
purpose and delivery path. No synchronous/silent fallback for these journeys.

An intent expires **10 minutes after request admission**, independently of token
expiry. At admission assign a monotonic generation per recipient and purpose,
including unknown recipients. Only the newest admitted generation may issue;
older pending generations become superseded. Suppressed requests create no
generation. Workers lock/claim the intent and enforce a unique token/outgoing-mail
record per intent: duplicate or concurrent execution reuses that record, never
issues again. Check generation, expiry and current account state in the issuance
transaction. A late worker cannot supersede a newer request's token. Once issued,
the token's own lifetime governs retries, and a newer issuance revokes it per §3.
Pending-intent expiry creates no token or email; the generic retry guidance applies.

Recovery mail contains purpose, one fixed-origin link, exact expiry in UTC,
"If you did not request this, ignore this email", and administrator contact
guidance. Never include a password, role decision or account restrictions.
Store any necessary raw token/mail payload encrypted with a separate configured
key; broker arguments contain only intent IDs. Delete encrypted payload on
success, permanent failure, supersession or expiry. Token digests/terminal
delivery records are purged after 7 days; audit retention follows existing audit
policy. Pending recipient payloads are encrypted as well.

SMTP transient/network failure: initial attempt plus **3 retries after 30, 120,
300 seconds**; reuse the exact token and expiry. Permanent SMTP rejection stops
immediately. Never send expired, consumed or superseded tokens; check before
each attempt. SMTP acknowledgement is "sent", not proof of receipt; duplicate
mail after an uncertain send is possible and contains the same single-use link.
Terminal failure is audited and alerted internally without email/token payload.
No unauthenticated delivery-failure disclosure. The confirmation screen says
"Email may take a few minutes. Check spam, try again after 60 seconds, or contact
RDCO or your department administrator." A new request follows the same limits.
Reset completion also creates a non-secret password-changed notification intent
after commit; failure to deliver that notice never rolls back the password.

### 7. User-visible journeys and accessibility

Sign-in's "Forgot password" opens an email form. Registration confirmation,
sign-in and invalid verification screens offer "Resend verification email".
Never require signing in or registering again. Offer a fixed `/login` return;
no caller-supplied redirect or automatic login. Do not prefill an address from
a recovery token. Reset completion reminds users verification/approval and
restrictions still apply; verification completion says approval may still be pending.

Both email forms have visible labels, inline associated validation, a pending
state announced through `role=status`, disabled duplicate-submit while pending,
generic confirmation and a visible 60-second resend countdown. Announce cooldown
completion once, not every second. Network/503 failures preserve typed email,
announce retry guidance and re-enable submission after the stated delay. A
network timeout has unknown outcome; retrying may suppress mail and must not
claim the first attempt failed. 429 uses the server delay.

Reset shows two password fields, show/hide controls and password-policy text;
verification requires an explicit button. Both handle idle, submitting, success,
validation, network/503, throttled and generic invalid-link states. For expired,
invalid and used links show the same invalid-link copy and a new-email action.
Never show account-specific eligibility or delivery failure on a public page.
Clear password/token memory on completion or leaving the page. Move focus to
the error summary or completion heading, associate errors via aria-describedby,
use aria-invalid, provide keyboard-operable controls, visible focus, adequate
contrast and usable layouts at 320 CSS pixels and 200% zoom. Do not communicate
status by color alone. During ambiguous confirmation timeout, retry the same
token; if it was committed the generic used-link state guides return to sign-in
or a fresh request, without exposing a success receipt endpoint.

### 8. Audit, configuration and bounded implementation

Add audit event types `RECOVERY_REQUESTED`, `RECOVERY_SUPPRESSED`,
`RECOVERY_TOKEN_REJECTED`, `RECOVERY_EMAIL_SENT`, `RECOVERY_EMAIL_FAILED`,
`PASSWORD_RESET_COMPLETED`, `EMAIL_VERIFICATION_COMPLETED`. Request events use
an anonymous actor; successful consumption may identify the affected user,
never impersonate a signed-in actor. Allowlist metadata: purpose, correlation
UUID, coarse outcome/reason and attempt number. Recipient HMAC and IP counters
stay outside audit metadata. Never log raw email, password, confirmation, token,
token digest, JWT, full link, request body, SMTP exception text or encrypted
payload in audit, application/proxy logs, traces, error reporting or Celery results.
Audit rejection uses coarse invalid_link only. Completion audit is transactional;
delivery outcomes are recorded separately. Log redaction must cover old activation
URLs during migration. Operations monitor aggregate failure/queue-age counts.

Document environment configuration in `backend/.env.example` on implementation:

| Key | Proposed value / validation |
|---|---|
| `FRONTEND_URL` | Existing fixed HTTPS origin in production; no request Host-derived links |
| `RECOVERY_RESET_TTL_SECONDS` | 1800 |
| `RECOVERY_VERIFICATION_TTL_SECONDS` | 86400 |
| `RECOVERY_COOLDOWN_SECONDS` | 60 |
| `RECOVERY_REQUEST_IP_10M`, `RECOVERY_REQUEST_IP_DAY` | 10, 50 |
| `RECOVERY_CONFIRM_IP_10M` | 30 |
| `RECOVERY_RECIPIENT_HOUR`, `RECOVERY_RECIPIENT_DAY` | 5, 10 |
| `RECOVERY_COUNTER_HMAC_KEY` | Required secret, separate from Django SECRET_KEY |
| `RECOVERY_MAIL_ENCRYPTION_KEY` | Required secret; rotation must retain decryption for unexpired intents |
| `RECOVERY_DISPATCH_INTERVAL_SECONDS` | 30 |
| `RECOVERY_INTENT_TTL_SECONDS` | 600 |
| `RECOVERY_MAIL_MAX_ATTEMPTS` | 4, delays fixed above |
| `RECOVERY_RECORD_RETENTION_DAYS` | 7 |

Also require existing SMTP sender/host/credentials, shared Redis and Celery
configuration. Validate positive bounds and required secrets at startup; never
silently disable limits or fall back on missing dependencies. Values above are
the proposed defaults; changing them requires documented security review and
updated tests. No real secrets belong in examples.

Narrow shared work belongs in `apps/accounts`: token/intent persistence and
migrations, recovery service, dedicated mail dispatcher, serializers/views/URLs,
audit types, credential-version enforcement in sessions/authentication and token
issuance, registration's verification adapter, frontend auth routes and API calls.
IR-642 owns shared token/delivery/limit primitives and credential invalidation;
IR-643 may proceed independently by introducing only its purpose's shared subset
first. Both use one additive schema/service contract described here; whichever
merges second reuses it and reconciles migrations. No separate gateway, generic
identity framework, role-policy refactor or broad mail-system rewrite.

At verification rollout invalidate all pre-contract activation links: stop
accepting GET `/activate/<uid>/<token>/` (return generic invalid-link, no mutation),
and make the existing frontend activation route offer resend guidance. Do not
keep a default-generator compatibility bypass. Registration and resend must
switch atomically to the new verification format. Inform users to request new
links. This trades old-link convenience for purpose separation and single use.

### 9. Required automated evidence at implementation seams

These are a test plan, **not executed tests or coverage claims**. Agree seams
when implementing: anonymous HTTP plus actual email outbox, authenticated HTTP,
worker/durable delivery boundary, and accessible UI journeys. Use deterministic
time and mail transport; real PostgreSQL transactions for concurrency.

| Evidence | Required cases |
|---|---|
| HTTP/email journey | Request → committed mail → link → POST → sign-in; old password rejected/new accepted; resend → verify; GET/scanners do not mutate |
| Account matrix | Every row in §1 for both issuance and consumption; changes between issuance and use; roles/requests/restrictions unchanged; reset never verifies |
| Token isolation | Cross-purpose use, malformed/unknown/used/revoked tokens; exact expiry boundary; older-link invalidation; cooldown/retry does not rotate; email/password changes |
| Atomic races | Two consumers exactly one winner; resend versus consume; lock/deactivate versus consume; reset versus login/refresh; rollback leaves no change, audit or dispatched mail |
| Credential invalidation | All tabs/devices, rotated refresh and access JWTs, sid-less/legacy JWTs, Django session; post-commit requests fail; new sign-in works |
| Password validation | Mismatch, length boundaries 7/8/128/129, common/numeric/current password, no trimming, validation failure leaves link usable |
| Privacy/limits | Same status/body/headers across eligibility; no account lookup on request path; atomic limits across workers, shared recipient limits/cooldown, cutoff and Retry-After; trusted proxy rules; counter outage |
| Delivery | No pre-commit mail; rollback, broker loss/on-commit crash, dispatcher recovery, duplicate/concurrent workers issue once, older delayed intent versus newer generation, intent expiry boundary, SMTP transient/permanent failure, duplicate delivery, expiry/supersession before retry, notice failure and payload deletion |
| UI/accessibility | Both full journeys; every §7 state; keyboard, narrow screen, zoom, status/focus/errors; fragment stripping, no external leakage, no automatic consumption or redirects |
| Audit/configuration | Correct event/state atomicity; redaction through logs/tasks/telemetry; payload retention, absent secrets/invalid config fail startup; realistic migration and legacy-link rollout |

### 10. Alternatives and approval checklist

Keeping administrator-only recovery avoids new public credential endpoints but
leaves users dependent on office availability; retain it only as support guidance.
Reusing stateless Django tokens is simpler but does not supply this contract's
explicit purpose, resend invalidation and concurrency guarantees. Persisted
single-use tokens and durable mail cost schema, worker and cleanup complexity,
but make these guarantees testable. Immediate revocation on resend simplifies
ordering and closes older links, but a failed new email strands the old link;
cooldowns, generic retry guidance and support are the chosen mitigation.

Human review must explicitly approve eligibility, lifetimes, immediate resend
revocation, generic delivery states, limits, forced credential rollout and legacy
activation retirement. Record approval above, then replace dependent-ticket draft
references with this accepted revision and reassess readiness. Until then this
document is a proposal, and the final approval acceptance criterion remains open.
