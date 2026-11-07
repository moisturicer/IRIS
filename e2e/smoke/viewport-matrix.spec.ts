// IR-910: every routed screen at 360, 768, 1280 and 1745 px.
//
// Per screen and width, two assertions and one record:
//   1. the PAGE does not scroll sideways (WCAG 1.4.10; a data table may scroll
//      inside its own container, the page may not),
//   2. the screen's primary action can be reached (support/viewport.ts),
//   3. for a table-heavy screen, what the table did is recorded, and a table
//      that is cut off instead of scrolling fails.
// Each check is its own test so one broken screen does not hide the others;
// matrix-reporter.ts turns the annotations into the per-screen table.
import { expect, test } from "./support/mock-api";
import { signedIn } from "./support/fixtures";
import { SCREENS, TABLE_BEHAVIOUR } from "./support/screens";
import { checkReachable, describeTable, measureOverflow, VIEWPORTS } from "../support/viewport";
import type { MatrixCell } from "./support/matrix-reporter";

SCREENS.forEach((screen, order) => {
  for (const vp of VIEWPORTS) {
    test(`${screen.id} at ${vp.name}px`, async ({ page, api }, testInfo) => {
      // Recorded first and filled in below, so a screen that never finishes
      // drawing still gets a failing cell instead of a missing one.
      const note = {
        type: "matrix",
        description: JSON.stringify({
          order, screen: screen.id, viewport: vp.name, overflow: 0, primary: screen.primaryLabel,
          reachable: false, reason: "the screen did not finish drawing",
        } satisfies Omit<MatrixCell, "status">),
      };
      testInfo.annotations.push(note);

      await page.setViewportSize({ width: vp.width, height: vp.height });
      if (screen.role) await signedIn(page, api, screen.role);
      screen.mocks?.(api);

      await page.goto(screen.path);
      await expect(page.getByRole("heading", { name: screen.heading }).first()).toBeVisible();
      await page.waitForLoadState("networkidle");

      // A screen that crashed into the error screen has no overflow to find and
      // no action to reach; the heading above would not catch every one.
      await expect(page.getByRole("heading", { name: "Something went wrong" })).toHaveCount(0);

      const { overflow, culprits } = await measureOverflow(page);
      const reach = await checkReachable(screen.primary(page));
      const table = screen.table && (await screen.table(page).count()) > 0
        ? await describeTable(screen.table(page)) : undefined;

      const cell: Omit<MatrixCell, "status"> = {
        order, screen: screen.id, viewport: vp.name, overflow, primary: screen.primaryLabel,
        reachable: reach.reachable, reason: reach.reason, table,
      };
      note.description = JSON.stringify(cell);

      expect.soft(overflow, `page scrolls sideways; widest: ${culprits.join(" | ") || "unknown"}`).toBe(0);
      expect.soft(reach.reachable, `primary action "${screen.primaryLabel}": ${reach.reason}`).toBe(true);
      if (screen.table) {
        expect.soft(table, `a table was expected on ${screen.id}; ${TABLE_BEHAVIOUR}`).toBeDefined();
        expect.soft(table?.behaviour, "a table must fit or scroll inside its container, never be cut off").not.toBe("clipped");
      }
    });
  }
});
