# Answer quality — answer-quality-v2 v2

**PASS** against IR-955's bar: the agent matches or beats Django `lanes-v1` on overall correctness and citation support, leaks nothing, and drops no family by more than ten points.

- every condition of the bar holds

Families that decided it: none (closest: F11 Paper Chat scoped to one Record)

| family | engine | n | correct | cited support | page | refusal | leaks | failed | US$/q | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| overall | django | 108 | 36.1% | 26.8% | 34.1% | 46.2% | 0 | 24 | 0.0038 | 25194 |
| overall | agent | 108 | 89.8% | 78.4% | 64.5% | 92.3% | 0 | 0 | 0.0045 | 39292 |
| F01 single fact | django | 10 | 10.0% | 10.0% | 10.0% | n/a | 0 | 0 | 0.0022 | 24476 |
| F01 single fact | agent | 10 | 100.0% | 100.0% | 70.0% | n/a | 0 | 0 | 0.0021 | 20663 |
| F02 meaning only | django | 10 | 40.0% | 38.9% | 30.0% | n/a | 0 | 3 | 0.0044 | 27108 |
| F02 meaning only | agent | 10 | 80.0% | 98.6% | 60.0% | n/a | 0 | 0 | 0.0050 | 43694 |
| F03 multi-paper comparison | django | 8 | 12.5% | 20.8% | 6.2% | n/a | 0 | 2 | 0.0038 | 24532 |
| F03 multi-paper comparison | agent | 8 | 62.5% | 100.0% | 18.8% | n/a | 0 | 0 | 0.0068 | 39292 |
| F04 exact metadata count | django | 8 | 37.5% | 0.0% | n/a | n/a | 0 | 0 | 0.0018 | 22422 |
| F04 exact metadata count | agent | 8 | 87.5% | 0.0% | n/a | n/a | 0 | 0 | 0.0005 | 14331 |
| F05 listing | django | 8 | 12.5% | 0.0% | n/a | n/a | 0 | 0 | 0.0025 | 19810 |
| F05 listing | agent | 8 | 93.8% | 12.5% | n/a | n/a | 0 | 0 | 0.0032 | 28505 |
| F06 naming a paper | django | 10 | 45.0% | 35.0% | n/a | n/a | 0 | 4 | 0.0045 | 31865 |
| F06 naming a paper | agent | 10 | 100.0% | 63.3% | n/a | n/a | 0 | 0 | 0.0009 | 11048 |
| F07 late detail in a long Manuscript | django | 10 | 40.0% | 44.4% | 40.0% | n/a | 0 | 3 | 0.0033 | 21521 |
| F07 late detail in a long Manuscript | agent | 10 | 85.0% | 86.3% | 90.0% | n/a | 0 | 0 | 0.0031 | 22999 |
| F08 multi-turn follow-up | django | 10 | 0.0% | 0.0% | 0.0% | n/a | 0 | 5 | 0.0048 | 32594 |
| F08 multi-turn follow-up | agent | 10 | 100.0% | 100.0% | 60.0% | n/a | 0 | 0 | 0.0025 | 17606 |
| F09 compaction then exact-detail recovery | django | 8 | 43.8% | 60.2% | 75.0% | n/a | 0 | 0 | 0.0083 | 15568 |
| F09 compaction then exact-detail recovery | agent | 8 | 81.2% | 97.9% | 62.5% | n/a | 0 | 0 | 0.0096 | 32787 |
| F10 unanswerable or out of corpus | django | 10 | 40.0% | 0.0% | n/a | 40.0% | 0 | 6 | 0.0053 | 25468 |
| F10 unanswerable or out of corpus | agent | 10 | 90.0% | n/a | n/a | 90.0% | 0 | 0 | 0.0101 | 45875 |
| F11 Paper Chat scoped to one Record | django | 8 | 100.0% | 66.7% | 75.0% | n/a | 0 | 0 | 0.0015 | 11116 |
| F11 Paper Chat scoped to one Record | agent | 8 | 93.8% | 97.9% | 62.5% | n/a | 0 | 0 | 0.0038 | 29705 |
| F12 two readers with different access | django | 8 | 62.5% | 50.0% | 60.0% | 66.7% | 0 | 1 | 0.0029 | 25194 |
| F12 two readers with different access | agent | 8 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 0 | 0.0067 | 55555 |

Proxy corpus only: never a finding about CIT-U research.
