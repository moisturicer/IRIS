// Records the viewport matrix (IR-910) as a table: one row per screen, one
// column per width. Reads the `matrix` annotation each matrix test leaves, so
// the table is built from what was measured, never from what passed.
//
// Writes test-results-smoke/viewport-matrix.{json,md}. CI appends the .md to the
// run's summary; the .json is the machine-readable record.
import { mkdirSync, writeFileSync } from "node:fs";
import type { TableReport } from "../../support/viewport";
import type { FullResult, Reporter, TestCase, TestResult } from "@playwright/test/reporter";

export interface MatrixCell {
  /** The screen's place in the catalogue, so the table reads in that order whatever order the workers finish in. */
  order: number;
  screen: string;
  viewport: string;
  status: "pass" | "fail";
  overflow: number;
  primary: string;
  reachable: boolean;
  reason: string;
  table?: TableReport;
}

const OUT = "test-results-smoke";

export default class MatrixReporter implements Reporter {
  private readonly cells: MatrixCell[] = [];

  onTestEnd(test: TestCase, result: TestResult) {
    const note = [...result.annotations, ...test.annotations].find((a) => a.type === "matrix");
    if (!note?.description) return;
    const cell = JSON.parse(note.description) as MatrixCell;
    cell.status = result.status === "passed" ? "pass" : "fail";
    this.cells.push(cell);
  }

  onEnd(_result: FullResult) {
    if (this.cells.length === 0) return;
    this.cells.sort((a, b) => a.order - b.order || Number(a.viewport) - Number(b.viewport));
    mkdirSync(OUT, { recursive: true });
    writeFileSync(`${OUT}/viewport-matrix.json`, JSON.stringify(this.cells, null, 2));
    writeFileSync(`${OUT}/viewport-matrix.md`, renderMatrix(this.cells));
  }
}

export function renderMatrix(cells: MatrixCell[]): string {
  const widths = [...new Set(cells.map((c) => c.viewport))].sort((a, b) => Number(a) - Number(b));
  const screens = [...new Set(cells.map((c) => c.screen))];
  const failing = cells.filter((c) => c.status === "fail");
  const lines = [
    "### Viewport matrix (IR-910)",
    "",
    `${cells.length} checks over ${screens.length} screens: ${cells.length - failing.length} passed, ${failing.length} failed. ` +
      "Each cell is the page's horizontal overflow in px (0 = none) and whether the primary action could be reached.",
    "",
    `| Screen | Primary action | ${widths.map((w) => `${w}px`).join(" | ")} |`,
    `|---|---|${widths.map(() => "---").join("|")}|`,
  ];
  for (const screen of screens) {
    const row = widths.map((w) => {
      const c = cells.find((x) => x.screen === screen && x.viewport === w);
      if (!c) return "n/a";
      const mark = c.status === "pass" ? "ok" : "FAIL";
      return `${mark} (${c.overflow}px${c.reachable ? "" : ", action unreachable"})`;
    });
    const primary = cells.find((x) => x.screen === screen)?.primary ?? "";
    lines.push(`| ${screen} | ${primary} | ${row.join(" | ")} |`);
  }
  const tables = cells.filter((c) => c.table);
  if (tables.length) {
    lines.push("", "#### Table-heavy screens", "", "| Screen | Width | Table | Container | Small-screen behaviour |", "|---|---|---|---|---|");
    for (const c of tables) {
      lines.push(`| ${c.screen} | ${c.viewport}px | ${c.table!.tableWidth}px | ${c.table!.containerWidth}px | ${c.table!.behaviour} |`);
    }
  }
  if (failing.length) {
    lines.push("", "#### Failures", "");
    for (const c of failing) {
      const why = [c.overflow > 0 ? `${c.overflow}px sideways overflow` : "", c.reachable ? "" : `primary action: ${c.reason}`]
        .filter(Boolean).join("; ");
      lines.push(`- ${c.screen} @ ${c.viewport}px: ${why || "see the test report"}`);
    }
  }
  return lines.join("\n") + "\n";
}
