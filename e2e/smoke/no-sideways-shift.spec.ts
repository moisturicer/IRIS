import type { Page, Route } from "@playwright/test";
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

  const places: Place[] = [];
  for (const tab of TABS) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
    places.push(await placeOf(page, heading));
  }
  expectOnePlace(places);
});

// The same for My Reviews, where Done gathers every decision and grows long
// while To review and In review stay short. Advisers and office staff share
// this page; the smoke screen opens it as RDCO staff.
const reviews = SCREENS.find((entry) => entry.id === "my-reviews")!;

function reviewRow(n: number, decided: boolean) {
  return {
    key: `seat:${n}`, kind: "seat", record: 100 + n, title: `Campus energy monitoring, part ${n}`,
    record_type_name: "Thesis / Research", authors: ["Maria Clara Santos"], unit: "College of Computer Studies",
    version: 1, opens: "review", party: "itso", party_label: "ITSO", seat: n, assignment: n, holder: 5,
    holder_name: "Ana Reyes", is_mine: true, routed_by: "Prof. Santos", routed_reason: "Potential IP concern",
    submitted_by: null, waiting_since: "2026-10-01T00:00:00Z", waiting_days: 2, waiting_on: null,
    outcome: decided ? "cleared" : null, outcome_label: decided ? "Cleared" : null,
    decided_at: decided ? "2026-11-01T00:00:00Z" : null, can_claim: false, can_assign: false,
    due_at: null, original_due_at: null, is_overdue: false, clock_paused: false, overdue_days: null,
    clearance_strip: [],
  };
}

test("My Reviews keeps its place from To review to Done and back", async ({ page, api }) => {
  await page.setViewportSize({ width: 1920, height: 900 });
  await openScreen(page, api, reviews);
  // Two to review, one in review, twelve done: Done alone is taller than the window.
  await page.route("**/api/v1/reviews/mine/**", (route: Route) => {
    const tab = new URL(route.request().url()).searchParams.get("tab") ?? "to_review";
    const count = tab === "done" ? 12 : tab === "in_review" ? 1 : 2;
    return route.fulfill({ json: {
      rows: Array.from({ length: count }, (_, i) => reviewRow(i + 1, tab === "done")),
      counts: { to_review: 2, in_review: 1, done: 12 },
      outcome_counts: { all: 12, cleared: 12, finding: 0, accepted: 0, rejected: 0, published: 0 },
      next: null,
    } });
  });
  const heading = page.getByRole("heading", { level: 1, name: "My Reviews" });

  const places: Place[] = [];
  for (const tab of [/^To review/, /^In review/, /^Done/, /^To review/]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("aria-selected", "true");
    places.push(await placeOf(page, heading));
  }
  expectOnePlace(places);
});

interface Place { x: number; scrolls: boolean }

async function placeOf(page: Page, heading: ReturnType<Page["getByRole"]>): Promise<Place> {
  await page.waitForTimeout(300);
  return {
    x: (await heading.boundingBox())!.x,
    scrolls: await page.evaluate(() => document.documentElement.scrollHeight > innerHeight),
  };
}

// The test means something only if some tabs scroll and some do not.
function expectOnePlace(places: Place[]) {
  const scrolling = places.map((place) => place.scrolls);
  expect(scrolling).toContain(true);
  expect(scrolling).toContain(false);
  expect(new Set(places.map((place) => place.x)).size).toBe(1);
}
