/**
 * Inline citation chips (IR-329): a marker in the answer text becomes a
 * clickable chip when it resolves, a placeholder while streaming, and
 * nothing at all when it never resolves.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { Citation } from "@/types/ai";

import { CitationText } from "./CitationText";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         4,
  text:         "we trained a convolutional neural network on rainfall gauge data",
  context_path: ["Flood Prediction in the Mananga Catchment", "Methods"],
  regions:      [],
};

describe("a finished message's inline citations", () => {
  it("turns a resolved marker into a clickable chip", () => {
    renderScreen(<CitationText text="Rainfall gauges feed the model [1]." citations={[citation]} />);

    const chip = screen.getByRole("link", {
      name: /Open Flood Prediction in the Mananga Catchment at page 4/i,
    });
    expect(chip.getAttribute("href")).toBe("/records/7?page=4");
    expect(chip.textContent).toBe("1");
  });

  it("renders an out-of-range marker as nothing, with no dangling chip", () => {
    renderScreen(<CitationText text="Rainfall gauges feed the model [7]." citations={[citation]} />);

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Rainfall gauges feed the model/)).toBeTruthy();
  });

  it("renders a replayed pointer-only citation as a bare chip", () => {
    renderScreen(
      <CitationText
        text="Rainfall gauges feed the model [1]."
        citations={[{ marker: 1, record_id: 7, chunk_id: 11, page: 4 }]}
      />,
    );

    const chip = screen.getByRole("link", { name: /Open the source at page 4/i });
    expect(chip.getAttribute("href")).toBe("/records/7?page=4");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <CitationText text="Rainfall gauges feed the model [1]." citations={[citation]} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});

describe("a still-streaming message's markers", () => {
  it("hides a complete marker behind a placeholder rather than raw brackets", () => {
    renderScreen(
      <CitationText text="Rainfall gauges feed the model [1]." citations={[]} streaming />,
    );

    expect(screen.queryByText(/\[1\]/)).toBeNull();
    expect(screen.getByText(/Rainfall gauges feed the model/)).toBeTruthy();
  });

  it("leaves a marker still arriving as literal text until it closes", () => {
    renderScreen(<CitationText text="Rainfall gauges feed the model [1" citations={[]} streaming />);

    expect(screen.getByText(/\[1/)).toBeTruthy();
  });

  it("renders no chip yet even once citations resolve, until streaming ends", () => {
    // Deliberate: the caller only flips `streaming` off once the finished,
    // canonicalized text is in hand -- passing `citations` early with
    // `streaming` still true must not render a chip against raw markers.
    renderScreen(
      <CitationText text="Rainfall gauges feed the model [1]." citations={[citation]} streaming />,
    );

    expect(screen.queryByRole("link")).toBeNull();
  });
});

// jsdom's getComputedStyle throws on MathML elements, so `getByRole("math")`
// cannot be used. KaTeX keeps the TeX source in an <annotation> inside its
// MathML, which is found by text instead.
const tex = (source: string) => screen.getByText(source, { selector: "annotation" });

describe("mathematics in an answer (IR-429)", () => {
  it("renders inline LaTeX as mathematics, not source", () => {
    renderScreen(<CitationText text="The loss uses $x_i$ per sample." citations={[]} />);

    expect(tex("x_i")).toBeTruthy();
    expect(screen.queryByText(/\$x_i\$/)).toBeNull();
  });

  it("renders displayed LaTeX as mathematics", () => {
    const { container } = renderScreen(
      <CitationText text={"Energy is\n\n$$\nE = mc^2\n$$\n\nas known."} citations={[]} />,
    );

    expect(tex("E = mc^2")).toBeTruthy();
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("leaves a citation chip working beside mathematics", () => {
    renderScreen(<CitationText text="Gauges feed $f(x)$ [1]." citations={[citation]} />);

    expect(tex("f(x)")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open Flood Prediction/i })).toBeTruthy();
  });

  it("passes axe with mathematics on the page", async () => {
    const { container } = renderScreen(<CitationText text="Uses $x_i$ here." citations={[]} />);

    await expectNoBlockingA11yViolations(container);
  });
});

describe("an image in an answer (IR-429)", () => {
  it("renders no image element for Markdown image syntax", () => {
    renderScreen(
      <CitationText text="Accuracy rose ![Figure 3](https://x.test/f3.png) after tuning." citations={[]} />,
    );

    expect(screen.queryByRole("img")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/Accuracy rose/)).toBeTruthy();
  });
});
