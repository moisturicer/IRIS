<!-- PR title format: IR-XXX Description     e.g. "IR-124 Implement RAG retrieval" -->

## What and why

<!-- What changed, and why. Not a restatement of the diff. -->

**Jira:** IR-

<!-- Branch: <type>/IR-XXX-short-description   Commits: type(IR-XXX): description
     Convention: docs/engineering/SDLC.md §2-4a -->

## Acceptance criteria

<!-- Copy each criterion from the Jira item and say HOW you verified it.
     "Looks right" is not a verification. -->

- [ ] …

## Test evidence

<!-- What you ran and what happened. Paste output or link the CI run.
     If no test was added, say why. -->

```
```

## Reviewer: look hard at

<!-- Where you are least confident, or where regression risk is highest. -->

## Checklist

**Required**
- [ ] Acceptance criteria satisfied and self-verified
- [ ] CI passing, or the failure is explained above and understood
- [ ] Branch is up to date with `feat/rag-service`
- [ ] No secret, credential or real institutional data committed
- [ ] No test was modified to make it pass

**When applicable**
- [ ] Tests added or updated, and executed
- [ ] `docs/testing/TRACEABILITY.md` updated for a requirement-bearing change
- [ ] Documentation updated
- [ ] Security implications addressed — auth, permissions, file access, secrets, external calls
- [ ] Migration included and tested against a realistic database copy
- [ ] Deployment or configuration change recorded

---

Definition of Done: [`docs/engineering/DEFINITION_OF_DONE.md`](../docs/engineering/DEFINITION_OF_DONE.md) §4.
Human approval is the gate — AI review may assist but does not approve.
