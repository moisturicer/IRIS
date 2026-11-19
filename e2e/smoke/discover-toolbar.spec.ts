// IR-1190: Discover's controls are ONE row under search -- Papers / People, Sort,
// Filters, the column toggle (from xl) and Publish -- at 360, 768, 1280 and 1745 px.
//
// jsdom draws no layout, so the unit tests can only check the class tokens that
// should give one row. This is the measurement: every control's own box, in a real
// browser, at each of the four widths the viewport matrix uses (IR-910).
import { expect, test } from "./support/mock-api";
import { PAPER, mockShell, signedIn } from "./support/fixtures";
import { measureOverflow, VIEWPORTS } from "../support/viewport";

/** Browsers round boxes to fractions of a pixel; a few px of difference is not a second row. */
const SAME_LINE = 3;
const TOUCH = 44;

for (const vp of VIEWPORTS) {
  test.describe(`Discover controls at ${vp.name}px`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("sit in one row that neither wraps nor scrolls, and the page does not scroll sideways", async ({ page, api }) => {
      await signedIn(page, api);
      mockShell(api);
      await page.goto("/");
      await expect(page.getByRole("link", { name: new RegExp(PAPER.title) }).first()).toBeVisible();

      const row = page.getByRole("group", { name: "Discover controls" });
      const boxes = await row.evaluate((el) => {
        const rowBox = el.getBoundingClientRect();
        const controls = Array.from(el.querySelectorAll<HTMLElement>("button, select"))
          .filter((c) => c.getBoundingClientRect().width > 0)
          .map((c) => {
            const b = c.getBoundingClientRect();
            const name = c.tagName === "SELECT" ? "Sort" : c.getAttribute("aria-label") ?? c.textContent?.trim() ?? c.tagName;
            return { name, left: b.left, right: b.right, top: b.top, bottom: b.bottom, width: b.width, height: b.height };
          });
        return {
          rowTop: rowBox.top, rowBottom: rowBox.bottom,
          scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
          overflowX: getComputedStyle(el).overflowX, flexWrap: getComputedStyle(el).flexWrap,
          controls,
        };
      });

      // Papers, People, Sort, Filters and Publish always; the column toggle from xl.
      const names = boxes.controls.map((c) => c.name);
      expect(names.length, names.join(" | ")).toBe(vp.width >= 1280 ? 6 : 5);

      // One row: nothing wraps, nothing scrolls inside it.
      expect(boxes.flexWrap).toBe("nowrap");
      expect(boxes.overflowX).toBe("visible");
      expect(boxes.scrollWidth).toBeLessThanOrEqual(boxes.clientWidth);
      const tops = boxes.controls.map((c) => c.top);
      expect(Math.max(...tops) - Math.min(...tops), `control tops: ${tops.join(", ")}`).toBeLessThanOrEqual(SAME_LINE);
      for (const c of boxes.controls) {
        expect(c.top, c.name).toBeGreaterThanOrEqual(boxes.rowTop - 1);
        expect(c.bottom, c.name).toBeLessThanOrEqual(boxes.rowBottom + 1);
        expect(c.left, `${c.name} left of the screen`).toBeGreaterThanOrEqual(0);
        expect(c.right, `${c.name} past the right edge`).toBeLessThanOrEqual(vp.width);
      }
      // Side by side, not on top of one another.
      const ordered = [...boxes.controls].sort((a, b) => a.left - b.left);
      ordered.slice(1).forEach((c, i) => expect(c.left, `${c.name} overlaps ${ordered[i].name}`).toBeGreaterThanOrEqual(ordered[i].right - 1));

      // On a phone every control, icon or not, is a 44 px target. From `sm` the
      // Papers / People segments sit inside a 44 px track (IR-1082), so the track,
      // not each segment, is the target there.
      if (vp.width < 640) {
        for (const c of boxes.controls) {
          expect(c.height, `${c.name} height`).toBeGreaterThanOrEqual(TOUCH - 1);
          if (c.name !== "Sort") expect(c.width, `${c.name} width`).toBeGreaterThanOrEqual(TOUCH - 1);
        }
      }
      for (const name of ["Papers", "People", "Publish"]) await expect(row.getByRole("button", { name })).toBeVisible();
      await expect(row.getByRole("button", { name: /^Filters/ })).toBeVisible();
      await expect(row.getByRole("combobox", { name: "Sort" })).toBeVisible();
      await expect(row.getByRole("button", { name: /column/ })).toHaveCount(vp.width >= 1280 ? 1 : 0);

      const { overflow, culprits } = await measureOverflow(page);
      expect(overflow, `page scrolls sideways; widest: ${culprits.join(" | ")}`).toBe(0);
    });

    test("leave Publish out for someone who cannot author", async ({ page, api }) => {
      await signedIn(page, api, "System Admin");
      mockShell(api);
      api.on("GET", "/dashboard/queue-counts/", { reported_comments: 0 });
      await page.goto("/");
      await expect(page.getByRole("link", { name: new RegExp(PAPER.title) }).first()).toBeVisible();
      const row = page.getByRole("group", { name: "Discover controls" });
      await expect(row.getByRole("button", { name: "Publish" })).toHaveCount(0);
      await expect(row.getByRole("button", { name: /^Filters/ })).toBeVisible();
    });
  });
}

// The tightest the labelled row gets: no sidebar below 768 (content 584 px at 640), the
// icon rail at 768, the full sidebar at 1024 (content 728 px) -- with three filters on,
// so the Filters count badge is drawn too.
for (const width of [640, 700, 1024]) {
  test(`Discover controls stay one row at ${width}px with filters on`, async ({ page, api }) => {
    await page.setViewportSize({ width, height: 900 });
    await signedIn(page, api);
    mockShell(api);
    await page.goto("/?type=1&year_from=2025&year_to=2025&ip=has_ip");
    const row = page.getByRole("group", { name: "Discover controls" });
    await expect(row.getByRole("button", { name: "Filters, 3 active" })).toBeVisible();
    const fit = await row.evaluate((el) => {
      const rowBox = el.getBoundingClientRect();
      const tops = Array.from(el.querySelectorAll<HTMLElement>("button, select"))
        .filter((c) => c.getBoundingClientRect().width > 0).map((c) => c.getBoundingClientRect().top);
      return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, rowHeight: rowBox.height, spread: Math.max(...tops) - Math.min(...tops) };
    });
    expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
    expect(fit.spread, "controls on one line").toBeLessThanOrEqual(SAME_LINE);
    expect(fit.rowHeight, "a second row would make it taller").toBeLessThan(TOUCH * 1.5);
    const { overflow, culprits } = await measureOverflow(page);
    expect(overflow, `page scrolls sideways; widest: ${culprits.join(" | ")}`).toBe(0);
  });
}

test.describe("Discover on a phone", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  test("starts the first result within the first screen", async ({ page, api }) => {
    await signedIn(page, api);
    mockShell(api);
    await page.goto("/");
    const first = page.getByRole("link", { name: new RegExp(PAPER.title) }).first();
    await expect(first).toBeVisible();
    const top = (await first.boundingBox())!.y;
    expect(top,"the first result's top, below the app bar, search, heading and controls").toBeLessThan(740);
  });

  test("keeps the one row over People", async ({ page, api }) => {
    await signedIn(page, api);
    mockShell(api);
    api.on("GET", "/users/search/", { count: 0, next: null, results: [] });
    await page.goto("/");
    const row = page.getByRole("group", { name: "Discover controls" });
    await row.getByRole("button", { name: "People" }).click();
    await expect(row.getByRole("button", { name: "People", pressed: true })).toBeVisible();
    await expect(row.getByRole("button", { name: "Publish" })).toBeVisible();
    const { overflow } = await measureOverflow(page);
    expect(overflow).toBe(0);
  });
});
