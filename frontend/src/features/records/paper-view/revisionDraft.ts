/**
 * A reviewer's unsent revision request, kept across a navigation (IR-272,
 * carrying IR-143's criterion: opening a document does not lose it).
 *
 * The same reasoning as `officeReviewDraft.ts`: the dialog is modal, closing
 * it to read the paper unmounts the form, and `sessionStorage` keeps the
 * reason for this tab only. One draft per record. Every access is guarded.
 */
const KEY_PREFIX = "iris_revision_draft:";

export function readRevisionDraft(recordId: number): string {
  try {
    return sessionStorage.getItem(`${KEY_PREFIX}${recordId}`) ?? "";
  } catch {
    return "";
  }
}

/** Keep this reason, or forget it once it is blank again. */
export function writeRevisionDraft(recordId: number, reason: string): void {
  try {
    if (reason.trim() === "") sessionStorage.removeItem(`${KEY_PREFIX}${recordId}`);
    else sessionStorage.setItem(`${KEY_PREFIX}${recordId}`, reason);
  } catch {
    // Storage refused or full: the reviewer keeps typing either way.
  }
}

/** Forget it -- once the request is actually made. */
export function clearRevisionDraft(recordId: number): void {
  writeRevisionDraft(recordId, "");
}
