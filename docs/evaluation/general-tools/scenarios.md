# IR-608 access, recovery and browser exercises

This free development harness implements ADR-042's A11–A15 safety checks. It calls no vendor and supplies no production approval. From `backend/`:

```powershell
python manage.py eval_scenarios --workers --out ../docs/evaluation/runs
```

The command launches fixed pytest suites in isolated test databases (base name `iris_ir608`, configurable with `--test-database-name`). PostgreSQL with pgvector and permission to create test databases are required. Do not run another collection against that same test database concurrently. Independent child interpreters share the test Postgres and admission ledger, with explicit stdin gates controlling races. They use scripted generation, real application claims, fences, state commits and physical admission accounting. These are worker correctness measurements, not a Celery broker delivery or throughput benchmark. The HTTP reconnect exercise separately checks the reader cursor and final-event deduplication.

The access/recovery suite uses IR-606 `collect_case`: fresh saved Conversations, authenticated `public-1` requests, complete public SSE events and reopened history. Optional `before_turn(number, conversation_id)` and `observe(number, conversation_id, events, transcript)` hooks let controlled fixtures revoke sources between delivered turns and inspect the current public output without changing application permissions. Hook failures remain failures. Existing registry and controller suites cover foreign handles, Paper Chat scope, stale versions, malicious passages and disabled public tools. The four controlled cases distinguish candidates without answered passages, no candidates, rejected arguments and an answer-provider failure after real authorized retrieval. The harness never grants access to make a test pass.

A revocation regression exposed public history retaining answer prose after its citation was removed. Public history now withholds that Turn's answer, question, resolved question, summary and derived listing/comparison when any cited Record is unreadable. Readable historical source pointers retain their existing semantics. The legacy protocol is unchanged.

## Evidence and access

The run records the tested commit, evidence kind, measured/not_measured status, counts and pass/fail per suite. Any failed or unmeasured required exercise blocks enablement. Missing Postgres, dependencies, workers, browser evidence, skips, collection errors and timeouts never pass. Raw pytest tracebacks and XML stay in a temporary directory and are removed after extraction; the saved report carries no paper text, diagnostic trace, credentials or screenshots. Actual Conversation data remains owned by its reader and follows the existing application access/deletion rules. No review endpoint or new permission is introduced.

Collected per-turn stream/answer data is private review material: a turn captured before revocation may still contain what was authorized then. Never publish it or hand it to another reader; re-open through the application's authenticated public API for a current-access view. Keep any local copies under the same access, retention and deletion policy as the source Conversation; deleting a Conversation does not automatically delete an operator's local files. The runner's committed evidence contains counts only. No live or paid campaign is implied by deterministic contract results.

## Browser exercise (separate from jsdom)

Use a development reader account and synthetic papers. Copy `browser-evidence.example.json` to a private evidence directory. Record the named operator, UTC time, exact tested commit, browser/version, viewport and the saved Conversation ID. For each check record `status: measured`, a boolean `passed`, and a private screenshot/recording reference only after performing it:

1. Before submitting anything, verify the exact persistent mistake notice below both Ask IRIS and Paper Chat composers. Tab through composer, submit and citation controls; verify accessible names and visible focus.
2. Submit the safety conversation and inspect the live answer and public network stream. Neither may contain routing, tool arguments, provider identifiers or raw reasoning. Reopen its saved address and repeat the inspection.
3. Copy the answer and inspect the clipboard. Inspect the exported presentation if the interface supports one. If export is absent, leave `exported` as `not_measured`; copying does not prove export.
4. Open Paper Chat and check source scope and the same safe presentation. Expand/collapse any safe analytical summary with keyboard and check its accessible expanded state. If no summary can be exercised, leave that check unmeasured.
5. At a mobile viewport (for example 390 × 844), verify readable content, composer/notice visibility, working controls and no horizontal clipping. Check keyboard navigation and accessibility in the real browser, including checks that jsdom cannot perform.

An absent capability or environment stays `not_measured`, never a fabricated pass. Attach completed evidence with `--browser-evidence PRIVATE_FILE.json`. Evidence must refer to the command's current commit. This is explicitly named manual browser evidence, not an automated browser result; the summary omits private references and content. The browser record is an operator attestation and still needs human review. Public research remains disabled pending its own approval; no browser or worker result enables it.
