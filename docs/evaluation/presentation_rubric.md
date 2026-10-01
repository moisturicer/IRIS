# Answer presentation — manual rubric (IR-424)

Not automated and not CI. An automated grader would be a second model judging
a first with no ground truth, and `eval_retrieval` measures recall only
([ADR-023](../adr/023-retrieval-quality-evaluation.md)); it cannot see
presentation.

## How to run it

1. Pick ten questions, mixing: a one-line fact, a two-point answer, a three-way
   comparison, two that hit an equation, two that hit a figure or table.
2. Run them once on the commit **before** IR-424 and once **after**, against
   the same corpus, through Ask IRIS in the browser.
3. Score each answer 0 or 1 on the five criteria below and fill the tables.

## Criteria

| # | Criterion |
|---|---|
| 1 | Valid Markdown (nothing left as stray `#`, `|` or `**`) |
| 2 | Structure proportionate to the answer (no heading on a one-paragraph answer) |
| 3 | Mathematics rendered, not shown as LaTeX source |
| 4 | Zero URLs and zero images |
| 5 | Citations still resolve (chips present and open the right page) |

The one regression to look for: an answer so busy with headings that the
citation chips are lost in it.

## Run — 2026-10-01

Model `openai/gpt-oss-120b`, the 40-paper arXiv proxy corpus, asked as
`iris-ierc@cit.edu` with the disclosure bypass on. Ten questions from
`docs/evaluation/proxy_starter.json`: q19 and q37 (fact), q17 (two-point), q13
and q49 (comparison), q47, q36 and q50 (equation), q24 (table), q44 (figure or
table).

**Two things differ from the method above, and the numbers should be read with them in mind.**
- *Before* is the old prompt (grounding rules only) on the current code, not a
  checkout of the earlier commit. It shows what the model writes without the
  presentation rules, and it is scored as the old renderer would have shown it
  (no math rendering).
- Scoring was done from the stored model text and the renderer's behaviour,
  not by reading each answer in the browser. Criteria 1 and 2 are mechanical
  proxies (balanced `**`, no `#` heading), so they cannot catch a badly
  proportioned answer, and criterion 5 counts that every marker resolved
  rather than clicking the chips. A person should spot-check q44 and q47 in
  Ask IRIS before IR-430 closes.

## Result

| Criterion | Before | After |
|---|---|---|
| 1 Valid Markdown | 10/10 | 10/10 |
| 2 Proportionate structure | 10/10 | 10/10 |
| 3 Mathematics rendered | 8/10 | 10/10 |
| 4 No URLs or images | 10/10 | 10/10 |
| 5 Citations resolve | 10/10 | 10/10 |

The model did not invent a URL or image in either run, so criterion 4 was never
under pressure here; `strip_images` stays as the backstop.

**Finding: the prompt alone did not deliver criterion 3.** Told to write `$..$`,
the model still wrote `\(..\)` and `\[..\]` in 2 of 10 answers (q19, q47), which
the renderer reads as plain text. `normalize_math` in `answers/citations.py`
now rewrites them, and the *after* score above includes it. Without it the
after column was 8/10 on criterion 3.

## Before — old prompt, old renderer

| Question | 1 | 2 | 3 | 4 | 5 | Notes |
|---|---|---|---|---|---|---|
| q19: how many qubits are needed to index the signal samples? | 1 | 1 | 1 | 1 | 1 | no math |
| q37: by how much did the total light reaching the instrument grow in the L  | 1 | 1 | 1 | 1 | 1 | no math |
| q17: what two different kinds of unevenness do they separate when analysing | 1 | 1 | 1 | 1 | 1 | no math |
| q13: what do the two fields each actually care about when they judge a mode | 1 | 1 | 1 | 1 | 1 | no math |
| q49: what are the two competing pictures for where these small carbon molec | 1 | 1 | 1 | 1 | 1 | no math |
| q47: how is the handedness imbalance of the hot gluon bath defined in pract | 1 | 1 | 0 | 1 | 1 | LaTeX shown as source (no math renderer) |
| q36: instead of describing a dark-matter halo by its density, what do they  | 1 | 1 | 0 | 1 | 1 | LaTeX shown as source (no math renderer) |
| q50: how does this approach treat regions larger than the horizon? | 1 | 1 | 1 | 1 | 1 | no math |
| q24: in the supply-waveform sweep, which phase lengths came out cheapest? | 1 | 1 | 1 | 1 | 1 | no math |
| q44: how do they connect simulated binary populations to what a radio teles | 1 | 1 | 1 | 1 | 1 | no math |

## After — IR-424 prompt, normalize_math, new renderer

| Question | 1 | 2 | 3 | 4 | 5 | Notes |
|---|---|---|---|---|---|---|
| q19: how many qubits are needed to index the signal samples? | 1 | 1 | 1 | 1 | 1 | math converted to $ delimiters |
| q37: by how much did the total light reaching the instrument grow in the L  | 1 | 1 | 1 | 1 | 1 | no math |
| q17: what two different kinds of unevenness do they separate when analysing | 1 | 1 | 1 | 1 | 1 | no math |
| q13: what do the two fields each actually care about when they judge a mode | 1 | 1 | 1 | 1 | 1 | no math |
| q49: what are the two competing pictures for where these small carbon molec | 1 | 1 | 1 | 1 | 1 | no math |
| q47: how is the handedness imbalance of the hot gluon bath defined in pract | 1 | 1 | 1 | 1 | 1 | math converted to $ delimiters |
| q36: instead of describing a dark-matter halo by its density, what do they  | 1 | 1 | 1 | 1 | 1 | no math |
| q50: how does this approach treat regions larger than the horizon? | 1 | 1 | 1 | 1 | 1 | no math |
| q24: in the supply-waveform sweep, which phase lengths came out cheapest? | 1 | 1 | 1 | 1 | 1 | no math |
| q44: how do they connect simulated binary populations to what a radio teles | 1 | 1 | 1 | 1 | 1 | math converted to $ delimiters |

**Status: run 2026-10-01 by script; browser spot-check outstanding.**
