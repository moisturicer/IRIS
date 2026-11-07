# Release-readiness manifest (IR-741)

`eval_readiness` answers one question honestly: **does the evidence on file meet the selected
acceptance profile?** It reads files an operator already holds, runs no model, makes no
database or network call, and writes one versioned manifest. Collecting the evidence is
IR-755; the cutover procedure that reads the manifest is IR-742. Authority: ADR-049 §25-§26.

`evidence_met` means the recorded evidence meets the profile. It authorizes no release,
spending, deployment or traffic switch. A named person's decision is always listed as a human
review gap, so a manifest can never be fully green on its own.

## Gates

Each gate has one status and only `met` clears it: `met`, `not_met` (measured and short),
`inconclusive` (too little to say), `not_measured` (absent), `incomparable` (cannot be set
beside its baseline), `contract_only` (fake providers or a deterministic check, never quality
or capacity) and `breached` (an access or disclosure breach, which no average offsets).

| Gate | Needs |
|---|---|
| `comparison` | an architecture-mode campaign report that measured the candidate arm |
| `quality` | 90% task completion and 95% claim/citation/page objectives per repetition and per family, judged on the point estimate with the Wilson interval reported beside it; three repetitions, ten reviewed cases per family in each, a report that lists the set's families, real providers |
| `safety` | zero access or disclosure breaches in the arm |
| `human_review` | a counted report; every case reviewed twice; otherwise each gap is listed |
| `baseline` | a frozen baseline pinned by SHA-256, counted, recorded conditions equal to the candidate's, no aggregate regression |
| `access_disclosure`, `postgres_workers` | IR-608 evidence of the required kind, run, not skipped, passed |
| `browser_accessibility` | a named manual browser exercise at the candidate's commit with every check measured |
| `authorization` | workload, profile, every operational cap and every approval recorded |
| `workload` | a measurement of the declared workload, real PostgreSQL and independent workers, queue-inclusive p95 and resource pressure inside the profile |
| `cost` | cost per successful task inside the profile, failures and unknown usage included |

Capability and model results (`--capability`, `--model`) are carried in `separate_results`.
They never affect a gate and are never credited to the architecture.

## Use

```bash
python manage.py eval_readiness --preflight --workload w.json --profile p.json --approvals a.json
python manage.py eval_readiness --build --report campaign.json --candidate runtime \
    --baseline frozen.json --baseline-arm controller --baseline-sha256 <digest> \
    --scenarios ir608.json --workload w.json --profile p.json --measurements m.json \
    --approvals a.json
python manage.py eval_readiness --verify manifest.json [--check-files] [--assert-ready --expect-commit SHA]
```

- `--preflight` names every unrecorded declaration, operational cap and approval, and exits
  non-zero unless paid collection could begin. Nothing supplies a default or approves anything.
- `--build` writes `docs/evaluation/runs/<stamp>-IR-741-readiness-<set>.json`. A blocked
  manifest is a normal result: it exits 0 and prints each blocking reason.
- `--verify` fails when the schema is unknown, the manifest was edited after it was sealed
  (`manifest_sha256`), a gate was removed, or a `met` gate lacks an evidence reference.
  `--check-files` re-hashes every input the manifest names (`inputs`), so invented digests do
  not pass. `--assert-ready --expect-commit SHA` (the commit is required and must be clean)
  **rebuilds the manifest from the files it names** and refuses unless the rebuild is
  byte-identical, so a verdict edited by hand and resealed, or one whose `inputs` were emptied,
  does not pass. It also refuses a blocked manifest or one for another commit; this is what
  cutover preflight calls. Run it from the directory the manifest was built in, since inputs
  are recorded by the paths given to `--build`. The digest is not a signature: the rebuild is
  what makes the verdict checkable.
- `--baseline-sha256` is the SHA-256 of the canonical JSON of the baseline report (sorted
  keys, compact separators). A baseline whose digest differs is `incomparable`. The pin is the
  operator's argument (`pin_source: operator_argument`): it proves the file is unchanged, not
  that the right file was frozen, so record the digest wherever the baseline was frozen. A
  baseline that is the candidate itself (same arm, same runs, or same commit and engine) is
  `incomparable`.

Every input is recorded in the manifest by path and file SHA-256, and a gate cannot be `met`
without a reference to the evidence it rests on. The manifest holds no time of day, so identical
inputs give identical bytes.

## Not evidence

Fake providers, in-process or non-PostgreSQL runs, jsdom results and the synthetic fixtures in
`evaluation/tests/readiness_fixtures.py` are contract checks. A fixture that declares itself
`real` exists only to exercise the gate logic. No production campaign, load measurement,
browser exercise or human review has been collected for this manifest.

## Provenance of IR-608 evidence

`eval_scenarios` records the commit it ran at **once, on the run file** (`git_commit`), not on
each suite row, and `eval_campaign --scenarios` reads only the rows. So that the recorded
provenance reaches the gate, `eval_readiness` copies the run-level commit onto a row that has
none, marking it `git_commit_source: "run_file"`. Nothing is inferred:

| What the evidence records | Gate result | `provenance` |
|---|---|---|
| the candidate's commit | may be `met` | `verified` |
| no commit, or `unknown` (`git describe` could not say) | `not_measured` | `unverified` |
| the candidate's commit unknown | `not_measured` | `unverified` |
| another commit | `incomparable` | `mismatch` |
| the candidate's commit, but both are `<sha>-dirty` | `not_measured` | `unverified` |

This applies to `access_disclosure`, `postgres_workers`, the browser exercise and the workload
measurement alike. A dirty tree names no reproducible source, so it never verifies. The
browser producer keeps no private reference; it now records `evidence_recorded: true` per
measured check, and readiness accepts that or an `evidence_ref`.

## Success rates

The `workload` gate reports, per class, `successes`, `failures` and `observed_success_rate`.
**No success-rate threshold is approved, so none is enforced**; only a class in which every
sample failed blocks. A run with a 5% success rate and a fast p95 therefore still passes this
gate. That is a limitation of the policy, stated in the gate (`success_rate_policy`) and in
every manifest (`policy_decisions`), not a judgement that such a rate is acceptable.

## `workload-measurement-1`

The file an operator or IR-755's collector writes after running the declared workload. Shape is
checked by `validate_measurement` (`eval_readiness --validate-measurement FILE`); a well-formed
file is **not** evidence and the `workload` and `cost` gates still judge the numbers. A
malformed file makes both gates `not_measured` rather than crashing them. A committed example,
marked fake, is `workload-measurement.example.json`.

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | exactly `workload-measurement-1` |
| `run_id` | yes | non-empty string naming the load run |
| `git_commit` | yes | the commit the measured runtime was built from; must be the candidate's, and clean |
| `providers` | yes | `real` or `fake`; `fake` can only reach `contract_only` |
| `environment` | yes | `{database, workers}`; only `{postgresql, independent_processes}` counts as real |
| `started_at` | yes | timezone-aware ISO 8601; must be at or after the workload's `declared_at` |
| `concurrency` | yes | positive number actually run; below the declared concurrency is `incomparable` |
| `workload_sha256` | yes | 64 lowercase hex: SHA-256 of the declared workload as canonical JSON (sorted keys, separators `,` and `:`, `ensure_ascii=False`); a different digest is `incomparable` |
| `resources` | yes | non-negative numbers `peak_memory_mb`, `peak_connections`, `lock_waits`, `max_lock_wait_ms` |
| `samples[]` | yes | one per request; see below |

Sample fields: `class` (`ordinary`, `deep` or `ingestion`); `outcome` (non-empty; `success`, or
anything else, which counts as a failure); `usage_reported` (boolean); `cost_usd` (non-negative
number, or `null` meaning no usage and no reservation, which makes cost unbounded); `queue_ms`
and `total_ms` (non-negative; **required for `ordinary` and `deep`**, with `total_ms` >=
`queue_ms` so latency is queue-inclusive); `tool_ms` and `model_ms` (optional in the shape, but the `workload` gate is
`not_measured` while any `ordinary` or `deep` sample lacks either). Every number must be finite.
The declared `mix` is the minimum samples per class. Latency percentiles and the cost per
successful task include failed requests. A class in which every sample failed, ingestion
included, is `not_met`; an ingestion sample with no cost leaves `cost` `not_measured`.

The workload must be declared under the conditions the candidate's campaign ran under: its
`corpus_snapshot_digest`, `model_ids`, `data_policy` and `cache_state` must equal the arm's
recorded conditions, or both `workload` and `cost` are `incomparable`.

## What readiness re-checks rather than trusts

The campaign report is not sealed, so readiness recomputes what it can: every reported fraction
from its numerator and denominator (a stated value that disagrees, NaN included, is
`incomparable`); distinct cases and distinct repetitions (a run or case listed twice counts
once); that `set_families` names every family the arm ran; and the report's own
`enablement_blocked`, `blocking` and `excluded_runs`, which block the `comparison` gate. Campaign
spend whose rows record no cold or warm cache state is not bounded and keeps `cost` open.

## IR-755 integration contract

IR-741 does not collect. A collector can be written against this alone:

1. Declare the workload, the authorized profile (including every operational cap) and the
   approvals **before** collecting; `eval_readiness --preflight` must report `allowed`.
2. Run the declared workload against real PostgreSQL with independent workers and write a
   `workload-measurement-1` file; check it with `--validate-measurement`.
3. Run `eval_scenarios --workers` (and attach the named manual browser exercise) at the
   candidate's commit; keep the run file.
4. Produce a counted `eval_campaign` report: three or more real-provider repetitions of the
   candidate, two human reviews per case, and a frozen baseline report whose SHA-256 is
   recorded.
5. Run `eval_readiness --build`, then `--verify --assert-ready --expect-commit <sha>`.

Until those exist the manifest is `blocked`, correctly.

**The current set cannot clear `quality`.** `conversation_set_v1.json` has seven conversations
per family, below the ten distinct cases each reported family needs, and families A04, A07 and
A09-A13 have no supported cases. `quality` therefore stays `inconclusive` until IR-755 (or a
later set) supplies ten distinct supported cases per family. This fails safely; it is not a
defect of the gate.
