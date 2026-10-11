# Research planner — IR-512

**Implemented, offline only.** This is the single inner loop specified by
IR-512, built on IR-509/510's tool registry and IR-511's provider ports. It is
not connected to the Ask IRIS views. ADR-038 remains Proposed; this document
records implementation, not architectural approval or permission to merge.

`ResearchPlanner.answer(question, context)` returns a grounded answer, source
number-to-ledger-handle mapping, step telemetry, stop reason and validation
codes. The application supplies the user, Conversation, scope, disclosure
predicate and budgets through `RunContext`. The planner proposes one call at
a time; the registry validates arguments and executes the closed tool set.
`finish` has no arguments. Duplicate calls return the cached result and spend
a call. Malformed calls get one correction; a second ends planning.

`plan` has a separate profile and circuit breaker, inheriting the answer
model/account by default. `LLM_PLAN_*` can override it; naming a vendor stops
credential inheritance. Its fallback model list is independently configured.
Reasoning is off by default and never fed back to the planner. This slice
feeds tool results back verbatim. Recent history, planner notes, aggregate
context and the outer loop remain IR-513.

The run enforces the configured call, round, prompt-token and wall-clock
limits. Prompt tokens are estimated locally with the existing conservative
counter and reconciled upwards with vendor-reported planner usage. Synthesis
also charges its prompt. Provider timeouts are bounded by the remaining wall
clock, including Voyage retrieval. The ledger retains its configured number
of passages, dropping the weakest first. This inner-loop slice starts one
round; it does not reset a sub-task to evade its limit.

Evidence is fed through `GroundedAnswerService` using `LedgerRetriever`, so
numbered sources and `parse_citations` remain the answer path. Visibility and
disclosure are checked again before synthesis. Planner or tool failures and
spent budgets preserve evidence; absent passages fall back to the existing
pipeline. A successful `finish` with no passages returns `no_sources`. A spent
wall clock or synthesis-token budget cannot authorize another vendor call:
sources remain available with an unavailable answer and coverage note.

Raw answer validation runs before citation parsing can drop invented markers.
It checks citation numbers against the supplied source-to-handle mapping,
literal numbers against computed rows or cited passages, marked title spans
against the ledger, and completeness phrases against all successful results.
The research prompt requires titles to use `«exact title»`; quoted, italicized
and `titled ...` spans are checked too. These are literal checks, not semantic
claim verification: unmarked titles, paraphrased completeness and arbitrary
number wording are not guaranteed to be recognizable. Claim support remains
an offline measurement. The conservative implementation withholds the whole
answer on failure, reports reason codes, and retains the sources. Proposal
13's open D4 policy still requires human confirmation before merge.

`ResearchRun` and `ResearchStep` contain identifiers, argument digests, statuses,
latency and token counts; no question, tool arguments, passage, answer, planner
notes or reasoning text. Owner-only read access is
`GET /api/v1/ai/research/runs/<uuid>/`; unknown and other-reader runs both return
404. Staff have no special access. Deleting the Conversation or owner cascades
the audit. Nothing new is written to conversation history by this command.

To exercise the lane with the configured providers:

```text
python manage.py ask_agent "Do the studies on flooding agree?" --user student@cit.edu
```

`--conversation <id>` selects an owned Conversation and preserves Paper Chat
scope. Each step and the cited answer are printed. The command spends vendor
credits when providers are configured; CI uses scripted models and deterministic
embedding/reranking fakes. There was no paid planner run in this implementation.
