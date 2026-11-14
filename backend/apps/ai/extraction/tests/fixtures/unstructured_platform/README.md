# Unstructured Platform recordings (IR-985)

What the Platform partition endpoint (`POST https://api.unstructuredapp.io/general/v0/general`,
`strategy=hi_res`, ADR-067's 2026-11-14 amendment) returns for the synthetic PDFs in
`../` (IR-1101 added `paper_columns` and `ruled_table`), a blank page (`blank`) and bytes that are not a PDF (`rejected`, a 422).
`../../unstructured_platform_vendor.py` serves them, so CI never calls the vendor.
The Transform recordings in `../unstructured/` stay as IR-984's spike evidence.

Recorded 2026-11-14. **Do not hand-edit a recording**; re-record it. Manual only,
with a development key, from `backend/`:

```bash
UNSTRUCTURED_PLATFORM_API_KEY=... python -m apps.ai.extraction.tests.fixtures.record_unstructured_platform
```

Pass names (`two_columns`, `blank`, …) to record only some. Never commit the key,
and never record a third-party paper here.
