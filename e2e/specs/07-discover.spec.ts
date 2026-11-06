// AC6 (the part that needs no Ask IRIS) · Discover and reading: a reader finds
// published research by search and filters, opens a paper, and opens its
// manuscript at `?page=N` on that page. IR-902.
//
// Nothing here calls Ask IRIS, an embedding model or any paid provider: Discover's
// search is the catalogue's own text search (`?q=` -> the list endpoint's
// `search`), its filters are query parameters, and the reader draws the PDF in
// the browser. Records are created and published by the spec itself, the short
// way ADR-047 allows (`publishViaRdco`); spec 01 covers the full routing.
//
// The reader is a signed-in student with no tie to either paper, the same
// standing as any other member of the institution.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { as, signInBrowser, type Client } from "../support/api";
import { uniqueTitle } from "../support/accounts";
import { NEW_PASSWORD, newStudent } from "../support/people";
import { multiPagePdf } from "../support/pdf";
import { A11yLedger } from "../support/a11y";
import { createDraft, publishViaRdco } from "../support/workflow";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

const PAGES = 6;
const LAND_ON = 4;
const thisYear = new Date().getFullYear();
const lastYear = thisYear - 1;

// One stem shared by all three titles, so a single search finds the whole set
// and nothing from another journey or an earlier run; the last word of each
// title is what tells them apart.
const stem = uniqueTitle("discover");
const thesisTitle = `${stem} Mangrove restoration`;
const projectTitle = `${stem} Solar irrigation`;
const draftTitle = `${stem} Private draft`;

let student: Client, adviser: Client, rdco: Client, reader: Client;
let thesisId: number, draftId: number;

test.beforeAll(async () => {
  [student, adviser, rdco] = await Promise.all(["student", "adviser", "rdco"].map((who) => as(who)));
  reader = await newStudent("discover");

  // A Thesis/Research from last year with a six-page manuscript whose every
  // page says which page it is, and a Project from this year. Both published.
  const manuscript = multiPagePdf(
    Array.from({ length: PAGES }, (_, i) => `Synthetic page ${i + 1} of ${PAGES} for ${stem}`),
  );
  thesisId = await createDraft(student, {
    title: thesisTitle, type: "Thesis / Research", adviserId: adviser.userId, manuscript, yearAccomplished: lastYear,
  });
  const projectId = await createDraft(student, {
    title: projectTitle, type: "Project", adviserId: adviser.userId, yearAccomplished: thisYear,
  });
  await publishViaRdco(student, adviser, rdco, thesisId);
  await publishViaRdco(student, adviser, rdco, projectId);

  // A third paper that is never submitted: it must not be discoverable.
  draftId = await createDraft(student, { title: draftTitle, type: "Project", adviserId: adviser.userId });
});

test.afterAll(async () => {
  await Promise.all([student, adviser, rdco, reader].map((c) => c?.dispose()));
});

const searchBox = (page: Page) => page.getByRole("textbox", { name: "Search records" });
// `first()`: a card may offer the title link more than once to assistive technology.
const paperLink = (page: Page, title: string) => page.getByRole("link", { name: title }).first();
const filtersButton = (page: Page) => page.getByRole("button", { name: /^Filters/ });

/** The Discover card for `title`, to read what the card says about the paper. */
const card = (page: Page, title: string): Locator =>
  page.locator("article").filter({ has: paperLink(page, title) });

async function openDiscover(page: Page) {
  await signInBrowser(page, reader.email, "/", NEW_PASSWORD);
  await expect(page.getByRole("heading", { name: "Discover", level: 1 })).toBeVisible();
}

async function search(page: Page, text: string) {
  await searchBox(page).fill(text);
}

/** Open the Filters sheet and choose `option` in the single-select named `control`. */
async function choose(page: Page, control: RegExp, option: string) {
  const sheet = page.getByRole("dialog", { name: "Filters" });
  if (!(await sheet.isVisible())) await filtersButton(page).click();
  await expect(sheet).toBeVisible();
  await sheet.getByRole("button", { name: control }).click();
  await sheet.getByRole("option", { name: option, exact: true }).click();
  return sheet;
}

test("search finds published papers by what they say, and never an unpublished one", async ({ page }, testInfo) => {
  await openDiscover(page);

  // The stem is in all three titles; only the two published papers come back.
  await search(page, stem);
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toBeVisible();
  await expect(paperLink(page, draftTitle), "a draft is not in the catalogue").toHaveCount(0);
  await expect(page).toHaveURL(/[?&]q=/);

  // The card says what the paper is, as declared: its origin is not guessed.
  await expect(card(page, thesisTitle)).toContainText("Synthetic");
  await expect(card(page, thesisTitle)).toContainText("Thesis / Research");
  await expect(card(page, projectTitle)).toContainText("Project");

  await a11y.scan(page, testInfo, "discover-results");
  await a11y.reflow360(page, "discover-results");

  // Narrowing the words narrows the list to the paper they name.
  await search(page, `${stem} Mangrove`);
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toHaveCount(0);

  // Searching for something nobody wrote says so, and offers the way out.
  await search(page, `${stem} nothing-was-ever-written-about-this`);
  await expect(page.getByRole("heading", { name: "No research matches these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(searchBox(page)).toHaveValue("");
  await expect(page.getByRole("heading", { name: "No research matches these filters" })).toHaveCount(0);
});

test("filters narrow the results, the address holds them, and Clear all undoes them", async ({ page }, testInfo) => {
  await openDiscover(page);
  await search(page, stem);
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toBeVisible();

  // Type: Project leaves the Project.
  let sheet = await choose(page, /^Type/, "Project");
  await expect(paperLink(page, projectTitle)).toBeVisible();
  await expect(paperLink(page, thesisTitle)).toHaveCount(0);
  await expect(filtersButton(page)).toHaveAccessibleName("Filters, 1 active");
  await expect(page).toHaveURL(/[?&]type=\d+/);
  await a11y.scan(page, testInfo, "discover-filters-open");

  // Clear all restores both.
  await sheet.getByRole("button", { name: "Clear all" }).click();
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toBeVisible();
  await expect(filtersButton(page)).toHaveAccessibleName("Filters");

  // Year (completed) is a different filter on the same two papers.
  sheet = await choose(page, /^Year/, String(lastYear));
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toHaveCount(0);
  await sheet.getByRole("button", { name: /^Show \d+ results?$/ }).click();
  await expect(sheet).toHaveCount(0);

  // The address holds the whole query, so a reload brings the same view back.
  await page.reload();
  await expect(searchBox(page)).toHaveValue(stem);
  await expect(paperLink(page, thesisTitle)).toBeVisible();
  await expect(paperLink(page, projectTitle)).toHaveCount(0);
  await expect(filtersButton(page)).toHaveAccessibleName("Filters, 1 active");
  await a11y.reflow360(page, "discover-filtered");
});

test("a card opens its paper, and Back returns to the same search", async ({ page }) => {
  await openDiscover(page);
  await search(page, `${stem} Mangrove`);
  await paperLink(page, thesisTitle).click();

  await expect(page).toHaveURL(new RegExp(`/records/${thesisId}$`));
  await expect(page.getByRole("heading", { name: thesisTitle, level: 1 })).toBeVisible();

  await page.goBack();
  await expect(page.getByRole("heading", { name: "Discover", level: 1 })).toBeVisible();
  await expect(searchBox(page)).toHaveValue(`${stem} Mangrove`);
  await expect(paperLink(page, thesisTitle)).toBeVisible();
});

test("the manuscript opens at ?page=N and lands on that page", async ({ page }, testInfo) => {
  await signInBrowser(page, reader.email, `/records/${thesisId}?page=${LAND_ON}`, NEW_PASSWORD);

  const paper = page.getByRole("region", { name: `Paper, ${PAGES} pages` });
  await expect(paper).toBeVisible();

  // The page asked for is drawn, and it is the page asked for: its own text.
  const target = page.getByRole("group", { name: `Page ${LAND_ON}` });
  await expect(target).toContainText(`Synthetic page ${LAND_ON} of ${PAGES}`);

  // The reader has scrolled to it: the counter names it, it sits inside the
  // reader's view, and the first page is out of it.
  await expect(page.getByText(`Page ${LAND_ON} / ${PAGES}`)).toBeVisible();
  const inView = (el: Locator) => async () => {
    const [box, area] = await Promise.all([el.boundingBox(), paper.boundingBox()]);
    if (!box || !area) return false;
    return box.y < area.y + area.height && box.y + box.height > area.y;
  };
  await expect.poll(inView(target), { message: `page ${LAND_ON} is in the reader's view` }).toBe(true);
  await expect.poll(inView(page.getByRole("group", { name: "Page 1" })), { message: "page 1 is scrolled past" }).toBe(false);

  await a11y.scan(page, testInfo, "paper-at-page");
  await a11y.reflow360(page, "paper-at-page");
});

test("a paper that is not published is the same as a missing one to a reader", async ({ page }) => {
  // The draft's page, opened by id, shows the reader nothing of it (the API
  // side of this is spec 02; this is what the person sees).
  await signInBrowser(page, reader.email, `/records/${draftId}?page=1`, NEW_PASSWORD);
  await expect(page.getByRole("region", { name: /^Paper/ })).toHaveCount(0);
  await expect(page.getByText(draftTitle)).toHaveCount(0);
});

test("accessibility: no serious or critical findings on this journey's key screens", async ({}, testInfo) => {
  a11y.assertClean(testInfo);
});
