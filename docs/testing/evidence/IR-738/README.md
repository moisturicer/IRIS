# IR-738 verification

Date: 2026-11-03. Authority: ADR-049 and the accepted IR-716 publication design;
IR-738 owns local extraction and pending chunk revisions only.

## Executed checks

- Restricted PostgreSQL behavioral suite: 48 passed across
  `test_runtime_extraction.py`, `test_docling_client.py`, and
  `test_manuscript_publication.py` before the additional live fixture was added.
- Generated two-page synthetic PDF through the local Docling 1.36.0 endpoint:
  passed; pending output retained both pages and owner status reported extraction.
- AI unit suite: 42 passed. The initial run lacked `pytest-asyncio`; installing
  that test dependency and rerunning resolved its eight async-test failures.
- Undefined-name static checks: passed for changed Python modules.
- `manage.py check`: passed with the existing `documents.W001` warning that
  PDF-intake bounds are not configured in the development environment.
- Built `ai/ingestion/Dockerfile` from repository root and ran its non-root
  entry point with `--help`: passed, with no Django installation or ORM dependency.

The worker/status tests use a dedicated `test_iris_ir738` database and ephemeral
logins belonging only to `iris_ai_runtime`. Independent worker subprocesses
exercise shared leases and late-write fencing. No grant, password, source file,
real manuscript content or private exception is retained in this evidence.

## Migration and review evidence

The additive Django migrations `publication/0006–0007`, role provisioning and
AI migrations `0001–0009` passed on a separate development database copy,
preserving all 63 Records. `provision_research_roles --check` passed afterwards.
The original development database was unchanged.

Separate GPT-6.1 Sol reviews at high reasoning effort covered standards and
specification. Standards found a migration-evidence gap, now supplied above.
Spec found that SELECT-only RLS suppressed the canonical row lock. An independent
connection reproduced the bug: deletion did not wait. Additive migration `0007`
restricts update-side visibility to the verifier, and the regression now confirms
that a competing canonical deletion times out while the worker holds the lock.
An expired lease now projects pending recovery; a newer corrected profile's
status cannot be masked by an older longer lease (`0009`).

## Remaining verification

The full backend suite is in progress and has failures in this stale, dirty
checkout. Its actual results will be recorded before delivery. No CI or human
approval is claimed. Current-main compatibility is being verified separately.

## Scope limits

Only synthetic bytes and a generated PDF were processed through the new worker.
No provider/model request, live writer transfer, active research publication,
production deployment or data reset was performed. Profiles and capacity values
remain explicitly selected operational inputs. The legacy pipeline stays enabled;
pending AI output is a separate ownership expansion for IR-751 to consume.


## Full-suite integration findings

The initial clean four-shard run found a cross-owner migration dependency:
AI row policies referenced a Django-owned function directly, preventing historical
Django migrations from rolling back and causing follow-on schema failures.
AI migration `0010` replaces that reference with an AI-owned invoker wrapper
that resolves current institutional authority at execution and denies access
when it is unavailable. Existing historical migration tests exercise the fix.
The policy-shape test was deliberately updated to require the new verifier-only
UPDATE policy and its exact predicate; runtime write-denial assertions remain.
The new role-using test module was registered with local parallel test isolation.
The local image also lacked the declared `pytest-xdist` test dependency; it was
installed for the final run. These failures were not counted as passing evidence.

A second coverage regression demonstrated that a success envelope missing a PDF
page was accepted when checked against only the extractor's own page list.
The worker now compares against the actual source PDF page count using pypdf,
and deterministic workers use generated two-page PDFs. The original branch's
runtime regression run passed 12 tests, with its opt-in Docling test skipped in
that particular run (the separate live extraction test already passed).
