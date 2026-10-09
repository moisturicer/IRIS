/**
 * A decider's unsent comment or reason, kept across a navigation (IR-270,
 * carrying IR-143's criterion: opening a document does not lose it).
 *
 * The same reasoning as `officeReviewDraft.ts`: the dialog is modal, closing
 * it to read the paper unmounts the form, and `sessionStorage` keeps the text
 * for this tab only. One draft per record and outcome, so a half-written
 * rejection never turns up pre-filled as a publish comment. Every access is
 * guarded.
 */
import type { DecisionOutcome } from "@/types/records";

const KEY_PREFIX = "iris_decision_draft:";
const OUTCOMES: readonly DecisionOutcome[] = ["publish", "keep_unlisted", "reject"];

function keyFor(recordId: number, outcome: DecisionOutcome): string {
  return `${KEY_PREFIX}${recordId}:${outcome}`;
}

export function readDecisionDraft(recordId: number, outcome: DecisionOutcome): string {
  try {
    return sessionStorage.getItem(keyFor(recordId, outcome)) ?? "";
  } catch {
    return "";
  }
}

/** Keep this text, or forget it once it is blank again. */
export function writeDecisionDraft(recordId: number, outcome: DecisionOutcome, text: string): void {
  try {
    if (text.trim() === "") sessionStorage.removeItem(keyFor(recordId, outcome));
    else sessionStorage.setItem(keyFor(recordId, outcome), text);
  } catch {
    // Storage refused or full: the decider keeps typing either way.
  }
}

/** Forget every draft for this record -- once it is actually decided. */
export function clearDecisionDrafts(recordId: number): void {
  for (const outcome of OUTCOMES) {
    try {
      sessionStorage.removeItem(keyFor(recordId, outcome));
    } catch {
      // As above.
    }
  }
}
