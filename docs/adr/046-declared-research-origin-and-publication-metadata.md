# ADR-046: Declared research origin and publication metadata

## Status

Accepted by Lee Jasmin Adolfo in the IR-563 implementation discussion on 2026-10-30. The user approved the vocabulary, no inferred backfill, authorless citations, separate publication year, administrative correction path, and verification seams before implementation. This decision is not implementation review approval.

## Context

IRIS substituted institutional authorship for missing authors and displayed submitting owners as authors. Completion and creation years also appeared as publication metadata. External references and fabricated demonstrations could consequently look like CIT-U research.

## Decision

- `Record.origin` declares `institutional` (CIT-U research), `imported_reference` (external research), `synthetic` (fabricated demonstrations/tests), or `unknown` (not recorded). Real external evaluation papers are references, not synthetic research.
- Origin is separate from authors, owners and the import actor. It never changes authorization, workflow, retrieval visibility or disclosure policy.
- Existing records migrate to `unknown`. No names, dates, authors or provenance are inferred or retrospectively classified. New demo records explicitly declare `synthetic`; importers declare origin or leave it unknown.
- Missing authors render as quiet italic “Authors not recorded,” without a chip. Real author names retain their order. Owner and institution substitutions are removed. Authorless citations lead with the title; citations attribute CIT-U only for explicitly institutional records.
- A nullable `publication_year` is distinct from both completion fields and `created_at`. Existing years are never copied into it. Undated citations use `n.d.`; creation timestamps are labeled Added.
- Imported reference and synthetic origins have outlined badges containing an icon and a word. Catalogue wording does not classify every record as institutional output.
- Existing authorized metadata editors and spreadsheet/corpus import paths can declare origin. Existing web-edit permissions stay intact. A separate administrative correction command requires an active superuser actor, a reason, per-record evidence, strict record IDs and supported fields. It validates the entire manifest before writing, locks targets, and commits corrections and before/after audit events together. Dry runs write nothing.

## Alternatives Considered

Infer origin from missing authors or import account: less input, but unsupported assertions. Reuse completion year as publication year: no schema addition, but changes the meaning of existing facts. Broaden published-record web editing: convenient, but enlarges authorization beyond this ticket. All three were rejected in favor of explicit declarations and a bounded correction command.

## Decision Rationale

Unknown metadata must stay unknown. Explicit declarations allow correction without turning a display convention into a factual or authorization rule.

## Consequences

Existing demonstrations visibly retain unknown origin and missing authors until corrected. Publication years require separate entry. The migration preserves existing metadata and relationships; the correction command provides an auditable path for verified corrections.

## MVP Impact

Truthful discovery, reading, AI source cards and copied citations; no new workflow stages.

## SaaS Impact

An institution's catalogue may contain external references without claiming their authorship. The existing installation-wide institution label is not generalized in this change.

## Security Impact

Origin grants no permissions. Normal object-level editing rules remain unchanged. Administrative corrections require server access and an active superuser actor; the actor email identifies the authorizing account, not a new authentication mechanism.

## Deployment Impact

Apply the records metadata and audit-event-choice migrations before serving updated code. No live metadata correction or inferred backfill accompanies deployment.

## Research Impact

External evaluation papers remain identifiable as references and fabricated demonstrations as synthetic examples. No retrieval algorithm or evaluation labels change.

## Related Requirements

IR-552 User Story 6; truthful author/origin and publication metadata in IR-563.

## Related Tasks

[IR-563](https://citiris.atlassian.net/browse/IR-563).
