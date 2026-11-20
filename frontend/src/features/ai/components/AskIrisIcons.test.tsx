import { render } from "@testing-library/react";
import type { ComponentType } from "react";
import { describe, expect, it } from "vitest";

import * as icons from "./AskIrisIcons";
import { OUTLINE_ICONS } from "./AskIrisIcons";

// IR-1235: one stroked set, 20 px in a control and 16 px beside text, drawn as
// inline SVG and always hidden from assistive technology: the button or text
// that holds an icon carries its name.

const outline = Object.entries(OUTLINE_ICONS);

describe("the Ask IRIS outline icon set", () => {
  it("covers the icons the feature draws", () => {
    for (const name of ["PlusIcon", "CloseIcon", "RetryIcon", "PencilIcon", "SearchIcon", "BookIcon"]) {
      expect(Object.keys(OUTLINE_ICONS), name).toContain(name);
    }
  });

  it.each(outline)("%s is a 20 px stroked SVG at 1.75, hidden from assistive technology", (_name, Icon) => {
    const svg = render(<Icon />).container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("stroke", "currentColor");
    expect(svg).toHaveAttribute("fill", "none");
    expect(svg).toHaveAttribute("stroke-width", "1.75");
    expect(svg).toHaveClass("size-5");
  });

  it.each(outline)("%s drops to 16 px when set beside text", (_name, Icon) => {
    const svg = render(<Icon inline />).container.querySelector("svg");
    expect(svg).toHaveClass("size-4");
    expect(svg).not.toHaveClass("size-5");
  });

  it("hides every other icon the module draws unless it is given a name", () => {
    for (const [name, Icon] of Object.entries(icons)) {
      if (!name.endsWith("Icon") || typeof Icon !== "function") continue;
      const Component = Icon as ComponentType;
      const svg = render(<Component />).container.querySelector("svg");
      expect(svg, name).toHaveAttribute("aria-hidden", "true");
    }
  });
});
