/**
 * An office reviewer's unsent comment, kept across a navigation (IR-269,
 * carrying IR-143's criterion: opening a document does not lose it).
 *
 * The *Clear* / *Record finding* dialog is modal. To read the paper or a file
 * the reviewer closes it, and closing unmounts the form, so the comment is
 * kept here rather than in component state. One draft per record and outcome:
 * a half-written finding never turns up pre-filled as a clearance's note.
 *
 * `sessionStorage`, as the retired review form's draft did: a half-written finding is
 * somebody's opinion of somebody else's work, and should not outlive the tab
 * on a shared machine. Every access is guarded; losing a draft is a shame,
 * losing the dialog would be a defect.
 *
 * One draft per user, record and outcome (IR-931): the key carries the signed-in
 * user's id, so the next person signed in on this tab never sees it, and nothing
 * is cleared on sign-out, which would lose a draft to an idle expiry. With nobody
 * signed in nothing is read, written or cleared.
 */
import type { OfficeReviewOutcome } from "@/types/records";

const KEY_PREFIX = "iris_office_review_draft:";

/** Who is signed in; none means nothing is read, written or cleared. */
type UserId = number | null | undefined;

function keyFor(userId: number, recordId: number, outcome: OfficeReviewOutcome): string {
  return `${KEY_PREFIX}${userId}:${recordId}:${outcome}`;
}

export function readOfficeReviewDraft(userId: UserId, recordId: number, outcome: OfficeReviewOutcome): string {
  if (userId == null) return "";
  try {
    return sessionStorage.getItem(keyFor(userId, recordId, outcome)) ?? "";
  } catch {
    return "";
  }
}

/** Keep this comment, or forget it once it is blank again. */
export function writeOfficeReviewDraft(
  userId: UserId,
  recordId: number,
  outcome: OfficeReviewOutcome,
  comment: string,
): void {
  if (userId == null) return;
  try {
    if (comment.trim() === "") sessionStorage.removeItem(keyFor(userId, recordId, outcome));
    else sessionStorage.setItem(keyFor(userId, recordId, outcome), comment);
  } catch {
    // Storage refused or full: the reviewer keeps typing either way.
  }
}

/** Forget both drafts for this record -- once a verdict is actually recorded. */
export function clearOfficeReviewDrafts(userId: UserId, recordId: number): void {
  if (userId == null) return;
  for (const outcome of ["cleared", "finding"] as const) {
    try {
      sessionStorage.removeItem(keyFor(userId, recordId, outcome));
    } catch {
      // As above.
    }
  }
}
