// The Full Text Rule (IR-1218, DESIGN.md): text is given its whole box and is
// never cut. A pane that scrolls inside itself hides a name that runs past its
// row without ever making the page scroll, so the viewport matrix cannot see it;
// this measures the text against its own row instead.
import { expect, test } from "./support/mock-api";
import { openScreen } from "./support/open-screen";
import { SCREENS } from "./support/screens";

const LONG_NAME = "Final_Thesis_Manuscript_Revised_Signed_Adviser_Copy_v3.pdf";

test.describe("the Full Text Rule", () => {
  test("a long file name wraps inside its Documents row at phone width (IR-1203)", async ({ page, api }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    const screen = SCREENS.find((s) => s.id === "paper-view-review-documents");
    if (!screen) throw new Error("screens.ts has no paper-view-review-documents");
    await openScreen(page, api, screen);

    const name = page.getByRole("heading", { name: LONG_NAME });
    await expect(name).toBeVisible();
    const fit = await name.evaluate((el) => {
      const row = el.closest("li") ?? el.parentElement!;
      const text = el.getBoundingClientRect();
      const box = row.getBoundingClientRect();
      return { overflow: el.scrollWidth - el.clientWidth, pastRow: Math.max(0, Math.round(text.right - box.right)) };
    });
    expect(fit, "the name runs past its own box or its row").toEqual({ overflow: 0, pastRow: 0 });
  });
});
