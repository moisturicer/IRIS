# ADR-023: Retrieval quality is measured separately from the ISO 9241-11 spine

## Status

**Accepted** — 2026-09-17 · **amended 2026-09-28 (IR-391)**.

**Amended — 2026-09-28 (IR-391): how a run is labelled, what it measures, and
how it is conducted.** See §Amendment — IR-391 below. The two-tier split, the
proxy-versus-thesis rule and the standing of each tier are unchanged; the
amendment restates the proxy rule rather than relaxing it.

**Does not supersede [ADR-011](011-evaluation-framework.md).** ADR-011 remains the evaluation spine for the thesis. This ADR adds a measurement ADR-011 does not contain and deliberately keeps it outside [ADR-011](011-evaluation-framework.md)'s framework.

**Consequence of [ADR-013](013-chunk-level-rag-pipeline.md) §Research Impact (amended 2026-09-04)**, which made RAG thesis-critical. A thesis-critical contribution with no measurement is an assertion.

## Context

[ADR-011](011-evaluation-framework.md) settled **one framework: ISO 9241-11** — effectiveness, efficiency, satisfaction, in a defined context of use — and was explicit that GQM is a methodology subsection rather than a second framework. Its metrics are human-subject: task success rate, offices re-reviewed, preserved clearances, time-on-task, SUS. Its comparison is the within-subjects `CLEARANCE_AWARE` vs `RESTART_ALL` design from [ADR-004](004-restart-all-comparison-mode.md).

**None of that measures whether retrieval returns the right passages.** ADR-011 was written when the thesis contribution was the workflow alone. On 2026-09-04 [ADR-013](013-chunk-level-rag-pipeline.md) §Research Impact was amended to make RAG thesis-critical too, and no evaluation decision followed it.

IR-133 names recall@10. Nothing records why that metric, against what, or what counts as passing.

### What the corpus actually is, audited in the tree

| Finding | Detail |
|---|---|
| **No real corpus exists** | `backend/media/` holds 4,910 files whose entire content is the ASCII bytes `%PDF-1.7 fake bytes`. Two distinct hashes across all 4,910 |
| **One real document** | `docs/Kimi K3 Open Frontier Intelligence.pdf` — a Moonshot AI technical report, 1.8 MB. This is the "real 47-page submission" the chunker docstrings characterise against. It is not CIT-U research |
| **IR-116 is blocked on this, not on code** | Subtasks A–G of IR-89 are `Done`; IR-89 is still `In Progress` solely because H ("End-to-end ingestion on a real thesis") has no thesis to ingest |

Acquiring real CIT-U submissions requires author and institutional permission. That is a **people problem with weeks of lead time**, and no amount of engineering velocity compresses it.

## Decision

**Retrieval quality is measured as an information-retrieval property, outside [ADR-011](011-evaluation-framework.md)'s framework and subordinate to it.**

**Two tiers, never conflated:**

| Tier | Corpus | Question it answers | Standing |
|---|---|---|---|
| **Pipeline validation** | Proxy — the Kimi K3 report plus openly-licensed theses | Does the pipeline work at all? Are chunks coherent, vectors written, passages relevant? | **Engineering gate.** Never cited as a thesis finding |
| **Corpus evidence** | Real CIT-U submissions | Does Ask IRIS retrieve well *on CIT-U research*? | **Thesis evidence.** The only tier that may be reported as such |

**A proxy-corpus number may never be presented as a finding about CIT-U research.** The two tiers answer different questions, and reporting the first as the second is the failure this split exists to prevent.

**The harness is built before the corpus arrives.** The question-set format, the recall@k runner and its command are code, testable against a small fixture corpus. Building them now means the corpus is the only thing tier 2 waits on.

**Corpus acquisition is a tracked, human-owned dependency**, started before the code it blocks — not discovered at the end.

**The metric is recall@10 over a labelled question set**, each question naming the passages that should be retrieved. Reported with and without reranking, which [ADR-015](015-voyage-embedding-and-reranking.md)'s two-stage design makes a configuration change rather than a code path.

## Alternatives Considered

**Fold retrieval quality into [ADR-011](011-evaluation-framework.md) as a domain metric under "effectiveness".** Rejected. ADR-011's "context of use" does permit context-specific measures, so this is defensible on the letter. But ISO 9241-11's effectiveness is *a user completing a task*, and recall@10 is a property of a ranking measured without a user present. Filing it under effectiveness means the framework no longer describes one kind of thing, which is the exact dilution ADR-011 exists to prevent.

**No formal retrieval evaluation — demonstrate the feature and describe it.** Rejected. This is what [ADR-013](013-chunk-level-rag-pipeline.md)'s amendment made untenable: a thesis-critical contribution needs a result, and "it looked right in the demo" is not one. It is also the cheapest thing for a panel to attack.

**LLM-as-judge on generated answers instead of recall on retrieved passages.** Rejected as *primary* evidence. It measures the answer rather than the retrieval, so a good judge score cannot distinguish good retrieval from a model covering for bad retrieval. It is also circular when the judge and the generator come from the same vendor family. Fine as a secondary signal; not the finding.

**Wait for the corpus before building anything.** Rejected. It idles the entire foundation effort on a dependency with unknown lead time, and every ticket in that effort is testable against fakes.

## Decision Rationale

The split is the whole decision. Without it there are two bad outcomes and no good one: either the team measures nothing until real papers arrive — which may be after the defence — or it measures against convenient documents and quietly lets that number stand in for a claim about CIT-U research.

Naming the proxy tier an engineering gate makes it usable immediately and unusable as evidence, which is exactly the standing it should have.

## Consequences

- IR-133 splits: a harness ticket that proceeds now, and a measurement ticket blocked on the corpus.
- A corpus-acquisition ticket exists, is owned by a person, and starts before the code tickets. It blocks IR-116 as well.
- `docs/testing/TRACEABILITY.md` gains the retrieval metric as a distinct row from [ADR-011](011-evaluation-framework.md)'s ISO measures.
- The 4,910 stub files in `backend/media/` must not reach the ingestion backfill; a run against the current database would attempt 4,910 Docling extractions of 16-byte files.
- If the corpus never arrives, the thesis reports tier 1 honestly, as pipeline validation, and says the corpus evidence was not obtained. That is a real finding and a defensible one. Silently promoting tier 1 is not.

## Amendment — 2026-09-28 (IR-391): labels, two measures, one change at a time

Written alongside [ADR-033](033-hybrid-retrieval-and-passage-selection.md),
whose techniques all ship off and are switched on only on a run of this
harness. That rule makes the harness a gate rather than a report, so four
things about it have to be settled rather than left to the implementation.

### A label points at a Record, a page and a quote — never a chunk id

A question's expected passages are labelled as **`(record, page, short
quote)`**. A chunk id is not a stable identifier: `apps/ai/repositories.py`
replaces a `ChunkSet` **wholesale** when a document is re-chunked, so every
label in the question set would silently stop matching the moment the chunking
policy or the token ceiling changed — and those are exactly the things the
harness is used to evaluate. A record, a page and a quote survive re-chunking,
and are also what a human labeller can actually read off a PDF.

### Every run reports two measures, not one

| Measure | Over what | What it catches |
|---|---|---|
| **Retrieval recall** | The passages retrieval returned | Whether the right passage was found at all |
| **Final-set recall** | The passages actually sent to the model | Whether it survived the relevance cut-off, the per-paper cap and the token budget |

Retrieval recall alone was sufficient when nothing stood between retrieval and
the prompt. ADR-033 §3–§4 puts three filters there, each able to discard a
correctly retrieved passage, so a run that reports only the first measure can
show a healthy number for a configuration that sends the model nothing useful.
**Recall@10 stays the retrieval figure** this ADR already chose; the second
measure is reported next to it, never instead of it.

### Comparison is one change at a time against a fixed baseline

A run compares **exactly one** changed setting against a baseline whose
configuration is recorded with the result. No combination matrix: with six
switches it is a large grid of vendor-paid runs whose interactions this corpus
is far too small to resolve, and the output would be an unattributable "the
stack got better". One change, one before, one after, and a named reason to
move a default.

### Divergence — IR-394: the harness warns about two changes, it does not refuse them

**Recorded, not decided.** "A run compares **exactly one** changed setting"
(above) is stated as an absolute. `apps/ai/evaluation/techniques.py` permits a
run to move more than one switch and **warns loudly** instead of refusing,
because two of the six settings are one technique: ADR-033 §1–§2's fusion does
nothing unless keyword retrieval also participates, so a code-enforced cap of
one would make that technique unmeasurable.

Per `CLAUDE.md`'s source-of-truth rule this contradiction is written down
rather than silently reconciled. **It awaits a human decision**, which is
either to ratify this reading (the rule governs what a run *means*, and a
multi-switch run is attributable only when the switches are one technique) or
to have the harness refuse and give fusion a single setting. Until then the
discipline holds by convention, as it did before the switch existed.

### A run is a manual command, never CI

The harness is a management command a person runs deliberately. It spends
Voyage credits on every question in the set, so putting it on a push or a
schedule turns the evaluation budget into a function of commit frequency. This
also keeps `015-voyage-embedding-and-reranking.md`'s disclosure gate under a
human decision at the moment of spending.

### Restated, because ADR-033 makes it load-bearing

**Proxy-corpus results decide engineering switches and are never cited as
findings about CIT-U research.** ADR-033's defaults move on proxy-corpus runs,
which is a legitimate tier-1 use — an engineering gate. The number that moved a
default is not evidence about CIT-U research and does not become so by having
been acted on.

## MVP Impact

None on scope. The foundation effort proceeds against fakes and the proxy corpus.

## SaaS Impact

The harness is per-instance. Under [ADR-005](005-instance-per-tenant.md) each tenant's corpus differs, so a recall number is a property of one instance and does not transfer between them.

## Security Impact

The proxy corpus must be openly licensed. Real CIT-U submissions used for evaluation stay inside the deployment and remain subject to [ADR-015](015-voyage-embedding-and-reranking.md)'s disclosure gate — an evaluation run is an outbound vendor call like any other, and an embargoed record is no more disclosable because a test is what is reading it.

## Deployment Impact

None. The harness is a management command, not a service.

## Research Impact

This is the ADR that makes the RAG half of the thesis measurable. It also records, deliberately, that the measurement may come back weak — a low recall@10 on real CIT-U papers is a valid finding about applying chunk-level RAG to this corpus, and is reported rather than tuned away.

## Related Requirements

FR-M4, NFR-P2 — stable labels only, per the frozen-SRS rule.

## Related Tasks

IR-133 (splits), IR-116 (unblocked by corpus acquisition), IR-89. **IR-391** (this amendment), IR-394 (the harness measures what the model received, with labels that survive re-chunking).
