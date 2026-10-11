# Development chat routing (IR-515)

`AI_RESEARCH_LANE=off` is the default. The chat requests, response shape and stream
remain on the existing passage path without constructing a router or its providers.
`on` is development-only: startup rejects it with `DEBUG=False`. Production rollout,
staff access and asynchronous planner progress belong to IR-504. ADR-038 remains
Proposed; this branch is reviewable implementation, not approval to merge it.

Both chat endpoints route the raw reader question and resolved question with only
recent reader questions as routing history. Passage keeps the existing pipeline;
research calls the bounded planner synchronously; listing finds and screens records;
count uses the application topic-count workflow; comparison resolves full paper
titles and reserves a passage per paper before selecting extra passages.

Lists contain application rows only. Their titles are resolved from current readable
database records; model text cannot add a row. They say `matches_found`, while topic
counts retain their screening coverage and unassessed totals. A comparison requires
at least one citation for every paper with supplied evidence, otherwise its answer
is withheld and the sources remain available. Papers with no evidence are named.

A response carries `routing`, an SSE stream first emits `routing_decided`, and `done`
carries the same metadata. Optional `listing` carries its wording and rows. Each Turn
stores the decision and record pointers; replay rechecks visibility and resolves
current titles. Reader controls send `route_override` with the original question and
scope choice, creating a new Turn. Overrides cannot escape Paper Chat scope or
injection screening. Landscape decisions refuse without retrieval until the
research-landscape capability exists; this ticket/draft ADR conflict is recorded in
ADR-038's IR-515 divergence paragraph.

Repository guidance conflict: the user-supplied AGENTS instructions rank SRS/SDD
above ADRs, whereas CLAUDE.md freezes those documents and ranks ADRs first. No
SRS/SDD justification was required for this work; their contents were not changed.
The conflict remains unresolved rather than silently rewriting either authority.

Trade-off: listing and count responses use deterministic wording and rows, which
prevents model-invented records but gives up model-written grouping. Comparison
uses exact full titles, so ambiguous or partial names require clarification rather
than selecting a paper silently. Research holds a web worker and offers no live
planner steps in this slice, as IR-515 specifies.


Saved-turn overrides include `route_override_turn_id`. The owned Turn fixes the
original question, resolved question, scope choice and history boundary, so rerunning
an older follow-up does not resolve it against a newer paper. Cross-conversation
references return the same 404 as missing references. Listing and count Turns remain
reader-visible but are excluded from model history: this slice does not persist all
aggregate visibility/disclosure provenance needed to reuse their totals safely.
Ambiguous unquoted comparisons ask for explicit titles instead of silently omitting
an unresolved name. Quote each full title to compare available evidence while
reporting a missing paper.
