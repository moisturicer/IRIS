# LlamaParse recordings (IR-849)

What LlamaParse returns for the four synthetic PDFs in `../`, read once with
ADR-056's full request. Shaping (IR-840) and the LlamaParse Extractor (IR-841)
are both built against these files, so CI never calls the vendor.

The PDFs are synthetic, written from `../layouts.py`. They are not Manuscripts,
so the consent and embargo gate does not apply.

Recorded on 2026-11-02 in IR-841's development checkout, using IR-849's
script. IR-840 consumes the canonical recordings now committed by IR-841.
The four raw results, grounding files and manifests are unchanged. No image crops were
returned. The run cost 93 credits for six pages; see `OPEN_CONDITIONS.md` for
the observed formula, confidence and Figure limitations.

**Do not hand-edit a recording.** If IR-840 or IR-841 finds the format wrong,
re-record it here.

## What each folder holds

| File | Contents |
|---|---|
| `result.json` | The raw v2 result: `items`, `markdown`, page and document `metadata`, `job_metadata` and `job.usage.credits`. Presigned URLs are removed. |
| `grounded_items.jsonl` | The word, line and cell boxes (one row per page). LlamaParse returns these as a separate file. |
| `images/` | The `layout` figure crops. |
| `manifest.json` | The tier, the version, the full request, the `expand` list, the PDF's SHA-256, the job id and the credits charged. |

## Re-recording

Manual only. It needs a development key from the project owner. From `backend/`:

```bash
LLAMAPARSE_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_llamaparse
```

- Pass fixture names to record only some of them, e.g. `figures two_columns`.
- `--version` pins a different dated release. `latest` is refused. The
  default, `2026-09-28`, is the first release the docs name for watermark
  text, and was accepted for these recordings. LlamaParse rejects an
  unpublished date before parsing.
- `--base-url` picks the region. The default is North America. Region is still an open condition of ADR-056.

The script uploads each PDF, starts the job, polls it, then downloads the
result, the boxes and the figure images. It deletes the uploaded file in a
`finally` block, so the file is removed even when the job fails, and a refused
delete fails the run. The request sets `disable_cache`. Table quality flags and
watermark text have no request option: they arrive in `items` and `metadata`.

Never commit the key, and never record a third-party paper here.

## What one run costs

Four PDFs, **6 pages** in all. Per page, from LlamaParse's pricing page
(2026-11-02, $1.25 per 1,000 credits):

| Item | Credits per page |
|---|---|
| `agentic` | 10 (3 for a page Cost Optimizer sends to `cost_effective`) |
| `layout` images | +3 |
| High-effort confidence | +5 |
| Granular boxes, chart parsing | not priced on that page |

So about **108 credits ($0.14)**, plus whatever granular boxes and chart
parsing add. The real figure is in each `manifest.json` and in
`OPEN_CONDITIONS.md`. If billing has not reported credits by the time the
result is fetched, the manifest records `null` rather than lose a paid run.
