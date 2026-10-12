/**
 * The one width rule for app pages (IR-519, IR-521).
 *
 * Pages stopped at four different caps (1152, 1200, 1400px, or none), so at
 * 90% zoom -- a ~2130px-wide window on a 1920px screen -- most of them sat in
 * a narrow column between wide empty margins. `PageContainer` is the single
 * cap: "standard" centres content at ~1440px, "full" uses the whole width.
 *
 * jsdom computes no layout, so a width can only be read off the class. The
 * classes are the exported constants, not strings repeated here.
 */
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the config is plain JS and ships no declaration file
import tailwindConfig from "../../../tailwind.config.js";

import { renderScreen, screen } from "@/test/render";

import { PAGE_WIDTH, PageContainer } from "./PageContainer";

describe("PageContainer", () => {
  it("centres standard pages at the shared cap", () => {
    renderScreen(
      <PageContainer width="standard">
        <p>Body</p>
      </PageContainer>,
    );

    const box = screen.getByText("Body").parentElement!;
    expect(box.className).toContain(PAGE_WIDTH.standard);
    expect(PAGE_WIDTH.standard).toContain("max-w-page");
    // The cap is a theme token, not a literal: 90rem is 1440px.
    expect(tailwindConfig.theme.extend.maxWidth.page).toBe("90rem");
    expect(PAGE_WIDTH.standard).toContain("mx-auto");
  });

  it("lets full pages use the whole width", () => {
    renderScreen(
      <PageContainer width="full">
        <p>Body</p>
      </PageContainer>,
    );

    expect(screen.getByText("Body").parentElement!.className).not.toMatch(/max-w-/);
  });

  it("is standard unless told otherwise", () => {
    renderScreen(
      <PageContainer>
        <p>Body</p>
      </PageContainer>,
    );

    expect(screen.getByText("Body").parentElement!.className).toContain(PAGE_WIDTH.standard);
  });
});
