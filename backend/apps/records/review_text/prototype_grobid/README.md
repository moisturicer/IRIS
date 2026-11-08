# PROTOTYPE: GROBID, and a GROBID + rules hybrid, beside IR-871's rules (throwaway, never merge)

**Question.** Does GROBID, self-hosted so no paper leaves the machine, read real CIT-U papers better than IR-871's rule-based reader (`../reader.py`, `RULES_VERSION = 2`)? Either alone, or as a hybrid where the rules read the body and GROBID supplies the reference list? And what does it cost?

**Answer (2026-11-08): no, not as the main reader, and the hybrid doesn't earn its cost yet. Keep the rules.** This is a recommendation. Adopting GROBID would need an ADR-058 amendment, and that is the team's decision.

- **GROBID alone loses words.** It dropped every body word on whole pages of 4 papers, pages where the rules lost none (see *Word loss*). The rules never do that, and a Thread's quote must always be findable.
- **GROBID's section keys are unstable** across Versions: 8 false changes on held-out pairs (18 on tuning), against the rules' 1 (1).
- **Its reference lists weren't better on tuning, they were worse.** It had 17 entries off pattern against the rules' 3: GROBID glued 12 entries together and split off 5 fragments. On held-out, it found entries on 3 papers where the rules found only part of the list. It also glued and split there, and it drops the printed `[n]` from every IEEE entry.
- **The hybrid** matches the rules on Version pairs on held out (on tuning it made 2 false changes against the rules' 1), raises mean word coverage slightly, and inherits GROBID's reference errors. It costs a second service of about **4 GB**, against the rules' 38–304 MiB.

## What it is

- **GROBID 0.9.1, CRF build** (`grobid/grobid@sha256:2239577…f38f4cd`), Apache-2.0. It's machine-learned (CRF), but runs entirely in a local container. This is not the `-full` deep-learning image.
- **Every request turns consolidation off** (`consolidateHeader=0`, `consolidateCitations=0` and `consolidateFunders=0`), so no reference metadata goes to Crossref. It sets `segmentSentences=1` and `includeRawCitations=1`, with coordinates for `head`, `s`, `biblStruct` and `figure`.
- **Files:**
  - `fetch.py` sends each paper to local GROBID and logs seconds and the container's peak memory.
  - `tei_reader.py` maps the TEI into the reader's stored shape. Keys, hashes and the fail-safe come from the reader's own `_finish()`, so both readings are judged by the same code.
  - `score.py` holds the measures.
  - `run.py` runs the rules (one fresh process per paper), builds `hybrid` and `hybrid_fallback`, and scores all four.
- **The two hybrids:**
  - `hybrid`: the rules' reading, with its references section replaced by GROBID's entries.
  - `hybrid_fallback`: the same, but when the rules collapse and GROBID doesn't, it takes GROBID's whole reading.
- `split.json` fixed the tuning and held-out sets before any GROBID output was read (commit `78128ad2`).
- `out/` is git-ignored, because it holds paper text. Its ignore file is local, since the root `.gitignore` ignores every `.gitignore` file.

## Run

```
pip install pdfplumber==0.11.10 httpx lxml psutil       # pdfplumber pinned as in backend/requirements/base.txt
docker run -d --name grobid-proto -p 127.0.0.1:8070:8070 --memory 4g -e JAVA_OPTS=-Xmx2g \
  grobid/grobid@sha256:223957791ac2bbe48609dcc58a689b16b60baeae13a8734ef440ae6bfb38f4cd
python -I fetch.py <folder of sample PDFs>                 # GROBID running
docker stop grobid-proto                                   # so the rules' timings are their own
python -I run.py <folder> tuning
python -I run.py <folder> held_out
```

The papers are the ignored `samples/`. They are never committed, never quoted and never sent anywhere but the local container.

**Which papers.** All 36 papers used match Hermoine's list by **SHA-256**, so they are the same bytes; none was matched by DOI or title.
- Tuning has all **10** of its papers.
- Held out has **26 of 27**. **test1_v1 was left out**, because it's a thesis that can't be shared.
- sample27, a duplicate of sample26, is outside the split by design.
- All five Version pairs counted.

**Freeze point: `5156de7a`.** The mapping, the scoring and the choice of hybrid were fixed there, on tuning results only. Held out ran once, afterwards, with no change.

### What changed before the freeze (tuning only)

1. **Mapping:** a figure outside every division could be filed under References by page, where its caption counted as an entry. Figures now never go to the reference list.
2. **Memory:** a Windows venv's `python.exe` is a launcher, so the rules' memory had read 4 MiB. It's now measured across the process tree.
3. **Scoring, a year range in a title:** "(1999–2019)" counted as a second citation year, for every approach alike (the rules went from 5 to 3 off pattern, GROBID from 19 to 17). It no longer counts.
4. **Scoring, IEEE, decided by Ashlee:** GROBID drops the printed `[n]` from `raw_reference`, and gives no `<label>`. So:
   - Each paper's style comes from the **rules' reading** of it.
   - An IEEE entry is off pattern only if **a second `[n]` appears inside it** (glued).
   - Entries with no leading label are counted apart, as `unlabelled`.
   - The entry count is compared with the highest `[n]` in the rules' reading, with too few and too many reported apart.
5. **The candidate is the plain hybrid, with no guard.** On tuning, no guard beat the rules on references:

   | Guard on GROBID's refs (tuning, measured **before** the year-range fix 3, so the rules show 5 and GROBID 19 here, against 3 and 17 in the results) | Off pattern | Entries |
   |---|---|---|
   | Rules alone | 5 | 237 |
   | Always use them | 19 | 231 |
   | Only if ≥ 80% as many entries | 16 | 236 |
   | Only if ≥ 90% as many entries | 10 | 242 |

   These were measured before fix 3. The fallback never fired on tuning, because no tuning paper collapsed, so `hybrid_fallback` is reported beside the plain hybrid rather than put forward.

The 19 tuning entries that were off pattern before fix 3 were checked one by one:
- **12** were GROBID gluing 2–4 entries together.
- **5** were GROBID splitting off a fragment, such as a DOI or URL tail.
- **2** were the year range from fix 3.

None came from the mapping.

## Results (counts only, no paper text)

### Tuning: 10 papers, 2 Version pairs

| | Rules | GROBID | Hybrid | Hybrid + fallback |
|---|---|---|---|---|
| Collapsed (≤ 1 section or `sections_unreliable`) | 0 | 0 | 0 | 0 |
| Headings vs bookmarks, precision / recall (**2 papers**) | 0.65 / 0.59 | 0.78 / 0.91 | 0.65 / 0.59 | 0.65 / 0.59 |
| Reference entries | 237 | 231 | 231 | 231 |
| Off pattern | **3** | 17 | 17 | 17 |
| Over 120 words | 0 | 0 | 0 | 0 |
| IEEE papers: unlabelled entries / too many | 0 / 0 | 55 / 2 (1 paper) | 55 / 2 | 55 / 2 |
| Word coverage, mean / **min** | 0.956 / 0.883 | 0.933 / 0.880 | 0.959 / 0.889 | 0.959 / 0.889 |
| Version pairs: false changes / missed edits | **1 / 1** | 18 / 2 | 2 / 1 | 2 / 1 |
| Seconds per paper, median (range) | 6.8 (3.7–19.6) | 2.3 (1.7–16.2*) | 10.3 | 10.3 |
| Peak memory, MiB | 84–304 | 3,741–4,035 | 4,035 | 4,035 |

\* The 16.2 s was the first request after the container started. Warm requests took 1.7–3.6 s.

### Held out: 26 papers, 3 Version pairs (test1_v1 left out)

| | Rules | GROBID | Hybrid | Hybrid + fallback |
|---|---|---|---|---|
| Collapsed | 1 (sample11) | 0 | 1 | **0** |
| Headings vs bookmarks, precision / recall (**4 papers**) | 0.51 / 0.86 | 0.42 / 0.80 | 0.51 / 0.86 | 0.51 / 0.86 |
| Reference entries | 525 | 561 | 560 | 560 |
| Off pattern | 195 | 227 | 227 | 227 |
| …without the 2 numbered-style papers† | **34** | 64 | 64 | 64 |
| Over 120 words | 0 | 3 | 3 | 3 |
| IEEE papers: unlabelled / too few / too many | 0 / 0 / 2 | 54 / 2 / 2 | 54 / 2 / 2 | 54 / 2 / 2 |
| Word coverage, mean / **min** | 0.957 / 0.582 | 0.882 / **0.143** | 0.958 / 0.577 | 0.954 / 0.577 |
| Version pairs: false changes / missed edits | **1 / 1** | 8 / 1 | **1 / 1** | **1 / 1** |
| Seconds per paper, median (range) | 5.2 (0.5–14.4) | 1.6 (1.0–2.5) | 6.8 (max 16.8) | 6.8 |
| Peak memory, MiB | 38–212 | 4,031–**4,088** | 4,088 | 4,088 |

† Two papers (sample22 and sample32) number their references "1." (Vancouver style), which is neither APA nor IEEE. So every entry fails the pattern check for **every** approach: 161 of the rules' 195, and 163 of GROBID's 227. This breakdown was made after the held-out run, and the measure itself wasn't changed. GROBID drops the "1." numbers too.

**The rules' 34 held-out entries off pattern**, without those two papers, per paper (for IR-992, the backlog for the next rules version):

| Paper | Style | Entries | Off pattern |
|---|---|---|---|
| sample12_v1 | APA | 10 | 5 |
| sample12_v2 | APA | 10 | 5 |
| sample12_v3 | APA | 10 | 5 |
| sample9 | APA | 10 | 5 |
| sample23 | APA | 38 | 5 |
| sample13 | APA | 14 | 4 |
| sample20 | APA | 17 | 2 |
| sample8 | APA | 1 | 1 |
| sample16 | IEEE | 17 | 1 |
| sample25 | APA | 23 | 1 |

- **Only 1 of the 34 comes from the three cut-short lists** (sample8). sample15 and sample24 have no entry off pattern: their problem is missing entries (4 and 12 found, against GROBID's 20 and 17), not malformed ones.
- **15 of the 34 are the same 5 entries**, counted once in each of sample12's three Versions.

**The hybrid's time** is the rules' time plus GROBID's, because production would run both. **GROBID's memory** is the container's peak, including its own baseline: about **3.1 GiB when idle**. All figures are from the CPU-only CRF build on one Windows 11 laptop with 15.6 GB of RAM, under Docker Desktop.

**Per pair, held out:**

| Pair | Rules | GROBID | Hybrid / fallback |
|---|---|---|---|
| sample2 | exact | exact | exact |
| sample12 v1→v2 | exact | 1 false change | exact |
| sample12 v2→v3 | 1 false, 1 missed | 7 false, 1 missed | 1 false, 1 missed |

No pair collapsed.

### Word loss: where, in counts and pages

This breakdown, made after the held-out run, splits the coverage measure by page. A page counts as lost when it has at least 20 body words and fewer than half of them appear in passages on that page.

**The rules lose a baseline** of words the token match can't pair up, mostly on journal papers (up to about 1,350 words a paper, with no page under half). GROBID shares that baseline. **What GROBID adds is whole pages:**

| Paper | Pages | Body words | GROBID lost | Rules lost | Pages GROBID read none of |
|---|---|---|---|---|---|
| sample6_v1 (tuning) | 27 | 3,701 | 261 | 0 | p.2, plus p.17 under half |
| sample6_v2 (tuning) | 27 | 3,693 | 195 | 0 | p.2 |
| sample16 | 11 | 3,340 | 856 | 72 | pp.8, 9 and 11 |
| sample31 | 25 | 3,023 | 179 | 2 | pp.1 and 2 |
| sample28 | 1 | 56 | 48 | 0 | most of its only page |

GROBID also read under half of one page on each of samples 2 (v1 and v2), 8, 17 (two pages) and 29. sample32 loses about 1,400 words on the same six pages for **all four approaches**, so that loss isn't GROBID's.

Altogether, GROBID lost 4,279 words on tuning (rules 3,388) and **8,261 on held out (rules 4,718)**. It lost 50 words or more on 23 of 26 held-out papers, against the rules' 13.

## What this shows

1. **GROBID as the main reader is ruled out by word loss alone.** That's the same failure the layout-model prototype had, and it's worse here: whole pages, with no warning. A collapse in the rules is safe, because every sentence is kept. A dropped page isn't.
2. **GROBID's headings looked better on tuning and worse on held out.** That's 2 and 4 bookmarked papers, too small a sample to say either way. Its keys change more between Versions, which is what the section comparison needs most.
3. **References were the reason to try GROBID, and the tuning set didn't bear that out.** On held out, GROBID did find entries on **3 papers where the rules found only part of the list** (sample8, sample15 and sample24: rules 1, 4 and 12 entries, GROBID 29, 20 and 17). It glued and split entries elsewhere, though, and it strips the printed `[n]` from every IEEE entry (55 on tuning, 54 on held out).
   - **Stripped labels are a real cost:** an in-text citation like "[3]" can no longer be matched to a stored entry.
   - **The cheaper fix is in the rules.** A rules change for those three cut-short lists needs no new service and no ADR amendment.
4. **The fallback rescued the one held-out collapse (sample11), but it cost words.** GROBID's reading kept 0.886 of the words, against 0.994 for the collapsed rules reading. That trades a safe failure for a lossy one, so it isn't recommended as it stands.
5. **Cost:**
   - GROBID idles at about 3.1 GiB and peaked at 4,088 MiB, inside a 4 GiB limit.
   - On the 7.5 GB laptop, it was `OOMKilled` under `--memory 2500m` on the first paper, both with `-Xmx2g` and `-Xmx1500m`. A smaller heap didn't help, so the memory goes to GROBID's native parts, not the Java heap.
   - A production worker would need about **4 GB for GROBID** on top of the rules' 38–304 MiB.
   - GROBID is fast once warm (1–4 s a paper, against the rules' 0.5–20 s), but speed was never the problem for background reading (ADR-058 §1 reads after submission).
6. **Network:**
   - In this prototype the container could still reach the internet, and turning consolidation off is what kept the data in.
   - In production GROBID would sit on an `internal: true` Compose network with no route out.
7. **Governance:** ADR-058 §1 reads review text "with pdfplumber and plain rules", and IR-871 does it "without AI". GROBID's CRF models are machine learning, so adopting even the hybrid needs an **ADR-058 amendment**, and a second reader version to store (`reader` names both).

## Not tested

- **test1_v1**, the 69-page thesis that IR-871's latest rules were written for. It wasn't available here.
- GROBID's deep-learning (`-full`) image, a GPU, Linux timing, and memory limits other than 4 GiB.
- Scanned papers. GROBID's PDF helper doesn't OCR either, so neither reader covers them.
- Whether GROBID's dropped pages are a parsing failure (tables, front matter or a layout it misclassifies) or something a different setting would fix. The pages were counted, not examined.
- A reference-pattern check for numbered "1." (Vancouver) lists.

## If revisited

- **Fix the rules first.** Three held-out papers had a reference list the rules ended early. That's a rules change, with a new `RULES_VERSION` and no ADR amendment.
- If GROBID is tried again, use its references only behind a guard that can't hide errors, for example when the rules found no list at all. Put the printed `[n]` labels back from the PDF by position. **Never take GROBID's whole reading** without checking every body word is kept, and warning otherwise.
