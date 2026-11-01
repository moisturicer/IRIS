# IR-810: backend CI parallelism

The user approved parallel backend jobs and superseded PR cancellation after
measurement: run 41317690981 spent 11m08s in tests of a 12m10s Backend job;
run 41317350408 spent 15m02s in pytest. Dependency installation was 17s in
the first run. Optimizing downloads alone cannot address that wait.

## Design and trade-offs

Use four GitHub Actions matrix jobs, each with its own PostgreSQL service.
Every job collects the complete suite and deterministically assigns whole
modules by descending test count to the least-loaded shard. Preserve the
original order within each shard. Keeping files together preserves module
fixtures; separate runners isolate database roles and migration rewinds.
Tests still run sequentially on each runner.

This reduces elapsed waiting at the cost of four environments and repeated
collection/setup. Counts are an initial balancing proxy, not measured durations;
the slowest module is indivisible. In-process workers were rejected because
some tests change cluster-wide database roles. A manual app/path split was
rejected because it can omit newly added test locations and concentrate AI work.

Retain the Backend check as an always-running aggregate requiring all matrix
jobs to succeed. All existing static, settings, migration and strict database
checks remain. Keep fail-fast disabled to collect evidence from every shard.
Store JUnit reports per shard. Cancel obsolete runs only within the same PR;
main pushes get unique concurrency groups.

## Implementation and verification

Change `.github/workflows/ci.yml`; add the opt-in pytest plugin in
`backend/testing/ci_sharding.py`, regression tests in
`backend/apps/tests/test_ci_sharding.py`, and developer instructions.
No runtime code, dependency or requirement changes.

Verify deterministic complete/disjoint partitioning, whole-module assignment,
order preservation, invalid-option rejection, and actual pytest subprocess
execution. Run collection against the real backend suite and inspect every
shard's result in GitHub CI. Compare the slowest shard to the baseline only
after the run finishes; passing collection alone is not test execution evidence.

The user’s “go for it” approved this scope; human PR review remains required.
