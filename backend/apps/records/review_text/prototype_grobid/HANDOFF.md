# Handoff to Ashlee: GROBID prototypes for the review text reader (2026-11-08)

From Hermoine. This was started on a 7.5 GB laptop, where GROBID can't run: it was killed for running out of memory on the first paper (details in §5). It needs your 16 GB machine.

**What you're picking up.** Two throwaway prototypes, to be compared against the review text reader we already ship:

1. **GROBID alone** reads each paper.
2. **A hybrid**: our current rules read the body, and GROBID supplies the reference list.

The question is **which reads real CIT-U papers better, and at what cost.** The answer goes in a README, which is the deliverable. Nothing here is ever merged.

---

## 1. Background: what the "rules" are and why they matter

### What review text is for (IR-871, ADR-058 §1 as amended 2026-11-05)

When a student uploads a new Version of their manuscript, reviewers (the Adviser and the offices) need two things:

- **To see which sections changed** since the last Version. IRIS compares the two Versions section by section. Each section has a **key**, made from its heading, and a **hash** of its text. Same key with a different hash means the section changed. A key in only one Version means it was added or removed.
- **To anchor a comment (a Thread) to a quote.** Each sentence is stored as a **passage**, with its page and its rectangles on the page, so the interface can highlight it.

So the stored "review text" of a Version is:

```
{reader, page_count, warnings: [...],
 sections: [{key, heading, page, text_hash,
             passages: [{text, page, paragraph, kind: "sentence"|"row",
                         regions: [{page, left, top, right, bottom}]}]}]}
```

`regions` are fractions of the page (0–1), the same shape ADR-031 uses for citations.

**ADR-058 §1 (amended, Accepted) says this text is read "with pdfplumber and plain rules", on campus, without AI.** That's deliberate. Student manuscripts are unpublished and often embargoed, so the text must never leave our machine, and a rule can be explained when it goes wrong. LlamaParse, the AI extraction, is a separate thing and is gated by the embargo. Keep the two apart.

### What the rules reader does (`backend/apps/records/review_text/reader.py`, `RULES_VERSION = 2`)

It's pure Python: pdfplumber plus the standard library. It has no Django, no network and no model, and it runs in a sandboxed child process (`sandbox.py`). In order:

1. **Words per page.** pdfplumber reads every word with its font and size. Then the reader:
   - reads a character drawn twice in the same place once (sample12 v3 prints a table twice over itself)
   - drops anything drawn outside the page
   - rejoins words that pdfplumber split at a font change: "arti fi cial", "Nursing ' s", and small capitals
2. **Tables.** A ruled grid with two columns or more becomes one passage per row (`kind: "row"`, with the cells joined by ` | `). A stack of one-cell boxes is a shaded paragraph, not a table.
3. **Running heads, footers and page numbers are dropped.** That means a line in the top or bottom 12% of the page that repeats on most pages once digits are ignored, or a bare page number. It also covers numbers that count up with the page at the same height, like a journal's 827, 828… A "CHAPTER N" line is never dropped.
4. **Columns.** A page is split at a vertical gutter that no body word crosses, apart from a few lines that span the page, such as a journal title over a two-column abstract. Known limit: there's only one gutter, so three columns read wrongly.
5. **Headings.** A line is a heading if it's bold, numbered ("2.1", "II.", "A."), in capitals, or larger than the body text, and also shaped like a heading:
   - at most 100 characters, with no ending punctuation, and not starting lowercase
   - not a table-of-contents line with dot leaders, not a caption ("Table 3…"), and not an unruled table row
   - a heading that wraps onto a second line joins it only when the font matches and the case doesn't change, so "INTRODUCTION" over "Background of the Study" is two headings
6. **Passages.**
   - Paragraphs are split into sentences at punctuation, except after abbreviations, initials ("J. Cruz") and list numbers.
   - A word hyphenated at a line end is rejoined or kept hyphenated according to how the paper itself spells it elsewhere.
   - Under a references heading, **each reference entry is one passage, kept whole**.
   - Contents lines are collapsed.
7. **Keys and hashes.** The key is the heading, lowercased, with its numbering removed ("2.1 Methods" becomes "methods"). Text before the first heading is `front-matter`, and a repeated heading gets `#2`, `#3`. The hash is SHA-256 over the normalized passage text.
8. **The fail-safe (`_unreliable`).** If the sections look wrong, the paper is stored as **one section** keyed `document`, with the warning `sections_unreliable`. It looks wrong when it has:
   - no headings at all
   - about as many headings as sentences
   - the same heading over and over before the appendices (appendices repeat headings by design: one CV per person)
   - mostly empty sections

   Every sentence still has its page, so Threads still work, but the section comparison is lost. **A collapse is the reader's main failure.** It's safe but unhelpful.
9. **Other warnings:** `long_section` (a section over 15 pages), `pages_without_text`, and `unmapped_characters` (the PDF's font has no Unicode map). Above 20% unmapped, the paper is "unreadable" and stored as "No text for vN".

**Changing a rule means a new reader version.** Stored text is never re-read in place (ADR-058 §1 point 5), which is why `RULES_VERSION` exists.

### How the rules got here

They were tuned on **37 public CIT-U papers** in the gitignored `samples/`, in PRs #555, #564 and #615 (all merged), plus #622 (merged by you). #622 added two rules from a 69-page thesis, `test1_v1.pdf`:

- headings repeated in the appendices are trusted
- a web address's capital-letter tail isn't a heading, and an entry back at the margin after an address ending in "/" starts a new reference entry

That thesis went from one collapsed `document` section to 112 sections. Every rule's evidence and the known limits are in `docs/testing/traceability/IR-871.md`. IR-871 itself is Done.

### Why GROBID, and the earlier layout-model prototype

The rules' weak spots are collapsed sections on unusual layouts, student-thesis headings that aren't bold or numbered, and three columns. Each new paper tends to need a new rule.

**GROBID** (Apache-2.0, self-hosted) is a mature tool built for exactly this: scholarly PDFs to structured TEI XML. It's machine-learned (CRF models in the build we're using) but runs entirely locally. **Reference parsing is its strongest part.**

An earlier prototype tried a self-hosted **layout model** (PP-DocLayout v2) and lost to the rules. It **silently dropped words** (0–48 per paper outside every box) and was no better overall. See `prototype_layout_detector/README.md` on the `prototype/layout-detector` branch, which is pushed. Its README is the template for this one. **Word loss is exactly what to check GROBID for**, because a Thread's quote must always be findable in the stored text.

---

## 2. What's on this branch (`prototype/grobid-reader`, cut from `main` after #622)

Everything is in `backend/apps/records/review_text/prototype_grobid/`:

| File | State |
|---|---|
| `split.json` | **Committed and frozen (commit `78128ad2`). Don't change it.** 10 tuning files and 27 held-out files, plus five Version pairs listing the sections the author really edited. It was fixed before any GROBID output was read. sample27 is a duplicate of sample26 and is left out. |
| `fetch.py` | Sends each split paper to local GROBID one at a time. It saves `out/tei/<name>.xml`, and logs seconds and the container's peak memory from `docker stats` to `out/fetch.json`. It's resumable: papers already fetched are skipped. It has only ever run up to GROBID being killed on the first paper. |
| `tei_reader.py` | Maps GROBID's TEI into the reader's stored shape (above). **Never run on real TEI yet.** |
| `score.py` | The measures (§4). **Never run.** |
| `run.py` | Reads every paper in a set with today's rules (each in a fresh process, timed, peak memory measured, cached in `out/rules/`), maps the TEI, builds the hybrid, scores everything, and writes `out/scores-<set>.json`. **Never run.** |
| `HANDOFF.md` | This file. |

Expect small bugs in the three untested files. Fixing them is fine. Changing **what** is measured after seeing held-out results is not.

### How the mapping works (`tei_reader.py`)

- **Front matter:** the TEI header's title. The **abstract** becomes a section headed "Abstract".
- **Sections:** each `<div>` with a `<head>` (and its `n` number, if any) becomes a section. Divs typed `acknowledgement` or `annex` with no head get that type as their heading.
- **Passages:**
  - each `<s>` (sentence) in a `<p>`
  - `<formula>` and list `<item>` elements
  - figure descriptions
  - table rows as `kind: "row"`
- **Figures outside every div** go to the section whose start page is the last one at or before the figure's page.
- **References:** `<div type="references">`. Each `<biblStruct>` becomes one passage, using GROBID's `raw_reference` note, which is the citation as printed.
- **Regions** come from the TEI `coords` (`page,x,y,w,h`, in points from the top left), divided by the `<facsimile><surface lrx lry>` page sizes.
- **Keys, hashes and the fail-safe** come from the reader's own `_finish()`, imported from `../reader.py`. So GROBID's output is keyed and judged by exactly the same code as the rules'.

### The hybrid (`run.py: hybrid()`)

- **`hybrid`:** the rules' reading, with its references section's passages replaced by GROBID's entries (paragraphs renumbered, hash recomputed). If the rules collapsed or found no references heading, it's unchanged.
- **`hybrid_fallback`:** the same, but when the rules' fail-safe fired and GROBID's didn't, it takes GROBID's whole reading instead.

**Pick between these, or add a guard such as "only use GROBID's references when it found at least 80% as many entries", on the tuning set only.**

---

## 3. Steps

1. **Get the code.** Once Hermoine has pushed the branch: `git fetch` then `git worktree add ../IRIS-grobid prototype/grobid-reader`.
2. **Get the samples privately from Hermoine** into `samples/` at the repo root. It's gitignored.
   - **You'll get only the papers you're allowed to have.** Those are the CC BY and CC BY-NC papers as files, plus links to the free-download papers, which you download yourself from their source. Any paper whose licence doesn't allow sharing stays on Hermoine's laptop.
   - **So you won't have all 37 files `split.json` names. Don't edit `split.json`.** Both scripts already skip papers that aren't in your folder. `run.py` prints the left-out papers and records them as `left_out` in `out/scores-<set>.json`, and a Version pair counts only when both of its files are present. **List the left-out papers of each set in the README.**
   - **Rules for the samples:**
     - never commit them or quote their text, in a README, PR, Jira or chat
     - never send them anywhere: not LlamaParse, not Voyage, not `load_corpus`, not any online GROBID demo
     - CC BY-NC papers must never appear in a product, a demo or `seed_demo`
     - outputs report **counts only**
3. **Make sure `out/` is ignored. It will hold paper text.** The repo root's `.gitignore` (line 77) ignores every `.gitignore` file, so the folder's own `out/` rule **wasn't committed and won't be in your clone**. Create it yourself: a file named `.gitignore` in `backend/apps/records/review_text/prototype_grobid/`, holding the one line `out/`. Git obeys it even though it can't be committed. Then check:
   ```
   git check-ignore -v backend/apps/records/review_text/prototype_grobid/out/x
   ```
   The check must print a line naming that `.gitignore`. If it prints nothing, `out/` isn't ignored, so stop. Always stage files by name, never `git add .`.
4. **Python.** Use the backend's environment (`pip install -r backend/requirements/development.txt`, which gives the same pdfplumber the reader uses), plus `pip install httpx lxml psutil`. Run scripts with `python -I`.
5. **Start GROBID** with the image pinned by digest. This is the CPU-only CRF build, not `-full` (14.8 GB, wants a GPU):
   ```
   docker pull grobid/grobid@sha256:223957791ac2bbe48609dcc58a689b16b60baeae13a8734ef440ae6bfb38f4cd
   docker run -d --name grobid-proto -p 127.0.0.1:8070:8070 --memory 4g -e JAVA_OPTS=-Xmx2g ^
     grobid/grobid@sha256:223957791ac2bbe48609dcc58a689b16b60baeae13a8734ef440ae6bfb38f4cd
   ```
   - **Keep the name `grobid-proto`**: `fetch.py` reads `docker stats` by that name.
   - **Bind to `127.0.0.1` only.**
   - **Don't use `--rm`**: if it dies, `docker inspect -f '{{.State.OOMKilled}}' grobid-proto` tells you why.
   - If it's killed at 4 GB, raise `--memory` to 6g and record both numbers. Peak memory is one of the results.

   Wait until `curl http://127.0.0.1:8070/api/isalive` says `true`, which takes about a minute.
6. **Smoke-test on one paper first.** Put a single tuning paper, preferably sample21 or sample30 (they have bookmarks), in a folder on its own, and run `fetch.py` and then `run.py` on that folder. This shows whether GROBID fits in memory and whether the untested scripts work end to end. It says nothing about which approach is better. Fix what breaks, then do the full fetch.

   **Fetch:** `python -I fetch.py <path-to>/samples`. It skips papers already fetched and papers you don't have. Every request sends:
   - `consolidateHeader=0`, `consolidateCitations=0` and `consolidateFunders=0`. **With consolidation on, GROBID sends reference metadata to Crossref.** Don't turn it on.
   - `segmentSentences=1` and `includeRawCitations=1`
   - `teiCoordinates` for `head`, `s`, `biblStruct` and `figure`
7. **Check the mapping's assumptions on a tuning paper's TEI only** (for example `out/tei/sample1_v1.pdf.xml`). Confirm:
   - **IEEE labels:** does `raw_reference` keep the printed `[n]`? If GROBID strips it, the "IEEE entry starts with `[n]`" check would unfairly fail GROBID and the hybrid. Then judge IEEE entries by GROBID's `<label>`, or detect the style from the rules' reading, and say which you chose.
   - **Coords:** they're 1-based pages and in points, matching the `surface` sizes.
   - **Figures:** where GROBID puts `<figure>`, inside a div or after the body.
   - **Headings:** whether `head` carries `n`.
   **Don't open any held-out paper's files before the freeze in step 8.** `fetch.py` fetches every paper, so `out/tei/` holds held-out TEI too, and `out/rules/` will later hold held-out rules readings. Looking at them while you tune would shape the hybrid on papers meant to test it, and the held-out score would no longer be fair. The held-out files are listed under `held_out` in `split.json`.
8. **Tune:** `python -I run.py <path-to>/samples tuning`. Look at the tuning results only, fix mapping bugs, and choose the hybrid variant. **Then commit, and write that commit's hash in the README as the freeze point.**
9. **Validate once:** `python -I run.py <path-to>/samples held_out`. Don't change the mapping or the hybrid after this. If you find a bug, fix it, say so in the README, and report both runs.
10. **Write `README.md`** in the layout prototype's shape: question, answer, what it is, how to run it, results tables (tuning and held out apart), what this shows, not tested, and if revisited.
11. **Clean up:** `docker rm -f grobid-proto`.

The rules readings run in subprocesses, while GROBID runs in Docker. Don't run them at the same time, or the timings mix.

---

## 4. What's scored (`score.py`), per set, for rules, grobid, hybrid and hybrid_fallback

- **Collapse:** at most one section, or `sections_unreliable`. Fewer is better.
- **Headings:** precision and recall against the PDF's **bookmarks** (the answer key), comparing heading text with numbering and punctuation removed. Only six papers have bookmarks:
  - tuning: samples 21 and 30
  - held out: samples 8, 22, 23 and 32

  So these numbers are small-sample: say so.
- **Reference entries:**
  - the number found
  - **off pattern:** an APA entry must have exactly one "(year)", and an IEEE entry must start with `[n]`
  - **over 120 words:** entries glued together
- **Word coverage:** the share of pdfplumber's body words found in the output. Body words exclude the top and bottom 6% of the page, and words broken by a line-end hyphen. This is the check that caught the layout model losing text. **Look at the minimum, not just the mean.**
- **Version pairs:** for each pair, the sections marked changed against the sections `split.json` says were edited, counting false changes and missed edits. Any edit falls into a collapsed paper's single section, so its missed edits are 0. **Report pairs that collapsed separately.**
- **Speed and memory:**
  - seconds per paper; the hybrid is rules time plus GROBID time, since in production it would run both
  - peak MiB: the rules' child-process RSS, and GROBID's container peak, which includes its own baseline
  - say that these come from the CPU-only build on your machine

---

## 5. What's already known

- **The memory cost is a finding in itself.** Docker's VM on the 7.5 GB laptop had 3.5 GB. GROBID 0.9.1-crf under `--memory 2500m` was `OOMKilled` (exit 137) on the first paper (`sample1_v1.pdf`), both with `-Xmx2g` and with `-Xmx1500m`. A smaller heap didn't help, so the extra memory goes to GROBID's native parts (the PDF-to-XML helper and the CRF models), not the Java heap. Put this in the README's cost section. A production worker would need several GB more than the rules' 75–270 MB.
- **Network:** in the prototype, the container can still reach the internet; consolidation off is what keeps data in. In production, GROBID would sit on an `internal: true` Compose network with no route out. Say both in the README.
- **The decision is the team's, not the prototype's.** Adopting GROBID, even self-hosted, contradicts ADR-058 §1's "pdfplumber and plain rules" and IR-871's "without AI", because CRF models are machine learning. It would need an **ADR-058 amendment**. Hermoine decided ADR-058, and the team decides any amendment. The README should **recommend**, not decide.
- **Jira:** there's no issue key for this prototype. **Don't invent one.** The layout-detector prototype was recorded under IR-871's evidence, and Hermoine may want the same here. Ask her.
- **If GROBID wins only on references,** the hybrid is the likely recommendation. The README should still say what it costs: a second service and its memory, plus a second reader version to store (`reader` names both).
- **If GROBID loses words** like the layout model did, say how many and where (counts and pages, no text), because that alone rules it out as the main reader.

## 6. Ask Hermoine for

- the 37 sample PDFs (privately)
- whether to record this under IR-871's evidence
- the review of the README before it's shared with the team
