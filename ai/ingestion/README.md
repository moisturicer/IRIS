# Committed Manuscript work (IR-737)

Django's `publication` app owns an institutional outbox. Its PostgreSQL trigger
commits work with the Record's source, including bulk SQL updates. Changing the
source revokes previous work; rollback removes both changes. Soft deletion
revokes work permanently. Restoring a Record cannot restore an old grant.
Adviser, publication status, embargo state, and owner removal/reassignment advance
processing authority's generation and invalidate old grants. The same current
work remains pending and can receive fresh authority after canonical rechecking,
so ordinary submission never discards its work. Non-content invalidation facts
survive hard deletion and are reconciled separately; delayed cleanup can only
remove receipts at or below its generation, never a newer acknowledgement.
The database forbids another work identity for the same Record/revision/operation.

The revision is the accepted Manuscript UUID when available, otherwise a fresh
attachment revision UUID. Storage uses unique attachment paths; this contract
does not authorize overwriting bytes at an existing storage key. This change
has no dependency on the uncommitted source-identity changes.

Django issues an `ingestion` grant with a `wrk` ID and `local_extraction`
operation, using the existing signing settings and TTL. Issuance and renewal
lock the Record and reject revoked, deleted, superseded or missing work.
PostgreSQL rechecks current facts on processing reads. Legacy ingestion grants
retain their old contract and cannot use the new source interface.

The restricted AI login discovers granted work and obtains only its exact
source binding through `iris_authz.processing_source()` in a verified ingestion
transaction. It cannot use that identity as a reader, read unrelated research,
write the outbox or read signing keys. Local processing authority grants no
provider transmission or active-publication permission.

## Setup and operation

Apply Django migrations, then run `python manage.py provision_research_roles`
with maintenance credentials. Apply AI migrations through the existing
`python -m ai.runs.migrate` maintenance entry point. Only that AI owner migrates
receipts. Django can execute a boolean acknowledgement projection and receives
no receipt-table write grant.
The AI worker owns both source and invalidation receipts; neither can authorize
a content read. Only a currently verified institutional grant can do that.

After commit, Django attempts to sign current work. A missed publisher,
disabled grants or lost wakeup leaves durable pending work. Reconcile from
`backend/`:

```text
python manage.py reconcile_manuscript_work --limit 10
```

For continuous reconciliation add an operator-chosen `--poll-seconds` greater
than zero and at most 60. Limit must be 1..1000. With research grants disabled,
reconciliation publishes zero items and preserves pending work.

Run a separate ingestion process from the repository root with the restricted
`RUNS_DATABASE_URL` login:

```text
python -m ai.ingestion.worker --limit 10 --poll-seconds 5
```

`--once` scans one page and exits. Continuous operation pages through work IDs
and starts another sweep after the last page. `INGESTION_REDIS_URL` is optional
in both processes: bounded best-effort hints use `iris_ai:ingestion:wakeup`.
PostgreSQL remains authoritative. Ingestion never takes reader-run slots.
No Compose service is started. Example bounds are demonstration inputs, not
approved production capacity values.

The receipt worker above acknowledges durable work only. IR-738 adds the
separately enabled pending extraction worker below. Indexing and active
publication belong to IR-751. No model is called. Existing extraction writers
and reader behavior remain in place.

## Owner status and verification

The existing owner-only `GET /api/v1/records/<id>/metadata-suggestions/` adds
`runtime_processing`: null without current work, otherwise the revision and
`pending_processing` or `acknowledged_pending`. Both mean incomplete processing. Existing
extraction status stays separate. Grants, storage keys, internal errors and
extracted text are excluded. Old receipts cannot replace a newer revision's
status. Before AI schema installation, status remains pending.

`backend/apps/ai/tests/test_manuscript_publication.py` covers commit/rollback,
owner status, restricted-role reads/refusals, renewal, lost publication,
competing independent processes and authenticated PDF upload. Use an isolated
test database when other tasks are running. The upload test skips on Windows
because bounded intake requires Linux; also run it on Linux.

On 2026-11-02, additive Django and AI migrations ran on a development DB copy
containing 63 Records, without switching live writers. Deployment and human
approval remain separate from implementation.

## Pending local extraction (IR-738)

Apply Django migrations `publication/0006–0007`, rerun `provision_research_roles`,
then apply AI migrations `0008–0009` through `python -m ai.runs.migrate`.
The latter remains the only migration/writer authority for `iris_ai`.
The AI runtime has insert-only access to immutable extraction revisions;
row policies require a verified grant for that exact current work. Django
receives only the safe status function, with no output-table grant.

The new worker reuses the pure Docling mapper, normalizer, context-path
chunker and pinned tokenizer. It does not import Django or write its derived
tables. It stores source-byte SHA-256, Manuscript revision, structured
extraction hash, extractor/configuration pin, chunk hash/options, page sizes,
element/page regions and citation/embedding text together in one immutable
pending revision. The pipeline pin includes the operator's deployed Docling
revision; changing extractor code/models requires a new pin. Storage keys
remain immutable, as required by IR-737. Local filesystem storage is the
supported isolated path; this worker does not add an object-storage adapter.

Create a JSON profile from the existing deployment's extraction/chunking
settings. For example, these are the current repository defaults, **not a
newly approved production profile**; replace `extractor_revision` with the
actual pinned local image/model identity:

```json
{
  "extractor_revision": "your pinned local Docling image and model revision",
  "extraction": {
    "do_ocr": false,
    "do_formula_enrichment": true,
    "do_code_enrichment": true,
    "do_picture_classification": true
  },
  "chunks": {
    "strategy": "structural-markdown-v1",
    "max_tokens": 700,
    "min_tokens": null,
    "context_path_max_tokens": 64,
    "exclude_sections": ["References", "Bibliography", "Works Cited", "Literature Cited",
                         "Table of Contents", "Contents", "List of Tables", "List of Figures"]
  }
}
```

Build the isolated image from the repository root:

```text
docker build -f ai/ingestion/Dockerfile -t iris-local-extraction .
```

Its entry point is `python -m ai.ingestion.extract_worker`. Supply the
restricted `RUNS_DATABASE_URL`, a read-only media mount and a profile mount,
and join only the deployment's local PostgreSQL/Docling network. The endpoint
must be the existing on-prem Docling service; no public extraction/provider
service is authorized. Example entry-point arguments (synthetic bounds only):

```text
--once --limit 10 --poll-seconds 5 --lease-seconds 180 --max-source-bytes 10485760
--media-root /media --profile /config/profile.json
--docling-url http://docling:5001 --docling-timeout 120
```

For a local interpreter, install `ai/ingestion/requirements.txt` and put
`backend/` on `PYTHONPATH` to expose the same pure modules. All worker timing,
source size and deployed profile inputs are explicit. The lease must exceed
the Docling request timeout; allow additional local chunking time. A lease
lost during computation fences the write. Grant expiry also fences it;
reconciliation must issue fresh authority and a later sweep retries unfinished
work. No open database transaction is held during extraction. A crash leaves
a recoverable lease, not a completed output. Polling reconciles lost hints;
the extraction worker uses no reader execution slots.

Duplicate completed work returns before reading bytes or calling Docling.
An independent claimant receives `busy` until the lease expires; takeover
replaces the attempt UUID, so a late worker cannot commit. Final persistence
locks canonical Record facts and rechecks grant, generation and current
source, in the same transaction as the output write. There is no active
pointer here to replace: even successful output is pending for IR-751.

The owner-only metadata-suggestions endpoint now reports `processing`,
`extracted_pending`, `failed` or `incomplete`, in addition to the receipt
states. It returns only state and revision. A partial-success Docling
envelope, missing page coverage, or absent page provenance cannot be reported
as a complete extraction. Conservative coverage can also withhold blank or
unmapped pages; it makes no claim about semantic extraction quality. Private
errors and extracted text never enter this projection. Terminal failed or
incomplete jobs are not automatically repeated by polling; an operator must
select a new corrected pipeline profile to retry them. Superseded jobs may
remain as historical pending metadata but cannot authorize reads or appear
as the current revision's output.

`test_runtime_extraction.py` exercises the public worker/status boundary with
restricted PostgreSQL roles, out-of-order completion, revocation/deletion,
independent-process lease takeover, RLS isolation and immutable output grants.
Set `IRIS_TEST_LOCAL_DOCLING` to an on-prem test endpoint to run its generated
two-page PDF through the real extractor; without it the check explicitly skips.
