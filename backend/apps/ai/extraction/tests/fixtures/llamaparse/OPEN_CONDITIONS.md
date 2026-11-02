# What the recording shows for ADR-056's open conditions

**Not recorded yet.** No development LlamaParse key was available when the
script was written (IR-849). Fill this in from the first run.

## Formulas arrive as LaTeX? (open condition 4)

Pending. `two_columns` prints `E = m c^2` and `figures` prints
`a^2 + b^2 = c^2`. Check their `items` text for `$...$` or `\(...\)`
delimiters.

## Credits charged per page (open condition 3)

Pending. Divide each manifest's `credits` by the PDF's page count, and note
how many pages Cost Optimizer moved (`metadata.pages[].cost_optimized`).

| Fixture | Pages | Credits | Per page |
|---|---|---|---|
| `figures` | 1 | | |
| `numbered_headings` | 2 | | |
| `table_across_pages` | 2 | | |
| `two_columns` | 1 | | |
