# Correcting declared research metadata

[ADR-046](../adr/046-declared-research-origin-and-publication-metadata.md) defines research origin and publication metadata. Unknown origin is a real state: missing authors, submitting owners and import actors do not establish it.

Authorized metadata editors can declare origin and publication year through the existing editor. Spreadsheet imports accept optional `Origin` and `Publication Year` columns. Origins are `unknown`, `institutional`, `imported_reference` and `synthetic`; omitted origin stays unknown. Invalid explicit values are reported rather than silently reclassified. Completion year columns retain their existing meaning.

The corpus loader also accepts an explicit `--origin`; its default is unknown. Newly created demo records declare synthetic origin. Neither tool retrospectively relabels existing records.

Published legacy records can be corrected using the `correct_research_metadata` management command. It requires server access, `--actor` naming an active superuser, and a nonblank `--reason`. The positional manifest is a UTF-8 JSON array. Each object contains an existing integer `id`, nonblank `evidence` identifying the verified source, and at least one of `origin`, nullable `publication_year`, or ordered `authors` (an empty list explicitly clears recorded authors). Omitted fields are preserved. Unsupported fields, duplicate IDs and invalid values reject the whole manifest.

Review the manifest against source metadata first. Run with `--dry-run` to validate without writes. Remove that flag only for authorized corrections. The command locks all target records and writes corrections and `RESEARCH_METADATA_CORRECTED` audit events in one transaction. Audit metadata contains reason, evidence and the before/after author, origin and publication-year values. Owner, submitting actor, completion years and workflow state are untouched. Actor email identifies the authorizing administrator; it does not authenticate the server operator.

IR-563 intentionally applies no corrections to live records. Deployment adds unknown origin and an empty publication year to existing data. Demonstration and imported records retain unknown metadata until explicitly corrected.
