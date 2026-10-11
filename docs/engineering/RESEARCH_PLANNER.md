# Research planner — IR-512 and IR-513

**Implemented, offline only.** IR-512 supplies the grounded answer and audit;
IR-513 adds full context and outer planning around bounded sub-task loops,
built on IR-509/510's tool registry and IR-511's provider ports. It is
not connected to the Ask IRIS views. ADR-038 remains Proposed; this document
records implementation, not architectural approval or permission to merge.

`ResearchPlanner.answer(question, context)` returns a grounded answer, source
number-to-ledger-handle mapping, step telemetry, stop reason and validation
codes. The application supplies the user, Conversation, scope, disclosure
predicate and budgets through `RunContext`. The planner proposes one call at
a time; the registry validates arguments and executes the closed tool set.
The outer decision offers `plan_research` with one to ten nonempty short
sub-tasks, `finish`, and `continue_plan` when a task remains. The inner loop
offers the corpus tools and argument-free `subtask_done`. After each task,
the outer model checks whether the aggregate evidence answers the question;
it can finish after the first task, continue, or replace the remaining plan.
`finish` has no arguments. Duplicate calls return the cached result and spend
a call. Malformed calls get one correction; a second ends planning.

`plan` has a separate profile and circuit breaker, inheriting the answer
model/account by default. `LLM_PLAN_*` can override it; naming a vendor stops
credential inheritance. Its fallback model list is independently configured.
Reasoning is off by default and never fed back to the planner, including
leaked `<think>` text. Notes are the text accompanying a valid call, clipped
to 200 tokenizer tokens per note; they are labelled non-evidence, shown back
to planning, and excluded from synthesis, citations and the audit.

Every request is rebuilt from retained ledger passages and abstracts, recent
owned Conversation history (the existing token window and generated-state
predicate), computed tool results, notes and the latest call/result pair.
Passages and abstracts remain verbatim with their handles. No memory recall
runs, and no embedding is needed to make the initial plan. Visibility, fixed
scope and disclosure are rechecked before each planner request. Under the
owner-confirmed D6 policy, a history exchange with any currently restricted
or gated cited paper is omitted in full; a widened exchange citing another
paper also stays outside a fixed Paper Chat run. If exposed context loses
permission, its notes, plan and latest arguments are discarded. Content-bearing
computed results are withheld in full when one of their sources loses access.

The run enforces the configured call, round, prompt-token and wall-clock
limits. Prompt tokens are estimated locally with the existing conservative
counter and reconciled upwards with vendor-reported planner usage. Synthesis
also charges its prompt. Provider timeouts are bounded by the remaining wall
clock, including Voyage retrieval. The ledger retains its configured number
of passages, dropping the weakest first. The defaults are three outer plans,
four corpus calls per sub-task and ten calls per run. Control calls spend the
run-wide allowance; malformed inner calls also spend the sub-task allowance.
A full sub-task returns to the outer check. Continuing or replanning resets
only local calls, preserving the run's clock, prompt spend, call count and cache.

`AI_RESEARCH_CONTEXT_TOKEN_BUDGET` (16,000 estimated tokens) caps each complete
planner or synthesis request, including planner schemas. Within the cumulative
run ceiling, whole lowest-scoring passages are dropped until the request fits;
dropped content is never kept in an old tool message. Both passage-count and
token dropping append a deterministic coverage notice to the returned answer.
Non-passage context that cannot fit stops planning. If even the fixed synthesis
prompt cannot fit after exhaustion, generation is refused and sources remain
available. The counter is the existing conservative local estimate, not a
claim of exact vendor tokenization.

Evidence is fed through `GroundedAnswerService` using `LedgerRetriever`, so
numbered sources and `parse_citations` remain the answer path. Visibility and
disclosure are checked again before synthesis. Planner or tool failures and
spent budgets preserve evidence; absent passages fall back to the existing
pipeline. A successful `finish` with no passages returns `no_sources`. A spent
wall clock or synthesis-token budget cannot authorize another vendor call:
sources remain available with an unavailable answer and coverage note.

Raw answer validation runs before citation parsing can drop invented markers.
Bracketed references to notes or any label outside numbered sources are
invalid, including `[N1]`, `[planner_note]` and raw `[E1]` or `[R1]` handles.
Only source numbers mapped to retained ledger passages can resolve.
It checks citation numbers against the supplied source-to-handle mapping,
literal numbers against computed rows or cited passages, marked title spans
against the ledger, and completeness phrases against all successful results.
The research prompt requires titles to use `«exact title»`; quoted, italicized
and explicit unmarked introductions such as `the paper Imaginary Study`
are checked too. Leaked `<think>` reasoning is removed before these checks.
These are literal checks, not semantic
claim verification: unmarked titles, paraphrased completeness and arbitrary
number wording are not guaranteed to be recognizable. Claim support remains
an offline measurement. The implementation withholds the whole answer on
failure, reports reason codes, and retains the sources. The owner confirmed
this D4 policy in the IR-512 implementation chat on 2026-10-11: "Withhold the
answer (Recommended)". This confirmation applies to the validation-failure
policy; ADR-038's broader architectural approval remains outstanding.

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
