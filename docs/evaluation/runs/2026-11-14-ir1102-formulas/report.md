# IR-1102: formulas as exact LaTeX — transcription and retrieval

Proxy tier (ADR-023): an engineering gate, never a finding about CIT-U research.
Run 2026-11-14 on the four proxy papers the IR-984 spike read with Unstructured
`hi_res` (records 25, 38, 40, 58), from the spike's stored results and PDFs.

## 1. Transcription against the authors' LaTeX

`manage.py eval_formula_transcription` (`transcription.json`): each `hi_res`
Formula is shaped, cropped at 300 dpi by the production renderer, sent to
`anthropic/claude-sonnet-5.5` with the production prompt (version 1), and
scored with the spike's `formulas/latex_truth.py`.

| | Count |
|---|---|
| Formulas located | 36 |
| Transcribed | 36 |
| Exact after normalization | 32 |
| Similarity ≥ 0.95 | 34 |
| Typesets like the source (read by hand) | 35 |
| Cosmetic difference | 1 (`\frac` where the source has `\dfrac` with display-style integrals) |
| Mathematical error | 0 |

The spike measured 34 of 36 with no mathematical error. The four non-exact
replies were read by an agent against the arXiv source; each `hand` note is in
the run file, for a person to confirm. The file holds counts and scores only.

## 2. Retrieval with formulas in and out of the indexed text

`manage.py eval_retrieval --questions docs/evaluation/proxy_formulas.json`: 16
questions asked in words, each labelled with a LaTeX snippet of its formula as
the chunk shows it. Run on a copy of the dev database (`iris_ir1102`); on the
copy, the four papers' extractions were replaced by the stored `hi_res` reads,
their formulas cropped and transcribed (36 of 36), and the proxy papers given
AI consent, which the disclosure gate requires and the dev data lacks (IR-815).
The other 36 papers are unchanged in both arms.

| `formula_text` (`AI_FORMULA_TEXT_INDEXED`) | recall@10, no reranking | recall@10, reranking |
|---|---|---|
| off (`20261114-143930-proxy_formulas.json`) | 0.812 | 0.938 |
| on (`20261114-144142-proxy_formulas.json`) | 0.938 | 0.938 |

- On finds two more passages without reranking (f05, f06). With reranking,
  which is on in production, both arms miss only f07.
- One question is 0.062 of the score; sixteen questions cannot separate the
  arms under reranking. The default stays off (ADR-033 §5).
- Both arms show the LaTeX to readers: the switch moves only the embedded and
  keyword-indexed text.

## Found on the way

Voyage's reranker refuses an empty document, and an uncaptioned Unstructured
Figure chunks to empty `content`. The off arm's first run failed on it; reranking
now drops passages with no content before the call (`reranking.py`).
