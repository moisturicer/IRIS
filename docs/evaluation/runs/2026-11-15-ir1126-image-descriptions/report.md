# IR-1126: Unstructured's image descriptions against IRIS's describer

**Proxy tier (ADR-023).** Six openly licensed arXiv papers in `iris_ir1054`, the
papers behind IR-1125's figure set. Nothing here is a finding about CIT-U research.

**Verdict: the enrichment is worse on both checks, so IRIS does not adopt it.**
The ticket's rule was to switch only if the enrichment is no worse. No code for
it is kept: the partition endpoint IRIS uses never returns a description.

| Check | IRIS's describer (Claude Sonnet 5.5) | Unstructured enrichment (Claude Sonnet 5, via Unstructured) |
|---|---|---|
| Figures with a factual error (of 29) | **1** (1 major) | **14** (9 major, 5 minor) |
| Figure-set recall@10, reranking on | **0.931** (27/29) | **0.897** (26/29) |
| Where it can be requested | IRIS's own call | Jobs API only, not the partition endpoint |

## 1. Spike: is the enrichment accepted, and what comes back?

**The partition endpoint IRIS uses ignores it.** A `hi_res` call to
`POST https://api.unstructuredapp.io/general/v0/general`, carrying the field
`advanced_options={"enrichments": {"image_description": {}}}`, returned 200.
Each `Image` element's `text` was still OCR, and no description field appeared
(`spike-partition-endpoint.json`). Unstructured documents the enrichment only on
its Workflow/Jobs API. The partition endpoint's own parameter page lists none.

**The Jobs API does produce it.** The request was
`POST https://platform.unstructuredapp.io/api/v1/jobs/`, with IRIS's existing
Platform key and these `job_nodes`:

- `partition` / `unstructured_api` / `hi_res`
- `prompter` / `anthropic_image_description` / `claude-sonnet-5`

The job is asynchronous: create it, poll it, then download each node's output.
In the result, each `Image` element's `text` becomes a JSON string with these
fields:

- `type`: `diagram` or `graph`
- `description`
- `texts`
- `data`, for graphs: the read-off values

`metadata.enrichment_origins` names `anthropic` / `claude-sonnet-5`
(`spike-jobs-api.json`). Element ids match between a job's partition node and its
enrichment node. They do not match IRIS's earlier partition-endpoint read,
because the ids depend on the uploaded filename. For this measurement, the 29
Figures were therefore joined to the stored ones by page and box. All 29 matched
at a box overlap of 1.0, and no enriched image was left over.

**Billed pages: not measured.**
- The six papers are 78 pages, about $1.17 at $0.015 a page.
- The partition endpoint reports pages in `x-num-pages`. That header said 5 for
  the 5-page paper.
- The Jobs API returned no page or credit count, and no usage endpoint was
  found.
- Whether the enrichment costs anything beyond the page price can only be read
  from Unstructured's usage dashboard. A person with the account must check it.
  The spike jobs ran on 2026-11-14 at 22:33 and 22:34 UTC.

## 2. Quality: factual errors on the same 29 Figures

The full list is in `figures.json`, which gives both descriptions and a note
for each error.

- **Rubric:** *major* means a wrong axis, unit, value, range or structure.
  *Minor* means a wrong marker shape or colour only.
- **Coverage:** 27 of the 29 images were checked against both descriptions. The
  two not checked are flowcharts (n=1, n=2), and their two descriptions agree.
- **Unstructured's errors:**
  - axis units: two charts given as `ns` where the axis reads `ms`
  - a series' data range
  - a value range
  - circuit structure: gate span, brace groups, gate order
  - a point's position in a diagram
  - starting values
  - five marker or colour slips
- **Sonnet's one error:** a wire said to end at a node it passes through.
- Unstructured's descriptions are shorter: about 1,170 characters on average
  against Sonnet's 1,710. For graphs, it moves values into `data`, which IRIS
  does not store.

**Review:** the verdicts were drafted by an agent (Claude) on 2026-11-15, from the
images. The named reviewer is Jive Tyler Revalde. Their confirmation is recorded
as `"confirmed": false` in `figures.json` until they sign it.

## 3. Retrieval: `eval_retrieval` on IR-1125's figure set

**Setup:**
- `AI_RERANKER_READS=fallback`, reranking on, k=10, retrieved as
  `student@cit.edu`.
- Two trial chunk sets with the same spec,
  `unstructured:labeled-structure-v1:max_tokens=2000`, built over the 43
  Unstructured-read papers.
- The only difference between them is the stored description on these 29
  Figures. The Sonnet text was swapped out for the second set and restored after
  it (29 of 29 checked).

**Results:**

| Arm | recall@10 | final-set recall | Missed | Run file |
|---|---|---|---|---|
| Sonnet | 0.931 | 0.931 | fig10, fig13 | `retrieval-sonnet.json` |
| Unstructured | 0.897 | 0.897 | fig10, fig13, fig18 | `retrieval-unstructured.json` |

The Sonnet arm reproduces IR-1125's arm C (0.931). One question separates the
two arms: Sonnet answers it and the enrichment does not. That is too few to
separate them statistically. It is reported because the ticket asks whether the
enrichment is *no worse*, and on this set it is not better on any question.

Voyage spend: about 131,500 new embedding tokens across both trial sets
(118,284 for the first, 13,223 for the second; under $0.02 by the command's
estimate), plus the rerank calls.

## 4. Data path (for the ADR-067 amendment)

- **Where the enrichment runs:** inside Unstructured's job, and it calls
  **Anthropic**. The provider and model are named per request in the node
  settings, and the output records them in `enrichment_origins`.
- **Whose key:** Unstructured's AI-providers page says SaaS plans use models
  Unstructured provides, with their cost "already factored into the pricing
  structures". Customer keys apply only to dedicated or in-VPC deployments. So
  on IRIS's plan the call is made **under Unstructured's key**.
- **Retention and training:** no Unstructured page read states either terms
  for the enrichment's model calls or zero data retention.
- **Inputs kept by Unstructured:** the job stores input files under an
  `ephemeral` job, and its output names an internal `data_source` path.
  How long those are kept is not stated.

## Cost of this measurement

| Item | Cost |
|---|---|
| Unstructured | about $1.25: 83 pages (78 in jobs, 5 in the partition spike), before any enrichment charge |
| Voyage | under $0.02 of embeddings, plus 58 rerank calls |
