# IR-751 verification

Implementation revision: `8905b32f`. Baseline: `15c1ac36` from `origin/main`,
including merged IR-738 PR #495. The original checkout and unrelated edits were
preserved. This is additive expansion; no live writer transfer took place.

## Executed evidence

- Restricted PostgreSQL and independent-process tests cover immutable completed
  batches, interruption/redelivery, conservative unknown outcomes, retained
  original job caps, disclosure/source invalidation, current-space compatibility,
  incomplete-publication refusal, and shared ingestion-lane limits.
- Authenticated reader questions find the new revision and save page/text/revision
  citations. An independent older job cannot reactivate after the new revision
  publishes. Semantic queries use `query` semantics and matching space identity,
  with a separate admitted reservation under the reader's original AskRun cap.
- The first 11-case indexing run passed. A later 28-case indexing/reader/research
  run passed after the first review fixes. The complete AI unit suite passed
  **44 tests**. The final full-backend results appear below.
- Publication migration `0008`, AI migrations through `0011`, role provisioning
  and `provision_research_roles --check` passed on a separate development-database
  copy. **63 Records before and 63 after**. The original database was unchanged.
  `makemigrations --check --dry-run publication` found no changes.
- Python F-rule checks, compilation and diff whitespace checks passed.
- The non-root isolated worker image built; its indexing `--help` and pure
  chunking/indexing imports ran without loading Django. No provider request ran.

## Independent review

Two separate GPT-6.1 Sol reviewers at high reasoning effort reviewed Standards
and Spec. Their initial attempts hit an account usage limit; both resumed after
its reset. Their final source reviews report **no remaining material findings**.
They inspected source; the executed tests are the author's evidence, not an
independent human approval.

Standards found three material issues, all corrected and verified with behavioral
regressions. Spec found two overlapping issues, also corrected:

1. Provider inference held a canonical Record lock. An independent connection's
   withdrawal timed out in RED. Authorization now commits before inference; a
   fresh source/attempt/space check fences output. Withdrawal during inference
   completes and the old result cannot publish (GREEN).
2. Replay omitted uncited sources and exempted legacy positive source revisions.
   RED retained a combined answer after an uncited paper's consent was withdrawn.
   Replay/prior now verify all journaled sources and final citations, across
   legacy and AI-owned revisions, and return a safe placeholder when unavailable.
3. The new prior-history filter initially lacked bound reader identity at claim.
   RED dropped unchanged authorized history. The worker now verifies/binds its
   stored reader grant and checks reader/scope before the RLS-dependent history
   query. Both retained-history and revoked-history cases are GREEN.

## Failed attempts and environment corrections

The first full run used four xdist workers on one server and finished with
**5,984 passed, four failed, 18 skipped, one xfailed and 625 passed subtests**.
Two failures were loaded-machine Hypothesis health checks; two independent
extraction probes saw a different media path from their xdist parent. The entire
three affected test files subsequently passed **58 tests** in serial with the
repository's existing `ci` Hypothesis profile, without modifying those tests.
The final run uses the repository's four-shard CI collector, separate PostgreSQL
servers, serial execution per shard, and container-private media storage.

Early checks also caught missing declared AI test dependencies, incomplete
synthetic settings, a missing dependency on the IP-release schema, and an array
versus JSON projection mismatch. These were corrected before the passing runs.
A Docker snapshot attempt failed because of a missing cached content digest;
the disposable test runtime was built explicitly from the backend image instead.
The test-run guard correctly refused two concurrent runs on one PostgreSQL server;
the review regressions then ran on their own separate synthetic server.

Automatic approval review rejected adding an UPDATE grant for Embedding Space
locking. No such grant was added. Indexing rechecks the read-only space identity;
reader projections withhold a publication if the current identity no longer
matches. Parallel model upgrades remain IR-752/IR-739.

## Final full-suite result

All four shards exited 0 on implementation `8905b32f`:

| Shard | Passed tests | Passed subtests | Optional skips | Expected failures |
|---|---:|---:|---:|---:|
| 1 | 1,513 | 108 | 0 | 1 |
| 2 | 1,525 | 133 | 0 | 0 |
| 3 | 1,520 | 236 | 16 | 0 |
| 4 | 1,434 | 148 | 2 | 0 |
| Total | **5,992** | **625** | **18** | **1** |

Zero failures and zero errors. JUnit includes 6,636 cases when subtests and
skipped/expected-failure cases are counted. See [aggregate results](local-results.json).
The 15 indexing/recovery tests all pass in shard 2. Optional skips cover absent
local Docling, Redis and LlamaParse fixtures; the existing expected failure is
IR-469's HNSW scan-depth property. None is counted as a new pass.
The final three review regressions were observed RED before their fixes and
GREEN afterwards; the full final run includes them. No existing assertion was
weakened. Newly written assertions were corrected to the existing HTTP 201 and
pure chunking semantics while preserving that behavior.

## Delivery limits

All provider transports exercised are recording fakes on synthetic manuscripts.
They establish contracts, not paid-provider quality/capacity or production caps.
The realistic database copy was used only for migrations and role checks; no
copied manuscript was sent to a provider. The semantic adapter is explicit service
injection; its existing provider-gated default remains. No live paid campaign,
production rollout, traffic switch, institutional data reset or parent-ticket
modification occurred. Existing ADR-056/extractor-retirement enablement gates
remain. Human approval and remote CI remain separate delivery gates.
