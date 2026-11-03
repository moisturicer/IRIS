# NFR-S6

[Back to the matrix](../TRACEABILITY.md)

## NFR-S6

**Requirement:** Account protection

**Implementation:** Lockout events defined in the audit model. **IR-536:** the browser counter counts only rejected credentials; outages and unverified accounts do not count. **IR-555:** axes returns JSON 429 with `code: too_many_attempts` and `unlock_at` computed from its persisted attempts and configured cool-off. Login authenticates the underlying Django request so axes' lockout flag reaches both WSGI and ASGI middleware, and axes keys attempts by the submitted username. A manual lock returns 403 `locked_by_admin` with no unlock time. The dialog counts down only to a known end, names RDCO for manual locks, and retains the older plain-text 429 fallback without inventing a duration. The browser's own counter retains its separate 15-minute duration. **IR-661:** login and registration have scoped rate limits per client address, apart from the lockout

**Evidence:** `apps/accounts/test_auth_throttles.py` (IR-661). `apps/accounts/test_lockout.py`: six REST cases (lockout JSON/time, a refused attempt moving the deadline, admission after expiry, refusal before expiry, ASGI, manual lock). `features/auth/LoginPage.test.tsx`: server deadline, manual lock, old-server fallback, browser lock, axe, and unchanged IR-536 cases. 2026-10-30: all six lockout tests and all 57 accounts tests passed in the isolated PostgreSQL container; frontend/full-suite evidence on the IR-555 PR

**Status:** **PARTIAL**
