/**
 * A reviewer's unsent revision request, kept across a navigation (IR-272,
 * carrying IR-143's criterion: opening a document does not lose it).
 *
 * The same reasoning as `officeReviewDraft.ts`: the dialog is modal, closing
 * it to read the paper unmounts the form, and `sessionStorage` keeps the
 * reason for this tab only. One draft per user and record (IR-931). Every
 * access is guarded.
 */
const KEY_PREFIX = "iris_revision_draft:";

/** Who is signed in; none means nothing is read, written or cleared. */
type UserId = number | null | undefined;

function keyFor(userId: number, recordId: number): string {
  return `${KEY_PREFIX}${userId}:${recordId}`;
}

export function readRevisionDraft(userId: UserId, recordId: number): string {
  if (userId == null) return "";
  try {
    return sessionStorage.getItem(keyFor(userId, recordId)) ?? "";
  } catch {
    return "";
  }
}

/** Keep this reason, or forget it once it is blank again. */
export function writeRevisionDraft(userId: UserId, recordId: number, reason: string): void {
  if (userId == null) return;
  try {
    if (reason.trim() === "") sessionStorage.removeItem(keyFor(userId, recordId));
    else sessionStorage.setItem(keyFor(userId, recordId), reason);
  } catch {
    // Storage refused or full: the reviewer keeps typing either way.
  }
}

/** Forget it -- once the request is actually made. */
export function clearRevisionDraft(userId: UserId, recordId: number): void {
  writeRevisionDraft(userId, recordId, "");
}
