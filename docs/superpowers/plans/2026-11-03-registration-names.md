# IR-857 registration names implementation plan

**Goal:** First and last names only at registration, with matching accessible client and REST validation.

**Spec:** IR-857 and its approved parent IR-855. Existing React/TypeScript and DRF boundaries stay in place. No model or stored-name changes.

- [x] Update `SignupPage.test.tsx` at the agreed page seam for invalid names, correction, focus and Unicode names; remove the obsolete M.I. expectations deliberately.
- [x] Update `SignupPage.tsx` and `types/auth.ts`: omit M.I., balance the two fields, validate letters/marks with spaces, apostrophes and hyphens, trim only outer whitespace, and focus invalid inputs.
- [x] Add `apps/accounts/test_registration_names.py` at the agreed REST seam: reject missing, blank, numeric and symbol-only names without writes; accept legitimate names and preserve existing middle initials.
- [x] Add registration-only serializer validation. Keep model fields and profile editing unchanged.
- [x] Record traceability, review against base `c119ed416d235c1f086087ff0a269ed4c2c5d8cb`, commit, push and open a PR. Use GitHub CI for full tests, lint and typechecking; local targeted checks support development and browser behavior.

PR publication and CI results are recorded in Jira and the PR; human approval remains pending.
