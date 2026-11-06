# ADR-060: Forms use react-hook-form and zod

## Status

**Proposed** — 2026-11-06 ([IR-911](https://citiris.atlassian.net/browse/IR-911)), awaiting a named approver. Drafted by an AI agent; the choice is the team's.

## Context

`frontend/package.json` carried four form libraries, used by two unrelated approaches:

| Approach | Where it was used |
|---|---|
| react-hook-form + zod (+ `@hookform/resolvers`) | Publish dialog, Edit details dialog, the shared `MetadataForm` and `metadataSchema` |
| formik + yup | The sign-in form (`LoginForm`, and `LoginPage`'s `FormikHelpers` type) only |

Two ways to build a form means two ways to read an error, mark a field invalid and track submission, and two schema languages that cannot share a rule.

## Decision

- Forms use **react-hook-form** with a **zod** schema through `@hookform/resolvers/zod`.
- The sign-in form moves to it (IR-911): same fields, same messages, same names, `mode: "onTouched"` so an untouched field shows no error. `LoginForm`'s `onSubmit` now takes the values only and resolves when the attempt is over; the form stays busy until then.
- `formik` and `yup` are removed from `package.json`.
- A new form uses these two. Adding a different form or schema library needs a new ADR.

## Consequences

**Gains:**

- One approach, one schema language. The Publish and Edit details forms already share a zod schema; a rule written once can be reused.
- Two fewer dependencies (13 packages with their own), and `npm ls` shows every remaining form library in use.
- Fewer re-renders than Formik's controlled fields on the large metadata form.

**Costs:**

- The sign-in form was rewritten, not just re-pointed. Its 60-odd existing tests pass unchanged, but sign-in is the most sensitive screen; reviewers should try it by hand.
- zod's `.trim()` is applied on parse, so `onSubmit` now receives the trimmed email, where Formik passed the raw string. `LoginPage` trimmed it too, so nothing changes in what is sent.

**Rejected:**

- **formik + yup everywhere:** three larger forms and the shared metadata schema would move, for no gain over what is already shared.
- **Keeping both:** it is the state this ADR ends.
