// IR-908 (routes): axe in a real browser on every routed screen.
//
// One test per entry in support/screens.ts, the catalogue the viewport matrix
// also uses and viewport-coverage.spec.ts holds equal to the router, so a new
// route cannot ship without being scanned here. WCAG 2.x A and AA, contrast
// included (jsdom cannot check it; this is a real browser). A serious or
// critical finding fails that screen's test with the rule, the node and the
// reason; each screen is its own test so one defect does not hide the others.
//
// Scanned once per screen, at the desktop width: colour contrast and the
// accessible tree do not change with the window. Reflow at narrow widths is
// the viewport matrix's job (IR-910). The states a screen can be left in and
// the dialogs it opens are scanned by axe-states.spec.ts and axe-dialogs.spec.ts.
import { axeScan } from "../support/a11y";
import { expect, test } from "./support/mock-api";
import { expectNotCrashed, openScreen, settle } from "./support/open-screen";
import { SCREENS } from "./support/screens";

for (const screen of SCREENS) {
  test(`${screen.id} has no serious or critical accessibility findings`, async ({ page, api }, testInfo) => {
    await openScreen(page, api, screen);
    await expect(page.getByRole("heading", { name: screen.heading }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expectNotCrashed(page);
    await settle(page);

    const { findings } = await axeScan(page, screen.id, testInfo);
    expect(findings, `${screen.path} as ${screen.role ?? "a signed-out visitor"}`).toEqual([]);
  });
}
