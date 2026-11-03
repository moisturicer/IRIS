# IR-831 verification evidence

Date: 2 November 2026 (Asia/Manila). Source: `feature/IR-831-bounded-pdf-source`, based on `78fb8014`. Scope: the approved [IR-831](https://citiris.atlassian.net/browse/IR-831) / [IR-830](https://citiris.atlassian.net/browse/IR-830) PDF intake and accepted-source contract. No deployment or paid/provider transmission was performed.

## Behavior and review

- The initial bounded-validator run failed 14 of 15 new cases against the old implementation, including empty-password encryption, active content, generic MIME acceptance and actual resource limits.
- The authenticated source-identity test initially failed because status had no persistent revision. Subsequent source tests verify idempotent original bytes, changed revisions, invalid replacements, removal, safe retrying/final status and owner-only explicit retry.
- Independent PostgreSQL worker connections complete, fail and retry A after B succeeds. Only B's text/status and source-bound chunk handoff survive. The active set and embedding handoff identify B's revision.
- Four authenticated upload routes exercise valid, malformed, encrypted, active-content and page-limited PDFs. Refusal stores no attachment/extraction. Unauthorized requests never enter parsing; general non-PDF attachments retain their policy.
- A version-boundary test keeps the submitted source's chunks active while the owner prepares a new Manuscript and deactivates them only on submission. Existing new-version and clearance-preservation tests remain in the regression suite.
- A raw-byte change with identical extracted text still gets a current-source chunk set; the old normalized ingestion key cannot suppress it. A deterministic embedding replacement test checks that superseded vectors are not persisted.
- Separate Standards and Spec reviews found two active-content bypasses, ambiguous ADR numbering references and a stale retry response. Actual subprocess reproductions accepted both bypass PDFs before fixes. Bounded indirect resolution and explicit action contexts now refuse them; reviewers confirmed resolution. The reference now points to IR-830, and stale retries return 409 before inspecting current processing status.
- Representative-paper checks identified ordinary opening-page navigation, a scheme-less citation link and non-action `/S` image-stream values. Regression fixtures preserve them without reopening the active-content bypasses.

## Resource profile

Linux container, Python 3.12.16, pypdf 6.21.4. Profile: 10-second wall deadline, 256 MiB address space, 1,000 pages, 200,000 traversal visits and depth 100. Real child-process tests deliberately lower wall, memory, page and traversal limits to provoke refusal. Missing limits refuse intake; the complete profile passes Django checks; a negative wall limit fails startup with `ImproperlyConfigured`.

All **40 public arXiv proxy papers** in the local development corpus were accepted by the final validator. Original sizes ranged from **248,647 to 20,333,543 bytes**. Slowest observed validation: **2.676 seconds**. This verifies a local candidate profile against that sample; it is not production capacity approval, a CIT-U research finding or a malware verdict.

## Migrations and static checks

Applied the additive AI `0039`, documents `0013`/`0014`/`0015` and records `0026` migrations to an isolated copy of the development PostgreSQL database. The copy contained **63 Records, 44 extractions and 44 chunk sets**; identity migration retained them. The phase backfill maps existing statuses without reading/replacing source bytes, and `0015` records the explicit processing-phase vocabulary. `makemigrations --check --dry-run` reports no missing migrations. The full repository Python undefined-name/import check passes.

## Backend integration verification

The completed local full run collected **6,023 cases**, with nine failures and one skip. It exposed two legacy task assertions missing the revision argument, a new test incorrectly assigning the derived embargo property, two historical-schema tests querying newer model columns, an undeclared retry route (two guard failures), the independent processing/library vocabulary collision and a CRLF-converted archive fixture checksum. No frozen migration, research label or audit pin was changed to fix these.

The corrected integration group ran **120 cases**: 119 passed, with only the archive checksum still failing before its committed LF bytes were restored in the disposable snapshot. A subsequent **31-case parser/fixture run passed completely**, covering that checksum and the final real-process memory-budget behavior. CI's Python 3.11 initially classified a cap below interpreter startup memory as malformed content; the child now installs its hard limit and explicitly refuses an already-over-budget runtime before importing the parser. The limit was not relaxed and the test still exercises a real child.

Authorization outcomes are now declared for all nine matrix roles; only the owner passes authorization for explicit retry. `ExtractionPhase` owns processing labels in a narrow module; its Reading PDF phase does not borrow the unrelated library `ReadingStatus`. Historical migration tests read only the schema under test and retain their original behavioral assertions. Final whole-suite evidence is the PR's CI run, with every backend shard required.

After integrating current main (`2c86e0eb`), CI run [41423160473](https://github.com/moisturicer/IRIS/actions/runs/41423160473) exposed a real inherited-memory-peak defect: Linux preserves `ru_maxrss` across exec, so the fresh parser could refuse valid PDFs based on its parent's earlier allocations. An isolated allocate/free/exec regression failed with budget code 5 before the fix. A probe measured a 324,452,352-byte historical peak against only 14,544,896 bytes of current address space. The child now reads its current Linux address space from a bounded `/proc/self/statm` read, installs the unchanged hard limit and checks that current footprint before parsing. The merged-code parser/source/upload/audit group then passed **143 cases**, zero failures or skips, including the inherited-peak regression and the actual 1 MiB refusal. Separate Spec and Standards reviews found no material issue in this correction; CI is rerun on the committed fix.

## Frontend verification

No frontend source or dependency files changed in this branch. With the project's Node 20.20.2 container and project dependencies (TypeScript 5.9.3, Zod 4.6.7, Vitest 5.0.5), typechecking and the production build pass. The full container test run completed **1,654 passed / 1 failed**; the only failure was an unavailable adjacent backend source fixture used by `AuditLogPage.test.tsx`. Providing that unchanged source fixture and rerunning the file passed **all five tests**, including the failed case. Every one of the 1,655 frontend cases therefore passed with the required fixture available; there was no frontend code fix or suppressed test.

An earlier host run used Node 24.14.0 with older installed dependencies. It reported 1,647 passed / 8 failed and seven AbortSignal errors, plus three type errors in unchanged Axios/Zod test/form code. The supported container resolved those dependency/environment failures. They are not represented as final source defects.

## Test environment

Early broad attempts were abandoned after a local Docker restart, missing AI test dependencies, mounted test-media write errors and inherited development-only disclosure settings. Those attempts are not final test evidence. The final backend run uses an exact committed snapshot on native container files, the repository-declared backend/AI dependencies, real isolated PostgreSQL, synthetic CI settings, no provider credentials and the disclosure bypass disabled.

The shared original checkout was concurrently switched/modified by another task. This ticket's authoritative commit is isolated in its attached worktree. Automatic approval review rejected removal of copied edits from the shared checkout, so those copies were left intact rather than risking concurrent work.
