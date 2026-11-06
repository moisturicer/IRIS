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
import { measureOverflow } from "./viewport";

/**
 * One axe pass over the page as it stands: WCAG 2.x A and AA, contrast included
 * (a real browser). Returns every violation for the attachment and one line per
 * serious or critical node for the verdict. Shared by the journeys' ledger and
 * the smoke tier's scans of routes, states and dialogs (IR-908), so all fail on
 * the same bar. With `testInfo`, every violation is attached as `axe-<label>.json`.
 */
export async function axeScan(page: Page, label: string, testInfo?: TestInfo) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  if (testInfo) {
    await testInfo.attach(`axe-${label}.json`, {
      body: JSON.stringify(results.violations, null, 2),
      contentType: "application/json",
    });
  }
  const findings: string[] = [];
  for (const v of results.violations) {
    if (v.impact !== "serious" && v.impact !== "critical") continue;
    for (const n of v.nodes) {
      findings.push(
        `[${label}] ${v.impact} ${v.id} @ ${n.target.join(" ")} :: ${n.html.slice(0, 160)} :: ` +
        (n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 220),
      );
    }
  }
  return { violations: results.violations, findings };
}

export class A11yLedger {
  private readonly findings: string[] = [];
  private readonly checked: string[] = [];

  async scan(page: Page, testInfo: TestInfo, label: string) {
    const { findings } = await axeScan(page, label, testInfo);
    this.checked.push(`axe ${label}`);
    this.findings.push(...findings);
  }

  /** WCAG 1.4.10 Reflow at 360 CSS px: nothing scrolls sideways. */
  async reflow360(page: Page, label: string) {
    const previous = page.viewportSize();
    await page.setViewportSize({ width: 360, height: 740 });
    // Reflow is judged on the settled layout. The app shell animates its margin
    // for 200 ms when the window narrows past `md`, and the sidebar's old
    // margin pushes the page sideways until it finishes: a measurement taken
    // straight after the resize reports that, which no one loading the page at
    // 360px ever sees (IR-934). Only transitions are awaited, and for 3 s at most:
    // an endless animation (a spinner, a skeleton) must not hang the check.
    await page.evaluate(async () => {
      const ended = Promise.all(
        document.getAnimations().filter((a) => a instanceof CSSTransition).map((a) => a.finished.catch(() => undefined)),
      );
      await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 3000))]);
    });
    const { overflow, culprits } = await measureOverflow(page);
    this.checked.push(`reflow ${label}`);
    if (overflow > 0) {
      const where = culprits.length ? `; widest: ${culprits.join(" | ")}` : "";
      this.findings.push(`[${label}] reflow: ${overflow}px horizontal overflow at 360px${where}`);
    }
    if (previous) await page.setViewportSize(previous);
  }

  assertClean(testInfo: TestInfo) {
    testInfo.annotations.push({ type: "a11y checked", description: this.checked.join(", ") || "nothing" });
    expect(this.findings, "serious/critical accessibility findings on this journey's key screens").toEqual([]);
  }
}
