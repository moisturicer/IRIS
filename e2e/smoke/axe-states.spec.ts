// IR-908 (states): axe on each state in docs/ui-ux/17-ui-states-matrix.md.
//
// The routes spec scans each screen once, drawn with data. A screen waiting on a
// read, empty, failed, timed out or refused is a different page with its own
// markup (skeletons, the error and interrupted states, the refusal screens), so
// each is scanned here. The cells are catalogued in support/states.ts.
import { axeScan } from "../support/a11y";
import { expect, test } from "./support/mock-api";
import { expectNotCrashed, openScreen, settle } from "./support/open-screen";
import { SCREENS } from "./support/screens";
import { STATES, stateId } from "./support/states";

for (const state of STATES) {
  const id = stateId(state);
  test(`${id} has no serious or critical accessibility findings`, async ({ page, api }, testInfo) => {
    const screen = SCREENS.find((s) => s.id === state.screen);
    if (!screen) throw new Error(`states.ts names a screen that screens.ts does not have: ${state.screen}`);

    await openScreen(page, api, { ...screen, path: state.path ?? screen.path }, {
      override: state.override,
      // Only the read under test times out: on a slow machine another read that did would put a second failure on screen.
      timeOut: state.timeOut ? { only: state.read.path } : undefined,
    });
    await expect(state.shows(page), `${id}: the screen is not in this state`).toBeVisible();
    await expectNotCrashed(page);
    await settle(page);

    const { findings } = await axeScan(page, id, testInfo);
    expect(findings, `${id} (${state.path ?? screen.path})`).toEqual([]);
  });
}
