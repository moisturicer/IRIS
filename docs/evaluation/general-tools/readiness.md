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

- `--preflight` names every missing declaration, operational cap and approval, and exits
  non-zero unless paid collection could begin. Nothing supplies a default or approves anything.
- `--build` writes `docs/evaluation/runs/<stamp>-IR-741-readiness-<set>.json`. A blocked
  manifest is a normal result: it exits 0 and prints each blocking reason.
- `--verify` fails when the schema is unknown, the manifest was edited after it was sealed
  (`manifest_sha256`), a gate was removed, or a `met` gate lacks an evidence reference.
  `--check-files` re-hashes every input the manifest names (`inputs`), so invented digests do
  not pass. `--assert-ready` implies it and additionally refuses a blocked manifest or one for
  another commit; this is what cutover preflight calls.
- `--baseline-sha256` is the SHA-256 of the canonical JSON of the baseline report (sorted
  keys, compact separators). A baseline whose digest differs is `incomparable`.

Every input is recorded in the manifest by path and file SHA-256, and a gate cannot be `met`
without a reference to the evidence it rests on. The manifest holds no time of day, so identical
inputs give identical bytes.

## Not evidence

Fake providers, in-process or non-PostgreSQL runs, jsdom results and the synthetic fixtures in
`evaluation/tests/readiness_fixtures.py` are contract checks. A fixture that declares itself
`real` exists only to exercise the gate logic. No production campaign, load measurement,
browser exercise or human review has been collected for this manifest.
