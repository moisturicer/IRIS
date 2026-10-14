# Proposed ADR-036 amendment: on-demand paper briefs (IR-556)

**Status: Proposed, not accepted.** This proposal does not amend the accepted
ADR-036 decision. Acceptance belongs to a human with architectural authority.
The implementation ships disabled through `AI_PAPER_BRIEFS_ENABLED=False`.

## Proposed contract

Add `brief` to the closed Inference task set. It inherits the complete `answer`
Profile: vendor account, model, ordered same-vendor fallbacks, endpoint pins and
no-training data policy. It has its own circuit breaker and returns structured
extraction without reader-facing reasoning. Independent `LLM_BRIEF_*`
configuration is refused; the main model remains the one chosen for answers.

A comparison first requests `brief_for(record, user=reader)`, or posts to
`/api/v1/ai/records/<id>/brief/`. This queues generation and returns `generating`;
repeating the request returns the current cached brief when ready. Explicit
`{"retry": true}` retries an unavailable generation. Indexing does not request
briefs. The existing AI Overview and its output stay unchanged. IR-549 owns the
comparison orchestration and its reader-facing presentation.

Each Record is read independently, from every undeleted active ChunkSet chunk
in sequence, with page markers. The fields are research question, data and
sample, method, evaluation, findings with reported numbers, stated assumptions
and stated limitations. Reported values carry exact supporting quotes and page
citations. Absent fields are `not_reported`; invalid or absent supporting
citations make the field `unsupported`, never an inferred finding.

The `answer` Profile gains explicit verified model context windows through
`LLM_ANSWER_CONTEXT_WINDOWS` (JSON map of model identifier to token capacity).
No capacity is guessed from a model name or inferred from chunk count. The
main model's window bounds each complete reading prompt; 4,096 tokens are
reserved for completion, including any
billable reasoning, and instructions/message framing are included in the
conservative UTF-8 input estimate inherited from shared admission. Before a
fallback's physical send, its verified window must also fit the complete prompt;
otherwise the attempt is refused without transmission. Brief fallbacks are
walked in application order, including on OpenRouter, so native vendor routing
cannot bypass these per-model checks. A missing fallback window does not refuse
the main-model call; it refuses only a later attempt to use that fallback.

A paper fitting one prompt is read once. Larger papers are read by extracted
section, subdividing oversized sections/chunks without dropping text. Each
section produces a verified brief. Their final combination is a lossless union
of verified values and citations, with duplicates removed. A second model
summary is unnecessary and could lose numbers or supporting quotes. A field is
`not_reported` only when every section explicitly reports it absent. The
Overview's `AI_OVERVIEW_TOKEN_CEILING` does not apply. Shared budget exhaustion
still returns `unavailable`; paper size alone is never the refusal criterion.

## Persistence, authorization and accounting

`PaperBrief` stores the Record, source ChunkSet and content hash, prompt version,
Profile fingerprint, actual generating model(s), section briefs, final fields
and usage. The fingerprint covers model chain, vendor, endpoint pins, data
policy and context windows, excluding credentials. Changes cause a new
on-demand reading; earlier versions remain stored until their source or Record
is deleted. A new ChunkSet also refreshes citation pointers even if its content
hash is identical.

Parent-row locks serialize first claims across readers. Publish happens after
commit on the same `embedding` queue as the Overview. A fresh UUID fences each
claim; one atomic start also suppresses duplicate worker deliveries. Before
every physical send (including internal retries/fallbacks) and the final write, current access for the requesting reader,
disclosure, active content and Profile are checked again. Every later cache use
checks the current reader. A cached brief confers no Record access.

Real generation requires `AI_PROVIDER_ADMISSION=enforce`. The existing stack
admits every physical attempt, retry and same-vendor fallback, charging the
`research` lane and a stable `brief:<brief id>` run across explicit retries. Stored input/output totals
include those attempts from `ProviderReservation`; unreported usage retains
conservative charges and is marked incomplete. Current-response model metadata
is observed separately from billing usage, so a response without token counts
still identifies its generating model. Deterministic unmetered fakes
report unknown usage, never a zero-cost claim. No vendor work is authorized by
this proposal or by its tests.

## Costs and operational limits

First use waits for background generation. Conservative byte sizing may create
more section calls than the model's actual tokenizer would require. The final
brief preserves all section values rather than promising a bounded summary
size. A worker crash after its start leaves a pending claim for operator
investigation; it is not automatically redelivered as potentially overlapping
paid work. Unavailable completed claims support explicit retries. Retention and
crash reconciliation can be designed separately if this workflow is accepted.

Production institutional disclosure still depends on IR-250, vendor/data
approval and the existing disclosure gate. Human acceptance of this proposal,
verified context metadata and approved shared admission limits are prerequisites
to enabling the feature. Human review remains separate from implementation.
