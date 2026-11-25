import { expect, test } from "./support/mock-api";
import { openScreen } from "./support/open-screen";
import { SCREENS } from "./support/screens";

// IR-1335: a page taller than the window shows a scrollbar, a short one does
// not, and the centred page moved sideways by half the bar's width as tabs
// switched. The smoke browser hides scrollbars, so this test shows them, as
// a Windows browser does.
test.use({ launchOptions: { ignoreDefaultArgs: ["--hide-scrollbars"] } });

const library = SCREENS.find((entry) => entry.id === "my-library")!;
const TABS = ["Overview", "My Submissions", "Saved Papers", "Saved Calls", "Download Requests"];

test("My Library keeps its place whichever tab is open, tall or short", async ({ page, api }) => {
  // Wide enough that the page is centred, short enough that some tabs scroll.
  await page.setViewportSize({ width: 1920, height: 900 });
  await openScreen(page, api, library, {
    override: (mock) => {
      mock.on("GET", "/opportunities/saved/", { results: [] });
      mock.on("GET", "/records/download-requests/mine/", []);
    },
  });
  const heading = page.getByRole("heading", { level: 1, name: "My Library" });

  const places = new Map<string, { x: number; scrolls: boolean }>();
  for (const tab of TABS) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
    await page.waitForTimeout(300);
    places.set(tab, {
      x: (await heading.boundingBox())!.x,
      scrolls: await page.evaluate(() => document.documentElement.scrollHeight > innerHeight),
    });
  }

  // The test means something only if some tabs scroll and some do not.
  const scrolling = [...places.values()].map((place) => place.scrolls);
  expect(scrolling).toContain(true);
  expect(scrolling).toContain(false);
  expect(new Set([...places.values()].map((place) => place.x)).size).toBe(1);
});
