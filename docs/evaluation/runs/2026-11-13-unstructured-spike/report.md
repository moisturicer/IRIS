# Unstructured spike (IR-984): what Transform returns, and the go/no-go

**Result: NO-GO.** Under ADR-067 decision 2's spike gate, reading order fails the
`two_columns` fixture. It fails under both profiles. Coordinates pass: 0 of 939
text elements on the proxy papers lack one. A text element is one whose text is
non-blank and whose type is not `Image`. Counting `Image` elements as well, all
1,056 proxy elements have a box.

Recorded 2026-11-13 against `POST https://transform.unstructured.io/api/v2/parse`
with `output=elements`, `include=coordinates&include=table_html` and
`profile=balanced` (one `best` run on `two_columns`, below). The proxy papers are
proxy tier (ADR-023): **never a finding about CIT-U research**.

| Input | Where |
|---|---|
| 4 synthetic fixtures | raw results and manifests committed under `backend/apps/ai/extraction/tests/fixtures/unstructured/`; counts in `fixtures_measurements.json` |
| 6 proxy papers (`docs/evaluation/proxy_ir851_six.json`) | third-party text, **not committed**; counts only, in `measurements.json` |
| `two_columns` on `profile=best`, and with `Prefer: wait=0` | raw results and manifests in `two_columns_best/` and `two_columns_wait0/` beside this report (synthetic fixture) |
| Recorder | `backend/apps/ai/extraction/tests/fixtures/record_unstructured.py` (`--measure` reproduces every count here) |

## The gate

| Rule (ADR-067 §2) | Measured | Verdict |
|---|---|---|
| Coordinates missing on >10% of text elements, proxy papers | 0 / 939 (0%) | pass |
| Reading order holds on `two_columns` | fails, `balanced` and `best` | **fail** |

What `two_columns` came back as (one page; left column then right column is the
expected order):

- **`balanced`** reads across the rows: one `NarrativeText` holds
  "Left column one opens. Right column one resumes.", then "Left column two
  continues. Right column two continues.", then "E = m c^2 Right column three
  ends.". Then "Left column three ends." follows as its own element.
- **`best`** gets the columns nearly right: one element holds left one, left two,
  `$$E = m c^2$$`, then right one to three. But "Left column three ends." still
  comes after the whole right column.

Both put left-column text after right-column text, so the rule fails. The
Platform API's `fast`, `auto`, `hi_res` and `vlm` strategies were also tried
(addendum below). None passes both rules. The
proxy papers were not scored for reading order: the gate names only the
fixture.

## The eight questions

### 1. Element types; heading levels?

Proxy papers: `NarrativeText`, `Title`, `Header`, `Footer`, `ListItem`, `Image`,
`Table` and `FigureCaption`. Fixtures add `PageNumber`. **No `Formula`,
`Address`, `EmailAddress`, `CodeSnippet` or `PageBreak` element appeared.**

**No heading level of any kind.** Every element's `metadata` has exactly
`page_number`, `coordinates`, `text_as_html` and `parse_confidence`. There is no
`category_depth`, `parent_id`, `emphasized_text_*`, `detection_class_prob`,
`languages` or `links`, and no field outside `element_id`, `type`, `text` and
`metadata`. All headings are flat `Title`s, e.g. "3. REPRESENTATION…" and "3.1.
Signal representation…" alike. On `figures` every element, title included, came
back as `NarrativeText`.

### 2. Coordinates

Each box is `{points: [[x,y]×4], system: "PixelSpace", layout_width,
layout_height}`, with four corners in the order top-left, bottom-left,
bottom-right, top-right. The units are pixels of a rendered page:
`layout_width`/`layout_height` are 2125×2750 for a US Letter fixture, which is
250 dpi, so points = pixels × 72/250. Every element on every proxy paper and
fixture has one. An element that spans pages carries an **array** of boxes,
each with its own `page_number`; the `table_across_pages` table did.

Boxes are per element only. `two_columns`' merged paragraph has a box spanning
both columns, which is too coarse for a citation highlight. ADR-067 §5's word
matching inside the element box is therefore the only route to line-level
highlights.

### 3. Image bytes?

**No.** The API has no option for image bytes, and no `image_base64` or any
other image field appears. An `Image` element carries text only: 116 of 117
proxy `Image` elements have some, usually OCR'd labels or LaTeX. Image
descriptions (`advanced_options.enrichments.image_description`) were not
requested. ADR-067 decision 10 (Figures from `image_base64`) cannot be built
on this API. IRIS would have to crop the PDF itself.

### 4. Table HTML on `table_across_pages`

Present and good. The table is one `Table` element on pages 1–2, with two
boxes. Its `text_as_html` is one `<table>` with a `<thead>` (`Sample`,
`Mass`) and 30 body rows, `Row 01 / 401 g` to `Row 30 / 430 g`. Unstructured
merged the two halves itself. Proxy papers: 26 tables, all with HTML.

(The `--measure` reading-order check reports `false` for `table_across_pages`.
That is an artefact: the fixture's phrases are LlamaParse markdown
(`| Row 01 |`), not a reading-order fault. `figures` passes.)

### 5. Formulas

**LaTeX, without a `Formula` type.**

- **Inline maths** comes back as `$…$` inside `NarrativeText`, e.g. `$(\Omega,
  \mathcal{F}, \mathbb{P})$`: 355 proxy text elements.
- **Display equations** come back as `Image` elements whose text is `$$…$$`,
  e.g. `$$|A_x\rangle = \sum_{n=0}^{N-1} x(n) |n\rangle \, .$$`. 36 `Image`
  and 36 `FigureCaption` elements carry LaTeX.
- **On the fixtures**, `balanced` returned `E = m c^2` and `a^2 + b^2 = c^2`
  as plain text, and `best` returned `$$E = m c^2$$`.

So ADR-067's mapping (`Formula` → formula) would find nothing. Formulas would
have to be recognised by delimiters, as ADR-056 did for LlamaParse, and an
`Image` would have to be told apart from a display equation.

### 6. Model or version for provenance

**Nothing beyond `profile` and `format_version`.**

- **Body:** `profile: "balanced"` and `format_version: "2.0"`, nothing else
  identifying.
- **Response headers:** only `date`, `content-type`, `transfer-encoding`,
  `connection`, `server: uvicorn` and, on a 202, `preference-applied` and
  `location`.
- **Effect:** ADR-067 decision 3 can record the request options, the profile
  and the format version, and nothing that names the model.

### 7. Pages billed, latency, warnings

**Pages billed are not in the response**: no usage, credit or page-billing
field. `metadata.page_count` is the only page figure. The spike sent 87 pages
in all: 6 fixture pages, 78 proxy pages, one page for the `best` run and two
for `Prefer: wait=0` (run twice; see question 8). All of it was within the free allowance, and no
402/403 came back.

| Paper (proxy) | Pages | Latency (s) | Text elements | Missing boxes | Tables |
|---|---|---|---|---|---|
| Expected Hypervolume Maximization… | 20 | 57.1 | 232 | 0 | 1 |
| Diverse Metallicities in Protoclusters… | 23 | 95.0 | 194 | 0 | 6 |
| State-Space-Based FIR Filtering… | 5 | 15.6 | 83 | 0 | 0 |
| Accelerating massive ensembles of ODEs | 17 | 78.4 | 239 | 0 | 6 |
| Noise-adjusted turnover… | 8 | 18.8 | 79 | 0 | 3 |
| MeshKV… | 5 | 22.5 | 112 | 0 | 10 |

That is about 3–4 s per page. Fixtures took 4.6–10.5 s each. **No
`warnings`, `failed_pages` or `degraded_pages`** on any run.

### 8. Async path

**Only on request.** Every call without a `Prefer` header returned **200**,
including the 23-page paper at 95 s. The server waits up to 15 minutes by
default. With `Prefer: wait=0`, `two_columns` returned **202** with
`Location: /api/v2/jobs/<id>`, a relative path, and `preference-applied:
wait=0`. Three polls of that path returned the completed result, with the same
five elements and boxes as the synchronous call.

**The poll needs `output=elements` and `include` again.** The first attempt
polled the bare `Location`. That job completed, but it came back as **markdown
with `elements: []`**, even though the parse request had asked for elements. The
jobs endpoint takes its own `output` and `include` query parameters and
defaults to markdown. The recorder now sends them on every poll, and
`unstructured_vendor.py` reproduces the markdown default, so IR-985's client
cannot miss it.

A client should send `Prefer: wait=0` and poll, rather than hold a connection
open for minutes.

## Addendum: the Platform API's strategies (2026-11-14)

Transform hides Unstructured's strategies behind its two profiles, so every
strategy was also run through the separate **Platform** API, using its own key:

- **`fast`, `auto` and `hi_res`** through the partition endpoint (`POST
  https://api.unstructuredapp.io/general/v0/general`), with coordinates, table
  structure and `extract_image_block_types` on.
- **`vlm`** through an on-demand job (`POST
  https://platform.unstructuredapp.io/api/v1/jobs/`). That endpoint rejects
  `strategy=vlm` with a misleading "file may be corrupted" error.

The requests and per-fixture counts are in `strategies.json`, and each
strategy's raw `two_columns` output is in `strategies/`.

| Strategy | `two_columns` order | Coordinates | Heading depth | Gate |
|---|---|---|---|---|
| `fast` | across the rows (L1, R1, L2, R2, …) | all | `parent_id` | fail (order) |
| `auto` | L1, L2, formula, R1–R3, **then L3** | all | `parent_id` | fail (order) |
| `hi_res` | same as `auto` | all | `parent_id` | fail (order) |
| `vlm` (default auto routing) | **correct**: L1–L3, then R1–R3 | **none** | `category_depth` + `parent_id` | fail (coordinates) |
| `vlm` (forced, JSON output) | **correct** | **none**: 0 of 81 on a 5-page proxy paper | `category_depth` + `parent_id` | fail (coordinates) |

**Every strategy fails one rule or the other**, so the result stays NO-GO.
The trade-off is structural, not a matter of settings:

- **Layout strategies** (`fast`, `auto`, `hi_res`, and Transform) know where
  every word sits but misread the column order.
- **The VLM** reads like a person but returns no boxes at all, so a citation
  could not highlight anything.

`--measure` reports `vlm` `two_columns` as failing. That is an artefact: the
model wrote `$$E = m c^2$$`. The raw output in `strategies/` shows the order is
right.

What the Platform strategies give that Transform does not:

- **Heading structure.** `parent_id` on every strategy, and `category_depth`
  on VLM.
- **A real `Formula` element type** (`auto`, `hi_res`, `vlm`).
- **Image bytes.** `image_base64` on `auto` and `hi_res` when
  `extract_image_block_types` is set; they were seen on Tables here.
- **Model provenance on VLM.** `metadata.enrichment_origins` names the provider
  and model: `anthropic` / `claude-sonnet-4-6` (forced), `claude-opus-4-5-20251101`
  (auto routing).
- **Personal data detection.** VLM marked an `Address` element on the proxy
  paper.

All of these sit on the side of the trade-off that fails the gate. VLM took
71 s for 5 pages.

## Other findings for IR-980's owner

- **Uploads and jobs were deleted after every run.** `DELETE
  /api/v2/upload/{id}` returned 204 and `DELETE /api/v2/jobs/{id}` was
  accepted. The docs say deleting a job does not delete its stored output at
  the same time, and Transform publishes no retention period for results.
  ADR-067 open condition 1 stays open.
- **No hierarchy, no image bytes, no `Formula` type.** Three of ADR-067's
  mapping rows (`category_depth`/`parent_id`, `Image` + `image_base64`,
  `Formula`) have nothing to map from this account.

## What follows from the rule

Per IR-984's go/no-go rule, the remaining Unstructured subtasks of IR-980 are
closed as "won't do" with this report linked. IR-982 (registry) and IR-983
(pricing) are unaffected, and LlamaParse stays (ADR-067 decision 2).
Recording the numbers in ADR-067 is its own change. Closing the tickets and
amending the ADR are for IR-980's owner.
