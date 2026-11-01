// Targeted automated accessibility for a journey's key screens (IR-631 Q16).
// Fails on serious and critical only, the same bar as the frontend's vitest
// axe checks. A real browser, so colour contrast IS checked here, unlike
// jsdom; screen-reader use and judgement calls stay in IR-414's manual pass.
//
// Findings are COLLECTED, not asserted where they are found. Journeys run in
// serial mode, where one failed test skips every test after it; asserting an
// axe finding in the middle of a journey would hide whether the workflow
// steps after it work. Each spec ends with `a11y.assertClean()` as its own
// test, so an accessibility defect is still a failed check -- just a separate
// one from the workflow's.
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";

export class A11yLedger {
  private readonly findings: string[] = [];
  private readonly checked: string[] = [];

  async scan(page: Page, testInfo: TestInfo, label: string) {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    await testInfo.attach(`axe-${label}.json`, {
      body: JSON.stringify(results.violations, null, 2),
      contentType: "application/json",
    });
    this.checked.push(`axe ${label}`);
    for (const v of results.violations) {
      if (v.impact !== "serious" && v.impact !== "critical") continue;
      for (const n of v.nodes) {
        this.findings.push(
          `[${label}] ${v.impact} ${v.id} @ ${n.target.join(" ")} :: ${n.html.slice(0, 160)} :: ` +
          (n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 220),
        );
      }
    }
  }

  /** WCAG 1.4.10 Reflow at 360 CSS px: nothing scrolls sideways. */
  async reflow360(page: Page, label: string) {
    const previous = page.viewportSize();
    await page.setViewportSize({ width: 360, height: 740 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    this.checked.push(`reflow ${label}`);
    if (overflow > 0) this.findings.push(`[${label}] reflow: ${overflow}px horizontal overflow at 360px`);
    if (previous) await page.setViewportSize(previous);
  }

  assertClean(testInfo: TestInfo) {
    testInfo.annotations.push({ type: "a11y checked", description: this.checked.join(", ") || "nothing" });
    expect(this.findings, "serious/critical accessibility findings on this journey's key screens").toEqual([]);
  }
}
