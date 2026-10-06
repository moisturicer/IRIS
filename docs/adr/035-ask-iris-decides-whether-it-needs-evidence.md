# ADR-035: Ask IRIS decides whether it needs evidence

## Status

**Proposed** — drafted 2026-10-06 (IR-461). **Not accepted.** No human review has taken place and none is claimed.

**This is a governance gate.** IR-464 (the deterministic detector) and IR-466 (the reader-invisible shadow pilot) are blocked on this ADR being *approved*, not merely drafted, because both contradict [ADR-028](028-no-tool-calling-in-the-answer-path.md) as it stands. An agent may draft this document. An agent may not approve it.

**Supersedes [ADR-028](028-no-tool-calling-in-the-answer-path.md)'s decision, and preserves its reasoning in full.** ADR-028 exists so that "expose retrieval as tools" is not re-proposed without new evidence. That service is still being done: its four reasons, its evidence table and its three revisit conditions are **kept, not overwritten**, and §Context below assesses each revisit condition as holding, partly holding or not holding. This ADR proceeds on the first condition plus a design argument — **not** on the third, which has not been met.

**Amends [ADR-034](034-ungrounded-answers-as-a-distinct-state.md) §2.** Withheld evidence does not affect the route. ADR-034's §Security Impact claim that distinct states keep a refusal indistinguishable from "nothing exists" was **already corrected in that file by IR-460**; this ADR carries the §2 amendment that makes the correction a rule about routing rather than only about the response boundary. See §7.

**Amends [ADR-026](026-conversational-retrieval-and-memory.md) §13.** The evidence decision is a new consumer of a Conversation's history with its own, narrower rule, which §13's single predicate does not describe. Implemented by IR-465, specified here. See §8.

**Amends [ADR-027](027-corpus-level-questions.md) §4.** Its obligation binds a question *"routed as corpus-level or landscape"*, and §5's router does not exist, so **§4 is dormant, not satisfied**. This ADR records a time-limited landscape exception with a named expiry. See §9.

## Context

### What is being decided, and what is not

Ask IRIS retrieves corpus Passages for every message and then instructs the model to answer only from them. Nobody has established whether a given question needs corpus evidence at all — it is assumed, and the model is then forbidden from answering without it. The visible failure is in ADR-034's §Context: a reader asks the colour of the sky and gets a sentence about not finding sky colour in a tilapia-ponds paper.

This ADR records the decision that **Ask IRIS decides, before retrieval, whether the question requires evidence** — and the mechanism by which the model is asked.

**It does not ship that behaviour to a reader.** Phase 0 (IR-456) builds the decision, records what it would have decided, and changes no answer anyone sees. Production `on` is a separate approval on a measurement (§11).

### What ADR-028 decided, and which of its revisit conditions hold

ADR-028 rejected tool calling on four grounds, in its order of weight: (1) the agentic trade buys answer accuracy by giving up page-localisation precision, which is the wrong trade in a system built for citations; (2) retrieval was the bottleneck and IRIS's retrieval did not work; (3) a tool-calling router is less accurate than the deterministic one it would replace (~77% on BFCL-v2); (4) collapsing routing, resolution and decomposition into one model decision would leave ADR-023 nothing to switch off and compare.

It named three revisit conditions, all three of which it said must hold.

| ADR-028 revisit condition | Assessment, 2026-10-06 |
|---|---|
| **1. IR-283 is live, so retrieval is genuinely chunk-level** | **Holds.** `apps/ai/composition.py` assembles two-stage chunk retrieval, `/ai/ask/` and `/ai/search/` answer from Passages, and chunk vectors are computed (IR-281). Reason (2) above — "retrieval does not work" — no longer describes the system |
| **2. ADR-023's recall harness exists and has run against a real corpus (IR-278)** | **Partly holds.** The harness exists and has run: recall@10 0.712 without reranking, 0.885 with, on the proxy tier (run `20260930-182254`). But the corpus is the **40-paper arXiv proxy**, never CIT-U data. IR-278 is not done, and the disclosure gate still refuses every record until IR-250 |
| **3. A measured comparison on that corpus shows an agentic loop beating the pipeline, and shows whether the page-precision loss appears in this data** | **Does not hold.** No such comparison has been run. No agentic loop exists to compare |

**This ADR therefore proceeds on condition 1 plus a design argument, and says so rather than implying the bar was cleared.** ADR-028 was explicit that only a measurement should overturn it. What is being overturned here is narrower than what ADR-028 rejected — one no-argument decision call, no loop, no model-written query, nothing executed (§4) — and the thing being bought is option value, not accuracy (§2).

### ADR-028's central objection cannot currently be tested

ADR-028's first and heaviest reason is that agentic retrieval costs page-localisation precision: agentic rephrasing "retrieves relevant but different pages". **IRIS has no instrument that can confirm or refute that.**

`apps/ai/evaluation/labels.py` scores a hit as **record identity plus normalised quote containment**. The page is carried on every label and reported in every run, and it is **deliberately never scored** — a chunk can span a page boundary and re-chunking moves page attribution, so requiring the page would fail labels that are correct. That is a good decision for the harness, and it means the one cost ADR-028 weighted most heavily is unmeasurable with what exists.

Recorded, not resolved: **page-precision measurement has no instrument and is out of scope for IR-456.** Nobody may later claim the page-precision objection was answered. It was not; it was set aside, and this is the record of that.

### What IR-462 measured

IR-462 (`docs/evaluation/spikes/ir462-findings.md`) compared **how the model is asked** — a native tool call against a structured JSON route label — on the configured model (`openai/gpt-oss-120b` on Groq), 44 labelled questions, three runs per configuration, reasoning medium and low, 528 calls.

| | Native tool call | Structured route label |
|---|---|---|
| Accuracy (parsed, medium reasoning) | 1.00 / 1.00 / 1.00 | .952 / .976 / .976 |
| Missed searches (the costly error) | 3 of 66 | 6 of 66 |
| Over-searches | 6 of 66 | 4 of 66 |
| Latency mean / p95 | 0.72 / 1.62 s | 0.51 / 0.66 s |
| Malformed output | 0 | 0 |

**The spike's own recommendation was the route label, and this ADR does not follow it.** That divergence is the most important thing in this section, and §2 gives the reason.

Its limitations, which bound every number above:

- **44 synthetic questions, one labeller.** One question is 2.3 accuracy points. The gap between mechanisms is a handful of questions and **is not established**.
- **Decisions flipped between runs on 6–11 of 44 questions in every configuration.** One run proves nothing; three runs bound the noise rather than removing it.
- **34 of 528 calls (6.4%) were lost to Groq rate limiting** after six retries. A production decision call must treat a vendor 429 as a normal outcome.
- **Prompts were written once and tuned for neither mechanism.** A tuned route prompt may close the missed-search gap.
- Both mechanisms sat far above the ~77% tool-calling figure ADR-028 cited, which weakens ADR-028's reason (3) **on this model for this one narrow decision** and says nothing about tool calling in general.
- One finding survives both mechanisms: `s02` — *"what does the training loop do with a problem the model has not managed to solve yet?"* — routed to "answer" in all three route runs. A mechanism question phrased with no repository vocabulary is the case **neither** the model nor the deterministic detector catches.

## Decision

### 1. Ask IRIS decides whether it needs evidence, and in Phase 0 the decision is recorded and nothing else

Before retrieval, the system establishes whether the question requires corpus evidence. A question that requires it retrieves exactly as today. A question that does not **could** be answered directly — and in Phase 0 never is.

The setting accepts `off | shadow`. **`on` is rejected as an invalid value**, not merely unimplemented, because a mode a parser accepts is one somebody enters by accident. Default `off`, sample rate default zero, registered in the technique registry (`apps/ai/evaluation/techniques.py`) so it is separately switchable for measurement under ADR-033 §5's convention.

### 2. The mechanism is native tool calling — chosen for option value, against the spike's recommendation

**The model is asked by being offered a `search_corpus` tool and reading back whether it called it.** Not a structured JSON route label.

**The spike recommended the route label and this ADR overrules that recommendation. The reason is not accuracy.**

- **The measurement does not separate the two mechanisms.** On 44 synthetic questions with one labeller and 6–11 decisions flipping between runs, neither the accuracy difference nor the missed-search difference is established. Nobody may cite this ADR as evidence that tool calls route more accurately. They may not.
- **Where the measurement does separate them, the route label wins.** Tool calls were about 0.2 s slower at the mean and **1.62 s against 0.66 s at p95**. That is a real, measured cost being accepted, not a tie being resolved.
- **What is being bought is option value.** If IRIS later adopts bounded, multi-step tool use — a second tool, a Lens call, a figure lookup — a provider port that already carries tools and tool-result turns is the starting point, and a bespoke JSON route protocol is a thing to delete and replace. Choosing the mechanism that extends rather than the one that would be thrown away is the whole argument. **It is a bet on a future this ADR does not commit IRIS to**, and if that future does not arrive the bet cost ~0.2 s of decision latency on a path no reader is on in Phase 0.
- **ADR-028's port objection is answered by what the call carries, not by denying it.** ADR-028 is right that tool calling needs a message list and tool-result turns, and that this weakens the `system`/`user` separation that keeps injected Passage text from outranking the system prompt. The mitigation is structural: **the decision call receives no Passage text, no recalled Turns and no prior assistant answer text** (IR-465). The grounded answer path keeps `generate(system, user)` unchanged. So the widened port exists on a call with no retrieved text in it, and the call that does carry retrieved text keeps the narrow port. Asserted on the request actually sent, not argued.
- **Reasoning stays as configured.** IR-462 found reasoning did not materially move latency or tool-call reliability (~0.05–0.07 s; accuracy differences within noise). The decision reuses the existing `answer` Inference task unchanged. **No fifth task and no per-call reasoning override**, and ADR-036 is not amended.

Every malformed shape routes to requiring evidence, each with its own reason code: unknown tool name, malformed arguments, several calls, empty completion, text and a tool call together, timeout, and a vendor rate limit. **A 429 is a normal outcome, not an exception** — 6.4% of the spike's calls were lost to one.

**Model-supplied arguments are never read.** The tool declares no parameters, and IR-462 found that 62 of 63 search calls carried a model-written `query` anyway — the norm, not an edge case. A parser that rejected them would fail nearly every search. Their presence is recorded as an anomaly and the call still routes to evidence, which is what a well-formed call produces.

### 3. The union rule

**Retrieval happens when either the deterministic detector demands it or the model asks for it. A direct answer requires both to permit it.**

Stated as the two halves that matter:

- **Either can require evidence.** Neither can authorize a direct answer alone.
- **On malformed output, failure, timeout, rate limit or uncertainty, the fallback is retrieval.** The expensive error is a question that needed passages being answered without them; the cheap error is a pointless retrieval. The asymmetry is deliberate and the default always falls to the cheap side.

### 4. `search_corpus` is a route signal, never an instruction

In Phase 0 and in the shadow pilot, a tool call the model emits is **recorded and not executed**.

- No second retrieval. Retrieval already ran in-request on the same Resolved question.
- No passages are passed back to the decision model. There is no second turn.
- **No agent loop.** One call, one route.

Nothing is lost by not executing it: the tool takes no model-written query, so a second search would return what the first returned. Running it would spend embedding and reranking credits on a result nobody reads, and would touch the corpus from a path that is meant to be inert.

### 5. The detector is defense in depth, not a classifier

The deterministic half (IR-464) is five rules emitting five reason codes, so an error is attributable per rule rather than in aggregate: `scope_record` (structural and reliable), and `institution_term`, `document_reference`, `sourcing_demand`, `aggregate_shape` (lexical and leaky).

- **It runs on the raw question and on the stored Resolved question, combined by OR.** A rewrite must never be able to weaken an evidence requirement, and the Resolved question is **untrusted input** — produced by a resolver that reads prior assistant answers, which are retrieval-derived and may carry text injected into a Passage. Where the two disagree, the requirement stands.
- **No claim is made that it guarantees correct routing.** It will miss paraphrases and it will over-fire. `s02` in the spike is the shape it cannot catch.
- **A high-recall rule may add retrieval. It may never drive a refusal.** Over-firing costs one retrieval; a refusal costs a reader an answer.
- **There is deliberately no restricted-evidence rule.** Restricted material is protected by `Record.objects.visible_to(user)` and ADR-015's disclosure gate, never by a word list.
- Institution and Area terms are settings under the instance-per-tenant posture, **read at startup, not per request**, and Django refuses to start when the list is empty and the decision is enabled — so disabling a rule requires turning the feature off rather than blanking a string.

### 6. The application owns identity, scope, authorization, visibility and disclosure — the model cannot supply or widen them

The model's output is a route. It is never a parameter to a protected operation.

- **Identity and authorization are the request's**, taken from the authenticated user, never from anything the model emits.
- **Scope is the Conversation's.** A Conversation bound to a Record is Paper Chat, and the model cannot unbind it.
- **Visibility stays one predicate applied inside retrieval** — `Record.objects.visible_to(user)` — exactly as `CLAUDE.md` requires and IR-285 enforced. The decision adds no candidate source and no second visibility path.
- **ADR-015's disclosure gate is unchanged and is not consulted for routing** (§7).
- **The AI Overview is excluded by construction**, not by a flag: the orchestrator is used by the two chat views only, and "summarise this paper" is document-specific by definition. The semantic search endpoint generates no answer, so there is no decision to make.

### 7. Withheld evidence does not affect the route — ADR-034 §2 amended

**ADR-034 §2's last clause said a question whose passages were all withheld by the disclosure gate is `no_sources` rather than `ungrounded`, and §Security Impact argued that keeping the states distinct keeps a refusal indistinguishable from "nothing exists". That argument did not hold as written**, and the correction already stands in ADR-034's own §Security Impact under IR-460: under that design nothing-found yields a general answer and everything-withheld yields a refusal, so **a refusal would itself be a one-bit signal that something was withheld**.

This ADR makes the correction a routing rule:

> **The route, the reader-facing response and the answer state are a function of exactly two things — whether any Passage was kept, and whether the question carried an evidence requirement — and never of *why* nothing was kept.**

`empty`, `withheld_all` and `none_relevant` (`apps/ai/retrieval/diagnostics.py`) are **one case to a reader**, and the retrieval outcome is diagnostic only. The evidence decision is computed from the question, never from the gate's result, so there is no path by which the disclosure gate can move a route and thereby become observable. `test_outcome_indistinguishable_http.py` (IR-460) holds the response-boundary half of this property today.

**Residual risk, recorded and not solved.** Equal response shape is not indistinguishability. **Timing differs with gate work and is not mitigated**, and repeated probing against a non-zero temperature is not addressed. The channel is narrowed, not closed, and is not claimed to be.

**An ADR records a decision. It is not evidence that the decision's assumptions were true.** ADR-034's claim was reviewed and accepted, and it was wrong. Prior ADR assumptions are reviewable on the same terms as this one's.

### 8. The decision call's view of a Conversation is its own rule — ADR-026 §13 amended

ADR-026 §13 keeps failed, refused and (per IR-453) ungrounded Turns out of "the model's history", as one predicate — `MODEL_HISTORY_STATES`, which `apps/ai/conversations.py` also reuses for embedding eligibility, deliberately, as the same set rather than a second one that agrees.

**The evidence decision is a consumer that predicate does not describe.** It receives the current question, the stored Resolved question, and **prior reader questions only**:

- **No prior assistant answer text.** A grounded answer is retrieval-derived and can echo an instruction injected into a Passage. A `generated` Turn is admissible to the answering model under §13 and is **not** admissible to a routing decision, so state is the wrong axis here.
- **No recalled Turns.** Recall needs a query vector, which would make the direct route pay an embedding call before deciding not to retrieve.
- **No Passage text.** §2's answer to ADR-028's port objection depends on it.

So §13's single predicate becomes per-consumer: what a model may be *shown* and what a *routing decision* may be shown are different questions. **The broader per-consumer refactor is IR-453's, not this ADR's**; what is specified here is the decision call's rule, implemented in IR-465 and asserted on the request actually sent.

### 9. The landscape exception — ADR-027 §4 is dormant, not satisfied

ADR-027 §4 is the obligation that the Lens computes and the model only reports, because *"asked for research gaps, a language model will produce a confident list drawn from its general knowledge of the field rather than from this corpus"*, and presented as gaps in CIT-U research, *"that is fabrication wearing institutional authority"*.

**That obligation binds a question "routed as corpus-level or landscape", and §5's router does not exist.** Verified 2026-10-06: `apps/ai` contains no routing module, no Lens, and no corpus-level path (IR-302–305 are unbuilt). So §4 binds nothing today. **It is dormant, not satisfied**, and the detector's `aggregate_shape` rule is where this bites — it is the rule that recognises exactly the questions §4 is about.

The exception, with its bounds:

1. **Ordinary retrieval does not satisfy Lens-or-refuse.** Retrieving ten passages and letting the model write about them is **not** a landscape analysis, and this ADR makes no claim that it is.
2. **No answer may claim a comprehensive landscape, a research-gap analysis, or a complete account of what the corpus holds**, from ordinary retrieval.
3. **Before any production `on`, an accountable owner must be explicitly named by a person — never inferred from a ticket, an assignee field or this document** — and must choose one of: build the Lens, refuse landscape questions, or approve a narrower written policy.
4. **The exception expires at the `on` go/no-go** and cannot be carried past it without re-approval. It is not a blanket postponement, and Phase 0 is the only thing it covers.

Phase 0 is inside the exception by construction: it delivers no answer, so no answer can overclaim.

### 10. Two instruments, never conflated

- **A curated evaluation command supplies every accuracy number.** It runs over the annotated question set (IR-463: `evidence_required`, `expected_outcome`, `institutional`), reports over-fires and misses **per reason code** for raw and Resolved questions separately, and creates no Conversation, no Turn and no shadow row.
- **Production-shaped Celery shadowing supplies integration and operational figures only** — coverage, latency, cost, contention, detector-model agreement on real traffic. **It carries no ground truth**, because nobody labelled real reader questions.

Reading an accuracy number off the shadow pilot, or an operational number off the curated set, is a category error. This separation is what keeps ADR-023's measurement discipline intact where ADR-028 reason (4) feared it would collapse: the detector, the model decision and the union are three separately switchable things, each with its own reason codes.

**A hypothetical direct answer is generated and never delivered or retained.** Because the decision is one call that either requests the tool or writes the answer, a direct route means the model wrote an answer. It is discarded in process — never `Turn.answer`, never `Turn.reasoning`, never the shadow row, never a log. What is recorded is route, reason codes, latency, token counts, and a presence flag with a character count. **A length, never content.**

### 11. Out of scope, and what the pilot is gated on

**Out of scope for this ADR and for IR-456:**

- **Production `on`.** The setting rejects it. Turning the behaviour on is a separate decision on a measurement, with its own approval.
- **Adaptive retrieval** — any loop that retrieves, assesses and retrieves again.
- **Model-written search queries.** The tool takes no parameters and any argument is discarded.
- **Web search**, and any source outside the corpus.
- **The future agent loop**, bounded or otherwise. §2 buys the option. It does not exercise it, and this ADR authorizes no second tool.
- **`insufficient_evidence` or any new answer state**, reader-facing overrides, streaming the decision, and any `EvidenceWorkflow` abstraction.
- **Page-precision measurement**, which has no instrument (§Context).

**Gating condition, stated as a condition and not an intention: shadowing real reader questions requires that the provider's request- and response-data retention and handling have been verified and approved first.** The no-training terms ADR-015 secured cover training, not retention, and the discarded hypothetical answer exists in the vendor's response whatever this system does with it. Until that verification is recorded, shadow runs only against the curated set.

## Alternatives Considered

**Keep ADR-028 as it stands and do nothing.** Rejected. The defect ADR-034 documents is real and reader-visible, and ADR-028's reason (2) — retrieval does not work — no longer describes the system. Leaving it in place would mean a decision standing on a premise that has expired.

**The structured route label, as IR-462 recommended.** The strongest alternative, and the one this ADR overrules. It is measurably faster at p95 (0.66 s against 1.62 s), needs no port change, and keeps ADR-028's `system`/`user` separation untouched. It was rejected only on option value (§2): it is a bespoke protocol to delete if bounded tool use is ever adopted. **If the pilot shows the latency matters, or if bounded multi-step tool use is abandoned, this alternative is the thing to revert to** — and reverting is cheap in Phase 0, where no reader depends on either.

**The deterministic detector alone, with no model call.** Rejected as insufficient, and it is also the fallback this design degrades to. IR-462's `s02` is the counter-example: a mechanism question with no repository vocabulary is missed by lexical rules by construction. It is kept as one half of §3's union rather than as the whole answer.

**The model decision alone, with no detector.** Rejected. It would make routing depend entirely on one unverified model call, and §5's structural `scope_record` rule — Paper Chat always needs the paper — is exactly the kind of fact that should not be a model's opinion.

**Intersection rather than union** — retrieve only when both agree. Rejected outright. It makes the expensive error (a question needing passages answered without them) reachable whenever either half fails, which inverts §3's asymmetry.

**A new Inference task for the decision, or a per-call reasoning override.** Rejected on IR-462's data: reasoning moved neither latency nor reliability materially. The same call would write the direct answer, so it belongs to the task tuned for answering.

**Execute the tool call in shadow, to measure the full loop.** Rejected. Retrieval already ran on the same Resolved question and the tool carries no query, so a second search returns the first search's result at the cost of embedding and reranking credits — and it would make an inert path touch the corpus.

**Ship straight to production `on` behind a flag.** Rejected. Nobody has established whether the decision is accurate enough for a reader to depend on, which is the entire purpose of a shadow pilot that changes no answer.

## Decision Rationale

Two things make this a decision rather than a ticket.

**The first is that it reverses a researched rejection.** ADR-028 did its job: it stopped the idea recurring until something changed. What changed is narrow and should be stated narrowly — retrieval is chunk-level now, and a measurement on the configured model put both mechanisms far above the ~77% figure ADR-028 reasoned from. What has *not* changed is that there is no measured comparison of an agentic loop against the pipeline, and no instrument for the page-precision cost ADR-028 weighted most heavily. **A reader of this ADR in six months should come away knowing the bar ADR-028 set was not cleared, and that this ADR took a narrower step on a different argument.**

**The second is that the mechanism choice goes against its own spike.** That is the kind of thing that looks like the evidence was ignored, so the reason is stated plainly rather than dressed up: the measurement was inconclusive on accuracy and unfavourable on latency, and the decision was taken on option value anyway. Option value is a legitimate reason and it is also the easiest reason to use badly, so it is bounded — one tool, no parameters, nothing executed, no loop, and an explicit revert path (§Alternatives) while Phase 0 keeps the cost at zero readers.

Everything else in this document is boundaries, for the same reason ADR-034 is mostly boundaries. The capability is one model call that returns a route. The value is in §3 (the union never permits the expensive error), §4 (nothing is executed), §6 (the model cannot widen authorization), §7 (the gate cannot move a route), §8 (the decision sees no retrieved text) and §9 (an unbuilt obligation is named as unbuilt). Each closes a route by which a route signal could become something more than a route signal.

## Consequences

- **Positive.** Whether a question needs evidence stops being an assumption. The ADR-034 defect gets a mechanism rather than a prompt tweak. The detector's reason codes make routing error attributable per rule. Three separately switchable mechanisms keep ADR-023's per-technique comparison possible, which ADR-028 reason (4) feared would be lost.
- **Positive.** The port that an eventual bounded tool-use design would need exists, exercised offline, on a call that carries no corpus text.
- **Negative.** A wider provider interface (`ToolCallingLLM`, abstract so no resilience decorator can silently bypass it), a new module between the chat views and the answer service, a shadow row with a claim-and-fence lifecycle, and a second Celery lane — all to change no reader's answer. That is the price of learning whether the decision is trustworthy before anyone depends on it.
- **Negative, measured.** About 0.2 s at the mean and ~1 s at p95 of decision latency against the rejected alternative. Zero reader impact in Phase 0; a real cost at `on`, and a reason the `on` decision may revert §2.
- **Risk — the decision is wrong in the expensive direction.** A question that needed passages is answered without them. Bounded by §3's union and its retrieval fallback, and by the fact that Phase 0 delivers nothing. `s02`-shaped questions (mechanism questions with no repository vocabulary) are the specific thing the pilot must watch, because **neither half of the union catches them**.
- **Risk — option value is never exercised.** Then the wider port and the slower mechanism bought nothing, and the route label should have been chosen. Named here so the `on` review can hold this ADR to it.
- **Risk — a landscape question gets a confident partial answer.** §9 bounds it by prohibition and by expiry, not by a mechanism, because the mechanism (the Lens) does not exist. **This is the weakest guarantee in the document** and the reason §9 insists on a person naming an owner.
- **Known limitation.** The vendor's retention of the discarded hypothetical answer is a property of the provider, not of this system. §11 gates the pilot on verifying it; the gate is a process control, and nothing in the code can enforce it.
- **Known limitation.** Timing remains a side channel on the empty/withheld distinction (§7), unmitigated.

## MVP Impact

**No reader-facing scope change, and a real capacity cost.** IR-456 is sized at 16–25 dev-days for Phase 0 plus the pilot, against roughly 45–70 dev-days of remaining RAG answer-path work — a 25–55% increase on an ADR-001 budget that has already been reversed four times. Under `CLAUDE.md`'s Scope rule, RAG is thesis-critical and this is protected work; under ADR-001's accounting, this ADR should say what it displaces, and the honest answer is that the displacement is supporting frontend work and the Lens (IR-302–305), whose absence §9 then has to cover with a prohibition. That circularity is recorded rather than resolved.

## SaaS Impact

Per-instance under [ADR-005](005-instance-per-tenant.md). Whether a deployment records shadow decisions at all, its sample rate, and its institution and Area term lists are per-deployment; the generic English rules are in code. One institution enabling shadow has no effect on another. The default is `off` with a zero sample rate, so a deployment nobody reviewed records nothing.

## Security Impact

**Net neutral, with four boundaries that carry the weight. Three are enforced in code; one is a process control.**

1. **No new visibility path.** The decision reads no records and runs no retrieval. `Record.objects.visible_to(user)` stays the one predicate, applied inside retrieval — the rule `CLAUDE.md` states and IR-285 enforced. The model's route is never a parameter to a protected operation (§6).
2. **The disclosure gate cannot move a route** (§7). The route is a function of the question, so there is no channel by which "something was withheld" becomes observable through routing. Residual: timing, and repeated probing at non-zero temperature. Not closed, not claimed to be.
3. **The widened port carries no retrieved text.** ADR-028's injection concern is about Passage text reaching a message list where it can outrank a system prompt. The decision call receives no Passage text, no recalled Turns and no prior assistant answer text (§8), and the grounded path keeps `generate(system, user)`. The Resolved question **is** treated as untrusted (§5), because a resolver reads prior answers. Asserted on the request sent, not argued.
4. **Vendor retention of the discarded answer is a process control, not a technical one** (§11). The hypothetical direct answer is discarded in this system and exists in the vendor's response. The no-training terms do not cover retention. Shadow must not run on real reader questions until retention and handling are verified and approved.

Also: logs carry Turn ids and reason codes only — no question text, no Passage text, no reasoning, no counts. A shadow row cascade-deletes with its Conversation, so a reader's deletion stays complete under ADR-026 §15's rule.

## Deployment Impact

No new service, no new vendor, no new credential. One migration for the shadow record. A **dedicated low-concurrency Celery queue** and a **separate circuit-breaker key** with a **shadow-only token lane**, so shadow cannot degrade a reader's answer: shadow is skipped when the answer task's breaker is open or its budget is spent, and skips count as missing coverage rather than as success. Residual, stated: **contention remains vendor-side**, where shadow and reader traffic compete with no priority mechanism, bounded only by shadow's concurrency and its own cap. A deployment that does nothing gets today's behaviour.

## Research Impact

Thesis-critical under [ADR-013](013-chunk-level-rag-pipeline.md) §Research Impact (amended 2026-09-04), and the defensible claim is a **method** claim, not a capability claim.

What is presentable: the prior decision not to adopt tool calling was written down with its evidence and its revisit conditions (ADR-028); the conditions were assessed one by one rather than waved at; two mechanisms were measured on the configured model before either was built; the spike's recommendation was overruled on a stated ground with its cost named; and the behaviour was built to record its decisions against labelled ground truth **before any reader depended on it**. Reversing a researched decision and showing exactly which part of its basis expired is a stronger artefact than either the original rejection or an unexamined adoption.

What may **not** be claimed: that tool calling routes more accurately (§2 — the measurement does not support it); that the page-precision cost ADR-028 identified was answered (§Context — there is no instrument); that ADR-023's recall numbers say anything about CIT-U research (the corpus is a 40-paper arXiv proxy); or that ordinary retrieval delivers a landscape or research-gap analysis (§9).

An evidence decision carries no retrieved passages, so it has no recall and enters no ADR-023 average. The curated command's accuracy numbers and ADR-023's recall numbers measure different things and are never reported as one figure (§10).

## Related Requirements

FR-M4, FR-M4-01 (RAG chatbot) · NFR-R2 (graceful degradation) · NFR-S4 (no unauthorized disclosure) — **stable labels only**, per the frozen-SRS rule. This ADR is the requirements authority once accepted.

## Related Tasks

**Parent:** [IR-456](https://citiris.atlassian.net/browse/IR-456) — the evidence decision, Phase 0 and a reader-invisible shadow pilot.

**This ADR:** [IR-461](https://citiris.atlassian.net/browse/IR-461) — ADR-035, Ask IRIS decides whether it needs evidence.

**Prefactors:** [IR-457](https://citiris.atlassian.net/browse/IR-457) (unique ADR numbers, which freed 035) · [IR-458](https://citiris.atlassian.net/browse/IR-458) (every answer state renders explicitly) · [IR-459](https://citiris.atlassian.net/browse/IR-459) (retrieval reports why it returned nothing) · [IR-460](https://citiris.atlassian.net/browse/IR-460) (empty and withheld indistinguishable at the response boundary — carries ADR-034's §Security Impact correction) · [IR-462](https://citiris.atlassian.net/browse/IR-462) (the mechanism spike this decision cites and overrules) · [IR-463](https://citiris.atlassian.net/browse/IR-463) (questions carry an evidence requirement).

**Blocked on this ADR being approved:** [IR-464](https://citiris.atlassian.net/browse/IR-464) (the detector and the curated command — §5; its `aggregate_shape` rule is what engages §9) · [IR-466](https://citiris.atlassian.net/browse/IR-466) (the orchestrator, the shadow record and the Celery task — §4, §10, §11).

**Implements parts of this ADR:** [IR-465](https://citiris.atlassian.net/browse/IR-465) (`ToolCallingLLM`, the tool schema, every fallback reason code, and §8's decision-call context rule) · [IR-467](https://citiris.atlassian.net/browse/IR-467) (the pilot reports what it found).

**Elsewhere:** [IR-453](https://citiris.atlassian.net/browse/IR-453) (ADR-034, and the broader per-consumer conversational-context refactor §8 does not do) · [IR-396](https://citiris.atlassian.net/browse/IR-396) (ADR-033 §3's relevance cut-off, which ADR-034 depends on) · [IR-250](https://citiris.atlassian.net/browse/IR-250) (the embargo field the disclosure gate waits on) · [IR-278](https://citiris.atlassian.net/browse/IR-278) (a real corpus — the reason ADR-028's second revisit condition only partly holds) · IR-302–305 (the Lens, unbuilt, which is why §9 exists).
