/**
 * How an answer's web links reach the reader today (IR-1172).
 *
 * An image in an answer is dropped, so it can never load on its own. A link is
 * not: an http(s) link a paper persuaded the model to write is rendered live,
 * with its address, query string included, left as written. These tests record
 * that; they change nothing. See
 * docs/architecture-review/2026-11-16-ir1172-paper-text-exposure.md.
 */
import { describe, expect, it } from "vitest";

import { renderScreen } from "@/test/render";

import { CitationText } from "./CitationText";

function links(text: string) {
  const { container } = renderScreen(<CitationText text={text} citations={[]} />);
  return { container, anchors: Array.from(container.querySelectorAll("a")) };
}

describe("web links in an answer (recorded, IR-1172)", () => {
  it("drops an image, so nothing is fetched without a click", () => {
    const { container } = links("Figure ![chart](https://collect.test/p.png?q=flood+question).");

    expect(container.querySelector("img")).toBeNull();
  });

  it("keeps a link's address and query string as the model wrote it", () => {
    const { anchors } = links("See [the approval letter](https://collect.test/a?q=which+paper+predicts+floods).");

    expect(anchors).toHaveLength(1);
    expect(anchors[0].getAttribute("href")).toBe("https://collect.test/a?q=which+paper+predicts+floods");
    expect(anchors[0].getAttribute("target")).toBe("_blank");
    expect(anchors[0].getAttribute("rel")).toBe("noreferrer");
  });

  it("turns a bare web address into a live link", () => {
    const { anchors } = links("Approved: https://collect.test/approved?id=7 per the board.");

    expect(anchors.map((a) => a.getAttribute("href"))).toEqual(["https://collect.test/approved?id=7"]);
  });

  it("shows link text that names one site while the address goes to another", () => {
    const { anchors } = links("Read it at [https://cit.edu/ethics](https://collect.test/x).");

    expect(anchors[0].textContent).toBe("https://cit.edu/ethics");
    expect(anchors[0].getAttribute("href")).toBe("https://collect.test/x");
  });
});
