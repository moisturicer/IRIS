/**
 * The rectangles a citation highlights, drawn over a rendered page (IR-334,
 * IR-335). Positioning is the property under test: a region's box must sit
 * at exactly the fraction of the page it was given, so it stays aligned with
 * the text under it whatever the page is rendered at.
 */
import { describe, expect, it } from "vitest";

import { render } from "@/test/render";
import type { Region } from "@/types/ai";

import { CitationOverlay } from "./CitationOverlay";

describe("the citation highlight overlay", () => {
  it("positions a region as a percentage of the page, not a pixel value", () => {
    const regions: Region[] = [{ page: 4, left: 0.1, top: 0.2, right: 0.6, bottom: 0.3 }];
    const { container } = render(<CitationOverlay regions={regions} />);

    // `parseFloat`, not exact string equality: `(0.3 - 0.2) * 100` is
    // `9.999999999999998` in IEEE 754, a real property of the arithmetic
    // rather than a bug -- the wire already rounds to six decimals, so this
    // is sub-pixel noise no reader could see.
    const box = container.querySelector("div > div > div") as HTMLDivElement;
    expect(parseFloat(box.style.left)).toBeCloseTo(10);
    expect(parseFloat(box.style.top)).toBeCloseTo(20);
    expect(parseFloat(box.style.width)).toBeCloseTo(50);
    expect(parseFloat(box.style.height)).toBeCloseTo(10);
  });

  it("draws one box per region", () => {
    const regions: Region[] = [
      { page: 4, left: 0.1, top: 0.1, right: 0.3, bottom: 0.2 },
      { page: 4, left: 0.5, top: 0.5, right: 0.7, bottom: 0.6 },
    ];
    const { container } = render(<CitationOverlay regions={regions} />);

    expect(container.querySelectorAll("div > div > div")).toHaveLength(2);
  });

  it("draws nothing for an empty region list -- the honest state for a recovered no-rectangle passage", () => {
    const { container } = render(<CitationOverlay regions={[]} />);

    expect(container.firstChild).toBeNull();
  });

  it("is hidden from assistive tech -- decorative, the citation link already names the page", () => {
    const regions: Region[] = [{ page: 4, left: 0.1, top: 0.1, right: 0.3, bottom: 0.2 }];
    const { container } = render(<CitationOverlay regions={regions} />);

    expect(container.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});
