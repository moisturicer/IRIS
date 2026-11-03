# What the recording shows for ADR-056's open conditions

Recorded 2026-11-02 (IR-841) on version `2026-09-28`, tier `agentic`, North
America. LlamaParse accepted the pinned version. Four synthetic PDFs, never a
finding about a real paper.

## Formulas arrive as LaTeX? (open condition 4)

**Only for a display formula.** `figures` prints `a^2 + b^2 = c^2` on its own
line and it came back as `$$a^2 + b^2 = c^2$$`. `two_columns` prints
`E = m c^2` inside a column and it came back as plain text, with no
delimiters. IR-851 should check real theses before relying on delimiters.

## Credits charged per page (open condition 3)

No page was moved by Cost Optimizer (`cost_optimized` is `false` everywhere).

| Fixture | Pages | Credits | Per page |
|---|---|---|---|
| `figures` | 1 | 15 | 15 |
| `numbered_headings` | 2 | 30 | 15 |
| `table_across_pages` | 2 | 33 | 16.5 |
| `two_columns` | 1 | 15 | 15 |

93 credits for 6 pages (about $0.12 at $1.25 per 1,000). The pricing page
predicts 18 per page (10 `agentic`, 3 `layout` images, 5 high-effort
confidence); no `layout` image was produced, which may be why it is lower.

## Not shown by these PDFs

- **Figure images.** `images_content_metadata.total_count` is 0 for all four.
  The fixtures draw vector rectangles, which came back as text items starting
  `drawing:`, not as `image` items. The figure path in the Extractor is tested
  against the documented response shape only; IR-845 needs a PDF with a
  raster figure to record.
- **Watermarks.** No fixture has one, so no page carries `watermark`.
- **Low confidence.** `two_columns` scored 0.3 although its text is correct.
