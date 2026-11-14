import { describe, expect, it } from "vitest";

import { plainSnippet } from "./plainSnippet";

describe("plainSnippet", () => {
  it("leaves plain prose as it is, with its whitespace collapsed", () => {
    expect(plainSnippet("We trained   a network\non gauge data.")).toBe("We trained a network on gauge data.");
  });

  it("drops heading, list and quote markers at the start of a line", () => {
    expect(plainSnippet("## 3.2 Methods\n- first step\n1. second step\n> quoted")).toBe(
      "3.2 Methods first step second step quoted",
    );
  });

  it("keeps the words of emphasis, code and strikethrough", () => {
    expect(plainSnippet("a **bold** and *slanted* and __also bold__ and `code` and ~~gone~~ claim")).toBe(
      "a bold and slanted and also bold and code and gone claim",
    );
  });

  it("keeps the text of links and the alt text of images, never the address", () => {
    expect(plainSnippet("See [the report](https://example.org/r.pdf) and ![a chart](img.png).")).toBe(
      "See the report and a chart.",
    );
  });

  it("does not mistake snake_case or a lone asterisk for emphasis", () => {
    expect(plainSnippet("the rain_gauge_data column, p < 0.05*")).toBe("the rain_gauge_data column, p < 0.05*");
  });

  it("flattens a table to its cell text and drops the separator row", () => {
    expect(plainSnippet("| Model | RMSE |\n| --- | --- |\n| CNN | 0.12 |")).toBe("Model · RMSE CNN · 0.12");
  });

  it("removes fences and HTML tags but keeps what they held", () => {
    expect(plainSnippet("```python\nx = 1\n```\n<b>done</b>")).toBe("x = 1 done");
  });

  it("leaves a display formula untouched, so it can still be typeset", () => {
    expect(plainSnippet("where $$a_i * b_i$$ holds")).toBe("where $$a_i * b_i$$ holds");
  });

  it("unescapes characters the Markdown escaped", () => {
    expect(plainSnippet("1\\. not a list, 2 \\* 3")).toBe("1. not a list, 2 * 3");
  });

  it("is empty for text that was only markup", () => {
    expect(plainSnippet("---\n\n")).toBe("");
  });
});
