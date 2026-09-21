# ADR-027: Corpus-level questions are answered from computed counts over named Areas

## Status

**Accepted** — 2026-09-18.

**Extends [ADR-013](013-chunk-level-rag-pipeline.md)** rather than amending it. ADR-013 made the chunk the retrievable unit, which is right for questions about a Record's contents. This ADR covers questions about the corpus itself, which retrieval cannot answer at all.

**Depends on [ADR-023](023-retrieval-quality-evaluation.md)** for its evaluation structure, and on [IR-153](https://citiris.atlassian.net)'s visibility guarantee for its security posture.

## Context

Three questions people want to ask Ask IRIS cannot be answered by retrieval, no matter how good retrieval gets:

- *"Which papers are trending right now?"*
- *"Where are the research gaps?"*
- *"Give me an idea for a research project."*

Retrieval finds passages resembling a question. Ask it for trends and it returns passages containing the word *trending*. Ask for gaps and it returns future-work sections. That is a keyword coincidence, not an answer.

**The deeper reason is structural.** A gap is an Area where *no paper exists*. Retrieval returns things that are there. By construction it can never return the thing that is missing.

### What the data already supports, audited 2026-09-17

| Available today | Detail |
|---|---|
| **Named Areas** | Every Record carries a `Classification` and a `PSCEDClassification` — established taxonomies assigned by a person at submission |
| **Submission dates** | `Record.created_at`, plus `year_accomplished` and `year_completed` |
| **A timestamped access stream** | `AuditEvent` has an `ACCESS` type among its 14, written by `increment_access` on every record view, with a `record` FK and an indexed `created_at` |
| **One visibility predicate** | `Record.objects.visible_to(user)`, already applied on every action |

Two corrections to earlier internal analysis are worth recording, because both were used to argue this capability was further away than it is. The architecture review claimed engagement tracking "needs a new event stream" — it does not; `ACCESS` events exist and are timestamped. And `Record.access_count` was read as an engagement signal — it is a lifetime cumulative counter with no timestamps, so it can only answer "most accessed ever", never "trending this month". The `AuditEvent` rows are the ones with dates.

**The consequence: this capability needs no vectors.** It is not blocked on the chunk-embedding chain.

## Decision

### 1. The unit is a named Area, from the existing taxonomies

A **Research landscape** question aggregates over **Areas** — `Classification` and `PSCED` categories (see `CONTEXT.md`). Not clusters derived from vectors.

Because an Area is assigned by a person, it has a name someone chose — which is what makes a claim about it checkable by hand against Discover.

> **Correction, 2026-09-19.** An earlier draft of this section said an Area "has siblings to be compared against", and built the worked example on sibling comparison. **The schema has no such structure**: `Classification` and `PSCEDClassification` are flat lookup tables holding a unique `name`, with no parent and no grouping. Every Area sits at the same level as every other one. What an Area is compared against is settled in §1a below, not assumed here.

**Clustering is a named follow-up, behind the same interface.** The interface treats an Area as a name, a member count, and a history — a taxonomy category supplies all three directly; a cluster supplies counts and must *derive* a name. Requiring a name keeps that weakness visible rather than letting an unnamed cluster reach an answer. Clustering finds emergent Areas the taxonomy has no words for, which is the more publishable version, and is therefore exactly the kind of claim ADR-023 says needs measurement before adoption.

### 1a. An Area is compared against its own past first, and the catalogue second

With no hierarchy in the schema there are no siblings, so a reference point has to be chosen rather than assumed.

**The primary comparison is temporal: an Area against its own history.** *"Eight records between 2020 and 2022, one since"* is a change, and a change is meaningful regardless of how large the Area is naturally. This needs no structure the schema lacks.

**The secondary comparison is against the catalogue-wide mean, and is always labelled as such** — never presented as comparison against like disciplines. Its weakness is recorded because it does not go away: Education and Engineering having different volumes is not a gap, it is what disciplines look like. A purely relative claim is therefore the weaker of the two and must never stand alone as a finding.

Temporal comparison cannot find an Area nobody has *ever* worked in, because there is no history to read. That is the hole the catalogue-wide comparison partially fills, and the reason both are kept.

**Deriving a hierarchy from PSCED codes is the preferred long-term fix**, and is deferred rather than rejected. PSCED is a hierarchical national standard, so genuine sibling comparison would be both possible and defensible — but only if the stored free-text names actually carry their codes, which cannot be checked until IR-278 delivers real records. Revisit once a corpus exists. Adding a parent foreign key to the lookup tables is the fallback if the names turn out not to carry codes, and it costs a migration plus somebody grouping the categories by hand.

### 1b. Unclassified Records are counted and shown, and can block an answer

Both classification fields are nullable, so a Record may be filed under no Area at all.

**The Unclassified count is always reported** alongside the Areas. Silently excluding unfiled Records would let the landscape misrepresent the catalogue while looking authoritative — if a third of records are unfiled, every count is wrong and nothing says so.

**Above a configured share of unfiled Records, gap claims are refused outright**, with the reason given. "The catalogue is not classified well enough to answer that" is an available answer, in the same way "no clear gaps" is under §4. Without this, the first real-world use produces a confident landscape built on a fraction of the data.

### 1c. Sparse is a stated fraction, shown in the answer

An Area is sparse when its count falls below a configured fraction of its reference value — a setting, not a constant, and **the fraction appears in the answer**: *"below 25% of the catalogue average"* is a sentence a reader can weigh and disagree with.

Ranking Areas and reporting the bottom N was rejected: it guarantees a finding whether or not one exists, which is precisely what §4's fourth rule forbids. A statistical threshold was rejected as over-engineered for a corpus of hundreds, where the distribution assumptions do not hold.

### 1d. Below a floor, there is no landscape to describe

**Landscape answers do not run below a configured minimum number of visible Records**, and above it the sample size is shown.

With a dozen Records every Area is sparse and every trend is noise. This matters immediately rather than theoretically: IR-278 has not started, so the *first* run of this capability will be against a near-empty catalogue. It must say "not enough records to describe a landscape" rather than invent one.

Showing the sample size above the floor is not sufficient on its own — a reader takes the claim and skips the caveat, which is what caveats are for.

### 2. "Trending" is two signals, reported separately and never blended

- **Submission velocity** — Records created per Area per period, from `created_at`.
- **Access velocity** — `ACCESS` events per Record per window, from `AuditEvent`.

**They are never combined into one score.** A blended ranking is untraceable: nobody can say why an Area ranked where it did, which is fatal for a claim in a thesis. Two labelled lists are both more useful and more defensible.

Their weaknesses are recorded rather than hidden. Submission velocity is slow-moving — in a small institution a "trend" may be three papers. Access velocity is gameable and sparse: with few users one person clicking repeatedly is a trend, and it measures whatever the frontend chooses to POST rather than a rigorous readership.

### 3. A landscape is always relative to what the asker may see

Aggregation runs over `visible_to(user)`, always.

**This is a security requirement, not a preference.** If the answer says an Area holds 12 submissions this quarter and the asker may see 2, that count has revealed that 10 Records exist which they are not permitted to see. IR-153 made a refusal a 404 identical to a missing Record precisely so the API never confirms someone else's draft exists; an aggregate walks straight through that.

**Two people are therefore correctly shown different landscapes.** Office staff, who already see everything, get a pipeline-inclusive view; everyone else gets a catalogue view. That is correct behaviour, not a limitation — a director should see a richer picture than a student.

**The tension is recorded because it does not go away:** the most useful trend signal is the pipeline, and the pipeline is exactly what must stay hidden. Reporting whole-corpus aggregates under a suppression threshold (only report an Area holding at least N Records) is the recognised statistical-disclosure route to having both. It is **not adopted here** — it needs its own security argument, and thresholds leak slowly under repeated querying. It is the obvious place to look if catalogue-only trends prove too weak to be useful.

### 4. The Lens computes; the model only reports

This is the decision the capability's credibility rests on.

Asked for research gaps, a language model will produce a confident list drawn from its general knowledge of the field rather than from this corpus. Presented as *"gaps in CIT-U research"*, that is fabrication wearing institutional authority — and the easiest thing for an examiner to take apart.

So the Lens returns **rows of computed facts**, and the model is handed those rows and constrained to describe them:

1. No Area may appear in an answer that is not in the computed rows.
2. No number may appear that is not from a row.
3. **No claims about the wider field.** The model's world knowledge is out of scope for a corpus question.
4. **"No clear gaps in your visible catalogue" is an acceptable answer.** Without this the system is quietly incentivised to manufacture a finding.

Worked contrast. Unconstrained, a model writes: *"There appears to be limited research in sustainable materials engineering, particularly around bio-based composites — a significant opportunity given growing global interest in circular-economy materials."* That contains a corpus claim that may be true, a sub-area (*bio-based composites*) **no data supports and the model invented**, and a claim about global trends drawn from training data, all presented as one analysis. None of it is checkable.

Constrained, it writes: *"Materials Engineering — 8 records 2020–2022, 1 since; most recent 2023. Catalogue average is 31 records per Area."* Every number is a query result, the comparison is labelled for what it is, and the temporal claim carries the weight.

**"Give me a project idea" therefore does not return an idea.** It returns sparse Areas near the asker's interests with the nearest existing Records, and the reader forms the idea. An invented project idea attributed to IRIS's analysis is the same failure as a machine-generated figure description, which [ADR-025](025-figures-and-formulas-in-extraction.md) declines for the same reason.

### 5. Routing is deterministic first, classified second, and always visible

A question must reach the Lens or the Retriever, and getting that wrong produces a confidently irrelevant answer.

1. **Deterministic patterns** settle unambiguous phrasings. On those cases a pattern is *more* accurate than a classifier, which could only introduce error. Free, and it removes the easy cases from the classifier's load.
2. **A small-model classifier** decides the rest: corpus question, passage question, or both. This is a deliberate per-question cost, accepted for accuracy.
3. **The routing decision is shown to the reader and is overridable.** This is what actually delivers accuracy. No classifier is perfect; what decides whether a misroute *hurts* is whether it is visible. A silent wrong route is a confidently irrelevant answer with no explanation; a visible one is a single click to correct. The same principle as the Resolved question in [ADR-026](026-conversational-retrieval-and-memory.md).

**Routing decisions are logged**, because routing accuracy is otherwise unmeasurable.

**Routing is deliberately not folded into ADR-026's question resolution**, even though both are small-model calls on the question and combining them would be cheaper. One call doing two jobs trades accuracy for cost, which is the wrong trade here.

### 6. Two surfaces, one Lens

A **Research landscape panel** in Discover is the primary surface — corpus answers are tabular, and a sparse-Area comparison belongs in a table and a chart, not a paragraph. Ask IRIS routes to the same Lens, so the question can also simply be asked. A routing miss yields an ordinary retrieval answer, which is a soft failure rather than a wrong one.

### 7. Computed live, with a dated snapshot kept for the thesis

Grouped counts over indexed columns on a corpus of hundreds are fast, and the visible set is per-asker, so caching is premature. Query counts are measured; caching per visibility scope is the next step if it proves slow.

Independently, a **dated snapshot is retained** for written work. A landscape claim in a thesis chapter needs a fixed date attached or it cannot be reproduced.

### 8. Evaluation follows ADR-023's two tiers

- **Engineering gate:** the counts are correct against a fixture corpus, and the answer invents nothing — assertable now, and the claim it supports is "IRIS reports the corpus accurately."
- **The finding:** faculty judge whether sparse Areas are real gaps. Small N, subjective, needs the corpus, and it is the only tier that may be reported as a finding about CIT-U research.

A gap has no ground truth, so there is no recall@10 analogue. Separating these keeps a provable claim apart from an interpretive one.

## Alternatives Considered

**Widen `Retriever` to answer corpus questions.** Rejected. The return shapes differ fundamentally — passages versus aggregates — so one interface serving both becomes a switch statement wearing an interface, and shallow. The retriever stays deep and the Lens sits beside it.

**Clusters from record vectors as the unit.** Rejected for now, kept behind the interface. A cluster has no name, so "cluster 7 is sparse" is not a claim anyone can check; it also requires the whole embedding chain and a corpus to tune against.

**A single blended trending score.** Rejected — untraceable, and a ranking nobody can explain cannot be defended.

**Whole-corpus aggregates.** Rejected: leaks the existence of Records the asker may not see, contradicting IR-153.

**Whole-corpus aggregates under a suppression threshold.** Not adopted, and explicitly left as the route to revisit if catalogue-only trends are too weak. It needs its own security argument.

**Letting the model write freely from retrieved aggregates.** Rejected. It reads better and there is no way to distinguish a computed claim from an invented one, so the failure is invisible.

**Returning only numbers, no prose.** Rejected — a table is not an answer to "where are the gaps?"

**A classifier alone for routing.** Rejected in favour of patterns first: a classifier can only add error on phrasings that are already unambiguous.

**A landscape panel only, with no chat routing.** Rejected — it does not answer the original ask, which was to be able to *ask* the question.

## Decision Rationale

The capability's value depends entirely on being believed, and the fastest way to lose that is one invented gap. Every decision above pushes in the same direction: named Areas over unnamed clusters, separate signals over a blended score, computed rows over model prose, a visible routing decision over a silent one. Each trades some fluency or sophistication for a claim someone can check.

The pleasant surprise is that the defensible version is also the cheap one. Named Areas and timestamped access events already exist, so the first version needs no vectors and is not blocked on the chunk-embedding chain.

## Consequences

- Corpus-level questions can be built **before** the embedding chain lands — unlike conversations, this is not gated on IR-277.
- Trends and gaps vary by role. This must be explained in the interface, or it reads as a bug.
- Gap-finding is limited to Areas the taxonomy already names. A genuinely novel cross-disciplinary Area is invisible until clustering arrives.
- **The taxonomies are flat**, so the strongest available gap claim is temporal rather than comparative. Whether real sibling comparison becomes possible depends on whether stored PSCED names carry their codes — unknowable until IR-278 delivers records, and a migration plus manual grouping if they do not.
- Three refusals are now first-class answers: no clear gaps, too many unclassified Records, and too few Records overall. Each needs surfacing in the interface as an answer rather than an error.
- Four numbers become configuration: the sparse fraction, the unclassified share that blocks a claim, the minimum Record count, and the trending window. Each should appear in or alongside the answer it shapes rather than acting invisibly.
- Access velocity is weak evidence in a small institution and must be labelled as readership, never as quality or importance.
- A new routing surface means a new per-question model call on questions the patterns do not settle.
- Routing decisions become a logged, measurable thing.
- The Lens is a new place where an aggregate could leak visibility, so `visible_to(user)` must be applied inside it rather than by its callers.

## MVP Impact

Not MVP-required. Current-phase RAG work, thesis-critical per ADR-013's 2026-09-04 amendment.

## SaaS Impact

Landscapes are per-instance under [ADR-005](005-instance-per-tenant.md). An Area's counts are meaningless across tenants and must never be aggregated between them.

## Security Impact

**The central risk is inference, not access.** Every other read path returns Records; this one returns *counts*, and a count over a set the asker cannot enumerate reveals that the set is larger than they can see. Applying `visible_to(user)` inside the Lens is what closes it, and applying it in callers instead would leave the Lens itself a leak waiting for its second caller.

Nothing here sends Record content to a vendor: the model receives computed counts and Area names, not passages. Area names come from an institutional taxonomy rather than from any Record's text.

## Deployment Impact

None. Grouped queries over existing indexed columns; no new services.

## Research Impact

This is the part of the RAG work that is genuinely novel rather than well-trodden. Retrieval-augmented question answering is a solved shape; **answering questions about the shape of an institutional corpus, under per-asker visibility constraints, without fabricating findings** is not.

The recorded refusal to let a model speculate about gaps is itself a position worth defending: the interesting result is that a useful answer to "where are the gaps?" requires *less* generation, not more.

## Related Requirements

FR-M4 — stable label only, per the frozen-SRS rule.

## Related Tasks

IR-278 (corpus — gates the interpretive evaluation tier), ADR-023 (evaluation structure), IR-296 (question resolution, deliberately kept separate from routing).
