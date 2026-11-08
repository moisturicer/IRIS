// IR-907: Ask IRIS when its event stream is cut, fails, or ends without an answer.
//
// The stream is `/ai/ask/stream/` (Server-Sent Events). The test answers it
// itself, so each case chooses exactly where the stream stops:
//
//   request-bound   no `run_queued`: the connection is the answer. Cut after some text,
//                   the reader keeps what arrived and is told it was cut off.
//   queued run      `run_queued` names a run (IR-544). A dropped connection reconnects from
//                   the last event id; a run that ENDS unanswered (`run_failed`,
//                   `run_cancelled`) says so and offers Retry (IR-548), which starts a new
//                   linked run and follows it.
//
// A route cannot reset a connection halfway through a body, so "cut" here is the
// server closing the stream without a final event, which is the same thing to
// the client (answerStream.ts reads both as the end of the events); a request
// that fails outright is also forced, with a status and with a network abort.
import type { Page, Request, Route } from "@playwright/test";
import { expect, test, type MockApi } from "./support/mock-api";
import { openScreen } from "./support/open-screen";
import { SCREENS } from "./support/screens";

const QUESTION = "What soil sensors were tested?";
const COMPOSER = "Ask a follow-up about the research corpus…";

/** One Server-Sent Events record, as the server writes it. */
const frame = (event: string, data: unknown, id?: number) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n${id === undefined ? "" : `id: ${id}\n`}\n`;

const stream = (...frames: string[]) => (route: Route) =>
  route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: frames.join("") });

const DONE = (answer: string, turnId: number) => frame("done", {
  answer, citations: [], sources: [], conversation_id: 1, turn_id: turnId,
}, 99);

const NOT_ANSWERED_COPY = {
  failed: "IRIS could not finish this answer. Please ask again.",
  expired: "IRIS ran out of time before it could answer. Please ask again.",
  cancelled: "You stopped this question before IRIS answered it.",
} as const;

/** Ask IRIS open on an empty Conversation, signed in, with nothing about asking mocked yet. */
async function openChat(page: Page, api: MockApi) {
  await openScreen(page, api, SCREENS.find((s) => s.id === "ask-iris-conversation")!);
  await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
}

async function ask(page: Page, question = QUESTION) {
  await page.getByRole("textbox", { name: COMPOSER }).fill(question);
  await page.getByRole("button", { name: "Send message" }).click();
}

const retryButton = (page: Page) => page.getByRole("button", { name: "Retry", exact: true });
const times = (api: MockApi, key: string) => api.seen.filter((k) => k === key).length;

test.describe("a slow answer", () => {
  test("shows that IRIS is working while the stream is held, then the answer when it arrives", async ({ page, api }) => {
    await openChat(page, api);
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    api.on("POST", "/ai/ask/stream/", async (route: Route) => {
      await held;
      await stream(DONE("Capacitive probes, in the end.", 40))(route);
    });
    await ask(page);

    // Waiting is visible and announced, and the question stays.
    await expect(page.getByRole("status").filter({ hasText: /Waiting|Thinking|Preparing/ }).first()).toBeVisible();
    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByText("cut off before it finished")).toHaveCount(0);
    await expect(retryButton(page)).toHaveCount(0);

    release();
    await expect(page.getByText("Capacitive probes, in the end.")).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: /Waiting|Thinking|Preparing/ })).toHaveCount(0);
  });
});

test.describe("a request-bound answer (no queued run)", () => {
  test("cut off after some text: keeps the text, says it was cut off, and the reader can ask again", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", stream(
      frame("text_delta", { text: "Capacitive probes were used" }),
    ));
    await ask(page);

    await expect(page.getByText("Capacitive probes were used")).toBeVisible();
    await expect(page.getByText("This answer was cut off before it finished — it may be incomplete.")).toBeVisible();
    // The question is still on screen and the composer is free: nothing is stuck waiting.
    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
    await expect(page.getByRole("status").filter({ hasText: /Waiting|Thinking|Preparing/ })).toHaveCount(0);

    // Asking again is the way on, and it works.
    api.on("POST", "/ai/ask/stream/", stream(DONE("Capacitive probes and tensiometers.", 12)));
    await ask(page, "Please try that again.");
    await expect(page.getByText("Capacitive probes and tensiometers.")).toBeVisible();
    expect(times(api, "POST /ai/ask/stream/")).toBe(2);
  });

  test("cut off before any text: says the answer was interrupted", async ({ page, api }) => {
    await openChat(page, api);
    // Only a keepalive comment arrives: an event with no name, which the client skips.
    api.on("POST", "/ai/ask/stream/", stream(": keepalive\n\n"));
    await ask(page);

    // The connection ended cleanly with no answer in it: the reply is the interrupted notice, not a blank.
    await expect(page.getByText("The answer was interrupted before it finished.")).toBeVisible();
    await expect(page.getByText("This answer was cut off before it finished — it may be incomplete.")).toBeVisible();
    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
  });

  test("the request fails with a server error: says so, keeps the question, and the reader can ask again", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", { detail: "IRIS is not available right now." }, 503);
    await ask(page);

    await expect(page.getByText("IRIS is not available right now.")).toBeVisible();
    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();

    api.on("POST", "/ai/ask/stream/", stream(DONE("Probes, mostly.", 13)));
    await ask(page, "And now?");
    await expect(page.getByText("Probes, mostly.")).toBeVisible();
  });

  test("the connection is aborted: says IRIS could not answer, and the reader can ask again", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", (route: Route) => route.abort("connectionreset"));
    await ask(page);

    await expect(page.getByText("IRIS could not answer right now. Check that the AI service is available.")).toBeVisible();
    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();

    api.on("POST", "/ai/ask/stream/", stream(DONE("Probes, mostly.", 14)));
    await ask(page, "And now?");
    await expect(page.getByText("Probes, mostly.")).toBeVisible();
  });
});

test.describe("a queued run", () => {
  test("a dropped connection reconnects from the last event and finishes the answer", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", stream(
      frame("run_queued", { run_id: "r1" }, 1),
      frame("text_delta", { text: "Capacitive probes " }, 2),
    ));
    let resumedAfter: string | null = null;
    api.on("GET", "/ai/ask/runs/r1/stream/", (route: Route, request: Request) => {
      resumedAfter = new URL(request.url()).searchParams.get("after");
      return stream(
        frame("text_delta", { text: "were tested." }, 3),
        DONE("Capacitive probes were tested.", 21),
      )(route);
    });
    await ask(page);

    await expect(page.getByText("Capacitive probes were tested.")).toBeVisible();
    // It carried on from where it was cut, not from the start, and the reader did nothing.
    expect(resumedAfter).toBe("2");
    await expect(page.getByText("cut off before it finished")).toHaveCount(0);
    await expect(retryButton(page)).toHaveCount(0);
  });

  test("reconnecting brings nothing, three times: keeps the text it has and says it was cut off", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", stream(
      frame("run_queued", { run_id: "r1" }, 1),
      frame("text_delta", { text: "Capacitive probes" }, 2),
    ));
    api.on("GET", "/ai/ask/runs/r1/stream/", stream(": keepalive\n\n"));
    await ask(page);

    await expect(page.getByText("This answer was cut off before it finished — it may be incomplete.")).toBeVisible();
    await expect(page.getByText("Capacitive probes")).toBeVisible();
    // A bounded number of tries, then it stops: the page is not left reconnecting for ever.
    const tries = times(api, "GET /ai/ask/runs/r1/stream/");
    expect(tries).toBeGreaterThan(0);
    expect(tries).toBeLessThanOrEqual(5);
    await expect(page.getByRole("textbox", { name: COMPOSER })).toBeEnabled();
  });

  for (const state of ["failed", "expired"] as const) {
    test(`a run that ${state} says so, and Retry starts a new run that answers`, async ({ page, api }) => {
      await openChat(page, api);
      api.on("POST", "/ai/ask/stream/", stream(
        frame("run_queued", { run_id: "r1" }, 1),
        frame("run_failed", { state }, 2),
      ));
      await ask(page);

      await expect(page.getByText(NOT_ANSWERED_COPY[state])).toBeVisible();
      await expect(retryButton(page)).toBeEnabled();
      // Nothing has asked again by itself.
      expect(times(api, "POST /ai/ask/runs/r1/retry/")).toBe(0);

      api.on("POST", "/ai/ask/runs/r1/retry/", { run_id: "r2", retry_of: "r1", state: "queued" }, 201);
      let followed: string | null = null;
      api.on("GET", "/ai/ask/runs/r2/stream/", (route: Route, request: Request) => {
        followed = new URL(request.url()).searchParams.get("after");
        return stream(
          frame("run_started", { run_id: "r2" }, 1),
          frame("text_delta", { text: "Probes, this time." }, 2),
          DONE("Probes, this time.", 22),
        )(route);
      });
      await retryButton(page).click();

      await expect(page.getByText("Probes, this time.").first()).toBeVisible();
      // The retry is the linked run, followed from its first event; one click, one retry.
      expect(times(api, "POST /ai/ask/runs/r1/retry/")).toBe(1);
      expect(followed).toBe("0");
      // The old notice stays as history, but its Retry is spent: a second would return the same retry.
      await expect(retryButton(page)).toHaveCount(0);
    });
  }

  test("a run the reader stopped says so and can be asked again", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", stream(
      frame("run_queued", { run_id: "r1" }, 1),
      frame("run_cancelled", {}, 2),
    ));
    await ask(page);

    await expect(page.getByText(NOT_ANSWERED_COPY.cancelled)).toBeVisible();
    // Their own choice, not an interruption: no "cut off" notice, but they may still ask it again.
    await expect(page.getByText("cut off before it finished")).toHaveCount(0);
    await expect(retryButton(page)).toBeEnabled();
  });

  test("a Retry the server refuses says so, keeps Retry, and works once the server allows it", async ({ page, api }) => {
    await openChat(page, api);
    api.on("POST", "/ai/ask/stream/", stream(
      frame("run_queued", { run_id: "r1" }, 1),
      frame("run_failed", { state: "failed" }, 2),
    ));
    await ask(page);
    await expect(retryButton(page)).toBeEnabled();

    api.on("POST", "/ai/ask/runs/r1/retry/", { detail: "IRIS is busy. Try again in a moment." }, 503);
    await retryButton(page).click();
    await expect(page.getByText("IRIS is busy. Try again in a moment.")).toBeVisible();
    // The refusal changed nothing: the notice and its Retry are still there.
    await expect(page.getByText(NOT_ANSWERED_COPY.failed)).toBeVisible();
    await expect(retryButton(page)).toBeEnabled();

    api.on("POST", "/ai/ask/runs/r1/retry/", { run_id: "r2", retry_of: "r1", state: "queued" }, 201);
    api.on("GET", "/ai/ask/runs/r2/stream/", stream(DONE("Probes, on the second go.", 23)));
    await retryButton(page).click();
    await expect(page.getByText("Probes, on the second go.")).toBeVisible();
    expect(times(api, "POST /ai/ask/runs/r1/retry/")).toBe(2);
  });

  test("reopening a Conversation whose last run ended unanswered shows why, with Retry", async ({ page, api }) => {
    // The stream was cut and the reader came back later: the Conversation carries the run.
    const screen = SCREENS.find((s) => s.id === "ask-iris-conversation")!;
    await openScreen(page, api, screen, {
      override: (a) => a.on("GET", "/ai/conversations/1/", {
        id: 1, title: "Soil sensors", record: null, record_title: null, turn_count: 0,
        created_at: "2026-11-05T08:00:00+08:00", updated_at: "2026-11-05T08:00:00+08:00", turns: [],
        latest_run: { id: "r1", state: "failed", end_reason: "worker_lost", question: QUESTION, retry_of: null, last_sequence: 2 },
      }),
    });

    await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
    await expect(page.getByText(NOT_ANSWERED_COPY.failed)).toBeVisible();
    await expect(retryButton(page)).toBeEnabled();

    api.on("POST", "/ai/ask/runs/r1/retry/", { run_id: "r2", retry_of: "r1", state: "queued" }, 201);
    api.on("GET", "/ai/ask/runs/r2/stream/", stream(DONE("Probes, after reopening.", 24)));
    await retryButton(page).click();
    await expect(page.getByText("Probes, after reopening.")).toBeVisible();
  });
});
