# IR-738 verification

Date: 2026-11-03. Authority: ADR-049 and accepted IR-716 publication design.
Implementation tested at `1d7c830b`, based on current main `70aa72ef`.

## Final results

The full backend suite ran in four module-preserving CI-style shards, each on
its own disposable PostgreSQL 16.15/pgvector server with synthetic configuration
and no provider credentials. Every shard exited 0:

| Shard | Passed | Skipped | XPASS | Passed subtests |
|---|---:|---:|---:|---:|
| 1 | 1,411 | 0 | 0 | 135 |
| 2 | 1,560 | 0 | 0 | 132 |
| 3 | 1,457 | 16 | 0 | 233 |
| 4 | 1,499 | 1 | 1 | 114 |
| Total | **5,927** | **17** | **1** | **614** |

JUnit records zero failures and zero errors (6,559 cases including subtests).
The 16 skips are optional LlamaParse document-clause fixtures; one skips a Redis
wakeup check because localhost Redis was unavailable. XPASS is the existing
non-deterministic IR-469 HNSW scan-depth test. None is represented as a new pass.
The separate AI unit suite passed **42 tests** in the final clean environment.

The full run includes the new worker/owner-status tests, historical migration
rollback, restricted-role and local parallelism checks. A focused integration
run of the worker, vector-redimension rollback, row policies and parallel
scheduler passed **39 tests** after the integration fixes.

## Extraction and ownership evidence

- A generated two-page synthetic PDF passed through local Docling 1.36.0 into
  page-bound pending output. No real manuscript or off-campus provider was used.
- Restricted `iris_ai_runtime` logins and independent processes exercise duplicate
  reuse, lease takeover, old completion, deletion/revocation before write,
  immutable grants, RLS isolation and safe owner HTTP status.
- Source coverage is checked against the actual PDF page count, not merely the
  extractor's own page list. A success response omitting a source page was
  reproduced as RED before the fix and is now incomplete. Explicit failed pages
  and partial-success envelopes also cannot become complete output.
- Django publication migrations 0006–0007, restricted-role provisioning/check,
  and AI migrations 0001–0010 passed on a separate development database copy,
  preserving all **63 Records**. The original database was unchanged.
- Undefined-name static checks and publication migration consistency passed.
  Django checks reported the existing unset development PDF-intake bounds warning.
- The final non-root isolated image builds, imports pypdf and the extraction
  worker, and confirms that no Django module is loaded.

## Reviews and corrected failures

Separate GPT-6.1 Sol reviewers at high reasoning effort reviewed standards and
specification. Their final follow-ups found **no material outstanding findings**.
Human approval and remote CI remain separate gates.

The initial canonical-lock implementation was filtered out by SELECT-only RLS.
An independent deletion reproduced the failure. Additive publication migration
0007 introduces verifier-only update visibility; the regression now proves a
competing deletion waits for the canonical lock. Expired leases report pending
recovery and newer profiles cannot be masked by older longer leases (AI 0009).

The first clean full run found AI policies directly depending on a Django-owned
authority function, preventing historical rollback and causing later schema
failures. AI 0010 replaces that reference with an AI-owned invoker wrapper that
resolves current authority at execution and denies when it is unavailable.
The policy-shape test was deliberately updated to require the exact verifier-only
predicate; runtime write-denial assertions remain. The new role-using suite was
registered with local parallel isolation. The final full run verifies the fixes.

An earlier stale/dirty-checkout run was interrupted and is not passing evidence.
An initial clean-container collection attempt lacked the repository-root mount;
that was corrected. Missing local pytest-asyncio/pytest-xdist dependencies were
installed from the declared test stack before final verification.

## Delivery limits

This is additive pending-only local work. No embedding, active publication,
legacy-writer transfer, paid provider campaign, production numeric approval,
live traffic switch or data reset occurred. ADR-056 adopts LlamaParse long term;
this transitional local Docling path requires that integration and IR-843
retirement to be resolved before live activation. Storage is local filesystem
only. Conservative coverage may withhold blank or unmapped pages; semantic
extraction quality is not mechanically proven. Terminal failures require a
corrected profile identity before retry.

The implementation was committed first on the user-requested original branch,
then adapted on an isolated current-main delivery branch to preserve unrelated
edits and current provenance/ADR-055 contracts. Publishing was blocked by automatic
approval review as private-source transfer without explicit authorization; no
push or pull request occurred. Jira remains In Progress pending publication.
