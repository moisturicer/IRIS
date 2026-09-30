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

## Before (commit: ____ , date: ____ )

| Question | 1 | 2 | 3 | 4 | 5 | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

## After (commit: ____ , date: ____ )

| Question | 1 | 2 | 3 | 4 | 5 | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

**Status: not yet run.** The tables above are blank on purpose.
