/**
 * The screens IR-259 moved onto the API do not read the old stage values.
 *
 * These are the stored values IR-260 retires. A screen that still switches on
 * them would silently fall through to its default once they stop arriving, so
 * this fails the build first. Scoped to IR-259's files on purpose: the review
 * screens are IR-268's, the upload/edit gates IR-273's, and the repo-wide
 * guard is IR-274's.
 */
import { describe, expect, it } from "vitest";

import workspacePage from "./MyWorkspacePage.tsx?raw";
import workspaceStages from "@/lib/workspaceStages.ts?raw";
import paperView from "./paper-view/PaperViewPage.tsx?raw";
import paperGovernance from "./paper-view/PaperGovernance.tsx?raw";
import statusBadge from "@/components/shared/StatusBadge.tsx?raw";

const RETIRED = ["adviser_review", "rdco_intake", "itso_review", "parallel_review", "rdco_review", "declined"];

/** Code only: a comment explaining what used to happen is not a read. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

/**
 * `StatusBadge` keeps a `status` fallback for the Evaluation screen until
 * IR-268, and its colour map for that fallback until IR-274. Only the part
 * above the fallback marker is the workflow-state path this ticket owns.
 */
function workflowStatePath(source: string): string {
  const marker = source.indexOf("IR-274: delete from here");
  expect(marker, "StatusBadge lost its fallback marker").toBeGreaterThan(-1);
  return source.slice(0, marker);
}

describe("IR-259's screens read no retired stage value", () => {
  it.each([
    ["MyWorkspacePage.tsx", workspacePage],
    ["lib/workspaceStages.ts", workspaceStages],
    ["paper-view/PaperViewPage.tsx", paperView],
    ["paper-view/PaperGovernance.tsx", paperGovernance],
    ["StatusBadge.tsx (workflow-state path)", workflowStatePath(statusBadge)],
  ])("%s", (_file, source) => {
    const found = RETIRED.filter((value) => new RegExp(`["'\`]${value}["'\`]`).test(code(source)));
    expect(found).toEqual([]);
  });
});
