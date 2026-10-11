# Paper screening and topic counts — IR-501

## Design confirmed 2026-10-11

The human user approved the screening/counting design and its tests in the
IR-501 implementation chat. Visible records the disclosure gate refuses are
**unassessed**, with no withholding reason exposed (ADR-038 D3). Neither their
titles nor abstracts may reach a model. This confirms D3 only; ADR-038's
overall Proposed status and human approval gate remain outstanding.

The public boundaries under test are the registered `screen_records` tool,
the application topic-count workflow, and captured requests to scripted
screening providers. Profiles are tested through the existing public
inference configuration boundary.

Implementation plan:

1. Add the independent `screen` inference profile, off until configured.
2. Screen title and abstract against a written criterion in bounded batches.
   Validate each include/exclude decision and its verbatim quote. Malformed,
   missing, unavailable or late responses leave records unassessed.
3. Screen all scoped visible records at or below `AI_SCREEN_MAX_RECORDS`.
   Above the ceiling, use ranked paper candidates and report `matches_found`.
4. Count distinct included record IDs in SQL over the current visibility and
   Paper Chat scope. Possible duplicate papers are flagged, never merged.
5. Run focused tests, the full backend suite, static and Django checks, then
   independent standards/spec reviews. Record evidence and open a draft PR.

Title-and-abstract screening can miss a topic present only in the body.
Every result names this method and carries the criterion, number checked,
number unassessed and completeness label. A topic count is never exact.
The model is independently configured through `LLM_SCREEN_*`; no model or
account is inherited from the answer task. Deployment operators select an
approved model and endpoint under ADR-036's no-training policy. This change
performs no paid quality measurement and enables no reader-facing route.

## Current implementation

`research_tools()` offers `screen_records` with one model argument:
`criterion` (1–300 characters). Candidates come from record handles already
collected in the run or from the application workflow; a model cannot supply
IDs, scope, identity, batch size or limits. Visibility and Paper Chat scope
are re-read, and the disclosure gate is applied before each batch.
Cache reuse rechecks visible candidates, disclosure and title/abstract content
identity. Unchanged duplicate calls return the cached result and spend a call;
changed permissions or text require fresh screening. Returned evidence and
decisions are checked again after all batches. A newly invisible paper is
removed from every result/count; a newly gated visible paper is unassessed.
A paper edited while the model is checking it is also unassessed: its earlier
text and judgment are discarded from the result.

`topic_count(run, criterion, filters=...)` screens all visible filtered
records at or below the ceiling (default 500). Above it, the existing fused
paper ranking supplies at most ten candidates, bounded by the ceiling.
Ranking keeps candidate IDs inside the application so refused candidates
remain unassessed. Only approved content reaches screening. Every included
record is counted in SQL with `COUNT(DISTINCT pk)` against current visibility.
Metadata counts through `count_records` retain their existing exact contract.

Screening uses title and abstract in batches of 20, within the run's prompt
budget and a 20-second per-call limit capped by remaining time. Missing,
duplicate, invalid or unsupported judgments become unassessed; the deciding
quote for an include/exclude must be a nonempty verbatim substring of that
paper's title or abstract. An outage affects its batch, preserving completed
batches. Unassessed quote text is discarded. These checks verify provenance,
not the screening model's judgment accuracy.

Results carry `criterion`, `method`, checked/unassessed totals, decision rows,
included matches, possible-duplicate flags and code-produced wording:
"N matched out of M checked; K could not be assessed." A sampled count adds
"These are matches found; other visible papers were not checked." The label
is `screened` or `matches_found`, never exact. Gated candidates appear only
in the unassessed total, with no individual identity or reason.

Normalized-title equality and same-model record-vector cosine similarity
at or above 0.98 produce possible-duplicate flags. They never merge records
or reduce the count. Versions, owners and chunks belong to a record and
never increase its count. The duplicate threshold and screening limits are
configurable starting values, not empirically calibrated quality claims.

The owner accepted the scope in IR-499's Jira comment, but the ADR document
still says Proposed. That tracking/document contradiction is recorded here
and remains a human approval prerequisite for merge and rollout.
