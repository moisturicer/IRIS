/**
 * The one page frame (IR-519, IR-521, IR-1353).
 *
 * Pages stopped at four different caps (1152, 1200, 1400px, or none), so at
 * 90% zoom -- a ~2130px-wide window on a 1920px screen -- most of them sat in
 * a narrow column between wide empty margins. IR-521 made the cap one value;
 * IR-1353 made the margin one value too, and removed the "full" width the
 * admin tables used: every page is the gutter outside, the 1440px cap inside.
 *
 * jsdom computes no layout, so a width can only be read off the class. The
 * classes are the exported constants, not strings repeated here. The pixels
 * are measured in the smoke tier (e2e/smoke/one-page-frame.spec.ts).
 */
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the config is plain JS and ships no declaration file
import tailwindConfig from "../../../tailwind.config.js";

import { renderScreen, screen } from "@/test/render";

import { PAGE_GUTTER, PAGE_WIDTH, PageContainer } from "./PageContainer";

describe("PageContainer", () => {
  it("centres a page at the shared cap", () => {
    renderScreen(
      <PageContainer>
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

  it("puts the gutter outside the cap, so the cap is the content's width (IR-1353)", () => {
    renderScreen(
      <PageContainer>
        <p>Body</p>
      </PageContainer>,
    );

    const box = screen.getByText("Body").parentElement!;
    const gutter = box.parentElement!;
    expect(gutter.className).toBe(PAGE_GUTTER);
    // Padding on the capped box itself would shrink the content to 1384px.
    expect(box.className).not.toMatch(/\bp[xlrt]?-/);
  });

  it("has one gutter: 16px on a phone and 28px from 640px", () => {
    expect(PAGE_GUTTER).toBe("p-4 sm:p-7");
  });

  it("keeps wide-left pages centred, so a wide window never leaves the spare room on one side", () => {
    expect(PAGE_WIDTH["wide-left"]).toContain("max-w-[100rem]");
    expect(PAGE_WIDTH["wide-left"]).toContain("mx-auto");
  });

  it("has no full width any more: a wide table scrolls in its own box (IR-1353)", () => {
    expect(Object.keys(PAGE_WIDTH)).toEqual(["standard", "wide-left"]);
  });
});
