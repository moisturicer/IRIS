// The Full Text Rule (IR-1218, DESIGN.md): text is given its whole box and is
// never cut. A pane that scrolls inside itself hides a name that runs past its
// row without ever making the page scroll, so the viewport matrix cannot see it;
// this measures the text against its own row instead.
import type { Page } from "@playwright/test";

import { expect, test, type MockApi } from "./support/mock-api";
import { openScreen } from "./support/open-screen";
import { account, PAPER } from "./support/fixtures";
import { SCREENS, type Screen } from "./support/screens";

const LONG_NAME = "Final_Thesis_Manuscript_Revised_Signed_Adviser_Copy_v3.pdf";

test.describe("the Full Text Rule", () => {
  test("a long file name wraps inside its Documents row at phone width (IR-1203)", async ({ page, api }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    const screen = SCREENS.find((s) => s.id === "paper-view-review-documents");
    if (!screen) throw new Error("screens.ts has no paper-view-review-documents");
    await openScreen(page, api, screen);

    const name = page.getByRole("heading", { name: LONG_NAME });
    await expect(name).toBeVisible();
    const fit = await name.evaluate((el) => {
      const row = el.closest("li") ?? el.parentElement!;
      const text = el.getBoundingClientRect();
      const box = row.getBoundingClientRect();
      return { overflow: el.scrollWidth - el.clientWidth, pastRow: Math.max(0, Math.round(text.right - box.right)) };
    });
    expect(fit, "the name runs past its own box or its row").toEqual({ overflow: 0, pastRow: 0 });
  });
});

// Long reading text is justified, with hyphenation, at every width, phones
// included (IR-1221; DESIGN.md's Full Text Rule, point 4).
test.describe("justified reading text", () => {
  for (const width of [360, 1280]) {
    test(`the Overview's abstract is justified and hyphenated at ${width} px`, async ({ page, api }) => {
      await page.setViewportSize({ width, height: 900 });
      const screen = SCREENS.find((s) => s.id === "paper-view");
      if (!screen) throw new Error("screens.ts has no paper-view");
      await openScreen(page, api, screen);

      const abstract = page.getByText(PAPER.abstract, { exact: true });
      await expect(abstract).toBeVisible();
      const style = await abstract.evaluate((el) => {
        const css = getComputedStyle(el);
        return { align: css.textAlign, hyphens: css.hyphens };
      });
      expect(style).toEqual({ align: "justify", hyphens: "auto" });
    });
  }
});

// Every screen, with the signed-in account's name and email made long, and
// every title the API answers with made long too (IR-1219). Measured at a wide
// screen, then a phone, then a laptop, in one page, so the text is checked
// after it re-wraps as the window narrows and widens again.
// What counts as cut: text a box hides at its edge (clipped sideways, or
// pushed past a box that hides its overflow), text clamped to a few lines, or
// text that spills out of the bottom of a box too short for it.
// The allowed cuts (DESIGN.md, "The six allowed cuts") pass only on their
// own terms: a clamp with a Show more that reveals it, a preview paragraph in
// a card that links to the paper, one line whose whole text shows on hover
// (`title`), and decoration hidden from screen readers.
// Which clamps exist at all is held by the guard test (fullTextRule.test.ts).
const WIDTHS = [1745, 360, 1280];

const LONG_TITLE_TAIL =
  ": a longitudinal mixed-methods field study of sensor calibration, irrigation scheduling and yield across upland, lowland and coastal municipalities of Central Visayas";

const LONG_ACCOUNT = {
  first_name: "Maria Cristina Remedios",
  last_name: "Dela Cruz-Santos y Villanueva",
  email: "maria.cristina.remedios.delacruzsantos@students.cit.edu",
};

/** Every `title` in a JSON reply, made long. Replies that fulfil the route themselves are left alone. */
function lengthenTitles(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(lengthenTitles);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, v]) =>
    [key, /(^|_)title$/.test(key) && typeof v === "string" && v ? v + LONG_TITLE_TAIL : lengthenTitles(v)]));
}

/** Wait for layout after a resize: two frames for ResizeObserver and its re-render, then any slide or fade it started. */
async function settle(page: Page) {
  await page.evaluate(async () => {
    await new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
    await Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined)));
  });
}

async function cutText(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    const ownText = (el: Element) =>
      [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim());
    const clips = (css: CSSStyleDeclaration) => css.overflowX === "hidden" || css.overflowX === "clip";
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      if (!ownText(el) || ["INPUT", "TEXTAREA", "SELECT", "OPTION", "SCRIPT", "STYLE"].includes(el.tagName)) continue;
      if (el.closest('[aria-hidden="true"]')) continue; // decoration: the search hint, the watermark's stamp
      const box = el.getBoundingClientRect();
      if (box.width <= 1 || box.height <= 1) continue; // sr-only text
      const css = getComputedStyle(el);
      if (css.visibility === "hidden" || css.display === "none") continue;
      if (css.clip.startsWith("rect") || css.clipPath !== "none") continue; // sr-only until focused, like Skip to content

      const clamp = css.webkitLineClamp && css.webkitLineClamp !== "none" && el.scrollHeight > el.clientHeight + 1;
      const clipped = clips(css) && el.scrollWidth > el.clientWidth + 1;
      // Spilled: a block in the page's flow, yet taller than a box that holds it,
      // so it runs past its top or bottom. Not inline text: its glyphs rise past
      // a tight line-height.
      let spilled = false;
      const outOfFlow = (c: CSSStyleDeclaration) => ["absolute", "fixed"].includes(c.position);
      let inFlow = !outOfFlow(css) && !css.display.startsWith("inline");
      for (let up = el.parentElement, depth = 0; inFlow && up && up !== document.body && depth < 4; up = up.parentElement, depth++) {
        const upCss = getComputedStyle(up);
        const edge = up.getBoundingClientRect();
        if (upCss.display !== "contents" && (box.bottom > edge.bottom + 1 || box.top < edge.top - 1)) { spilled = true; break; }
        inFlow = !outOfFlow(upCss);
      }
      let past = false;
      for (let up = el.parentElement; up && up !== document.body; up = up.parentElement) {
        const upCss = getComputedStyle(up);
        if (upCss.overflowX === "auto" || upCss.overflowX === "scroll") break; // reachable by scrolling it
        if (!clips(upCss)) continue;
        const edge = up.getBoundingClientRect();
        // Partly past the edge is a cut. Wholly outside is a closed drawer, not text cut short.
        const overlaps = box.right > edge.left && box.left < edge.right;
        past = overlaps && (box.right > edge.right + 1 || box.left < edge.left - 1);
        break;
      }
      if (!clamp && !clipped && !past && !spilled) continue;
      if (clamp && el.id && document.querySelector(`[aria-controls~="${el.id}"][aria-expanded="false"]`)) continue;
      if (clipped && !clamp && !past && !spilled && el.title === (el.textContent ?? "").trim()) continue;
      const preview = el.tagName === "P" && !el.closest("a, h1, h2, h3, h4");
      if (clamp && preview && el.closest("article, li")?.querySelector('a[href^="/records/"]')) continue;
      const kind = clamp ? "clamped" : clipped ? "clipped" : past ? "past its box" : "spilled out of its box";
      found.push(`${kind}: <${el.tagName.toLowerCase()} class="${el.className}"> "${(el.textContent ?? "").trim().slice(0, 60)}"`);
    }
    return found;
  });
}

/** A screen headed by the account's own name, or by a title, is headed by the long one. */
function longHeading(screen: Screen): string | RegExp {
  if (!screen.role) return screen.heading;
  const user = account(screen.role);
  const own = `${user.first_name} ${user.last_name}`;
  if (new RegExp(screen.heading).test(own)) return `${LONG_ACCOUNT.first_name} ${LONG_ACCOUNT.last_name}`;
  return screen.heading;
}

test.describe("no screen cuts its text (IR-1219)", () => {
  for (const screen of SCREENS) {
    test(`${screen.id} at ${WIDTHS.join(", ")} px`, async ({ page, api }) => {
      await page.setViewportSize({ width: WIDTHS[0], height: 900 });
      const long: MockApi = {
        on: (method, path, reply, status) =>
          api.on(method, path, typeof reply === "function" ? reply : lengthenTitles(reply), status),
        seen: api.seen,
      };
      await openScreen(page, long, screen, {
        override: (mock) => {
          if (screen.role) mock.on("GET", "/users/me/", { ...account(screen.role), ...LONG_ACCOUNT });
        },
      });
      await expect(page.getByRole("heading", { name: longHeading(screen) }).first()).toBeVisible();
      const cut: Record<number, string[]> = {};
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 });
        await settle(page);
        const found = await cutText(page);
        if (found.length) cut[width] = found;
      }
      expect(cut, "text a reader cannot see or reach").toEqual({});
    });
  }
});
