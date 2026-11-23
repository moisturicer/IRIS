# "Recent" test questionnaire (IR-1316)

Ask each question in a **new Ask IRIS conversation** and compare the answer with what is expected. It needs `agent-research-15`, and the 40 proxy papers filled by `manage.py fill_test_years` with seed 1316.

**The years are made up.** They test date handling and say nothing about the papers.

**Valid for:** questions asked on **24 November 2026**. "Recent" moves with the date, so on another day recompute the answers with the SQL at the end. Expected answers were computed from the development database on that date, not by a model. The papers were all uploaded on one day, 6 October 2026 (campus time).

- **Recent, completed or published:** 2022 to 2026.
- **Recent, uploaded:** 26 August to 24 November 2026.

**A pass** gives the expected answer, names the date it used (completed, published or added) and states the range. A wrong total, a paper outside the range, or a date from the paper's own text is a fail. Running these costs one AI question each.

## A. Counts

| # | Ask | Expected |
|---|---|---|
| 1 | How many recent papers are there? | **21**, completed 2022 to 2026 |
| 2 | How many papers were published recently? | **26**, published 2022 to 2026 |
| 3 | How many papers were uploaded recently? | **40**, added 26 August to 24 November 2026 |
| 4 | How many papers were completed last year? | **6**, completed 2025 |
| 5 | How many papers were published last year? | **4**, published 2025 |
| 6 | How many papers were completed before 2018? | **6** |

## B. Newest and lists

| # | Ask | Expected |
|---|---|---|
| 7 | What are the newest papers? | The five completed in 2026: Correlation-Free Transition Path Sampling (20), Expected Hypervolume Maximization (21), JWST Little Red Dots (26), Extreme MgII Emission (27), Beyond Linearity (50) |
| 8 | Which papers were published this year? | 11, published 2026: records 20, 21, 25, 26, 27, 35, 47, 50, 51, 52, 56 |
| 9 | List the papers completed last year. | Records 25, 35, 39, 45, 47, 52 |
| 10 | Recent papers in econometrics? | 4, newest first: Beyond Linearity (2026), Noise-adjusted turnover (2025), then Cosine metric and choice models (both 2024). *Stable Policy Learning* (2016) must not appear |
| 11 | Recent papers in hardware architecture? | Only *Evaluation of Power-Clock Waveforms* (2024). HBFlex and MeshKV (2015) must not appear |
| 12 | Which galaxy astrophysics papers are recent? | 6 by completion: 25, 26, 27, 29, 30, 34 |
| 13 | And which of those Areas' papers were *published* recently? (ask after 12, same conversation) | 8 by publication: 25, 26, 27, 28, 29, 30, 33, 34 |

## C. Recent papers on a topic

Search returns a sample, so check only that nothing outside the range is called recent.

| # | Ask | Expected |
|---|---|---|
| 14 | Recent papers about large language models | May name 22 (2022), 35 (2025). Must **not** call HBFlex, MeshKV (2015), 36 (2019) or 37 (2021) recent |
| 15 | What is the latest paper on dark matter? | Compares dates. *From Density to Mass* (29, completed 2023) is newer than 43 (2020) and 44 (2019) |
| 16 | Recent speech papers, by publication date, 2020 to 2023 | 36, 37, 38 at most (published 2021, 2023, 2020) |

## D. One paper's dates

| # | Ask | Expected |
|---|---|---|
| 17 | When was MeshKV completed, published and uploaded? | Completed 2015, published 2015, uploaded 6 October 2026 |
| 18 | Which papers completed in 2024 were published later than that? | 51, 54, 56 (54 in 2025, the others in 2026) |

## E. Edge cases

| # | Ask | Expected |
|---|---|---|
| 19 | Which papers were uploaded in the past month? | None since 24 October 2026; offers the newest, 6 October 2026 |
| 20 | Hardware architecture papers published last year? | None in 2025; offers the newest, 2026 (56) |
| 21 | Which paper studies recently-quenched galaxies? | Record 27. "Recently" is part of the topic: no date range |
| 22 | What month was MeshKV published? | Only the year is recorded |
| 23 | What does MeshKV propose? | Answers from the paper, with no date talk |

## F. Not published yet

Sign in as someone who **owns a draft or a paper in review**.

| # | Ask | Expected |
|---|---|---|
| 24 | When was *(your draft's title)* uploaded? | Says it can't find it |
| 25 | List the newest uploads. | Only published papers; your draft or paper in review is absent |

## Results

| Date | Asked by | Deployed commit | Passed | Failed (numbers) | Notes |
|---|---|---|---|---|---|
| | | | | | |

**Not run yet.** No question here has been asked of the live model.

## Recomputing the answers

```sql
WITH p AS (
  SELECT r.id, r.title, c.name AS area, coalesce(r.year_accomplished, r.year_completed) AS completed,
         r.publication_year AS published, (r.created_at AT TIME ZONE 'Asia/Manila')::date AS added
    FROM records_record r LEFT JOIN records_classification c ON c.id = r.classification_id
   WHERE NOT r.is_deleted AND r.pipeline_status = 'published' AND NOT r.is_embargoed
     AND r.ai_consent AND (NOT r.is_ip OR r.ip_released_at IS NOT NULL))
SELECT * FROM p WHERE completed BETWEEN 2022 AND 2026 ORDER BY completed DESC, title;
```
