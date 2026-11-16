// IR-1172: outside addresses in an answer are shown as text, never as live links.
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { CitationText } from "./CitationText";

function renderAnswer(text: string) {
  return renderScreen(<CitationText text={text} citations={[]} />).container;
}

describe("outside addresses in an answer (IR-1172)", () => {
  it("drops an image, so nothing is fetched", () => {
    renderAnswer("Figure ![chart](https://collect.test/p.png?q=flood+question).");

    expect(screen.queryByRole("img")).toBeNull();
  });

  it("shows a markdown link's address as text and makes nothing clickable", () => {
    const container = renderAnswer("See [the approval letter](https://collect.test/a?q=which+paper+predicts+floods).");

    expect(screen.queryByRole("link")).toBeNull();
    expect(container.textContent).toContain(
      "the approval letter (https://collect.test/a?q=which+paper+predicts+floods)",
    );
  });

  it("shows a bare web address once, as text", () => {
    const container = renderAnswer("Approved: https://collect.test/approved?id=7 per the board.");

    expect(screen.queryByRole("link")).toBeNull();
    expect(container.textContent).toBe("Approved: https://collect.test/approved?id=7 per the board.");
  });

  it("shows the real address beside link text that names another site", () => {
    const container = renderAnswer("Read it at [https://cit.edu/ethics](https://collect.test/x).");

    expect(screen.queryByRole("link")).toBeNull();
    expect(container.textContent).toContain("https://cit.edu/ethics (https://collect.test/x)");
  });
});
