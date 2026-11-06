# IR-854: full-suite execution

Local parallelism uses pytest-xdist with module-preserving scheduling and
pytest-django worker databases. All consumers of cluster-wide research roles
share one scheduling scope. The controller takes the existing maintenance-DB
run lock before starting workers, since controllers do not collect tests.
Migrations remain enabled; tests are not removed for speed. Each worker captures
initial migration data and restores it only when switching from transactional
flush tests back to rollback tests, including sequence reset after deserialization.

CI uses the existing four runners. Module weights come from committed JUnit
measurements, with 0.2 seconds per collected test for unknown modules. Greedy
longest-first assignment uses deterministic ties and retains collection order.
A refresh command uses defusedxml to reject XML entities, and validates timing
data and duplicate cases.

Regression checks cover complete/disjoint assignment, balancing by duration,
fallback weights, invalid measurements, and real concurrent workers creating
the same unique user independently while child connections verify their database.

The previous 3–5 minute local estimate is unverified. Record actual wall times
on the same checkout and environment; database creation is included.
