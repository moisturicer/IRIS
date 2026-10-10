/**
 * The retired pipeline vocabulary stays retired (IR-274).
 *
 * The fixed pipeline's five stage values and the stored `declined` were
 * migrated to `in_review` by IR-260 and removed by IR-274 (ADR-032 §13). A
 * screen that still switches on one would silently fall through to its default,
 * because the server never sends it again, so this fails the build first.
 *
 * Repo-wide: every non-test `.ts` and `.tsx` file under `src/`. It replaces
 * IR-259's `workflowVocabulary.test.ts`, which guarded only that ticket's
 * screens. Comments are stripped first: a comment explaining what used to
 * happen is not a read.
 *
 * `declined` survives as a role-request, download-request, clearance and
 * review-decision value, so only its *pipeline* reading is banned: compared
 * with `pipeline_status`, or named through `PIPELINE_STATUS`.
 */
import { describe, expect, it } from "vitest";

const STAGE_VALUES = ["adviser_review", "rdco_intake", "itso_review", "parallel_review", "rdco_review"];

const DECLINED_AS_PIPELINE = [
  /\bpipeline_status\s*[!=]==?\s*["'`]declined["'`]/,
  /["'`]declined["'`]\s*[!=]==?\s*[\w.?]*\bpipeline_status\b/,
  /\bpipeline_status\s*:\s*["'`]declined["'`]/,
  /\bPIPELINE_STATUS\.DECLINED\b/,
];

/** Every non-test source file, keyed `src/...`, read as text. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
  )
    .filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.startsWith("/src/test/"))
    .map(([path, source]) => [path.slice(1), source]),
);

/** Code only: block and line comments removed, strings and code kept. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

/** Every retired read in `source`, as "<what>: <text>". */
function retiredReads(source: string): string[] {
  const text = code(source);
  const found: string[] = [];
  for (const value of STAGE_VALUES) {
    if (new RegExp(`["'\`]${value}["'\`]`).test(text)) found.push(`stage value: ${value}`);
  }
  for (const pattern of DECLINED_AS_PIPELINE) {
    const match = text.match(pattern);
    if (match) found.push(`declined as a pipeline status: ${match[0]}`);
  }
  return found;
}

describe("the retired pipeline vocabulary", () => {
  it("scans the source tree", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(Object.keys(SOURCES)).toContain("src/lib/constants.ts");
  });

  it("is read by no source file", () => {
    const offenders = Object.entries(SOURCES)
      .map(([path, source]) => [path, retiredReads(source)] as const)
      .filter(([, reads]) => reads.length > 0);
    expect(offenders).toEqual([]);
  });

  it("catches each way a retired value could come back", () => {
    expect(retiredReads(`if (record.pipeline_status === "itso_review") go();`)).toEqual([
      "stage value: itso_review",
    ]);
    expect(retiredReads(`const d = record.pipeline_status !== 'declined';`)).toHaveLength(1);
    expect(retiredReads(`const d = "declined" === r.pipeline_status;`)).toHaveLength(1);
    expect(retiredReads(`fixture({ pipeline_status: "declined" })`)).toHaveLength(1);
    expect(retiredReads(`const s = PIPELINE_STATUS.DECLINED;`)).toHaveLength(1);
  });

  it("lets the surviving meanings of declined, and comments, through", () => {
    expect(retiredReads(`if (request.status === "declined") show();`)).toEqual([]);
    expect(retiredReads(`if (clearance.status === "declined") show();`)).toEqual([]);
    expect(retiredReads(`// a record used to sit at "rdco_intake"`)).toEqual([]);
    expect(retiredReads(`/* pipeline_status === "declined" was the old revision */`)).toEqual([]);
  });
});
