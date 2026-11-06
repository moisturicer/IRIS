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
// the viewport matrix's job (IR-910).
//
// Dialogs and the states matrix are NOT routes and are scanned by their own
// ticket work, not here.
import { axeScan } from "../support/a11y";
import { expect, test } from "./support/mock-api";
import { signedIn } from "./support/fixtures";
import { SCREENS } from "./support/screens";

for (const screen of SCREENS) {
  test(`${screen.id} has no serious or critical accessibility findings`, async ({ page, api }, testInfo) => {
    if (screen.role) await signedIn(page, api, screen.role);
    screen.mocks?.(api);

    await page.goto(screen.path);
    await expect(page.getByRole("heading", { name: screen.heading }).first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    // An error screen can be accessible; it is not the screen under test.
    await expect(page.getByRole("heading", { name: "Something went wrong" })).toHaveCount(0);

    // Contrast is read from the colours on screen at that instant, so a fade or
    // slide still running reads as the wrong colour (IR-934 met the same with
    // the shell's margin transition). Finite animations are awaited, for 3 s at
    // most; an endless one (a spinner, a skeleton pulse) must not hang the scan.
    await page.evaluate(async () => {
      const ended = Promise.all(
        document.getAnimations()
          .filter((a) => a.effect?.getTiming().iterations !== Infinity)
          .map((a) => a.finished.catch(() => undefined)),
      );
      await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 3000))]);
    });

    const { violations, findings } = await axeScan(page, screen.id);
    await testInfo.attach(`axe-${screen.id}.json`, {
      body: JSON.stringify(violations, null, 2),
      contentType: "application/json",
    });
    expect(findings, `${screen.path} as ${screen.role ?? "a signed-out visitor"}`).toEqual([]);
  });
}
