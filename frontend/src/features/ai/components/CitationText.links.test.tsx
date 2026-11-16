// IR-1172 (how answer links reach the reader): records today's behaviour, changes none.
// Images are dropped; http(s) links stay live. The fix under IR-1112 flips these deliberately.
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { CitationText } from "./CitationText";

function renderAnswer(text: string) {
  renderScreen(<CitationText text={text} citations={[]} />);
}

describe("web links in an answer, as rendered today (IR-1172)", () => {
  it("drops an image, so nothing is fetched without a click", () => {
    renderAnswer("Figure ![chart](https://collect.test/p.png?q=flood+question).");

    expect(screen.queryByRole("img")).toBeNull();
  });

  it("keeps a link's address and query string as the model wrote it", () => {
    renderAnswer("See [the approval letter](https://collect.test/a?q=which+paper+predicts+floods).");

    const [link] = screen.getAllByRole("link");
    expect(link.getAttribute("href")).toBe("https://collect.test/a?q=which+paper+predicts+floods");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noreferrer");
  });

  it("turns a bare web address into a live link", () => {
    renderAnswer("Approved: https://collect.test/approved?id=7 per the board.");

    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "https://collect.test/approved?id=7",
    ]);
  });

  it("shows link text that names one site while the address goes to another", () => {
    renderAnswer("Read it at [https://cit.edu/ethics](https://collect.test/x).");

    const link = screen.getByRole("link", { name: "https://cit.edu/ethics" });
    expect(link.getAttribute("href")).toBe("https://collect.test/x");
  });
});
