// Targeted automated accessibility for a journey's key screens (IR-631 Q16).
// Fails on serious and critical only, the same bar as the frontend's vitest
// axe checks. A real browser, so colour contrast IS checked here, unlike
// jsdom; screen-reader use and judgement calls stay in IR-414's manual pass.
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

export async function expectNoSeriousA11yViolations(page: Page, testInfo: TestInfo, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  await testInfo.attach(`axe-${label}.json`, {
    body: JSON.stringify(results.violations, null, 2),
    contentType: "application/json",
  });
  expect(
    blocking.map((v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.length} node(s))`),
    `axe serious/critical on ${label}`,
  ).toEqual([]);
}

/** WCAG 1.4.10 Reflow at 360 CSS px: nothing scrolls sideways. */
export async function expectReflowsAt360(page: Page, label: string) {
  const previous = page.viewportSize();
  await page.setViewportSize({ width: 360, height: 740 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow at 360px on ${label}`).toBeLessThanOrEqual(0);
  if (previous) await page.setViewportSize(previous);
}
