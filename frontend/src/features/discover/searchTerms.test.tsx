/**
 * Discover's search is by word, not by phrase (IR-1095, spec §4.6): a typed
 * sentence is split into its content words, those are what the catalogue is
 * asked for, and each one is highlighted where it matches. A question gets one
 * suggestion line, and an ordinary search does not.
 */
import { describe, expect, it } from "vitest";

import { render } from "@testing-library/react";

import { highlightTerms, looksLikeQuestion, searchTerms } from "./searchTerms";

describe("searchTerms", () => {
  it("splits a sentence into words and drops punctuation and stopwords", () => {
    expect(searchTerms("Can weather data forecast dengue?")).toEqual(["weather", "data", "forecast", "dengue"]);
  });

  it("keeps a hyphenated word whole and each word once", () => {
    expect(searchTerms("low-cost sensors, low-cost Sensors")).toEqual(["low-cost", "sensors"]);
  });

  it("keeps the typed words when every one is a stopword, so the search still runs", () => {
    expect(searchTerms("how to be")).toEqual(["how", "to", "be"]);
  });

  it("keeps a word that is also a subject, such as IT", () => {
    expect(searchTerms("IT governance")).toEqual(["it", "governance"]);
  });

  it("is empty for blank text", () => {
    expect(searchTerms("  ")).toEqual([]);
  });
});

describe("looksLikeQuestion", () => {
  it.each([
    "Can weather data forecast dengue?",
    "dengue forecasting?",
    "How does rainfall affect flooding in Cebu",
    "what research explores flood resilience",
    // Any search that opens with a question word, as the ticket words it.
    "can opener",
    "why dengue",
  ])("is true for %s", (text) => {
    expect(looksLikeQuestion(text)).toBe(true);
  });

  it.each([
    "dengue forecasting",
    "weather data",
    "",
    "?",
    "  ",
    // A question word on its own is not a question.
    "how",
    "Which",
  ])("is false for %j", (text) => {
    expect(looksLikeQuestion(text)).toBe(false);
  });
});

describe("highlightTerms", () => {
  it("marks every matched word, in any case, and nothing else", () => {
    const { container } = render(<p>{highlightTerms("Dengue cases follow rainfall and weather.", "Can weather data forecast dengue?")}</p>);

    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Dengue", "weather"]);
  });

  it("returns the text untouched when there is nothing to match", () => {
    expect(highlightTerms("Plain text", "")).toBe("Plain text");
  });

  it("does not treat what the reader typed as a pattern", () => {
    const { container } = render(<p>{highlightTerms("A (b) c", "(b")}</p>);

    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["b"]);
  });
});
