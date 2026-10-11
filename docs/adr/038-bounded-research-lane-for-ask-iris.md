# ADR-038: Ask IRIS gains a bounded research lane

## Status

**Proposed** — 2026-10-11 (IR-499). Drafted by an AI agent from [proposal 13](../architecture-review/13-bounded-research-agent-proposal.md) and the owner decisions recorded in its §Owner decisions — 2026-10-11, which **Jive Tyler Revalde** gave in a design review. **Awaiting approval by a named person.** The agent does not mark this accepted. Until a person records that approval in this file, nothing below is a decision, and **none of IR-500 (tool layer), IR-501 (screening and topic counts), IR-502 (planner, answer validation, run audit), IR-503 (Jev router and injection screen) or IR-504 (production rollout) may merge**.

**Supersedes [ADR-035](035-ask-iris-decides-whether-it-needs-evidence.md) §4 and §11 for the research lane only.** Everywhere else ADR-035 stands as written, including its Proposed IR-487 amendment, which this ADR neither accepts nor rejects.

**Amends** [ADR-036](036-openai-compatible-inference-provider.md) (three new Inference tasks, and a production approval for Jev's use in routing and screening), [ADR-027](027-corpus-level-questions.md) (topic counts), [ADR-026](026-conversational-retrieval-and-memory.md) §13 (history per consumer) and records on [ADR-028](028-no-tool-calling-in-the-answer-path.md) that its third revisit condition is still unmet. Each carries a dated amendment section pointing here.

**Reverses proposal 13 §3.2 principle 2.** The model that acts now also reads documents (§4).

## Context

### What exists, and what is missing

Ask IRIS finds **passages**. It cannot yet find, verify or count **papers**. A reader who asks "are there papers about aquaponics?", "how many?", "compare these three theses" or "do the studies on X agree?" gets a paragraph written from the top few passages. That paragraph is silently incomplete, and for a count it is wrong in a way the reader cannot see.

Proposal 13 diagnosed this and its conclusion is kept: most of these questions need **data operations written as application code**, not a model choosing tools. Only the open-ended multi-paper question ("which approaches to X disagree, and why?") needs a planner, because its next search depends on what the last one returned.

The owner decided on 2026-10-10 to build the bounded planner (option B in the proposal) and on 2026-10-11 how routing and the planner behave. This ADR records those decisions and the boundaries that make them safe to build.

### What blocks this today, and is not changed by it

- **The disclosure gate refuses every record in production** until IR-250 (the embargo field) lands. Every step that sends record text to a vendor therefore does nothing outside development. The lane is built and exercised under the development bypass.
- **There is no real corpus.** Every measurement available is on the 40-paper arXiv proxy. Nothing here may be reported as a finding about CIT-U research.

### ADR-035 §4 and §11, which this ADR supersedes for one lane

ADR-035 §4: a tool call is a route signal, recorded and never executed, with no agent loop. §11 puts adaptive retrieval, model-written search queries, any agent loop, a second tool and a new answer state out of scope. §2 bought the tool-calling port as **option value** and said plainly it was a bet. This ADR is that bet being taken, for one lane, under tighter bounds than ADR-028 ever considered.

### ADR-028's revisit conditions, assessed again

ADR-028 named three conditions that must all hold. ADR-035 assessed them on 2026-10-06 as: 1 holds, 2 partly holds, 3 does not hold.

| Condition | Now |
|---|---|
| 1. Retrieval is chunk-level | Holds, unchanged |
| 2. The recall harness has run on a real corpus | Partly holds, unchanged: the proxy corpus only |
| 3. A measured comparison shows an agentic loop beating the pipeline, including page precision | **Does not hold, and this ADR does not claim it does.** No loop exists to compare, and there is still no instrument for page precision |

**This ADR ships the lane before it is measured.** That is a decision to build ahead of the bar ADR-028 set, taken by a person, and it is stated here so nobody later reads the lane's existence as evidence that the bar was cleared. See §11.

## Decision

**Provenance, so the approver knows what to confirm.** Three kinds of content follow.

* **Owner decisions of 2026-10-11:** §3 (routing), §4.1 to §4.4 (the planner's view, aggregate context, two loops, no regenerate-until-a-judge-agrees), the numbers in §5, the history split in §7, the three tasks in §8, §9 (Jev), §10 (the residual risk) and the first paragraph of §11.
* **Carried from proposal 13, not decided by the owner:** the six-tool set and most of the §2 invariants beyond the owner's "unchanged, enforced in code" paragraph, §4.5 and §4.6, §5's duplicate-call cache and per-call timeout, §6's wording of screened counts, and the validators.
* **Added by the drafter:** the lane's off-by-default switch (§11), the deployment prerequisite (§11), the landscape reading (§3) and the choices marked as the drafter's in §Alternatives Considered.

The approver should confirm the second and third groups explicitly, because accepting this ADR as a whole accepts them. "Owner decisions 1–10" are numbered in proposal 13's section *Owner decisions — 2026-10-11*.

**Terms.**

* **Jev** is TypeSafe's decision model, reached through OpenRouter's Decisions endpoint. It writes no text and returns a probability for each question it is asked (ADR-036).
* **Handle** is a per-run label such as `R3` (a record) or `E7` (a passage). The model sees handles, never database ids.
* **Ledger** is the run's list of collected passages and records, each with its handle.
* **Uncertain band** is the range of Jev probabilities in which the router does not trust Jev alone and asks the LLM backup.
* **Completeness label** says how much of the corpus a result covers: `exhaustive`, `screened`, `matches_found` or `sample`.

**A worked example.** A reader asks *"how many papers are about aquaponics?"*. Routing sends it to the count route. The application counts the records the reader can see, screens them against the written criterion "is about aquaponics", and finds 7 matches among 112 screened, with 2 records it could not assess. The answer says "7 papers matched, out of 112 screened; 2 could not be assessed", labelled `screened`, and the application renders the list of 7. The model describes the list and cannot add an eighth. Had the reader instead asked *"do the studies on aquaponics agree on yield?"*, routing would send it to the research lane: the planner searches, reads the passages it gets back, replans up to 3 times, and the answer is written once from the passages it cited as `E1`, `E2` and so on.

### 1. A research lane exists, controlled by the application

A question may be routed to a **research lane**. In it, a **planner** model proposes tool calls, the **application** validates and executes them, and the results accumulate in an evidence ledger. The answer is written once, from that ledger, by a call that has no tools.

The lane is **a route outcome**, not a replacement for the grounded pipeline. Every other question, and every failure of this lane, goes to the passage pipeline exactly as it does today (§3.4, §4.6).

This supersedes ADR-035 §4 (nothing is executed; no loop) and §11 (no adaptive retrieval, no model-written queries, no agent loop, no second tool) **for the research lane only**. What stays out of scope everywhere: web search, a new answer state, and any tool outside the closed set in §2.

### 2. Invariants, enforced in code and tested

These are the lane's boundary. None depends on a prompt.

1. **Identity, scope, visibility, disclosure and limits come from the request, never from a model.** The application builds a run context from the authenticated user, the Conversation and settings. No tool argument can set or widen any of them.
2. **Visibility is one predicate.** `Record.objects.visible_to(user)` is applied inside every tool, before anything is scored or counted. No second visibility path is added. `test_one_retrieval_stack.py` and `test_outcome_indistinguishable_http.py` are extended to cover tool paths rather than given their own checks.
3. **The disclosure gate runs before any record content reaches a vendor,** on every tool path, including planning, screening and routing. Withheld evidence is indistinguishable from empty evidence (ADR-035 §7).
4. **Tools are read-only.** None writes, deletes or contacts anything outside the corpus. The tool set is closed: a name outside it is a malformed call.
5. **Tool arguments use handles issued in this run.** A model sees `R3` and `E7`, never a database id. A handle the run never issued is rejected, and a rejection is a monitored event.
6. **Counts and lists are computed in code** over `visible_to(user)` and rendered by the application. A model may describe rows. It may not add, remove or invent one (ADR-027 §4 and §9, applied to every lane).
7. **Every result carries a completeness label,** and the label, not the model, decides the wording (§6).
8. **A research question never reaches the ungrounded state** (ADR-034 §4). An empty ledger is `no_sources`. This is a test-backed invariant of every lane, including this one.
9. **Limits are enforced by the application** (§5). The model may propose to stop. It cannot continue past a limit.
10. **Citations resolve only to ledger handles.** A planner note is never citable (§4.2).

The tool set the lane starts with is **`search_passages`, `find_records`, `read_record_sections`, `count_records`, `screen_records` and `corpus_facets`**, as proposal 13 §4.3 describes them. Their contracts are IR-500's and IR-501's. This ADR fixes the boundary, not the signatures.

### 3. Routing

*Owner decisions 1–6.*

1. **Order.** Fixed phrase rules and logic checks run first. A Paper Chat Conversation stays on its paper.
2. **Jev is the main router.** One request to Jev's Decisions endpoint carries six named route questions (passage, listing, count, comparison, research, landscape) and one injection question. The highest-probability route wins.
   - **Whether one request may carry several questions is unverified.** The first task of IR-503 is one real call. If it is refused, the fallback is one call per question.
3. **An LLM backup** runs on a new `route` Inference task, which inherits `resolve`'s model by default. It runs when Jev fails (timeout, rate limit, malformed reply, unpinned build) **or** when Jev's best probability falls inside an **uncertain band**, which is a setting. The band's values are not chosen here.
4. **If everything fails,** the question goes to the passage pipeline. That is today's behaviour.
5. **Injection screening applies to the reader's question only.**
   - A flagged question skips the planner, is answered by the passage pipeline, and an audit event is logged.
   - If Jev is down, the backup asks the injection question too. If that also fails, the question is **treated as flagged.**
6. **The routing decision is shown to the reader and can be overridden** (ADR-027 §5).

Routing inputs follow the rule that the router sees **prior reader questions only** (§7). A route is a function of the question, never of what the gate withheld.

**Landscape.** This ADR gives the landscape route no new power. ADR-035 §9's rule stands: ordinary retrieval is not a landscape analysis, and no answer may claim a comprehensive landscape or a research-gap analysis from it. Until the Lens exists, a landscape-routed question is answered by the passage pipeline under that limit and never by the planner. *This is the conservative reading of an unchanged rule. The Jev router ticket (IR-503) confirms it with the owner.*

### 4. The planner reads documents

*Owner decisions 7–9. This reverses proposal 13 §3.2 principle 2.*

Proposal 13 separated a planner that sees only metadata from a synthesizer that sees passages. The owner reversed that: **the planner sees full context.**

1. **What the planner sees:** retrieved passage text, abstracts, and recent conversation history **including prior answers**. It does **not** see memory-recalled Turns.
2. **Aggregate context.** The planner works from the passages collected so far, verbatim with their handles (`E1` and on), plus **short planner notes** written in the same turn as a tool call. **Notes are a scratchpad and can never be cited.** Citations resolve only to handles.
3. **Two loops.**
   - An **outer loop**: plan, run sub-tasks, replan, then ask "is this answerable from the aggregate context?" and either finish or replan.
   - An **inner loop** of tool calls within each sub-task.
4. **No step regenerates the answer until a judge agrees.** The reference repository's regenerate-until-the-judge-agrees loop is not adopted (proposal 13 §11).
5. **The answer is written once, by a call with no tools,** from the ledger, through the existing grounded answer path. After it, deterministic checks run: every marker resolves to a handle, every number appears in a computed row or a cited passage, every named record is in the ledger, and completeness wording matches its label. *This is carried from proposal 13 §4.6 and was not part of the initial owner decisions. The subsequent human confirmation of D4 in the IR-512 implementation chat chooses whole-answer withholding on validation failure, retaining the gathered sources and reason codes (§12).* Whether a cited passage actually supports its sentence is **not** checked at runtime and is not claimed.
6. **Failure behaviour.** A malformed call gets one corrective message and a second ends planning. A tool or provider failure ends planning and hands the ledger to the answer call. An exhausted budget answers from the ledger with a coverage note that says the run stopped, not that nothing exists. An empty ledger is `no_sources`. A planner that is unavailable falls back to the passage pipeline. "Insufficient evidence" is a coverage note on a grounded answer, not a new answer state.

### 5. Limits

*Owner decision 10.* All are settings, enforced in code.

| Limit | Value |
|---|---|
| Outer loop rounds | 3 |
| Tool calls per sub-task (inner loop) | 4 |
| Tool calls per run | 10 |
| Wall clock per run | 90 s |
| Prompt tokens per run | about 120k |
| Passages in the ledger | 30, weakest dropped first |

A repeated `(tool, arguments)` pair returns the cached result marked `duplicate` and still counts against the budget. Each vendor call receives `min(per-call timeout, time left)`. Setting names and per-call timeouts are chosen by the implementing tickets. Because `generate` and `stream` carry no explicit timeout today, adding one is part of the planner ticket (IR-502).

### 6. Counts and lists — ADR-027 amended

ADR-027 defines counts over named Areas only. This ADR adds:

- **A metadata count is exact.** A database predicate (classification, PSCED, record type, year, IP flag), computed as `COUNT(DISTINCT id)` over `visible_to(user)`. The wording is "of the records you can see", because every count is relative to the asker (ADR-027 §3).
- **A topic count is a screened count,** never an exact one. It is find, screen against a written criterion, de-duplicate, count. It is computed in code from the screening results and carries a label: `exhaustive` (every visible record was screened), `screened`, `matches_found` or `sample`. The answer says how many were screened and how many could not be assessed, and it never says "there are N".
- **Counts are never taken from top-k retrieval or from chunks.** They count distinct `record_id`s. Possible duplicates are reported, never silently merged.
- **A record the reader can see but the gate refuses is never sent to a vendor.** D3 was confirmed in the IR-501 implementation chat (§12): a selected candidate is counted as `unassessed`. No withholding reason or individual gated record content appears in a model request or result. This is the same unassessed total used for provider failures, missing replies and insufficient evidence, and never depends on *why* a record was withheld (ADR-035 §7).
- **The model reports rows and never extends them,** which is ADR-027 §4 and §9 applied to counts of papers.

### 7. History is per consumer — ADR-026 §13 amended

ADR-035 §8 began making §13's single predicate per-consumer. This ADR continues it.

| Consumer | Sees of the Conversation |
|---|---|
| Router (Jev and the `route` backup) | Prior **reader questions** only. No prior answer, no recalled Turn, no Passage text. Unchanged from ADR-035 §8 |
| **Planner** | Recent history **including prior answers**. No memory-recalled Turns |
| Answering model | As §13 and ADR-035 already allow |

What "recent" means follows the existing history window by token budget (`apps/ai/history.py`). The planner's view is asserted on the request actually sent, as IR-465 does.

**A contradiction is recorded, not hidden.** ADR-035 §8 withheld prior answers from a routing decision because a grounded answer is retrieval-derived and can echo text injected into a Passage. The planner is a different consumer and the owner chose to show it those answers. The reason for withholding still applies to the planner. It is accepted as part of the residual risk in §10, not argued away.

### 8. New Inference tasks — ADR-036 amended

The closed set grows from four (`answer`, `resolve`, `summary`, `describe_figure`) to seven.

| Task | Does | Notes |
|---|---|---|
| `plan` | The planner's tool-calling turns | Needs the `ToolCallingLLM` port. The model and vendor are the planner ticket's (IR-502) to choose |
| `screen` | Per-record include or exclude judgements against a criterion | Highest call volume. Model and vendor are the screening ticket's (IR-501) to choose |
| `route` | The LLM backup in §3 | **Inherits `resolve`'s model by default** |

Each gets a Profile (vendor, model, ordered same-vendor fallbacks, reasoning visibility, the uniform no-training data policy) as ADR-036's 2026-09-28 amendment requires. `CompositionRoot.llm_for(task)` stays the only way to reach a model. A task with no configured model reports unavailable rather than borrowing another's, as `summary` does.

### 9. Jev's production approval for routing and question screening

*Supersedes the IR-487 ADR-036 change for these two uses.* Accepting this ADR is a person's act that approves **TypeSafe's Jev, reached through OpenRouter's Decisions API, for routing and for screening the reader's question, and for nothing else.**

| Fact | Status |
|---|---|
| Training | **No training or fine-tuning on input.** Accepted by the owner on IR-485 |
| Retention | **Unstated** by TypeSafe. The owner's rule is that retention is acceptable provided no model trains on the data. Zero retention is not required |
| Hosting | US-hosted |
| Endpoint | **Alpha.** A shape change is a malformed reply and routes as a failure. The rate limit is unstated and unmeasured under reader traffic |
| Pinning | `typesafe/jev-1.13`. The `~typesafe/jev-latest` alias is refused, and a served build that differs from the pin is a failure |

- **The approval switch defaults to off.** When it is off, or Jev fails for any reason, Jev is treated as down: the `route` backup decides, and the backup asks the injection question too (§3.5). The switch is a person's act and is never inferred from a configured API key. Its name is IR-503's to choose.
- **What Jev receives:** the reader's question, at most five prior reader questions and a fixed corpus description. No Passage, no recalled Turn, no prior answer, no identifier.
- **The `route` backup's vendor must meet the same rule.** Groq has no no-training terms recorded in the repository and is not approved for it. A `route` task that resolves to Groq is approved separately or moved.
- **Approved here:** reader questions to Jev. **Not approved here:** the evidence-decision uses in the IR-487 amendments to ADR-034, ADR-035 and ADR-036, which stay Proposed.

### 10. Residual risk: documents are not screened for injections

**Recorded plainly, because the owner chose it.**

Passage text and prior answers reach the planner with only the code invariants of §2 in front of them. A document or a prior answer can carry an instruction.

- **What a planted instruction can do:** misdirect searches inside the reader's own visible papers, or skew the wording of an answer.
- **What it cannot do:** read another user's records, widen scope, bypass the gate, write anything, or cite a note. Those are §2's invariants and they do not depend on the model behaving.
- **Chunk screening is deferred to IR-505.** Until then the planner is bounded by the invariants only.

Also recorded, not solved:

- **Timing.** An agent adds steps, so more timing signal about gate work (ADR-035 §7). Narrowed, not closed.
- **Query egress.** Each search embeds a model-written query at Voyage. The text is derived from the reader's question and is ungated, as the question is today. Volume rises.
- **Prior answers are not re-gated** if a cited record later becomes restricted. The planner carries more of them (proposal 13 D6, open).
- **Counts are inference channels** (ADR-027 §3). Per-user counts are safe by construction. Any cached or cross-user aggregate is not, and none is authorised here.

### 11. The design ships before it is measured

*Owner decision.* Evaluation, shadow mode and the ADR-023 amendment are the deferred evaluation ticket (IR-505). That removes proposal 13 §9's phase-2 gate ("the planner beats the workflows, with no page-precision loss") as a precondition for building the production planner.

What that does and does not mean:

- **The lane ships behind a setting that is off by default** *(the drafter's addition, not an owner decision)*, which keeps ADR-033 §5's rule that a technique is off until a harness run turns it on. Turning it on for readers is the production rollout ticket's (IR-504) and needs a person's approval. This ADR sets no threshold for it.
- **Nothing may be claimed** that the planner beats the pipeline, that it preserves page precision, or that any number says something about CIT-U research. The corpus is a 40-paper arXiv proxy (ADR-023).
- **The first measurement will be of a thing already built.** If it shows the lane does worse than the workflows alone, the switch is the rollback, and the passage pipeline, which no part of this ADR modifies, is what remains.
- **Deployment.** A planner run is up to 90 s. Under WSGI, a handful of concurrent runs would stall the four workers. *Carried from proposal 13 §9, not an owner decision:* ASGI (ADR-017) or running the planner in a Celery worker should be in place before the lane is turned on, and choosing between them is proposal 13 D8, open (§12).

### 12. Open decisions and subsequent confirmations

| Decision | Owner |
|---|---|
| Landscape route handling until the Lens exists: confirm §3's reading | Jive Tyler Revalde |
| ASGI against worker offload for long runs (D8) | Jive Tyler Revalde |
| The uncertain band's values, and the `plan` and `screen` models | Chosen by IR-503, IR-502 and IR-501 |
| Who approves this ADR | A named person, recorded in this file |

**D4 confirmation — 2026-10-11.** In the IR-512 implementation chat, the
human user selected **"Withhold the answer (Recommended)"** when asked whether
an unsupported number, title, citation or completeness claim should cause
whole-answer withholding or removal of the offending text. The confirmed
policy withholds the whole answer, reports validation failure and keeps the
gathered sources available. This is recorded with [IR-512's implementation
PR](https://github.com/moisturicer/IRIS/pull/234). It confirms this policy only;
the ADR remains Proposed and its named approval and merge gate are unchanged.

**D6 confirmation — 2026-10-11 (IR-513).** In the IR-513 implementation chat,
the human user instructed **"do what you recommend"** after a plain-language
explanation of the recommended history policy and its cost: omit an entire
recent question/answer exchange if any cited paper is now unreadable, outside
the fixed Paper Chat scope, or refused by disclosure. This avoids resending
restricted content but can lose context for follow-ups. The approved design
and test boundaries are recorded in
[IR-513's design](../superpowers/specs/2026-10-11-ir-513-research-context-design.md).
The planner rechecks history, passages and abstracts before each request;
notes and plan text derived from a context that loses permission are cleared.
This confirms D6 for the research planner only; the existing chat views are
unchanged, and the broader ADR approval and merge gate remain outstanding.

**D3 confirmation — 2026-10-11.** In the IR-501 implementation chat, the
human user selected **"Report them as unassessed, with no reason shown
(Recommended)"** after receiving a plain-language example: 7 matches among
90 checked papers and 10 unassessed papers. The approved design tests the
registered screening tool and application count workflow, including captured
scripted-provider requests. Gated candidates are never keyword-screened or
silently omitted. This confirms D3 only; the ADR remains Proposed and its
broader named approval and merge gate are unchanged.

## Alternatives Considered

**A. Workflows only, no planner.** Application code runs fixed workflows for presence, listing, counts and comparison, and the open-ended research question gets the passage pipeline. *Gain:* cheap, deterministic, testable now, and it is what proposal 13 recommended first. *Cost:* it misses the question whose next search depends on the last result, which is the case the owner wants served. **Not rejected: the workflows are built anyway** (IR-500, IR-501), and the planner calls them as tools.

**B. A planner that sees metadata only, a synthesizer that sees passages.** Proposal 13's original design. *Gain:* an instruction hidden in a document could reach only the answer call, which has no tools, and the planner only through length-capped titles. *Cost:* the planner cannot judge whether a result answered the question, so it either over-searches or stops blind, and a full-context planner replans better. **Reversed by the owner on 2026-10-11** (decision 7: the planner sees full context). Its injection benefit is given up and recorded in §10.

**C. A free agent loop, as in the reference repositories.** The model chooses tools, assembles its own context and loops until a judge agrees. *Gain:* fastest to demonstrate. *Cost:* the model builds the evidence it answers from, so counts and lists are unsafe, no per-technique measurement is possible, and the loop is bounded only by a recursion limit. This is what ADR-028 warned about. **Rejected** (the drafter's judgement; no owner decision considers it).

**D. Measure first, build second.** Keep proposal 13's phase-2 gate: build the planner offline, show it beats the workflows, then productionise. *Gain:* no capability ships on a hunch, and ADR-028's third condition is met before the lane exists. *Cost:* the thesis timeline pays for the measurement before anything usable exists, and the measurement is cheaper once there is something to measure. **Not taken, by the owner's decision that the design ships before it is measured.** The compensation is that the lane is off by default and the measurement is IR-505.

**E. Regenerate the answer until a judge agrees.** *Gain:* looks like verification. *Cost:* it is bounded by nothing but the loop limit and accepts whichever draft the judge tolerates. **Rejected** (§4.4; the owner's decision 9 rules out regenerating until a judge agrees).

**F. Reuse the `answer` task for planning, screening and routing.** *Gain:* no new tasks. *Cost:* the three have different volume, tool needs and vendor terms, and ADR-036 chose one Profile per task so each can be tuned and switched off alone. **Rejected** (the drafter's judgement; the owner's decisions name the three tasks).

## Decision Rationale

The decision is narrow once the invariants are in place. The planner is a model that proposes; the application owns identity, scope, visibility, the gate, limits and every count. Whatever the planner reads, what it can *do* is bounded by §2, and none of §2 depends on its behaviour.

Three choices need their reasons stated, because each looks like a lapse.

- **Reversing the metadata-only planner** trades an injection mitigation for answer quality. The owner made that trade deliberately, so §10 records the cost rather than softening it.
- **Shipping before measuring** goes against ADR-028's third condition, which asked for a measurement that would overturn it. The honest account is that it is overturned by a decision, not by evidence, and the off-by-default switch is what stops that from becoming a reader-facing claim.
- **Approving Jev for routing** uses a vendor whose retention is unstated and whose endpoint is alpha. The owner's rule is no-training, and the failure path is to a model already approved, ending at today's pipeline. A Jev outage costs routing quality, not availability.

## Consequences

- **Positive.** Presence, listing, counting and comparison questions get answers whose completeness the code can state. The open-ended research question gets a bounded multi-step search. Every limit and boundary is a setting or a test, not a prompt.
- **Positive.** The `ToolCallingLLM` port ADR-035 §2 bought is exercised by a real consumer.
- **Negative.** Roughly 3 to 10 times the model calls and latency of one grounded answer on a research question [proposal 13's estimate, unmeasured here], plus three new Inference tasks, a run-audit model and a tool layer.
- **Negative.** The planner reads untrusted text with only code invariants in front of it (§10).
- **Risk — the lane is worse than the pipeline.** Nobody has measured it. The switch and the unchanged pipeline are the mitigation, and IR-505 is the measurement.
- **Risk — a count over-claims.** The label decides the wording, and the validator checks it, but the screening judge's accuracy is unmeasured.
- **Risk — WSGI saturation.** A hard prerequisite for turning the lane on (§11).
- **Known limitation.** The disclosure gate refuses every record until IR-250, so nothing here reaches a reader in production until that lands.

## MVP Impact

**A real capacity cost.** Proposal 13 §13 estimates 25 to 35 person-days of shared work, 20 to 30 for corpus workflows and 15 to 25 for agent-specific work, ±50%, before review and before IR-250 and IR-278. ADR-001's budget has been reversed four times already. Under `CLAUDE.md`'s Scope rule, RAG is thesis-critical and protected, so the displacement falls on supporting frontend work and the Lens, the unbuilt whole-collection feature (IR-302 to IR-305), which this ADR then has to cover with the §3 limit on landscape questions.

## SaaS Impact

Per instance, under [ADR-005](005-instance-per-tenant.md). The lane switch, every limit, the Jev approval and the uncertain band are per-deployment settings. A deployment that changes nothing keeps today's behaviour, with no Jev call and no planner. There is no tenant column, so isolation is the instance boundary, and the cross-tenant tests are deployment tests.

## Security Impact

**Net neutral on authorization, a real increase in exposure to injected text.** The invariants in §2 carry the weight and are enforced in code.

- Authorization is unchanged: one visibility predicate, handles in place of ids, the gate before every vendor call, and read-only tools.
- **Two new vendor flows:** reader questions to Jev, and passage text and prior answers to the `plan` vendor. Passages pass the gate. The question and history do not, as today. This changes `docs/security/SECURITY.md` §8 and §11, which describe reader questions as ungated, and **that file is not updated by this ADR.**
- The authorization tests proposal 13 §7.2 lists must exist before any tool merges: another user's draft never appears in a tool output; an office user and a student get different counts; an unissued or raw-id handle is rejected; Paper Chat's scope cannot be widened by a tool; the gate runs before every vendor call by request capture.
- Logs carry run ids and reason codes, not question, passage or reasoning text.

## Deployment Impact

No new service. New Inference task Profiles and settings, a run-audit table with its migration (same privacy and retention as a Conversation under ADR-026 §11), and a decision on ASGI or worker offload before the lane is turned on. ADR-017's ASGI deployment is not built. Rollback is the lane switch, then the Jev switch.

## Research Impact

Thesis-critical under [ADR-013](013-chunk-level-rag-pipeline.md) §Research Impact, and the defensible claim is a method claim.

What is presentable: a researched rejection (ADR-028) was assessed condition by condition and overturned by a stated decision; the lane's boundaries are code invariants rather than prompts; counts carry completeness labels; and the cost of every reversal is recorded, including the one that gave up the metadata-only planner.

What may **not** be claimed: that the planner beats the pipeline, that page precision is preserved, that ADR-028's third condition is met, that screened counts are exact, or that any proxy-corpus number describes CIT-U research.

## Related Requirements

FR-M4, FR-M4-01 (RAG chatbot) · NFR-R2 (graceful degradation) · NFR-S4 (no unauthorized disclosure) — **stable labels only**, per the frozen-SRS rule. This ADR is the requirements authority once accepted.

## Related Tasks

**This ADR:** [IR-499](https://citiris.atlassian.net/browse/IR-499) — research lane 1/6.

**Proposal:** [IR-497](https://citiris.atlassian.net/browse/IR-497) — [proposal 13](../architecture-review/13-bounded-research-agent-proposal.md).

**Blocked on this ADR being accepted:** [IR-500](https://citiris.atlassian.net/browse/IR-500) (tool layer) · [IR-501](https://citiris.atlassian.net/browse/IR-501) (screening and topic counts) · [IR-502](https://citiris.atlassian.net/browse/IR-502) (planner, answer validation, run audit) · [IR-503](https://citiris.atlassian.net/browse/IR-503) (Jev router and injection screen, with LLM backup) · [IR-504](https://citiris.atlassian.net/browse/IR-504) (production rollout).

**Deferred:** [IR-505](https://citiris.atlassian.net/browse/IR-505) — evaluation, shadow mode, the ADR-023 amendment, chunk injection screening.

**Elsewhere:** [IR-250](https://citiris.atlassian.net/browse/IR-250) (the embargo field the gate waits on) · [IR-278](https://citiris.atlassian.net/browse/IR-278) (a real corpus) · [IR-485](https://citiris.atlassian.net/browse/IR-485) and [IR-487](https://citiris.atlassian.net/browse/IR-487) (Jev's vendor terms, and the proposed amendments this ADR partly supersedes) · IR-302 to IR-305 (the Lens, unbuilt).
