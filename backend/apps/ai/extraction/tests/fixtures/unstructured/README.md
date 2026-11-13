# Unstructured recordings (IR-984)

What Unstructured's Transform API (`POST /api/v2/parse`) returns for the four
synthetic PDFs in `../`, recorded once for ADR-067's spike gate. The client
(IR-985) and shaping (IR-986) build against these files, through
`../../unstructured_vendor.py`, so CI never calls the vendor.

The PDFs are synthetic, written from `../layouts.py`. They are not Manuscripts,
so the consent and embargo gate does not apply.

Recorded on 2026-11-13 with `output=elements`, `profile=balanced` and
`include=coordinates&include=table_html`, with no `Prefer` header. What they
show is in `docs/evaluation/runs/2026-11-13-unstructured-spike/report.md`.

**Do not hand-edit a recording.** If the format is wrong, re-record it here.

## What each folder holds

| File | Contents |
|---|---|
| `result.json` | The raw parse result: `elements` with `metadata.coordinates`, `text_as_html` and `parse_confidence`, plus `status`, `profile`, `format_version`, `warnings` and `source`. Signed URLs are removed (none were returned). |
| `manifest.json` | Endpoint, request options, HTTP status, `Location` if a 202 came back, polls, job id, latency, response headers (minus cookies and keys) and the PDF's SHA-256. |

## Re-recording

Manual only. It needs a development key. From `backend/`:

```bash
UNSTRUCTURED_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_unstructured
```

- Pass fixture names to record only some of them, e.g. `two_columns`.
- `--profile best` picks the other profile; `--wait N` sends `Prefer: wait=N`.
- `--pdf PATH --out DIR` records any other PDF **outside the repo**.
- `--measure DIR...` prints element types, coordinate coverage, table HTML,
  warnings and the reading-order check for recorded folders.

The script deletes the uploaded source (`DELETE /api/v2/upload/{id}`) and the
job (`DELETE /api/v2/jobs/{id}`) after every run that reaches a result or a
failure, and a refused delete fails the run.

Never commit the key, and never record a third-party paper here.
