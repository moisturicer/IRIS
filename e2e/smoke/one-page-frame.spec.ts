// IR-1353: one page margin and width for every page, every role, except Ask IRIS.
//
// Discover, Settings and My Library sat in a centred 1440px column, the admin
// tables ran edge to edge, Discover put its padding inside the cap rather than
// outside it, and the record Overview kept its own 56px left gutter. Moving
// between them moved the content sideways. Now every page is one frame: a
// gutter (16px on a phone, 28px from 640px) outside a centred cap.
//
// Per screen, at each width, the outermost box under its heading that caps its
// width must be exactly where that frame puts it, measured against `main` (the
// sidebar's edge), and the page must not scroll sideways: a wide table scrolls
// inside its own box instead.
import type { Page } from "@playwright/test";
import { expect, test } from "./support/mock-api";
import { signedIn } from "./support/fixtures";
import { SCREENS } from "./support/screens";
import { measureOverflow } from "../support/viewport";

const WIDTHS = [375, 768, 1280, 1920, 2560];
/** `max-w-page`, 90rem. */
const STANDARD_CAP = 1440;

/**
 * Workspaces that fill the window, outside the frame by the owner's decision
 * (IR-1353): Ask IRIS, the PDF reader and the review workspace.
 */
const WORKSPACE = (id: string) => id.startsWith("ask-iris") || id.startsWith("paper-view-");

/** The record Overview keeps its 1600px cap (`wide-left`, IR-1144), as its owner chose. */
const CAP: Record<string, number> = { "paper-view": 1600 };

interface Frame { left: number; right: number; mainLeft: number; mainRight: number; gutter: number }

/** The outermost width-capped box between the heading and `main`, and `main`'s own edges. */
async function measureFrame(page: Page, heading: string | RegExp): Promise<Frame> {
  const handle = await page.getByRole("heading", { name: heading }).first().elementHandle();
  return page.evaluate((h1) => {
    const main = document.querySelector("main")!;
    let capped: Element | null = null;
    for (let el = h1!.parentElement; el && el !== main; el = el.parentElement) {
      if (getComputedStyle(el).maxWidth !== "none") capped = el;
    }
    // Where content starts and stops: the box inside its padding, so a page that
    // pads inside its cap (as Discover did) is caught, not just a wrong cap.
    const el = capped ?? main;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const m = main.getBoundingClientRect();
    return {
      left: r.left + parseFloat(s.paddingLeft), right: r.right - parseFloat(s.paddingRight),
      mainLeft: m.left, mainRight: m.right, gutter: innerWidth < 640 ? 16 : 28,
    };
  }, handle);
}

for (const screen of SCREENS.filter((s) => s.role && !WORKSPACE(s.id))) {
  test(`${screen.id} sits in the one page frame at every width`, async ({ page, api }) => {
    await page.setViewportSize({ width: WIDTHS[0], height: 900 });
    await signedIn(page, api, screen.role!);
    screen.mocks?.(api);
    await page.goto(screen.path);
    await expect(page.getByRole("heading", { name: screen.heading }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");

    const cap = CAP[screen.id] ?? STANDARD_CAP;
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      // The sidebar's width eases in (`transition-shell`); measure after it settles.
      await page.waitForTimeout(400);
      const f = await measureFrame(page, screen.heading);
      const room = f.mainRight - f.mainLeft - 2 * f.gutter;
      const content = Math.min(cap, room);
      const left = f.mainLeft + f.gutter + (room - content) / 2;

      expect.soft(f.left, `${screen.id} at ${width}px: content's left edge`).toBeCloseTo(left, 0);
      expect.soft(f.right, `${screen.id} at ${width}px: content's right edge`).toBeCloseTo(left + content, 0);
      const { overflow, culprits } = await measureOverflow(page);
      expect.soft(overflow, `${screen.id} at ${width}px scrolls sideways; widest: ${culprits.join(" | ")}`).toBe(0);
    }
  });
}
