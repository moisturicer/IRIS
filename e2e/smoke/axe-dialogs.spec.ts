// IR-908 (dialogs): axe with each dialog open. Cases are in support/dialogs.ts.
import { axeScan } from "../support/a11y";
import { DIALOGS } from "./support/dialogs";
import { expect, test } from "./support/mock-api";
import { expectNotCrashed, openScreen, settle } from "./support/open-screen";
import { SCREENS } from "./support/screens";

for (const dialog of DIALOGS) {
  test(`${dialog.id} dialog has no serious or critical accessibility findings`, async ({ page, api }, testInfo) => {
    const screen = SCREENS.find((s) => s.id === dialog.screen);
    if (!screen) throw new Error(`dialogs.ts names a screen that screens.ts does not have: ${dialog.screen}`);

    if (dialog.viewport) await page.setViewportSize(dialog.viewport);
    await openScreen(page, api, { ...screen, path: dialog.path ?? screen.path }, { override: dialog.override });
    await expect(page.getByRole("heading", { name: screen.heading }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");

    await dialog.open(page);
    await expect(dialog.dialog(page), `${dialog.id}: the dialog did not open`).toBeVisible();
    await expectNotCrashed(page);
    await settle(page);

    const { findings } = await axeScan(page, dialog.id, testInfo);
    expect(findings, `${dialog.id} (from ${screen.path})`).toEqual([]);
  });
}
