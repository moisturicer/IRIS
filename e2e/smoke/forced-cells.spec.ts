// IR-907: the cells of docs/ui-ux/17-ui-states-matrix.md that support/states.ts
// cannot express, because the state is not the answer to one read of a screen's
// opening page: it takes a second read (Load more), a query (a filter that matches
// nothing), a partly refused list (Saved), a tab, or the first answer of a chat.
// forced-states.spec.ts holds the rest; forced-coverage.spec.ts holds the two together.
import type { Page, Request, Route } from "@playwright/test";
import { expect, test, type MockApi } from "./support/mock-api";
import { makeLaterReadsTimeOut, openScreen } from "./support/open-screen";
import { SCREENS } from "./support/screens";
import { PAPER, PAPER_DETAIL, RUNTIME_CONVERSATION, RUNTIME_CONVERSATION_ID, RUNTIME_CONVERSATION_PATH, paginated } from "./support/fixtures";
import { EMPTY_REVIEWS, TRACKER } from "./support/states";

const screen = (id: string) => SCREENS.find((s) => s.id === id)!;
const COMPOSER = "Ask about the research corpus";
const SECOND = { ...PAPER, id: 102, title: "Rainwater harvesting for terraced farms" };
const searchOf = (request: Request) => new URL(request.url()).searchParams;
const retryControl = (page: Page) => page.getByRole("button", { name: /^(Try again|Retry)$/ });

// --- Discover ---------------------------------------------------------------

test.describe("Discover", () => {
  test("a filter that matches nothing says so, and Clear filters brings the list back", async ({ page, api }) => {
    await openScreen(page, api, { ...screen("discover"), path: "/?q=flood" }, {
      // The server has papers; none matches "flood". Without the search it lists the one it has.
      override: (a) => a.on("GET", "/records/", (route: Route, request: Request) =>
        route.fulfill({ json: searchOf(request).get("search") ? paginated([]) : paginated([PAPER]) })),
    });

    await expect(page.getByRole("heading", { name: "No research matches these filters" })).toBeVisible();
    // Not the "nothing published" wording: papers exist, the filters hide them.
    await expect(page.getByRole("heading", { name: "Nothing has been published yet." })).toHaveCount(0);
    await expect(retryControl(page)).toHaveCount(0);

    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(page.getByText(PAPER.title).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "No research matches these filters" })).toHaveCount(0);
    await expect(page).not.toHaveURL(/[?&]q=/);
  });

  /** Page 1 lists one paper of two; what page 2 answers is the case under test. */
  const twoPages = (second: (route: Route) => unknown) => (api: MockApi) =>
    api.on("GET", "/records/", (route: Route, request: Request) =>
      searchOf(request).get("page") === "2"
        ? second(route)
        : route.fulfill({ json: { count: 2, next: "/records/?page=2", previous: null, results: [PAPER] } }));

  test("Load more that fails keeps the list, says so, and Try again loads the rest", async ({ page, api }) => {
    let secondPage = "fails";
    await openScreen(page, api, screen("discover"), {
      override: twoPages((route) => secondPage === "fails"
        ? route.fulfill({ status: 500, json: {} })
        : route.fulfill({ json: { count: 2, next: null, previous: null, results: [SECOND] } })),
    });
    await page.getByRole("button", { name: "Load more (1 left)" }).click();

    await expect(page.getByText("More results didn't load.")).toBeVisible();
    // What was already read stays on screen: one failed page does not empty the feed.
    await expect(page.getByText(PAPER.title).first()).toBeVisible();

    secondPage = "works";
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText(SECOND.title)).toBeVisible();
    await expect(page.getByText("More results didn't load.")).toHaveCount(0);
  });

  test("Load more that times out reads as an ordinary failure, keeps the list, and Try again loads the rest", async ({ page, api }) => {
    let secondPage = "hangs";
    await openScreen(page, api, screen("discover"), {
      override: twoPages((route) => secondPage === "hangs"
        ? new Promise<void>(() => undefined)
        : route.fulfill({ json: { count: 2, next: null, previous: null, results: [SECOND] } })),
    });
    // The first page has loaded; from here a read that is never answered times out.
    await expect(page.getByRole("button", { name: "Load more (1 left)" })).toBeVisible();
    await makeLaterReadsTimeOut(page, "/records/");
    await page.getByRole("button", { name: "Load more (1 left)" }).click();

    await expect(page.getByText("More results didn't load.")).toBeVisible();
    await expect(page.getByText(PAPER.title).first()).toBeVisible();

    secondPage = "works";
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText(SECOND.title)).toBeVisible();
  });
});

// --- My Library -------------------------------------------------------------

test.describe("My Library · Saved", () => {
  test("nothing saved says so and points to where papers are saved from", async ({ page, api }) => {
    await openScreen(page, api, { ...screen("my-library"), path: "/records/mine?section=saved" });
    await expect(page.getByText("No saved papers yet")).toBeVisible();
    await expect(page.getByText("Save a paper from Discover or a paper's page and it follows your account.")).toBeVisible();
    await expect(retryControl(page)).toHaveCount(0);
  });

  test("a saved paper the reader can no longer read is reported, not hidden, and the rest still show", async ({ page, api }) => {
    await openScreen(page, api, { ...screen("my-library"), path: "/records/mine?section=saved" }, {
      override: (a) => a.on("GET", "/library/saves/", {
        results: [
          { record_id: PAPER.id, available: true, reading_status: null, saved_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00", record: PAPER },
          // The server sends an id and nothing else for a Record the reader may no longer read (ADR-044 §4).
          { record_id: 999, available: false },
        ],
      }),
    });

    await expect(page.getByText(PAPER.title).first()).toBeVisible();
    await expect(page.getByText(/1 saved paper is no longer available to you/)).toBeVisible();
    // The page names no title, id or reason for the missing one: it cannot be used to learn about it.
    await expect(page.getByText("999")).toHaveCount(0);
    await expect(retryControl(page)).toHaveCount(0);
  });
});

// --- Ask IRIS ---------------------------------------------------------------

/** A finished run and the conversation it wrote, as the runtime serves them (IR-957). */
const answered = (answer: string) => {
  const run = {
    protocol: "runs-reader-1", id: "00000000-0000-4000-8000-000000000001", conversation_id: RUNTIME_CONVERSATION_ID,
    state: "completed", question: "What about the moon?", base_revision: 0, version: 3,
    turn_id: "00000000-0000-4000-8000-000000000003", depth: "ordinary", awaiting_reader: false,
    created_at: "2026-11-05T00:00:00+00:00", finished_at: "2026-11-05T00:00:00+00:00", kind: "ask",
    plan: null, context: null, compaction: null, cursor: 2, retry_of: null, retried_by: null,
    sources_available: true, capabilities: { manual_compaction: false },
  };
  return { run, conversation: { ...RUNTIME_CONVERSATION, revision: 1, runs: [run], turns: [{
    id: run.turn_id, run_id: run.id, ordinal: 1, question: run.question, answer, kind: "answer",
    created_at: run.finished_at, citations: [],
  }] } };
};

test.describe("Ask IRIS", () => {
  test("a new chat opens on its opening question with the composer ready", async ({ page, api }) => {
    await openScreen(page, api, screen("ask-iris"));
    await expect(page.getByText("What would you like to investigate?")).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
    await expect(retryControl(page)).toHaveCount(0);
  });

  test("a chat history that fails to load leaves the chat usable", async ({ page, api }) => {
    await openScreen(page, api, screen("ask-iris"), {
      override: (a) => a.on("GET", "/ai/runtime/conversations", { detail: "smoke: down" }, 500),
    });
    // The history is a convenience: the reader can still ask, and nothing claims the chat failed.
    await expect(page.getByText("What would you like to investigate?")).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
    await expect(retryControl(page)).toHaveCount(0);
  });

  test("an answer with nothing to cite offers no Sources button, and the reader can ask again", async ({ page, api }) => {
    await openScreen(page, api, screen("ask-iris-conversation"));
    const { run, conversation } = answered("The sources IRIS read do not establish an answer to this question.");
    api.on("POST", "/ai/runtime/runs", run, 201);
    api.on("GET", `/ai/runtime/runs/${run.id}`, run);
    await page.getByRole("textbox", { name: COMPOSER }).fill(run.question);
    api.on("GET", RUNTIME_CONVERSATION_PATH, conversation);
    await page.getByRole("button", { name: "Send message" }).click();

    await expect(page.getByText("The sources IRIS read do not establish an answer to this question.")).toBeVisible();
    await expect(page.getByRole("button", { name: /sources? for this answer/ })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
    // Not a failure: nothing to retry.
    await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  });
});

// --- Review -----------------------------------------------------------------

test.describe("My Reviews", () => {
  for (const [tab, title] of [
    ["in_review", "Nothing in review"],
    ["done", "No decisions yet"],
  ] as const) {
    test(`the ${tab.replace("_", " ")} tab with nothing in it says what arrives there`, async ({ page, api }) => {
      await openScreen(page, api, { ...screen("my-reviews"), path: `/review?tab=${tab}` }, {
        override: (a) => a.on("GET", "/reviews/mine/", EMPTY_REVIEWS),
      });
      await expect(page.getByText(title)).toBeVisible();
      // The read worked, so there is nothing to retry; and the tab is still the one asked for.
      await expect(retryControl(page)).toHaveCount(0);
      await expect(page.getByRole("tab", { selected: true })).toBeVisible();
    });
  }
});

test.describe("Paper View · review tracker", () => {
  test("a tracker nobody has acted on says no routing is recorded yet", async ({ page, api }) => {
    await openScreen(page, api, screen("paper-view"), {
      override: (a) => {
        a.on("GET", `/records/${PAPER.id}/`, { ...PAPER_DETAIL, is_participant: true });
        a.on("GET", `/records/${PAPER.id}/tracker/`, { ...TRACKER, current_holders: [] });
      },
    });
    await expect(page.getByText("No routing recorded yet.")).toBeVisible();
    await expect(retryControl(page)).toHaveCount(0);
  });
});

test.describe("Paper View · review timeline", () => {
  test("a timeline with nothing in it says nothing has happened yet", async ({ page, api }) => {
    await openScreen(page, api, { ...screen("paper-view"), path: `/records/${PAPER.id}?section=review` }, {
      override: (a) => {
        a.on("GET", `/records/${PAPER.id}/`, { ...PAPER_DETAIL, is_participant: true });
        a.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER);
      },
    });
    await expect(page.getByText("Nothing has happened in this review yet.")).toBeVisible();
    await expect(retryControl(page)).toHaveCount(0);
  });
});
