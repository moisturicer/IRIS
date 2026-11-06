/**
 * A decider's unsent comment or reason, kept across a navigation (IR-270,
 * carrying IR-143's criterion: opening a document does not lose it).
 *
 * The same reasoning as `officeReviewDraft.ts`: the dialog is modal, closing
 * it to read the paper unmounts the form, and `sessionStorage` keeps the text
 * for this tab only. One draft per record and outcome, so a half-written
 * rejection never turns up pre-filled as a publish comment. Every access is
 * guarded.
 * One draft per user, record and outcome (IR-931): the key carries the signed-in
 * user's id, so the next person signed in on this tab never sees it, and nothing
 * is cleared on sign-out, which would lose a draft to an idle expiry. With nobody
 * signed in nothing is read, written or cleared.
 */
import type { DecisionOutcome } from "@/types/records";

const KEY_PREFIX = "iris_decision_draft:";
const OUTCOMES: readonly DecisionOutcome[] = ["accept", "publish", "keep_unlisted", "reject"];

/** Who is signed in; none means nothing is read, written or cleared. */
type UserId = number | null | undefined;

function keyFor(userId: number, recordId: number, outcome: DecisionOutcome): string {
  return `${KEY_PREFIX}${userId}:${recordId}:${outcome}`;
}

export function readDecisionDraft(userId: UserId, recordId: number, outcome: DecisionOutcome): string {
  if (userId == null) return "";
  try {
    return sessionStorage.getItem(keyFor(userId, recordId, outcome)) ?? "";
  } catch {
    return "";
  }
}

/** Keep this text, or forget it once it is blank again. */
export function writeDecisionDraft(userId: UserId, recordId: number, outcome: DecisionOutcome, text: string): void {
  if (userId == null) return;
  try {
    if (text.trim() === "") sessionStorage.removeItem(keyFor(userId, recordId, outcome));
    else sessionStorage.setItem(keyFor(userId, recordId, outcome), text);
  } catch {
    // Storage refused or full: the decider keeps typing either way.
  }
}

/** Forget every draft for this record -- once it is actually decided. */
export function clearDecisionDrafts(userId: UserId, recordId: number): void {
  if (userId == null) return;
  for (const outcome of OUTCOMES) {
    try {
      sessionStorage.removeItem(keyFor(userId, recordId, outcome));
    } catch {
      // As above.
    }
  }
}
