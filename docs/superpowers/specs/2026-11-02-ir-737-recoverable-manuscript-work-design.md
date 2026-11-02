# IR-737: Recoverable committed Manuscript work

Status: design and three public test seams approved by the user on 2026-11-02.

Authority: ADR-049, the accepted publication specification in
`2026-10-31-ai-runtime/05-publication.md`, and Jira IR-737, read on 2026-11-02.
IR-718 and IR-723 are both Done in Jira. This document specifies an
implementation, not delivery evidence or authorization to switch live writers.

## Outcome

Saving an accepted Manuscript revision commits a durable work item in the same
database transaction. An AI ingestion worker can acknowledge that item even
after losing its Redis notification. Its acknowledgement means processing is
pending, never that extraction, indexing or research has completed.

## Current evidence and integration constraint

- The authenticated Record create/update flow already wraps saves in a transaction.
- The working checkout has uncommitted source-identity work in
  `apps/documents/sources.py`, Record revision/hash fields, and related migrations.
  Its `reset_manuscript` entry point is shared by upload and submission paths.
- Existing `ingestion_grant` signs an old `IngestionJob` binding without checking
  whether its source is current. PostgreSQL verifies that old binding; the
  research row policy deliberately gives ingestion grants no content access.
- `ai.runs.worker` explicitly reserves its slots for reader research. Ingestion
  must use a separate process and must not consume those slots.
- AI-owned schema migrations already have one owner: `ai.runs.migrate`.

The source-identity changes are pre-existing work, not part of this ticket's
commit. Integration must preserve them. Before committing executable work,
either their owning change must be available as a committed dependency or this
ticket must use a self-contained additive source binding. Do not silently stage
those changes into IR-737.

## Options

1. **Django outbox plus AI receipt (recommended).** Canonical work commits with
   the source; AI owns its acknowledgement. Reconciliation handles lost hints.
   Costs: additive tables, restricted database functions and a separate worker.
2. **Use the existing Celery extraction job as the durable identity.** Less new
   infrastructure, but its post-commit enqueue has a loss window and its current
   `IngestionJob` identity requires extraction and an Embedding Space. It cannot
   represent committed pre-extraction work without changing its responsibility.
3. **Let AI discover changed Records by scanning.** Avoids publication hooks but
   needs broader institutional reads and loses the transaction-bound work
   authority. Reject for this requirement.

## Proposed flow and ownership

### Commit and recover

Django creates immutable outbox rows under the same Record lock and transaction
as the canonical Manuscript change. Each row carries a durable work ID, Record,
exact source revision, source identity, permitted operation and creation time.
The database enforces one identity per Record/revision/operation. Repeated hints
reuse that identity; rollback removes both the source change and its work.

An on-commit notification is a best-effort hint only. A bounded Django
reconciliation operation discovers current unacknowledged work, rechecks it,
issues fresh short-lived authority and republishes the hint. A crash between
commit and notification therefore leaves recoverable work. Queue failure must
not turn a successfully committed save into a reported failed save.

### Restricted processing authority

Extend the grant contract additively with an explicit canonical-work binding;
do not reinterpret old chunk-and-embed jobs as committed source work. Bind the
work ID, Record, exact revision and allowed processing operation. The database
verifier reads current canonical facts on every verification and renewal.
Missing, deleted, revoked, superseded or mismatched work fails closed.

Expose only the source information required for that operation through a
restricted database interface. Do not enable ingestion to read every table in
the reader policy, impersonate a reader or access unrelated Records. Storage
reads must use the verified exact source binding. Local extraction authority
does not grant provider transmission permission.

Deletion or a source/access change takes effect through current canonical
checks immediately. Delayed facts and old notifications never set permission
back to true. A new permitted revision needs its own current work identity.

### AI acknowledgement and status

A separate AI ingestion process verifies authority and writes an idempotent
receipt in `iris_ai`, using the existing AI migration owner. Django remains the
only institutional outbox writer; AI remains the receipt writer. Concurrent
workers acknowledge the same work once through a unique database identity.
Reconciliation may redeliver until a receipt exists.

Add a safe processing projection to the existing authenticated owner processing
status surface. Report the current revision as pending or acknowledged/pending
processing; superseded work cannot replace its status. Exclude grants, storage
paths, extracted text, internal errors and unrelated work. A narrowly scoped
read interface exposes receipt status without granting Django AI-table writes.

Keep existing extraction/indexing writers and reader behavior in place. This
ticket does not execute extraction, embed, activate derived research, add a
reader engine selector or switch ownership of existing derived tables.

## Intended change areas

- Django documents: outbox model, additive migration and canonical-save hook.
- Django grants: issuance, renewal, additive database verification and narrowly
  scoped processing reads; role provisioning where required.
- AI ingestion: separate receipt/reconciliation consumer and worker entry point.
- AI schema: additive receipt migration through `ai.runs.migrate` and minimal grants.
- Existing owner processing status: safe current-work projection.
- Configuration examples, traceability and focused delivery evidence.

Final migration numbers must be chosen against the actual committed dependency
graph, preserving all existing migrations.

## Proposed public test seams

1. **Authenticated Manuscript save and owner processing status.** Proves that
   committed saves expose pending work, rollback exposes none, duplicate saves
   preserve identity, and another reader cannot inspect owner-only status.
   Does not alone prove database role isolation.
2. **Grant verification and restricted reads as real PostgreSQL runtime roles.**
   Proves exact-work/purpose/revision binding; forged, unrelated, superseded,
   deleted and revoked authority fails; renewal rechecks canonical facts.
   Does not prove transport recovery.
3. **Independent AI ingestion processes plus reconciliation.** Lose a wakeup,
   reconcile, race duplicate deliveries and deliver old facts last. Proves one
   current recoverable receipt and that canonical denial precedes cleanup.
   Does not claim extraction, vendor quality or production capacity.

Use one failing behavior then its implementation at a time. Run focused tests
and relevant type checks during implementation, and the full applicable suite
at the end. Test additive migrations on a realistic database copy. Record any
missing PostgreSQL/worker environment as unmeasured. Finish with independent
standards/spec review and commit only IR-737 work to the current branch, as
requested by the implement skill.
