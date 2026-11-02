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

The worker acknowledges durable work only. Extraction belongs to IR-738;
indexing and active publication belong to IR-751. No model is called. Existing
extraction writers and reader behavior remain in place.

## Owner status and verification

The existing owner-only `GET /api/v1/records/<id>/metadata-suggestions/` adds
`runtime_processing`: null without current work, otherwise the revision and
`pending` or `acknowledged_pending`. Both mean incomplete processing. Existing
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
