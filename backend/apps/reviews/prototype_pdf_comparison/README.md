# PROTOTYPE: PDF Version comparison without AI (throwaway, never merge)

**Question.** Can a PDF's text, read on campus with pdfplumber and no AI, support ADR-058 §3's Version comparison and the review threads that depend on it (Threads, Conversations, Changes)? Or should uploads switch to `.docx`?

**Answer (2026-11-05): yes, for born-digital PDFs laid out like a CIT-U thesis. Keep the PDF.** All 59 checks pass, but that is evidence from a test paper, not from a real thesis (see *What this does not show*).

## Run

```
cd backend
pip install pdfplumber==0.11.4 reportlab==4.2.5      # not in requirements
python apps/reviews/prototype_pdf_comparison/run.py  # --no-word to skip Word
```

The report is written to `out/report.html`: open it in a browser.

## What it does

- **Two Versions of one paper.** The seeded paper *Community Waste-to-Energy Feasibility in Metro Cebu* is written in two Versions (`make_versions.py`). `seed_demo` papers have no manuscript, so the text is written for the test.
- **Seven known edits in v2:**
  - a figure changed in a sentence
  - a section added, long enough to push every later page back
  - a paragraph removed
  - two sections swapped
  - a section renamed
  - a table value corrected
  - a sentence added
- **Two sources of each Version:**
  - **Drawn** by reportlab, so every position is known.
  - **Exported from Word** (`word_export.ps1`). Microsoft Word builds the `.docx` with:
    - Heading styles
    - automatic hyphenation
    - justified, double-spaced body text
    - a running head
    - a page-number field
    - a ruled table

    Word then exports it to PDF and reports the page each sentence starts on.
- **Reading** (`compare.py`). pdfplumber reads words and positions. Plain rules then:
  - drop running heads and page numbers that repeat in the margins
  - find headings by bold font, joining "CHAPTER N" to its title
  - repair line-end hyphens, keeping a compound's own hyphen when the word appears whole elsewhere in the paper
  - read ruled tables as rows
  - split two-column pages at the gutter
  - split sentences, keeping each one's page and line regions (ADR-031's shape)
- **Comparing.**
  - Sections are matched by heading with the numbering removed, a renamed section by its content, and a moved section by order.
  - Inside a section, sentences are compared with `difflib`. Each comes out unchanged, changed (with a word-level diff), added, removed or moved.
- **Threads.** A v1 quote is typed the way the browser's PDF text layer gives it, with the line break and hyphen left in. The prototype looks for it in v2 and reports *found on p. N* or *Outdated*, plus the nearest sentence.

## Findings worth keeping

1. **pdfplumber's default word gap merges words.** `x_tolerance` defaults to 3 pt, which is a space's width in 12 pt Times, so a line that isn't justified came back as one word. It needs to be set below that (1.5 here).
2. **Word's PDFs are easier to read than they look.**
   - The fonts keep their names (`TimesNewRomanPS-BoldMT`), so bold headings are found.
   - Hyphenation comes out as an ordinary `-`, not a soft hyphen.
   - Header and footer text repeats exactly, so it's easy to drop.
   - Word's own pagination matched what pdfplumber reported for all 110 sentences.
3. **A hyphen at a line end is ambiguous.** "small-" + "scale" could be *small-scale* or *smallscale*. Checking whether the whole word appears elsewhere in the paper settles most cases, with no dictionary and no AI.
4. **Unchanged text on a new page still reads unchanged.** Matching is on text, and the page is reported beside it, so a section pushed from p. 7 to p. 8 isn't a change.
5. **"Nearest now" for an Outdated thread** has to be scored against the quote, not the whole sentence, or short quotes match captions. For a removed passage it still shows an unrelated sentence. A real build needs a minimum score below which it shows nothing.

## What this does not show

The test paper is plain prose. Not tested:
- figures and equations
- footnotes
- in-text citations such as *(Lim et al., 2021)*, beyond a short abbreviation list
- bulleted lists
- tables without borders
- headings that aren't bold
- PDFs made by Google Docs, LibreOffice or "Print to PDF"
- scanned pages, which have no text at all (ADR-058 already says *"No text for vN"*)

The reader rules were also tuned while writing this test. **Before building, run it on two Versions of a real CIT-U thesis.** Point `run.py` at real PDFs, or replace `VERSIONS`.
