# Coding standards: judgement calls

What a reviewer enforces that **no automated check can**. If a rule can be a lint rule, a type, a test or a CI job, build that instead and keep it out of this file: a mechanical rule written as prose is a rule nobody enforces.

**Status: Proposed (IR-927).** A rule here is only a rule once a person has approved its wording in review. An agent may propose a rule; it may not make one.

Each rule says why it exists and names the incident, so it can be removed when the reason goes away.

## Frontend

### F1. A component that reads an API response degrades on a wrong shape; it never throws

If the response is not the shape the screen depends on (a list that is an object, a field that is missing), treat it as the failed-request state the screen already has: show what still works and say what could not be loaded.

*Why:* IR-913. The Audit Log read the new event-types response without checking it was a list. The router tests answer every `GET` with one paginated object, so the page threw once the response arrived. On CI the crash landed before the test's heading lookup and failed `roleNavigation.test.tsx`; locally the lookup won that race and the test passed. The test was generic by design, and the page was the thing that was wrong.

*A reviewer looks for:* a response's `data` used with `.map`, `.length` or property access on the strength of a TypeScript generic alone, where the value is read for display and a bad shape would crash the screen.

*Scope:* this holds until the frontend-to-backend contract check (IR-915) covers an endpoint. After that, the contract test is the guard for that endpoint and this rule need not be applied to it.

## Backend

No rules yet. Add one when a review finds a judgement call that a check cannot catch, with the incident that showed it.

## Cross-stack

### X1. A test reads only its own stack

A backend test does not read frontend source, and a frontend test does not read backend source. When the two sides must agree, the agreement goes through something both sides can test: an API response, a schema, or a fixture that both run against.

*Why:* IR-913. `AuditLogPage.test.tsx` read `backend/apps/audit/models.py` with a regex and required every backend event type to be a filter option. A backend PR that added an audit event type therefore failed the **Frontend** job until someone edited the frontend list. It happened three times on 2026-11-05, on three unrelated backend branches.

*Exception:* the `e2e/` suite, which runs against the whole stack on purpose and is not a unit-level guard.

*A reviewer looks for:* a path that climbs out of the stack's own folder (`../backend/`, `../frontend/`) inside a test.
