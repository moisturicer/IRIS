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
