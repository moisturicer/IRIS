// IR-907: forced-state browser tests, one per cell of docs/ui-ux/17-ui-states-matrix.md.
//
// axe-states.spec.ts (IR-908) proves each state is drawn accessibly. This spec
// proves what the reader SEES and can DO NEXT, with the state forced by
// intercepting the one request that decides it (the catalogue is
// support/states.ts, which names that read and what it answers when it works):
//
//   loading      the read is held, not failed: a placeholder, no error or empty claim;
//                released, the content replaces it
//   empty        the read worked and there was nothing: the empty words, no retry,
//                and the screen's own next step where it has one
//   error        a 500: says so and offers Try again, which asks again and, when the
//                read now works, shows the content
//   interrupted  no answer within the timeout (ADR-061): Retry, chosen by the reader;
//                nothing is retried on its own
//   revoked      403 or 404: one screen, the same words for both (IR-153), no retry
//
// Mid-session withdrawal (a permission taken away between a list and the page it
// links to) is exercised at the end of the file. The Ask IRIS stream is in
// ask-iris-stream.spec.ts.
import { expect, test } from "./support/mock-api";
import { openScreen, expectNotCrashed } from "./support/open-screen";
import { SCREENS } from "./support/screens";
import { STATES, stateId, type UiState } from "./support/states";
import type { Locator, Page, Route } from "@playwright/test";

const screenOf = (state: UiState) => {
  const screen = SCREENS.find((s) => s.id === state.screen);
  if (!screen) throw new Error(`states.ts names a screen that screens.ts does not have: ${state.screen}`);
  return { ...screen, path: state.path ?? screen.path };
};

/** The other states this same read can leave the same view in. A screen is in one at a time. */
const siblingsOf = (state: UiState) =>
  STATES.filter((s) => s !== state && s.screen === state.screen && s.path === state.path && s.read.path === state.read.path
    && s.read.method === state.read.method && s.state !== state.state
    // A 403 and a 404 are one state drawn twice; and the loading placeholder is not exclusive of a state it precedes.
    && s.state !== "loading");

const readKey = (state: UiState) => `${state.read.method} ${state.read.path}`;
const timesRead = (seen: string[], state: UiState) => seen.filter((k) => k === readKey(state)).length;

/** The control that asks again. A failure says "Try again"; a timeout says "Retry". */
const retryControl = (page: Page, name: "Try again" | "Retry"): Locator =>
  page.getByRole("button", { name, exact: true }).first();
const anyRetry = (page: Page) => page.getByRole("button", { name: /^(Try again|Retry)$/ });

async function expectOnlyThisState(page: Page, state: UiState) {
  for (const other of siblingsOf(state)) {
    await expect(other.shows(page), `${stateId(state)} must not also look like ${stateId(other)}`).toBeHidden();
  }
  await expectNotCrashed(page);
}

for (const state of STATES) {
  const id = stateId(state);

  if (state.state === "loading") {
    test(`${id}: holds a placeholder while the read is pending, then shows what it brought`, async ({ page, api }) => {
      let release: () => void = () => undefined;
      const held = new Promise<void>((resolve) => { release = resolve; });
      await openScreen(page, api, screenOf(state), {
        override: (a) => {
          state.override(a);
          // Held, not hung: the same read answers once the test lets it.
          a.on(state.read.method, state.read.path, async (route: Route) => {
            await held;
            await route.fulfill({ json: state.ok });
          });
        },
      });

      await expect(state.shows(page), `${id}: the placeholder is not showing`).toBeVisible();
      await expect(state.recovered(page)).toBeHidden();
      await expectOnlyThisState(page, state);
      // Waiting is not failing: nothing offers a retry for a read that has not answered.
      await expect(anyRetry(page)).toHaveCount(0);

      release();
      await expect(state.recovered(page), `${id}: the content never replaced the placeholder`).toBeVisible();
      await expect(state.shows(page)).toBeHidden();
      await expectNotCrashed(page);
    });
  }

  if (state.state === "empty") {
    test(`${id}: says there is nothing, offers no retry, and keeps the screen usable`, async ({ page, api }) => {
      await openScreen(page, api, screenOf(state), { override: state.override });
      await expect(state.shows(page), `${id}: the empty words are not showing`).toBeVisible();
      await expectOnlyThisState(page, state);
      // The read worked. Asking again would not change the answer, so nothing is offered.
      await expect(anyRetry(page)).toHaveCount(0);
      if (state.next) await expect(state.next(page), `${id}: the next step is missing`).toBeVisible();
    });
  }

  if (state.state === "error") {
    test(`${id}: says the read failed and Try again reads it again`, async ({ page, api }) => {
      await openScreen(page, api, screenOf(state), { override: state.override });
      await expect(state.shows(page), `${id}: the error is not showing`).toBeVisible();
      await expectOnlyThisState(page, state);
      await expect(state.recovered(page)).toBeHidden();

      const button = retryControl(page, "Try again");
      await expect(button).toBeVisible();
      await expect(button).toBeEnabled();

      // The server is back: the next read works. Only the reader's click sends it.
      const before = timesRead(api.seen, state);
      api.on(state.read.method, state.read.path, state.ok);
      await button.click();

      await expect(state.recovered(page), `${id}: Try again did not bring the content`).toBeVisible();
      await expect(state.shows(page)).toBeHidden();
      expect(timesRead(api.seen, state), `${id}: Try again reads once`).toBe(before + 1);
      await expectNotCrashed(page);
    });
  }

  if (state.state === "interrupted") {
    test(`${id}: says it took too long, retries nothing by itself, and Retry reads it again`, async ({ page, api }) => {
      // Only this state's read times out: another read on the screen that did would show a second failure.
      await openScreen(page, api, screenOf(state), { override: state.override, timeOut: { only: state.read.path } });
      await expect(state.shows(page), `${id}: the interrupted state is not showing`).toBeVisible();
      await expectOnlyThisState(page, state);
      await expect(state.recovered(page)).toBeHidden();

      const button = retryControl(page, "Retry");
      await expect(button).toBeVisible();
      await expect(button).toBeEnabled();
      // Not "Try again": a timeout is not a refusal, and says nothing about the server.
      await expect(retryControl(page, "Try again")).toHaveCount(0);

      // ADR-061: nothing is retried automatically. Whatever was asked by now stays what was asked.
      const asked = timesRead(api.seen, state);
      await page.waitForTimeout(750);
      expect(timesRead(api.seen, state), `${id}: something retried on its own`).toBe(asked);

      api.on(state.read.method, state.read.path, state.ok);
      await button.click();

      await expect(state.recovered(page), `${id}: Retry did not bring the content`).toBeVisible();
      await expect(state.shows(page)).toBeHidden();
      expect(timesRead(api.seen, state), `${id}: Retry reads once`).toBe(asked + 1);
      await expectNotCrashed(page);
    });
  }

  if (state.state === "revoked") {
    test(`${id}: shows the not-available screen and offers no retry`, async ({ page, api }) => {
      await openScreen(page, api, screenOf(state), { override: state.override });
      await expect(state.shows(page), `${id}: the not-available screen is not showing`).toBeVisible();
      await expectOnlyThisState(page, state);
      // A refusal is not a failure to ride out: access may have changed, so asking again is not offered.
      await expect(anyRetry(page)).toHaveCount(0);
      // And the screen never shows what it would have shown had the read worked.
      await expect(state.recovered(page)).toBeHidden();
      if (state.next) await expect(state.next(page), `${id}: the way out is missing`).toBeVisible();
    });
  }
}

/**
 * A hidden Record and a missing id read alike (IR-153): the page never confirms
 * that something exists. Both refusals are drawn for each view and the visible
 * words compared, so a status-dependent sentence cannot come back.
 */
const refused = STATES.filter((s) => s.state === "revoked");
for (const view of new Set(refused.map((s) => `${s.screen}|${s.path ?? ""}|${s.read.path}`))) {
  const pair = refused.filter((s) => `${s.screen}|${s.path ?? ""}|${s.read.path}` === view);
  const first = pair[0];
  // The variant ends in the status ("403", or "saved 403" where a surface has several views).
  const viewName = [first.screen, first.variant?.replace(/\s*\d{3}$/, "")].filter(Boolean).join(" · ");
  test(`${viewName}: a 403 and a 404 read the same`, async ({ page, api }) => {
    expect(pair.map((s) => s.variant)).toEqual(expect.arrayContaining([expect.stringContaining("403"), expect.stringContaining("404")]));
    const words: Record<string, string> = {};
    await openScreen(page, api, screenOf(first), { override: pair[0].override });
    for (const [i, state] of pair.entries()) {
      if (i > 0) {
        state.override(api);
        await page.reload();
      }
      await expect(state.shows(page)).toBeVisible();
      words[state.variant ?? String(i)] = await page.locator("body").innerText();
    }
    const [a, b] = Object.values(words);
    expect(a, `${view}: the 403 and the 404 screens differ`).toBe(b);
  });
}

// --- access withdrawn while the reader is already in the product ------------

test("Discover → Paper View: a Record withdrawn after it was listed lands on the same not-available screen, with a way out", async ({ page, api }) => {
  const discover = SCREENS.find((s) => s.id === "discover")!;
  const paper = SCREENS.find((s) => s.id === "paper-view")!;
  await openScreen(page, api, discover);
  // The list was read while the reader could see the paper. Then the permission goes.
  paper.mocks?.(api);
  api.on("GET", "/records/101/", { detail: "smoke: the read was refused" }, 404);

  await page.getByText(paper.heading as string).first().click();
  await expect(page.getByRole("heading", { name: "Record not available" })).toBeVisible();
  await expect(page).toHaveURL(/\/records\/101$/);
  await expect(anyRetry(page)).toHaveCount(0);
  // Entered from inside IRIS, so Back leads somewhere and is offered; the list is still there.
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page.getByRole("heading", { name: "Discover" })).toBeVisible();
});

test("Ask IRIS: a Conversation whose access is withdrawn after it was opened reads as not available", async ({ page, api }) => {
  const screen = SCREENS.find((s) => s.id === "ask-iris-conversation")!;
  await openScreen(page, api, screen);
  await expect(page.getByRole("heading", { name: /What do you want to ask/ })).toBeVisible();

  // Access to it is withdrawn; the reader reloads the address they were on.
  api.on("GET", "/ai/conversations/1/", { detail: "smoke: refused" }, 403);
  await page.reload();
  await expect(page.getByRole("heading", { name: "This conversation is not available." })).toBeVisible();
  await expect(anyRetry(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start a new chat" })).toBeVisible();
});
