# Extraction vendor comparison: LlamaParse vs Unstructured

**Purpose.** Evidence for ADR-056's vendor choice (IR-837). Every claim below is taken from the vendor's own public documentation, read on 2 November 2026. Where a document is silent, this says **not published** rather than guessing. Nothing here was measured on IRIS papers; the acceptance check in ADR-056 decision 14 is what measures.

**Sources read.**
- **LlamaParse:** 65 pages under `developers.llamaindex.ai/llamaparse/`: Parse, Extract, general, enterprise-readiness, self-hosting.
- **Unstructured:** 205 pages from `docs.unstructured.io/llms-full.txt`: Transform, Pipelines and workflow nodes, concepts, business, support. Connector pages were excluded except PostgreSQL.

Paths below are relative to those two sites.

## 0. Two Unstructured products, and which one a feature lives in

Unstructured's docs describe two overlapping ways in, and features differ between them:

| | **Transform `/api/v2/parse`** | **On-demand jobs `/api/v1/jobs` (workflow nodes)** |
|---|---|---|
| Sign-up | self-serve at `transform.unstructured.io` | the Transform quickstart uses it with a Transform key (`api-reference/transform/quickstart/embed`). But other pages say "Pipelines is sold separately from Transform. To purchase Pipelines, contact Unstructured Sales" (`overview-developer-guide`) |
| Controls | `profile` (`balanced`/`best`), one enrichment (`image_description`) | choice of strategy (Fast / High Res / VLM / Auto), VLM provider and model, chunkers, enrichments, embedder |
| Element metadata | thin public schema: `page_number`, `coordinates`, `text_as_html`, `parse_confidence` (`transform/api/parseRun`) | full schema: `category_depth`, `parent_id`, `coordinates`, `detection_class_prob`, `image_base64`, `languages`, `links` (`concepts/document-elements`) |
| Limits | 100 MB per document (`transform/limits`) | 10 files per job, 50 MB per file, 5 jobs at once per workspace on SaaS (`api-reference/transform/quickstart/embed`) |

**Which account gets which nodes is not clear from the docs.** Confirm with Unstructured before relying on any jobs-only feature. That includes the Voyage embedder, model choice, table merging, the hierarchy fields and image extraction.

LlamaParse has one Parse API (v2), plus separate Extract, Classify, Split, Verify and Index products under one key and one credit balance (`general/billing`).

## 1. Structure IRIS's citations depend on

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Element types | Fixed, documented: `text`, `heading`, `table`, `image`, `list`, `code`, `link`, `header`, `footer` | Jobs: documented list including `Title`, `NarrativeText`, `ListItem`, `Table`, `Image`, `Formula`, `Header`, `Footer`, `FigureCaption`, `PageNumber`. `/api/v2`: `type` is a free string | LP `parse/guides/response-format`; U `concepts/document-elements`, `transform/api/parseRun` |
| Heading hierarchy | `heading.level` 1–6 | Jobs: `category_depth` + `parent_id`, "more sophisticated hierarchy detection" on the hosted API only. `/api/v2`: none | LP response-format; U `concepts/document-elements`, `overview-developer-guide` |
| Box unit | page points (`x`,`y`,`w`,`h`) in the page's own frame; rotation already applied | pixel space (`points` + `system` with layout width/height), described for High Res. `/api/v2`: "coordinate projection when requested", shape not specified, and "some elements might not include" it | LP `parse/features/layout-and-bounding-boxes`; U `concepts/document-elements`, `transform/parse` |
| Finer boxes | word, line and table-cell boxes with byte spans into the text (`granular_bboxes`); per-box confidence where available | element-level only | LP layout-and-bounding-boxes, response-format |
| Running headers/footers | separated as `header`/`footer` items and markdown fields | `Header`/`Footer` element types | both |
| Printed page numbers ("v", "A-3") | `printed_page_number` | not published | LP response-format |
| Reading order | items per page in document order | elements in order | both |

**Edge: LlamaParse** on box precision and fixed types. Unstructured's jobs path closes most of the hierarchy gap, subject to section 0.

## 2. Content types

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Tables | `rows`, `html` (merged cells kept), `csv`, `md`. Cross-page merge (`merge_continued_tables`) and quality flags (`parse_concerns`: 9 kinds, e.g. `inconsistent_row_cell_count`, `scanned_page_table`) | `text_as_html` (High Res/VLM). Table-to-HTML and table-description enrichments. Cross-page merge is an **LLM** node (`chunk_by_table_merging`, with a confidence threshold) | LP `parse/features/tables`, response-format; U `concepts/enriching/table-to-html`, `.../chunker-chunk-by-table-merging` |
| Figures | `image` items with box and printed `caption`. Saved crops, embedded images or page screenshots by presigned URL. Chart values as tables (`specialized_chart_parsing`) | `Image` elements. `image_base64` for High Res image/table elements. **Image descriptions built in**: `type`, `description`, and for graphs `data` and `texts` | LP `parse/features/charts-and-figures`; U `concepts/enriching/image-descriptions` |
| Formulas / LaTeX | No formula item type. "Equations" named only as an `agentic_plus` use case; LaTeX output **not published** | `Formula` element type exists; LaTeX output **not published**. The word "LaTeX" does not appear in the docs | LP `parse/guides/tiers`; U `concepts/document-elements` |
| Scans / OCR | OCR on any page without a text layer; language list; phone-photo correction; `fast` runs no model | OCR built in. Generative OCR enrichment (a VLM rewrites text blocks); fine-tuned OCR models on the hosted API only | LP `parse/features/ocr-and-languages`; U `concepts/enriching/generative-ocr`, `overview-developer-guide` |
| Code, links, forms | `code` (with language), `link`. Forms and checkboxes (beta, +10 credits/page) | `CodeSnippet`, links, `FormKeysValues` | both |
| Watermarks | `watermark` text per page | not published | LP response-format |

**Edge: mixed.** LlamaParse is stronger on tables and figure crops. Unstructured has image descriptions built in. **Neither documents LaTeX**, so ADR-056's formula check applies whichever vendor is chosen.

## 3. Quality signals

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Per-element | box `confidence` where available | `parse_confidence` 0–1: "how closely the element text agrees with OCR text", **not** a probability (`/api/v2`). `detection_class_prob` (High Res) | LP response-format; U `transform/parse-response`, document-elements |
| Per-page / document | page `confidence`. High-effort judge (+5 credits/page) adds document mean, worst page, pages scored | not published | LP `parse/guides/configuring-parse` |
| Failed pages | per-page `success: false` with error; `allowed_page_failure_ratio` | `warnings` on `completed_with_warnings` | LP response-format; U parseRun |

**Edge: split.** Unstructured's per-element OCR agreement directly flags text a model may have changed, which matters when a Passage must quote the page. LlamaParse gives page- and document-level judgement.

## 4. Long documents, throughput, failures

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Size and pages | 512 MB, 10,000 pages | `/api/v2`: 100 MB, page limit not published; "took too long… try splitting it". Jobs: 50 MB per file | LP `general/limitations`; U `transform/limits`, parseRun |
| Timeouts | settable: base up to 2 h plus up to 5 min per page | `/api/v2` waits up to 15 min synchronously, otherwise 202 + job | LP limitations; U `transform/parse` |
| Concurrency | 5 parse jobs (Free/Starter), 20 (Pro), 100 (Enterprise) | Jobs: 5 per workspace on SaaS, 1 queued submission/s. `/api/v2`: "no public values… treat as unknown" | LP `general/billing`; U quickstart, `transform/limits` |
| Rate limits | published per endpoint, same on every plan; 429 has no `Retry-After` | Pipelines: published per action, 429 with `Retry-After` | LP `general/rate_limits`; U `support/issues/quota-billing-rate-limiting` |
| Error codes | about 19 documented, including `PDF_IS_PROTECTED`, `DOCUMENT_TOO_LARGE`, `TIMEOUT`, `CONTENT_POLICY_REFUSAL` | about 26 in `/api/v2`, including `could_not_parse`, `rate_limited`, `profile_temporarily_unavailable`, `quota_exceeded` | LP `general/troubleshooting`; U parseRun |
| Async | job + poll, webhooks; SDK retries 429/5xx | 202 + `Location`, server-sent progress events, cancel; webhooks/notification channels | both |

**Edge: LlamaParse** on long theses: published limits and settable timeouts. Note `CONTENT_POLICY_REFUSAL`: a model can decline to transcribe content.

## 5. Reproducibility and API stability

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Version pinning | `tier` + dated `version` **required** on every request. Pinned versions "stay available for the foreseeable future" | `/api/v2`: `profile` only. Jobs: model IDs set per node, but "if a workflow specifies a deprecated model that has a replacement, Unstructured uses the replacement model instead", a silent change | LP `parse/guides/tiers`; U `api-reference/workflow/models` |
| Recent churn | v1 → v2: parameters renamed (`do_not_cache` + `invalidate_cache` → `disable_cache`); `llama-cloud-services` package and Index v1 deprecated | Transform `/api/v2` is new, with an "earlier" Transform workflow alongside it; SDK connector classes deprecated; product docs partly inconsistent (section 0) | LP `parse/guides/migration-v1-to-v2`; U `transform/api-version-compatibility`, `api-reference/workflow/migration` |

**Edge: LlamaParse** on reproducibility. Both are changing quickly in 2026.

## 6. Privacy, retention and who sees the pages

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Upload retention | 48 h, then permanently deleted; deletable on demand | 24 h scratch storage; deletable | LP `general/data_retention`; U `transform/retention` |
| Result retention | not published (a 404 means expired) | not published (`result_expires_at` when present). Deleting a job does not synchronously remove source/output files | same |
| Cache | 48 h; `disable_cache: true` in v2. This replaces v1's `do_not_cache`, which explains the earlier naming conflict | not published | LP `parse/guides/migration-v1-to-v2`, configuring-parse |
| Training on customer data | not by default; opt-in programme only | "not used to train models" is stated for **dedicated instances**; for shared SaaS, **not published** | LP `general/enterprise-readiness/data-privacy-security`; U `business/dedicated-instances/security/security-common-questions` |
| Model providers seeing pages | Own model (OCRia-1) on `cost_effective`/`agentic`. States ZDR and no-training agreements with the LLM providers its managed service uses; custom prompts use a general model | VLM strategy defaults to Anthropic `claude-sonnet-4-6` through Unstructured's key. You may pass `provider_api_key` or pick provider and model (Anthropic, OpenAI, Bedrock, Vertex), so pages can go through **your own** account and terms | LP data-privacy-security, tiers; U `.../partitioner-vlm`, `business/ai-providers` |
| Ephemeral processing statement | not published | "does not store customer data long-term… removed upon completion or failure" (dedicated instances) | U security-common-questions |

**Edge: split.**
- **LlamaParse** publishes clearer retention and training terms for its standard service, and uses its own model by default.
- **Unstructured** lets IRIS choose, and pay for, the model provider directly, and its strongest privacy statements cover dedicated instances.

Neither mentions the Philippine Data Privacy Act; that stays IR-123's question.

## 7. Compliance, deployment, regions

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Certifications stated | SOC 2 Type II; GDPR (EU DPA, SCCs, Article 27 representative); HIPAA BAA (Enterprise); DPA, MSA, NDA; third-party pen tests | SOC 2 Type 1 and 2, ISO 27001, GDPR, HIPAA, FedRAMP, CMMC 2.0 Level 2; trust portal | LP `general/enterprise-readiness/compliance`; U `business/security-compliance/overview`, `pipelines/overview` |
| Shared SaaS regions | North America (us-east-1), EU (eu-central-1) | not published | LP `general/regions` |
| Dedicated / private | single-tenant SaaS; BYOC or self-host on Kubernetes (Enterprise): Postgres, MongoDB, Redis, Temporal and S3, still calling OpenAI/Anthropic/Google with your keys | dedicated instance in AWS/Azure regions **including Singapore, Tokyo, Seoul, Mumbai and Sydney**; in-VPC on AWS/Azure/GCP with your own AI provider keys; private links | LP `self_hosting`, `self_hosting/architecture`, `self_hosting/faq`; U `business/dedicated-instances/overview`, `business/overview` |
| Support / SLA | Slack channel (Pro, Enterprise); SLAs negotiated for Enterprise; public status page | support portal; SLA in Business agreements; public status page | LP `general/enterprise-readiness/support`; U `support/request`, `support/status` |

**Edge: Unstructured** on breadth of certifications and on Asia-Pacific dedicated regions near the Philippines. Both private options are cloud deployments, not something the university server can host.

## 8. Embedding and chunking: the Voyage question

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Built-in embedding | Index v2 only, with the model "managed by LlamaCloud"; no choice, no Voyage. Index v1 (deprecated) offered OpenAI, Azure, Bedrock, Cohere, Gemini, HuggingFace | Embedder node: `voyageai` with `voyage-3`, `voyage-3-large`, `voyage-3-lite`, `voyage-code-2`/`-3`, `voyage-finance-2`, `voyage-law-2`, `voyage-multimodal-3`; also Azure OpenAI, Bedrock, IBM. **`voyage-context-4` (ADR-015) is not listed** | LP `cloud-index-v2/migration-v1-to-v2`; U `api-reference/workflow/models` |
| Built-in chunking | Index v2: fixed sentence chunks, 1,024 tokens, 200 overlap | by title, page, character or similarity; LLM "contextual" chunking that prepends context to each chunk; LLM table merging | LP same; U `concepts/chunking`, `.../chunker-chunk-by-contextual` |
| Writing to IRIS's Postgres | Index v2 can't (managed store only); export instead | PostgreSQL/pgvector destination connector (Pipelines) | LP same; U `pipelines/destinations/postgresql` |

**What this means for IRIS, given ADR-015 and ADR-056 decision 13.** IRIS embeds with `voyage-context-4`, which reads each chunk in the context of its whole paper, through IRIS's own chunk sets, disclosure gate and spend admission. Unstructured's Voyage embedder would only help if IRIS also:

- switched to the `voyage-3` family, losing contextualized embeddings and invalidating the measured recall@10 baselines (ADR-023)
- let Unstructured chunk and write vectors itself, bypassing ADR-041 admission, ChunkSet swaps and the one visibility predicate

**With IRIS's current design, neither vendor's embedding is used; IRIS calls Voyage itself either way.** Unstructured's chunkers are the richer toolkit if that design ever changes.

## 9. Local and open-source options

| Criterion | LlamaParse | Unstructured | Evidence |
|---|---|---|---|
| Open-source parser | **LiteParse**: Apache-2.0, Rust, no LLM, Tesseract OCR, line boxes, page-complexity routing (`needs_ocr`, `multi-column`, `table-likely`) | **`unstructured` library**: Apache-2.0, Python. Lacks the hosted fine-tuned OCR, newer vision models, image extraction, by-page/by-similarity chunking and better hierarchy (vendor's own list) | LP `/liteparse/`, `/liteparse/guides/complexity`; U `overview-developer-guide` |
| Same engine as hosted? | No: LiteParse is text and layout only | No: hosted adds the models above | both |

**Edge: even.** Both have a real open-source library and neither is the hosted engine. Unstructured's library is more general (many file types, chunking). LiteParse is lighter and adds per-page routing.

## 10. Price for a 100-page thesis

Published self-serve rates. "All extras" means what ADR-056 decision 3 asks for.

| Configuration | LlamaParse | Unstructured |
|---|---|---|
| Rate basis | $1.25 per 1,000 credits (`general/pricing`) | $0.015 per page, "any file type and any pipeline", including model costs on SaaS plans (`transform/billing`, `business/ai-providers`) |
| Basic structured parse | `cost_effective` 3 cr/page = **$0.38**; `agentic` 10 cr/page = **$1.25** | **$1.50** |
| With ADR-056's extras | `agentic` 10 + high-effort confidence 5 + layout extraction 3 = 18 cr/page = **about $2.25**. Cost Optimizer lowers simple pages to 3 cr. Granular boxes have no listed price | **$1.50**, image descriptions included |
| Figure descriptions | not offered; IRIS's `describe_figure` through OpenRouter (separate cost) | included |
| Cited front-matter fields | Extract on an already-parsed job: extract tier only (cost-effective 5, agentic 15 cr/page). The first 5 pages on agentic = **about $0.09** | Extract: per-page price not separately published |
| Free allowance | 10,000 credits **every month** (Free plan) | 10,000 pages **once per account** |
| Paid plans | Starter $50/mo (40k cr), Pro $500/mo (400k cr) | pay-as-you-go; volume pricing via sales |

**Edge: Unstructured** on price and predictability for the "everything on" configuration. **LlamaParse** is cheaper if IRIS uses `cost_effective` or Cost Optimizer and skips the paid add-ons.

## 11. Other products that touch IRIS

- **LlamaParse:** Classify, Split (segmenting combined PDFs) and **Verify**, which reviews PDFs "for signs of local tampering or synthetic fabrication" (possibly relevant to research integrity, not evaluated). Batches of up to 10,000 files (Pro and up).
- **Unstructured:** NER and PII redaction nodes ("best-effort", explicitly "not a compliance mechanism on its own"), regex and LLM structured extraction, 50+ source and destination connectors.

## 12. Corrections to earlier statements in this design session

1. "Unstructured has no heading levels." True of `/api/v2` only. The jobs path returns `category_depth` and `parent_id`, subject to section 0.
2. "LlamaParse's two no-cache flags conflict." Resolved: `do_not_cache` is the v1 name, replaced in v2 by `disable_cache`.
3. "Unstructured's 10,000 free pages." They are once per account, not monthly.
4. "Unstructured's built-in Voyage." It lives on the jobs/Pipelines path and covers the `voyage-3` family, not `voyage-context-4`.

## 13. Summary

| Area | Stronger | Why |
|---|---|---|
| Citation precision (boxes, printed pages) | LlamaParse | word/line/cell boxes in page points; printed page numbers |
| Heading structure | LlamaParse (`/api/v2`) · even (Unstructured jobs) | levels vs depth/parent, subject to account access |
| Tables | LlamaParse | grid + flags + merge without an LLM call |
| Figure descriptions | Unstructured | built in, priced in |
| Formulas | neither proven | neither documents LaTeX |
| Text-matches-page check | Unstructured | per-element OCR agreement |
| Long theses | LlamaParse | 10,000 pages, settable timeouts |
| Reproducibility | LlamaParse | required dated versions; Unstructured silently replaces deprecated models |
| Published privacy terms (shared service) | LlamaParse | 48 h deletion, no training by default, provider agreements |
| Choice of model provider and terms | Unstructured | your own key and provider per node |
| Certifications | Unstructured | wider list, including ISO 27001 |
| Asia-Pacific hosting | Unstructured | dedicated instances in SG, JP, KR, IN, AU |
| Price, everything on | Unstructured | $1.50 vs about $2.25 per 100 pages |
| Price, minimal | LlamaParse | $0.38–$1.25 |
| Free allowance | LlamaParse | monthly vs once |
| Voyage `voyage-context-4` | neither | IRIS calls Voyage itself either way |
| Open source | even | both Apache-2.0, neither is the hosted engine |
| Clarity of product and docs | LlamaParse | Unstructured's Transform vs Pipelines entitlements are ambiguous |

**Reading this for IRIS without weighting it for you.**
- **LlamaParse** is stronger where IRIS's thesis contribution sits: precise, reproducible citations into long theses.
- **Unstructured** is stronger on cost with everything on, built-in figure descriptions, a direct check that quoted text matches the page, certifications, regional hosting, and control over which model provider sees the pages.

**What would settle it**, whichever you lean towards:
1. Run the ADR-056 decision 14 acceptance check on both, on the same 40 proxy papers.
2. Get Unstructured to confirm in writing which features a self-serve account includes.

