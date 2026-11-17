// IR-1209: selecting text in the paper reader must not jump to unrelated text.
// jsdom has no layout, so this is the one place a real drag is checked: drags
// on a two-column and a single-column page that end over a gap or a margin
// must hold only the text dragged through.
import type { Page, Route } from "@playwright/test";
import { expect, test } from "./support/mock-api";
import { PAPER, PAPER_DETAIL } from "./support/fixtures";
import { openScreen } from "./support/open-screen";
import { SCREENS } from "./support/screens";
import { twoColumnPdf } from "../support/pdf";
import type { MockApi } from "./support/mock-api";

const LEFT = ["Left column line one", "Left column line two", "Left column line three"];
const RIGHT = ["Right column line one", "Right column line two", "Right column line three"];

const paperView = SCREENS.find((entry) => entry.id === "paper-view")!;

async function openPaper(page: Page, api: MockApi, right: string[] = RIGHT) {
  await openScreen(page, api, { ...paperView, path: `/records/${PAPER.id}?section=paper` }, {
    override: (mock) => {
      mock.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, has_manuscript: true, abstract_file: `/api/v1/records/${PAPER.id}/manuscript/`,
      });
      // The Paper section's Ask IRIS panel lists the reader's conversations.
      mock.on("GET", "/ai/runtime/conversations", { protocol: "runs-reader-1", conversations: [] });
      mock.on("GET", `/records/${PAPER.id}/manuscript/`, (route: Route) => route.fulfill({
        status: 200, headers: { "content-type": "application/pdf" }, body: twoColumnPdf(LEFT, right),
      }));
    },
  });
  // Each line is one span of the text layer, found by its exact text.
  const span = (text: string) => page.getByText(text, { exact: true });
  await expect(span(LEFT[0])).toBeVisible({ timeout: 20_000 });
  return { span: async (text: string) => (await span(text).boundingBox())! };
}

/** Press at (x, y), drag through the given points, and return the selection while dragging and after. */
async function drag(page: Page, from: { x: number; y: number }, ...through: { x: number; y: number }[]) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  for (const point of through) await page.mouse.move(point.x, point.y, { steps: 8 });
  const whileDragging = await page.evaluate(() => window.getSelection()?.toString() ?? "");
  await page.mouse.up();
  const selected = await page.evaluate(() => window.getSelection()?.toString() ?? "");
  return [whileDragging, selected];
}

const words = (text: string) => text.replace(/\s+/g, " ").trim();

test("a drag along one line that ends over the gap selects only that line", async ({ page, api }) => {
  const { span } = await openPaper(page, api);
  const line = await span(LEFT[0]);
  const other = await span(RIGHT[0]);
  const y = line.y + line.height / 2;
  const gutter = line.x + line.width + (other.x - (line.x + line.width)) / 2;

  for (const text of await drag(page, { x: line.x + 1, y }, { x: line.x + line.width / 2, y }, { x: gutter, y }, { x: gutter + 2, y: y + 1 })) {
    expect(words(text).length).toBeGreaterThan(0);
    expect(LEFT[0]).toContain(words(text));
    for (const unrelated of [...LEFT.slice(1), ...RIGHT]) expect(text).not.toContain(unrelated);
  }
});

test("a drag across two lines of one column that ends over the gap selects only those lines", async ({ page, api }) => {
  const { span } = await openPaper(page, api);
  const first = await span(LEFT[0]);
  const second = await span(LEFT[1]);
  const other = await span(RIGHT[1]);
  const y = second.y + second.height / 2;
  const gutter = second.x + second.width + (other.x - (second.x + second.width)) / 2;

  for (const text of await drag(page, { x: first.x + 1, y: first.y + first.height / 2 }, { x: second.x + second.width / 2, y }, { x: gutter, y }, { x: gutter + 2, y: y + 1 })) {
    expect(text).toContain(LEFT[0]);
    expect(text).toContain("Left column line");
    for (const unrelated of [LEFT[2], ...RIGHT]) expect(text).not.toContain(unrelated);
  }
});

test("on a single-column page, a drag along one line that ends in the margin selects only that line", async ({ page, api }) => {
  const { span } = await openPaper(page, api, []);
  const line = await span(LEFT[0]);
  const y = line.y + line.height / 2;
  const margin = line.x + line.width + 60;

  for (const text of await drag(page, { x: line.x + 1, y }, { x: line.x + line.width / 2, y }, { x: margin, y }, { x: margin + 2, y: y + 1 })) {
    expect(words(text).length).toBeGreaterThan(0);
    expect(LEFT[0]).toContain(words(text));
    for (const unrelated of LEFT.slice(1)) expect(text).not.toContain(unrelated);
  }
});
