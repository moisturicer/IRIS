# How production chatbot/RAG products cite their sources

Research note, 2026-09-21. External research — not an audit of IRIS's own code (see the short comparison at the end for that). Written for whoever next touches `apps/ai/answers/citations.py` or `PassageQuote.tsx`, after a live bug in IRIS's own citation parser (see [ask-iris-manual-verification-transcript.md](ask-iris-manual-verification-transcript.md)) made the question of "how do other people avoid this" worth answering properly.

**Sourcing note.** Every claim below is traced to the primary source that owns it — official API docs, first-party product blog posts, or the paper itself. Two things were investigated and explicitly rejected rather than included: a widely-repeated "63% / 72% of users trust AI more when it explains itself" statistic attributed to Nielsen Norman Group, which does not appear anywhere in the NN/G article that supposedly carries it ([nngroup.com/articles/genai-ux-research-agenda](https://www.nngroup.com/articles/genai-ux-research-agenda/) — fetched and checked directly: it is a list of open research questions, not a source of any statistic); and any first-party confirmation of NotebookLM's exact click/highlight behavior, which could not be found on `support.google.com` after two direct attempts — that claim is reported below as community-observed, not vendor-confirmed, and flagged as such. Phind is excluded from the live comparison: it shut down January 16, 2026, confirmed independently by multiple outlets ([Devtalk](https://devtalk.com/t/phind-has-shut-down/230488), [neuronfeed.com](https://neuronfeed.com/startups/phind)), though no first-party Phind announcement is findable now that the company itself is gone.

---

## 1. How citations are surfaced

There are two structurally different families, and the difference is not cosmetic — it determines what can go wrong.

**Family A: the API returns citations as structured objects attached to spans of the response, separate from the visible text.** Anthropic's Citations API is the clearest example. A cited response is not one string with markers embedded in it — it's a *sequence of content blocks*, and only the blocks that make a sourced claim carry a `citations` array:

```json
{ "type": "text", "text": "According to the document, " },
{
  "type": "text",
  "text": "the grass is green",
  "citations": [{ "type": "char_location", "cited_text": "The grass is green.",
                   "document_index": 0, "start_char_index": 0, "end_char_index": 20 }]
}
```
— [Citations API docs](https://platform.claude.com/docs/en/build-with-claude/citations), "Response structure" section, quoted verbatim.

OpenAI's Assistants/Responses API file-search tool does the same thing in a different shape: an `annotations` array on the message, each entry a `file_citation` object with `type`, `index`, `file_id`, `filename` (and `quote` when present) — [OpenAI file-search guide](https://developers.openai.com/api/docs/guides/tools-file-search). Perplexity's Agent API follows the identical pattern: an `annotations` array with `{"type": "citation", "url": ...}` objects attached to `output_text` blocks — [Perplexity API docs](https://docs.perplexity.ai/getting-started/quickstart).

**Family B: the model emits inline text markers that a client must parse out of free-form output.** This is what IRIS does (`[1]`, `【1】`), and it turns out OpenAI's own consumer chat product does something structurally similar internally — but with a critical difference in the marker alphabet, covered in §3.

The practical consequence: in Family A, "is this claim cited or not" is a property you can read off the response with no parsing at all — an empty or absent `citations` array *is* the answer. In Family B, that question requires successfully parsing whatever the model actually wrote, which is exactly the step that broke in IRIS's live testing this week.

**Sources panel, independent of which family is used.** Perplexity and Bing's Copilot Search both pair inline citation numbers with a persistent list of every source the answer drew on — Perplexity as a horizontal strip of source cards above the answer plus an expandable right panel; Bing as "easy access to cited sources and all relevant web results at the top," separate from the inline links (Bing: "[Introducing Copilot Search in Bing](https://blogs.bing.com/search/April-2025/Introducing-Copilot-Search-in-Bing)," quoted directly below). This is the same shape IRIS already has — `sources` (record cards) returned alongside `citations` (resolved passage markers) on `/ai/ask/` — so this part of IRIS's design already matches the pattern, independent of the parsing bug.

---

## 2. Linking a citation to the exact supporting passage

Three distinct mechanisms show up, at three different levels of precision, and they map directly onto Anthropic's three document types:

| Precision | Mechanism | Who does it |
|---|---|---|
| Character span | Exact start/end offset into the source text | Anthropic plain-text documents — `start_char_index`/`end_char_index`, 0-indexed, exclusive end |
| Page | Page range in the original PDF | Anthropic PDF documents — `start_page_number`/`end_page_number`, 1-indexed, exclusive end. **This is the same granularity IRIS uses** (`Citation.page` → `?page=N` → PDF viewer `#page=N`) |
| Block | Index into caller-supplied content blocks (e.g. one RAG chunk = one block) | Anthropic "custom content" documents — `start_block_index`/`end_block_index`, and explicitly the recommended shape for RAG: *"if you want Claude to be able to cite specific sentences from your RAG chunks, you should put each RAG chunk into a plain text document"* (Citations API docs, "Automatic chunking vs custom content") |

Bing's Copilot Search does something IRIS does not: it inline-links the *entire cited sentence or passage*, not just a trailing marker — *"We inline link the entire sentence or passage within the responses so you can easily navigate to the sources"* (Bing blog, quoted directly). That's a stronger affordance than a single `[1]` at the end of a sentence: the whole claim is clickable, not just a two-character marker next to it.

NotebookLM is reported (not vendor-confirmed — see the sourcing note above) to go one step further: hovering a citation chip previews the quoted text without navigating away, and clicking opens the source panel with the exact passage highlighted in place, rather than only scrolled-to. If real, that's a stronger guarantee than page-level linking: it points at the *sentence*, not just the *page it's somewhere on* — which is precisely the gap IR-59 (PDF.js highlight overlay) exists to close for IRIS; today IRIS opens the right page and stops there.

None of the sources reviewed described "quote-on-hover" as a documented API behavior — where it appears, it's a client-side UI choice built on top of the `cited_text`/`quote` field the API already returns. IRIS already has the underlying data for this (`citation.text` is the exact passage) — the hover/preview treatment is a frontend decision, not something blocked on backend work.

---

## 3. What happens when a citation doesn't resolve

This is the question IRIS's live bug turned out to be about, and every primary source that addresses it converges on the same answer: **drop silently, never render a raw or partial marker.**

- **Anthropic**: not directly documented as a failure mode, because the architecture mostly prevents it — citations are extracted server-side from the model's internal output into `char_location`/`page_location`/`content_block_location` objects before they ever reach the client, so a client-visible "unparseable citation" case doesn't really exist in the same form. The reliability claim is explicit: *"citations are guaranteed to contain valid pointers to the provided documents"* (Citations API docs, "Comparison with prompt-based approaches").
- **OpenAI's chat product** uses a completely different internal marker format from its API's `file_citation` objects, worth reading in full because it's the closest primary-source analogue to IRIS's own bracket-parsing problem. Citations are delimited with **Unicode Private Use Area control characters** — `CITATION_START` (``), `CITATION_DELIMITER` (``), `CITATION_STOP` (``) — wrapping a citation family (`cite`), a source ID (`turn0file1`, `block5`), and an optional locator. The documented template: `{CITATION_START}cite{CITATION_DELIMITER}turn0file1{CITATION_DELIMITER}L8-L13{CITATION_STOP}` ([OpenAI citation-formatting guide](https://developers.openai.com/api/docs/guides/citation-formatting)). The stated design rationale: these markers were chosen because they *"closely match the markers our models are trained on"* — i.e. the model is trained to natively emit exactly this byte sequence, rather than a client retrofitting a parser onto whatever shape the model happens to produce. **This is the structural difference from IRIS's approach**: OpenAI controls both ends (training and parsing) of one fixed, invisible format; IRIS's regex is reverse-engineered against whatever a third-party-served open-weight model (gpt-oss-120b, via Groq) happens to emit, and that shape can drift out from under the parser with no warning — which is exactly what happened. The guide's own reference parser confirms the failure-mode convention: source IDs and locators are validated against a pattern (`^[A-Za-z0-9_-]+$` for IDs, `^L\d+(?:-L\d+)?$` for line locators), and anything that doesn't validate is **silently excluded from the result with no error raised** — the same "drop rather than render garbage" choice IRIS's own docstring states independently.

  One more thing worth naming: OpenAI's documented locator syntax is a line range, `L#-L#`. The malformed marker IRIS's live testing found was `【1†L1-L5】` — a number, a separator, then an `L#-L#` range. That shape is not a coincidence. `gpt-oss-120b` is OpenAI-lineage; the most likely explanation is that the model's citation behavior was shaped by training data or RL environments resembling OpenAI's own internal format, and it surfaced that trained-in habit even though IRIS's prompt never asked for it and Groq's serving stack does nothing to suppress it. Worth remembering the next time this format drifts again: the model's "invented" formats are unlikely to be arbitrary.

- **OpenAI's community forum** (secondary, but reporting a first-party bug against OpenAI's own API, so included as evidence of the failure mode rather than as a spec) confirms the same class of problem can hit the *structured* approach too: a thread titled *"Citation format differs in GPT-4.1-mini file search: annotations missing, replaced with raw references"* describes exactly IRIS's symptom — expected structured citations, got raw unparsed reference text in the output instead, model-dependent. Structured citation APIs reduce this failure mode; they don't eliminate it.

**No source reviewed described rendering a broken citation to the user as acceptable design.** The convergent answer across every primary source is: a citation that cannot be resolved to a real source is not shown as a citation at all — either dropped from the visible text (IRIS's own choice for a matched-but-out-of-range marker) or never produced as a citation to begin with (the structured-API approach).

---

## 4. Distinguishing grounded from ungrounded content

This is where the two families (§1) diverge most sharply, and it's the clearest limitation in IRIS's current design.

In Anthropic's and OpenAI's structured approaches, "grounded vs. not" is **structural, not visual** — it falls directly out of the response shape. A text block either carries a non-empty `citations`/`annotations` array or it doesn't; a renderer can style the two differently (bold source-backed spans, dim or plain-render the rest) with no additional inference, because the API already segmented the response into claim-sized pieces at generation time. Anthropic's example response shows this explicitly: plain narrative text ("According to the document, " / " and " / ". Information from page 5 states that ") sits in blocks with no `citations` key at all, interleaved with cited-claim blocks that have one.

IRIS's current design has no equivalent segmentation. `GroundedAnswer.text` is one undifferentiated string; some sentences happen to contain a resolved `[N]` marker and some don't, but nothing marks *which portion of the prose* a given citation actually supports versus connective or inferential text the model added on its own. Reconstructing "is this specific sentence grounded" from IRIS's output today would mean guessing sentence boundaries and heuristically associating them with nearby marker positions — brittle, and not something the current architecture gives a client for free the way the structured APIs do.

This gap is worth being honest about rather than working around cosmetically: closing it properly is closer to "adopt something like Anthropic's per-span citation model" than "add a CSS class." Not a small change, and not this document's call to make — but the shape of the gap is now on record.

---

## 5. Published research on citation trust

One directly relevant, well-sourced finding, from a real large-scale experiment rather than a survey or a blog post's impression:

**Li & Aral, "Human Trust in AI Search: A Large-Scale Experiment"** (MIT; submitted 8 Apr 2025; [arXiv:2504.06435](https://arxiv.org/abs/2504.06435)). ~12,000 search queries across seven countries plus a preregistered, randomized experiment on a U.S.-representative sample. The finding that matters most here, quoted from the abstract:

> "reference links and citations significantly increase trust in GenAI, **even when those links and citations are incorrect or hallucinated**."

And, in the same study, the inverse for a different transparency mechanism:

> "Uncertainty highlighting, which reveals GenAI's confidence in its own conclusions, makes us less willing to trust and share generative information whether that confidence is high or low."

Read together, these two findings say something uncomfortable and directly relevant to the citation-parser bug IRIS just fixed: **the mere presence of a citation-shaped thing raises trust, independent of whether it actually resolves to anything real.** A citation that silently fails to resolve — IRIS's own stated failure mode — is not neutral. It doesn't just fail to help; per this study, whatever *did* successfully render as a citation-looking artifact nearby is doing trust-building work regardless of whether the reader could actually verify it. That's an argument for treating citation-parser correctness as a trust-integrity property, not only a data-completeness one — a broken citation parser doesn't just produce fewer citations, it can produce a false signal of verifiability alongside a real drop in what's actually verifiable.

No other academic or first-party UX-research source reviewed produced a citation-specific, primary-sourced, quotable finding strong enough to include here without padding — several listicle-style "AI UX pattern" round-ups exist (aydesign.ai, shapeof.ai, AI UX Playground) but they're synthesis of the same product observations already covered in §1–3 above, not independent research, so they're not cited as authority here.

---

## Comparison: where this leaves IRIS's own design

Brief, because the point of this document is the external research, not another audit of `apps/ai/`.

| | IRIS today | The structured-API pattern (Anthropic, OpenAI, Perplexity) |
|---|---|---|
| Citation shape | Bracket marker embedded in free text (`[1]`, `【1】`), extracted by a hand-maintained regex | Structured object attached to a response span, extracted server-side before the client ever sees it |
| Failure mode | A marker format the regex doesn't recognize passes through unresolved and undetected — the bug just fixed | Largely designed out; the residual failure mode (OpenAI's `file_citation` forum report) is model-dependent and vendor-side, not client-parsing |
| Passage precision | Page number (`?page=N` → `#page=N`) | Character span, page range, or block index, selectable by document type |
| Exact-passage highlight | Not yet — opens the right page, not the highlighted span (blocked on IR-59) | NotebookLM reportedly highlights in place (unconfirmed by a first-party source); Anthropic's `char_location`/block index gives a client everything needed to do the same |
| Grounded vs. ungrounded | Not distinguished within one answer's text | Structural — a span either carries citations or it doesn't |

The one-line summary: IRIS's design sits in the same family OpenAI's own consumer chat product uses internally (trained marker format, client-side parsing), and inherits that family's characteristic failure mode — a marker shape the parser wasn't built for passes through silently. The structured-API family (Anthropic, and OpenAI's own *API*, as opposed to its chat product) designs that failure mode out by construction, at the cost of depending on the vendor to support it. Since IRIS's provider (`openai/gpt-oss-120b` via Groq, per ADR-021) does not expose a structured citations API today, the practical mitigation available now is what the parser fix already did: build the regression tests from real captured model output, and expect the format to drift again.
