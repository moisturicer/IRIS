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
 */
import type { OfficeReviewOutcome } from "@/types/records";

const KEY_PREFIX = "iris_office_review_draft:";

function keyFor(recordId: number, outcome: OfficeReviewOutcome): string {
  return `${KEY_PREFIX}${recordId}:${outcome}`;
}

export function readOfficeReviewDraft(recordId: number, outcome: OfficeReviewOutcome): string {
  try {
    return sessionStorage.getItem(keyFor(recordId, outcome)) ?? "";
  } catch {
    return "";
  }
}

/** Keep this comment, or forget it once it is blank again. */
export function writeOfficeReviewDraft(recordId: number, outcome: OfficeReviewOutcome, comment: string): void {
  try {
    if (comment.trim() === "") sessionStorage.removeItem(keyFor(recordId, outcome));
    else sessionStorage.setItem(keyFor(recordId, outcome), comment);
  } catch {
    // Storage refused or full: the reviewer keeps typing either way.
  }
}

/** Forget both drafts for this record -- once a verdict is actually recorded. */
export function clearOfficeReviewDrafts(recordId: number): void {
  for (const outcome of ["cleared", "finding"] as const) {
    try {
      sessionStorage.removeItem(keyFor(recordId, outcome));
    } catch {
      // As above.
    }
  }
}
