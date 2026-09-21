import { describe, expect, it } from "vitest";

import { citedPage, paperHrefAtPage } from "./citedPage";

describe("the page a citation asked for", () => {
  it("reads a page number off the query string", () => {
    expect(citedPage("12")).toBe(12);
  });

  it("ignores an absent or empty value", () => {
    expect(citedPage(null)).toBeNull();
    expect(citedPage("")).toBeNull();
    expect(citedPage("   ")).toBeNull();
  });

  it("ignores anything that is not a positive whole page", () => {
    // The query string is whatever was typed into the address bar. None of
    // these name a page, so none of them reach the viewer.
    expect(citedPage("0")).toBeNull();
    expect(citedPage("-3")).toBeNull();
    expect(citedPage("2.5")).toBeNull();
    expect(citedPage("twelve")).toBeNull();
    expect(citedPage("12; drop")).toBeNull();
  });
});

describe("opening the paper at that page", () => {
  it("asks the PDF viewer for the page with its own fragment", () => {
    expect(paperHrefAtPage("https://iris.test/media/thesis.pdf", 12)).toBe(
      "https://iris.test/media/thesis.pdf#page=12",
    );
  });

  it("links to the paper unchanged when no page was named", () => {
    expect(paperHrefAtPage("https://iris.test/media/thesis.pdf", null)).toBe(
      "https://iris.test/media/thesis.pdf",
    );
  });

  it("stays null when the reader may not fetch the file at all", () => {
    // The backend withholds the URL from someone who cannot download it, and
    // a page anchor must not conjure a link out of that absence.
    expect(paperHrefAtPage(null, 12)).toBeNull();
  });
});
