// IR-1313: a filter box keeps one width. A native <select> with no set width is
// as wide as its longest CURRENT option, so it grew when its list arrived, and
// Discover People's Department resized on every College choice, moving Role.
//
// jsdom draws no layout, so the unit tests can only check the width classes.
// This is the measurement: each filter select's own box, read before its list
// arrives, after, and after choosing every option in turn (and, for People,
// every College), at a phone and a desktop width. The option lists are the real
// reference data (accounts 0003's Colleges and Departments, the audit log's
// event types and the review offices) plus the longest label a person can type
// (a 60-character folder name, a long Area), so a cap is exercised too. At the
// desktop width a fixed-list box must also hold its longest option in full
// (DESIGN.md's Full Text Rule); only the typed-name boxes are capped.
import type { Locator, Page, Route } from "@playwright/test";
import { expect, test } from "./support/mock-api";
import type { MockApi } from "./support/mock-api";
import { PAPER, paginated, signedIn } from "./support/fixtures";
import { OPPORTUNITY, SCREENS } from "./support/screens";

/** Sub-pixel rounding is not a resize. */
const SAME = 0.5;

const COLLEGES = [
  { id: 1, name: "College of Engineering and Architecture" },
  { id: 2, name: "College of Management, Business & Accountancy" },
  { id: 3, name: "College of Arts, Sciences, & Education" },
  { id: 4, name: "College of Nursing & Allied Health Sciences" },
  { id: 5, name: "College of Computer Studies" },
  { id: 6, name: "College of Criminal Justice" },
];
const DEPARTMENTS: Record<number, string[]> = {
  1: ["Architecture", "Chemical Engineering", "Civil Engineering", "Computer Engineering", "Electrical Engineering",
    "Electronics Engineering", "Industrial Engineering", "Mechanical Engineering", "Mining Engineering"],
  2: ["Accountancy", "Business Administration", "Hospitality Management", "Tourism Management",
    "Office Administration", "Public Administration"],
  3: ["Communication", "English & Applied Linguistics", "Education", "Multimedia Arts", "Biology",
    "Mathematics", "Psychology", "Special Needs Education"],
  4: ["Nursing", "Pharmacy", "Medical Technology"],
  5: ["Computer Science", "Information Technology"],
  6: ["Criminology"],
};
/** From `AuditEvent.EVENT_TYPE_CHOICES`: the three widest of its 100 labels as drawn, and the shortest. */
const EVENT_TYPES = [
  { type: "LOGIN", label: "Login" },
  { type: "REVIEW_THREADS_CLOSED", label: "Review Threads Closed by Decision" },
  { type: "QUESTION_INJECTION", label: "Reader Question Injection Flagged" },
  { type: "RECORD_TYPE_DESCRIBED", label: "Record Type Description Changed" },
];
/** `reviews.Party` as the analytics endpoint labels it. */
const OFFICES = [
  { party: "adviser", label: "Adviser" }, { party: "intake", label: "Intake (retired)" },
  { party: "itso", label: "ITSO" }, { party: "ierc", label: "IERC" },
  { party: "ktto", label: "KTTO" }, { party: "rdco", label: "RDCO Final" },
];
/** `MAX_FOLDER_NAME` is 60. */
const LONG_FOLDER = "Readings for chapter two on capacitive soil moisture sensors";
/** Areas are Classifications, free text up to 200 characters. */
const AREAS = ["Agriculture", "Artificial Intelligence", "Healthcare & MedTech",
  "Renewable Energy Systems and Sustainable Infrastructure for Island Communities"];

/** An answer held back until `release()`, so the box can be measured before its list arrives. */
function gate() {
  let release!: () => void;
  const opened = new Promise<void>((resolve) => { release = resolve; });
  return {
    release,
    reply: (json: unknown) => async (route: Route) => { await opened; await route.fulfill({ json }); },
  };
}

/** Read once the web fonts are in: a box measured in the fallback font is a different width. */
const widthOf = (box: Locator) => box.evaluate(async (el) => {
  await document.fonts.ready;
  return el.getBoundingClientRect().width;
});

/** Choose each enabled option in turn (but `skip`), reading the width after each. */
async function everyOption(box: Locator, skip: string[] = []) {
  const values = await box.locator("option:not([disabled])").evaluateAll(
    (options) => options.map((o) => (o as HTMLOptionElement).value));
  const widths: number[] = [];
  for (const value of values.filter((v) => !skip.includes(v))) {
    await box.selectOption(value);
    widths.push(await widthOf(box));
  }
  return widths;
}

/** How wide the box would be with no width set: as wide as its longest option. */
const naturalWidth = (box: Locator) => box.evaluate((el) => {
  const clone = el.cloneNode(true) as HTMLSelectElement;
  clone.style.cssText = "position:absolute;left:0;top:0;width:auto;min-width:0;max-width:none";
  document.body.append(clone);
  const width = clone.getBoundingClientRect().width;
  clone.remove();
  return width;
});

/** At the desktop width a fixed-list box shows every option whole. */
async function holdsLongest(name: string, viewport: number, box: Locator) {
  if (viewport < 1280) return;
  const [width, natural] = [await widthOf(box), await naturalWidth(box)];
  console.log(`IR-1313 ${viewport}px ${name}: longest option needs ${Math.round(natural)}px of ${Math.round(width)}px`);
  expect.soft(natural, `${name}'s longest option is cut`).toBeLessThanOrEqual(width + SAME);
}

function report(name: string, viewport: number, widths: number[]) {
  const distinct = [...new Set(widths.map((w) => Math.round(w * 10) / 10))];
  console.log(`IR-1313 ${viewport}px ${name}: ${distinct.join(" / ")}`);
  expect.soft(Math.max(...widths) - Math.min(...widths), `${name} widths: ${distinct.join(", ")}`).toBeLessThanOrEqual(SAME);
}

async function noSidewaysScroll(page: Page, viewport: number) {
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scroll, "the page scrolls sideways").toBeLessThanOrEqual(viewport);
}

function screenMocks(id: string, api: MockApi) {
  SCREENS.find((s) => s.id === id)!.mocks!(api);
}

for (const width of [360, 1280]) {
  test.describe(`filter boxes at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("Discover People: College, Department and Role", async ({ page, api }) => {
      await signedIn(page, api);
      screenMocks("discover", api);
      const colleges = gate();
      api.on("GET", "/colleges/", colleges.reply(paginated(COLLEGES)));
      api.on("GET", "/departments/", async (route: Route) => {
        const college = Number(new URL(route.request().url()).searchParams.get("college"));
        await route.fulfill({ json: paginated((DEPARTMENTS[college] ?? []).map((name, i) => ({ id: college * 100 + i, name }))) });
      });
      await page.goto("/");
      await page.getByRole("button", { name: "People" }).click();

      const college = page.getByRole("combobox", { name: "College" });
      const department = page.getByRole("combobox", { name: "Department" });
      const role = page.getByRole("combobox", { name: "Role" });
      await expect(college).toBeVisible();
      const before = { college: await widthOf(college), department: await widthOf(department), role: await widthOf(role) };
      colleges.release();
      await expect(college.locator("option")).toHaveCount(COLLEGES.length + 1);

      const collegeWidths = [before.college];
      const departmentWidths = [before.department];
      const roleWidths = [before.role, await widthOf(role)];
      for (const { id } of COLLEGES) {
        await college.selectOption(String(id));
        await expect(department.locator("option")).toHaveCount(DEPARTMENTS[id].length + 1);
        collegeWidths.push(await widthOf(college));
        departmentWidths.push(...[await widthOf(department), ...await everyOption(department)]);
        roleWidths.push(await widthOf(role));
      }
      collegeWidths.push(...await everyOption(college));
      roleWidths.push(...await everyOption(role));

      report("People College", width, collegeWidths);
      report("People Department", width, departmentWidths);
      report("People Role", width, roleWidths);
      await holdsLongest("People College", width, college);
      await holdsLongest("People Role", width, role);
      // Department lists the chosen College's: the widest name is under College 3.
      await college.selectOption("3");
      await expect(department.locator("option")).toHaveCount(DEPARTMENTS[3].length + 1);
      await holdsLongest("People Department", width, department);
      await noSidewaysScroll(page, width);
    });

    test("Calls & Conferences: Area", async ({ page, api }) => {
      await signedIn(page, api);
      screenMocks("opportunities", api);
      const board = gate();
      api.on("GET", "/opportunities/", board.reply({
        count: AREAS.length, next: null, previous: null, can_post: false, can_review_requests: false,
        results: AREAS.map((name, i) => ({ ...OPPORTUNITY, id: i + 1, title: `${OPPORTUNITY.title} ${i + 1}`, areas: [i + 1], area_names: [name] })),
      }));
      await page.goto("/opportunities");
      // The filters are drawn once there is a board, so the first width is
      // read the moment the box appears with its list.
      board.release();
      const area = page.getByRole("combobox", { name: "Area" });
      await expect(area.locator("option")).toHaveCount(AREAS.length + 1);
      report("Calls Area", width, [await widthOf(area), ...await everyOption(area)]);
      await noSidewaysScroll(page, width);
    });

    test("Audit log: Event type", async ({ page, api }) => {
      await signedIn(page, api, "System Admin");
      screenMocks("audit-log", api);
      const types = gate();
      api.on("GET", "/audit/event-types/", types.reply(EVENT_TYPES));
      await page.goto("/admin/audit");
      const box = page.getByRole("combobox", { name: "Event type" });
      await expect(box).toBeVisible();
      const before = await widthOf(box);
      types.release();
      await expect(box.locator("option")).toHaveCount(EVENT_TYPES.length + 1);
      report("Audit Event type", width, [before, await widthOf(box), ...await everyOption(box)]);
      await holdsLongest("Audit Event type", width, box);
      await noSidewaysScroll(page, width);
    });

    for (const id of ["rdco-users", "admin-users"]) {
      test(`Users list (${id}): Role`, async ({ page, api }) => {
        const screen = SCREENS.find((s) => s.id === id)!;
        await signedIn(page, api, screen.role!);
        screen.mocks!(api);
        await page.goto(screen.path);
        const box = page.getByRole("combobox", { name: "Role" });
        await expect(box).toBeVisible();
        report(`Users Role (${id})`, width, [await widthOf(box), ...await everyOption(box)]);
        await holdsLongest(`Users Role (${id})`, width, box);
        await noSidewaysScroll(page, width);
      });
    }

    test("Workflow analytics: Office", async ({ page, api }) => {
      await signedIn(page, api, "RDCO");
      screenMocks("workflow-analytics", api);
      api.on("GET", "/reviews/analytics/", {
        parties: OFFICES, data_since: null, generated_at: "2026-11-05T08:00:00+08:00",
        range: { from: null, to: null }, thresholds: { median: 5, p90: 5 },
        open_now: [], time_in_stage: [], unmeasured: [], throughput: [], revision_cycles: [], preserved_by_office: [],
      });
      await page.goto("/rdco/analytics");
      const box = page.getByRole("combobox", { name: "Office" });
      await expect(box).toBeVisible();
      report("Analytics Office", width, [await widthOf(box), ...await everyOption(box)]);
      await holdsLongest("Analytics Office", width, box);
      await noSidewaysScroll(page, width);
    });

    test("My Library Saved papers: Folder and Sort", async ({ page, api }) => {
      await signedIn(page, api);
      screenMocks("my-library", api);
      api.on("GET", "/library/saves/", { results: [
        { record_id: PAPER.id, available: true, reading_status: null, saved_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00", record: PAPER },
      ] });
      const folders = gate();
      api.on("GET", "/library/folders/", folders.reply({ limit: 10, results: [
        { id: 1, name: "Thesis", record_ids: [PAPER.id], created_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00" },
        { id: 2, name: LONG_FOLDER, record_ids: [], created_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00" },
      ] }));
      await page.goto("/records/mine?section=saved");
      const folder = page.getByRole("combobox", { name: "Folder" });
      const sort = page.getByRole("combobox", { name: "Sort" });
      await expect(page.getByRole("heading", { name: "My Library" })).toBeVisible();
      // Saves and folders are read together, so the picker may not be drawn before both arrive.
      const folderWidths = await folder.isVisible() ? [await widthOf(folder)] : [];
      folders.release();
      await expect(folder.locator("option")).toHaveCount(5);
      folderWidths.push(await widthOf(folder));
      for (const value of ["__history__", "", "folder:1", "folder:2"]) {
        await folder.selectOption(value);
        folderWidths.push(await widthOf(folder));
      }
      report("Library Folder", width, folderWidths);
      await folder.selectOption("");
      report("Library Sort", width, [await widthOf(sort), ...await everyOption(sort)]);
      await holdsLongest("Library Sort", width, sort);
      await noSidewaysScroll(page, width);
    });
  });
}
