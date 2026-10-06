# ADR-034: An ungrounded answer is a distinct state, never a grounded one

## Status

**Accepted** — 2026-10-02 (IR-453).

> **Amendment to §2 — [ADR-035](035-ask-iris-decides-whether-it-needs-evidence.md) (Accepted 2026-10-06, IR-461).** It makes *withheld evidence does not affect the route* a routing rule: the route, the response and the answer state are a function of whether any Passage was kept and whether the question carried an evidence requirement, **never of why nothing was kept**. This completes the §Security Impact correction IR-460 already applied below. §2's own rule that a withheld question is `no_sources` rather than `ungrounded` is unchanged.

**Amends [ADR-008](008-ai-degradation-to-fts.md)** — *"Never a fabricated answer"* is kept for the grounded path and given an explicit boundary rather than an exception. See §1 and that file's IR-453 amendment.

**Amends [ADR-026](026-conversational-retrieval-and-memory.md) §13** — the new state joins the three already excluded from the model's history. See §5 and that file's IR-453 amendment.

**Amends [ADR-027](027-corpus-level-questions.md) §4** — *"the Lens computes; the model only reports"* becomes an absolute bound on this decision: no research question may reach the ungrounded path. See §4 and that file's IR-453 amendment.

**Amends [ADR-033](033-hybrid-retrieval-and-passage-selection.md) §5** — §3's relevance cut-off is exempted from the off-by-default rule and ships on, because leaving it off does not defer this behaviour, it deletes it. The other five techniques are unchanged. See that file's IR-453 amendment.

**Depends on [ADR-033](033-hybrid-retrieval-and-passage-selection.md) §3** — the relevance cut-off is what makes a zero-source question *detectable*. Without it retrieval always returns its top *k*, so the condition this ADR branches on never occurs. See §2.

## Context

Ask a question the corpus has nothing to do with — *"what is the colour of the sky?"* — and IRIS today produces a non-sequitur refusal. Verified in code 2026-10-02 against a two-paper corpus (IR-453):

- `apps/ai/retrieval/two_stage.py` ends in `.order_by(distance)[:limit]`. There is **no relevance floor anywhere on the path**, so retrieval returns the *k* nearest chunks however far away they are. The probe retrieved a flood-prediction paper and a tilapia-ponds paper.
- Both were numbered into the prompt under `Sources:`.
- `GROUNDING_RULES` (`apps/ai/answers/citations.py`) then instructs: *"Answer ONLY from the numbered sources below"* and *"If the sources do not contain the answer, say so plainly instead of guessing."*

The model is handed two irrelevant passages and told to answer only from them, so it refuses — correctly, given what it was asked. The reader gets a sentence about not finding information on sky colour in a tilapia-ponds paper.

**Two things make this a decision rather than a prompt tweak.**

First, the refusal is a `generated` Turn, not `no_sources` — verified on the probe. `MODEL_HISTORY_STATES` is `frozenset({GENERATED})` (`apps/ai/models/conversation.py`), so IR-448's exclusion of failed and refused Turns does not reach it: a model-written refusal over retrieved-but-irrelevant sources **stays in the history handed to the next model call**. IR-448 is correct as specified; this is a gap in the specification, not in that implementation.

Second, and the reason this needs an ADR rather than a ticket: answering such a question *at all* changes what IRIS is permitted to say. The grounding rules exist so every claim traces to a CIT-U source. An answer with no source has nothing to trace, and three ADRs currently forbid it in different words.

## Decision

### 1. An ungrounded answer is permitted, as its own state — and the grounded path is untouched

A new `Turn.state`, **`ungrounded`**, joins `generated`, `no_sources`, `unavailable` and `partial`. It means: *no passage in this reader's corpus was relevant, and the answer below comes from the model's general knowledge, not from CIT-U research.*

`GROUNDING_RULES` is **not weakened, reworded or made conditional.** That instruction is load-bearing for every grounded answer, and loosening it to accommodate this case would weaken all of them — which is the trade this decision exists to avoid. The ungrounded path uses a **separate prompt with no `Sources:` block at all**, so there is no numbered source list for the model to be told to ignore.

**ADR-008's *"Never a fabricated answer"* is unchanged, and this is not an exception to it.** That rule forbids presenting an invented answer *as a grounded one* — the failure mode where a reader cannot tell a cited finding from a guess. An answer carrying a distinct state, a distinct presentation and no citations is not that answer. The boundary, stated as a rule:

> **Fabrication is a grounded answer that is not grounded. An answer that says plainly it is not grounded is a different kind of answer, not a permitted fabrication.**

### 2. It is reachable only when zero passages survive the relevance cut-off

The ungrounded path is entered on exactly one condition: **retrieval, after ADR-033 §3's relevance cut-off, yielded no passages at all.**

- **If any passage clears the cut-off, the answer is grounded.** There is no partial mode, no "mostly grounded with a general aside", and no per-claim mixing. One Turn is grounded or it is ungrounded, and a reader never has to work out which sentence is which.
- **It therefore depends on the cut-off existing and being on.** Without §3 retrieval always returns its top *k*, the zero-source condition never arises, and this decision is inert by construction rather than by a flag. **This is why `033` §5 was amended rather than waited out**: leaving the cut-off off would not defer this behaviour to IR-402, it would delete it, since nothing downstream can branch on a condition that never occurs. IR-396 builds the cut-off and ships it **on**, with a loose provisional default.
- **The disclosure gate's zero is not this zero.** A question whose passages were all withheld by ADR-015's disclosure gate is `no_sources`, not `ungrounded`. Relevant research exists and the reader may not read it; answering from general knowledge would paper over a visibility boundary with prose.

### 3. It ships on, and the label is therefore not optional

**The setting defaults on.** An ungrounded answer is what IRIS is *meant* to do
with an off-corpus question, so the setting expresses that and the switch exists
to turn the behaviour **off** for a deployment that wants strictly grounded
answers — the per-instance posture ADR-005 already assumes.

This is a deliberate departure from `033` §5's off-by-default convention, taken
together with that ADR's §5 amendment, and it has one consequence that must not
be treated as a detail:

> **Reader-visible behaviour changes on upgrade.** With both defaults on, the
> first off-corpus question on a live deployment is answered from the model's
> general knowledge. There is no opt-in step in which someone reviews the
> presentation first.

So **§6's label ships in the same change as the behaviour, not after it.** An
ungrounded answer carries no citations and no Record cards, which means that
without the label it renders as a confident, uncited answer in the same place a
grounded answer appears — indistinguishable from a finding to anyone who does
not notice the missing citations. That window is the whole risk of this ADR, and
it is closed by ordering, not by vigilance: no deployment gets the behaviour
before it gets the label.

**It is absent in degraded mode**, for the same reason §3 of `033` is: with the
vendor unreachable there is no reranker score, so there is no cut-off, so the
zero-source condition this branches on is not trustworthy. Degraded mode already
tells the reader the system is running on fallback search, and stacking an
ungrounded answer on top of that caveat asks a reader to hold two qualifications
at once.

### 4. No research question may reach it — ADR-027 §4 is the bound

This is the thesis-critical property, and the one that must not slip.

ADR-027 §4 states the risk precisely: *"Asked for research gaps, a language model will produce a confident list drawn from its general knowledge of the field rather than from this corpus. Presented as 'gaps in CIT-U research', that is fabrication wearing institutional authority — and the easiest thing for an examiner to take apart."*

That sentence is the reason this ADR is narrow:

- **A question routed as corpus-level or landscape never goes ungrounded.** `027`'s §5 routing classifier already decides a question's kind; a question it routes to the Lens is answered by the Lens or refused, exactly as that ADR says. The Lens computes and the model reports, with no general-knowledge branch anywhere in it.
- **A zero-source research question is `no_sources`, not `ungrounded`.** *"What has CIT-U published on tilapia pond aeration?"* with nothing retrieved means the repository holds nothing on it — which is **a true and useful answer about the corpus**, and replacing it with the model's knowledge of tilapia aeration destroys the only information the reader actually asked for.
- **Paper Chat never goes ungrounded.** A Conversation scoped to one Record is a question *about that paper*; an answer from general knowledge is a non-answer there, whatever it is labelled.

A test proving a research question still refuses rather than answering from model knowledge is an acceptance criterion of IR-453, not an implementation detail.

### 5. An ungrounded Turn is kept out of the model's history — and the cost is recorded

ADR-026 §13 excludes failed and refused Turns from the history handed to the answering model and the §1 rewriter. **`ungrounded` joins them**, so `MODEL_HISTORY_STATES` stays `{GENERATED}`.

The reasoning is §13's own, applied to a case it did not anticipate: a refusal left in the prompt is a demonstration of refusing, and an **ungrounded answer left in the prompt is a demonstration of answering without sources** — precedent the next question is biased toward following. That bias runs in the direction this ADR is most concerned about, and the grounded path is the one that must not drift.

**The cost is real and is not hidden.** Unlike the three states already excluded, an ungrounded Turn holds genuine content, so a follow-up to an ungrounded aside is resolved against a history that does not contain it. *"What is the colour of the sky?"* then *"why?"* will not resolve as the reader expects. We accept that: an ungrounded aside is by definition not about the corpus, and the alternative — admitting ungrounded text into the prompt to make asides chainable — buys conversational polish with the one property the system is for. Revisit only on reader evidence that ungrounded follow-ups matter, never on taste.

It stays fully visible in the reader's transcript, like every other excluded state. The asymmetry is deliberate and is §13's existing decision.

### 6. Presentation makes it unmistakable, and it can never carry a citation

- **No citations, ever.** No `Sources:` block means no markers to resolve; any marker the model emits anyway is dropped by the existing parser, which already drops markers that resolve to nothing. No Record cards ride alongside an ungrounded answer.
- **Labelled in the interface as not from the repository**, not as a footnote under the text. A reader who skims the answer and misses the label is the entire failure mode, and `008`'s own recorded risk about a missing degradation banner is the precedent: the visible state is an acceptance criterion, not a nicety.
- **The relevance score stays invisible**, under `033` §3 and `apps/ai/presentation.py`'s existing rule. "Nothing cleared the floor" is a state, not a number to show.
- **`GET /api/v1/ai/status/` and the wire `mode` carry the state**, so a caller can distinguish it without matching on the answer's wording — the coupling `apps/ai/answers/citations.py` already warns against.

## Alternatives Considered

**Loosen `GROUNDING_RULES` so the model may answer from its own knowledge when the sources are unhelpful.** Rejected, and this is the alternative IR-453 itself argued against. It is one line of prompt and it weakens *every* grounded answer, because the model then holds a standing licence to decide a passage was unhelpful and substitute its own knowledge — with no state, no label and nothing in the transcript to show it happened. The failure would be invisible precisely where it matters most.

**A per-claim mix: grounded sentences cited, ungrounded sentences marked inline.** Rejected. It puts the burden of separating evidence from recollection on a reader skimming prose, which is the burden citations exist to remove, and it makes every grounded answer a place an ungrounded sentence might appear. §2's "a Turn is grounded or it is not" is the whole value.

**Answer ungrounded questions but store them as `generated`.** Rejected. The state is the only thing that lets the transcript, the API and `026` §13's history filter tell the two apart; without it this is just the current defect with better prose. It is also what IR-453 found: a `generated` refusal is exactly how the gap got into history.

**Detect off-corpus questions up front with a classifier and skip retrieval.** Rejected for now. It adds a model call on the hot path to answer a question retrieval answers for free — a cut-off that returns nothing *is* the detector, and it is derived from what the corpus actually holds rather than from a classifier's opinion about a question. `027` §5's existing routing call may later carry the signal at no extra cost (`026` §14's precedent for folding a second axis into one classification), which is a cheaper place to revisit this.

**Keep refusing, and fix only the non-sequitur wording.** Rejected as insufficient, though it was close. The cut-off alone makes the refusal honest — *"nothing relevant in the papers you can see"* instead of a sentence about tilapia ponds — and that is a genuine improvement this ADR keeps. But it leaves a reader's simple factual aside unanswered by a system that plainly could answer it, and every such refusal is a `generated` Turn today. Since the floor is being built anyway, the marginal cost of a distinct state is small and the marginal risk is bounded by §4.

**Permit it for every zero-source question, research questions included.** Rejected outright. See §4. This is `027` §4's fabrication-wearing-institutional-authority failure, and it is the one an examiner would go for first.

## Decision Rationale

The cheap framing of this decision is "should the chatbot be allowed to answer general questions", and that framing is what makes it look like a prompt tweak. The real question is narrower: **IRIS must never be unable to tell a reader where an answer came from.** Once a Turn carries its own state, the answer to "may it be ungrounded" stops being dangerous, because nothing downstream can mistake it — not the reader, not the transcript, not the history filter, not an API consumer.

That is why almost all of this ADR is boundaries rather than capability. The capability is one prompt without a sources block. The value is in §2 (one condition, no mixing), §4 (no research question), §5 (out of the model's history) and §6 (unmistakable presentation) — each of which closes a route by which an ungrounded answer could come to look grounded.

Shipping it off is what makes being wrong affordable, and it is also an honest ordering statement: this cannot be evaluated until the cut-off it depends on is on, and that is IR-402's decision on a measurement, not this ADR's.

## Consequences

- **Positive.** A reader's simple factual aside is answered instead of producing a non-sequitur. A whole class of model-written refusal stops entering the model's history, which is the IR-453 gap. The grounded path is untouched, and `GROUNDING_RULES` keeps its single unconditional meaning.
- **Negative.** A fifth `Turn.state` and a migration; a second prompt assembly path; new frontend presentation that has to be unmissable rather than merely present. A follow-up to an ungrounded aside does not resolve against it (§5).
- **Risk — the label is missed, and this risk is now live rather than opt-in.** A reader skims past the "not from the repository" marker and quotes an ungrounded answer as an IRIS finding. This is `008`'s silent-degradation risk in a new place, and `008`'s own recorded mitigation applies: the visible state is an acceptance criterion, not a nicety. **Because the setting now defaults on (§3), the mitigation is also an ordering constraint** — the label ships with the behaviour, in one change, and a deployment can never receive the second without the first.
- **Risk — a research question is misclassified as general.** §4 bounds it by question kind, and the bound is only as good as `027` §5's routing. The mitigation is the direction of the default: a question wrongly treated as *research* merely refuses, which is today's behaviour, while a question wrongly treated as *general* is the harmful case — so the gate is written to refuse when unsure, and tested in that direction.
- **Known limitation, recorded rather than fixed here.** In **degraded mode the IR-453 history gap persists**. With no reranker there is no cut-off (§3), so an off-corpus question still retrieves *k* FTS chunks, still meets `GROUNDING_RULES`, and still produces a model-written refusal stored as `generated`. IR-453's claim that the floor closes that gap "at no extra cost" holds on the reranked path only. Closing it in degraded mode needs a signal that does not exist there and is deliberately not invented — see `008`'s IR-391 amendment on why a threshold over FTS ranks would mean something different depending on whether Voyage was up.

## MVP Impact

**No scope change, but no longer optional either.** This started as the
supporting half of IR-396's thesis-critical cut-off and the part to cut if
capacity ran short. **That is superseded by §3's default.** Once the cut-off
ships on, the ungrounded branch is live, so its presentation is on the critical
path with it: the cuttable thing is now the *behaviour* (turn the setting off),
never the *label*. Shipping the floor without the label is the one combination
this ADR forbids.

## SaaS Impact

Per-instance under ADR-005. Whether an institution permits ungrounded answers at all is exactly the kind of policy that differs between institutions, and the setting is per-deployment. One institution turning it on has no effect on another's.

## Security Impact

**Neutral, with one boundary that must hold.** The ungrounded path reads no records and runs no retrieval beyond what already ran, so it adds no candidate source and no second visibility predicate — the rule `CLAUDE.md` states and IR-285 enforced.

The boundary is §2's last clause: **a question whose passages were withheld by the disclosure gate is `no_sources`, never `ungrounded`.** Inverted, an ungrounded answer would become a weak signal that relevant-but-unreadable material exists — the aggregate-leak shape `027` §3 records, where a count reveals records the asker may not see. **Correction (IR-460).** The sentence that stood here claimed that keeping the two states distinct keeps the refusal indistinguishable from "nothing exists". It does not hold as written: under this design nothing-found yields a general answer and everything-withheld yields a refusal, so **a refusal would itself signal that something was withheld**. The rule is therefore stated positively: the reader-facing response and answer state are a function of exactly two things -- whether any Passage was kept, and whether the question carried an evidence requirement -- and never of *why* nothing was kept. `empty`, `withheld_all` and `none_relevant` are one case to a reader, and the retrieval outcome is diagnostic only. Today no such channel exists (all three reach the same empty selection and byte-identical responses on `/ai/ask/` and `/ai/ask/stream/`), and `test_outcome_indistinguishable_http.py` holds that property. This is the property IR-153 established for records and `015`'s gate extends to passages.

**Residual risk, recorded not solved.** Equal shape does not prove indistinguishability. **Timing** differs with gate work and is not mitigated; repeated probing against a non-zero temperature is not addressed. The channel is not closed, and is not claimed to be.

No new outbound data: the ungrounded prompt sends the reader's question and no corpus text, which is strictly less than the grounded path already sends under `015`'s no-training terms.

## Deployment Impact

One migration (the `Turn.state` choice). No new service, no new vendor, no new credential, no new queue. The setting defaults off, so a deployment that does nothing gets today's behaviour.

## Research Impact

Thesis-critical under ADR-013 §Research Impact (amended 2026-09-04) — but as a **boundary**, not a capability. The defensible claim is not "IRIS can also answer general questions"; it is that **IRIS can always say which of its answers are grounded in CIT-U research and which are not**, enforced by a stored state rather than by prose. §4 is the part to present at defence: the system declines to answer a research question from general knowledge even when it could, and a test demonstrates it.

An ungrounded answer is **never** evidence about CIT-U research and never enters ADR-023's measurement. It has no retrieved passages, so it has no recall; a question that goes ungrounded is scored as retrieving nothing, which is what it did.

## Related Requirements

FR-M4-01 (RAG chatbot) · NFR-R2 (graceful degradation) — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-453 (this ADR and the state) · IR-396 (the relevance cut-off this depends on) · IR-402 (owns `033` §5's other five defaults; **no longer gates this** — the cut-off's default was moved by the §5 amendment) · IR-448 (the history exclusion this extends) · IR-454 (the harness measure that makes §3's default justifiable by a run) · IR-443 (the transcript the defect was found in) · IR-278 (a real corpus, after which the cut-off is recalibrated).
