# PROTOTYPE: a layout model beside IR-871's rules (throwaway, never merge)

**Question.** Does a small layout detector, self-hosted so no paper leaves the machine, read real papers better than IR-871's rule-based reader (`../reader.py`)? And what does it cost in memory and time?

**Answer (2026-11-06): no, not as a replacement. Keep the rules.**
- On the real samples it was faster at nothing and better only sometimes.
- It silently lost words.
- It also failed the three-column page.

Its one real advantage, reading scans with OCR, wasn't tested here.

## What it is

- **The model.** PaddlePaddle's **PP-DocLayout v2**, as ONNX through `rapid-layout` 1.2.1. Everything is Apache-2.0, the model is 214 MB and pinned by SHA-256, and it runs on CPU with ONNX Runtime. The AGPL YOLO models the package also offers were deliberately not used.
- **What it does.** It looks at each page rendered at 120 dpi and returns boxes in reading order: header, footer, page number, paragraph title, text, table, image, caption and so on.
- **Nothing is generated.** pdfplumber still reads every word, and each word goes into the box its centre falls in. IR-871's own sentence, hyphen and key code makes the passages, so only the layout differs.
- **Files:**
  - `layout_reader.py` is the reader.
  - `run.py <folder>` compares both readers on every PDF, each in a fresh process.
  - `three_columns.py` reads a drawn three-column page.
  - `out/` is git-ignored, because it holds section headings, which are paper text.

## Run

```
pip install onnxruntime rapid-layout==1.2.1 psutil   # not in requirements
python run.py <folder of sample PDFs>
python three_columns.py
```

The model downloads once from ModelScope and is checked against its SHA-256. No paper is sent anywhere.

## Results on the six real samples (11 PDFs; counts only, no paper text)

| | Rules | Layout model |
|---|---|---|
| Time per paper | 2–10 s | 13–36 s (about 1.3 s a page on a laptop CPU) |
| Peak memory | 75–270 MB | 470–675 MB |
| Reference lists (APA one year per entry, IEEE one `[n]`) | all correct | all correct |
| Version pairs: sections marked changed | exactly the edits; one front-page artifact on sample 1 | exactly the edits, without that artifact |
| Sentences of three words or fewer | sample 6: 19%, sample 5: 15% | sample 6: 11%, sample 5: 12% |
| Sentences not ending in punctuation (a proxy for cut) | lower on the three journal papers | lower on samples 4, 5 and 6 |
| Words lost | none | 0–48 per paper outside every box, dropped without notice: banners, stray footer numbers, and ~40 words of body text on one page |
| Three-column drawn page | column 1 right, columns 2 and 3 interleaved | read as one table, all three interleaved |

## What this shows

1. **Not clearly better.** The model helps on the single-column student paper (sample 6), where it found more headings and fewer fragments. It is slightly worse on the journal papers, and at least as good on everything else.
2. **It can lose text.** A word outside every box disappears. The rules never drop a word unless it's a running head or page number, which is the property review text most needs: a Thread's quote must be findable.
3. **Speed is fine for background work** (minutes per thesis, ADR-058 §1 reads after submission), and memory fits a 4 GB budget. Cost isn't what rules it out.
4. **Three columns need a rule either way.** The rules' single gutter split is the cause, and splitting each side again is the fix.

## Not tested

- OCR on scanned papers, the one thing rules can't do at all.
- PP-DocLayout v3 and the 7 MB PubLayNet model.
- A real three-column paper.
- GPU.
- Linux timing.

## If revisited

Use the model as a **fallback, not the default**: only when the rules' fail-safe triggers (`sections_unreliable`), or for a paper with no text layer, paired with a small OCR model. Never let a word outside every box go silently: put it back by position or warn.
