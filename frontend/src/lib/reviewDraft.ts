/**
 * The reviewer's unsent decision, kept across a navigation (IR-237).
 *
 * **Why this exists.** The evaluation screen's two links to the evidence used
 * to open new tabs, so that reading the documents could not unmount the form
 * and discard a typed clearance comment (IR-143). That cost the reviewer their
 * session — a new tab is a fresh browsing context and never receives the
 * `sessionStorage` the refresh token lives in — so the links navigate in-tab
 * now and this is what protects the comment instead. It protects strictly more:
 * an accidental back, a crash and a session expiry all used to lose the
 * comment even with the new tab.
 *
 * **`sessionStorage`, not `localStorage`, deliberately.** A half-written
 * clearance comment is somebody's unflattering opinion of somebody else's
 * thesis. It should not outlive the browser tab on a shared lab machine, and
 * since the navigation it has to survive is now in-tab, nothing is gained by
 * putting it on disk.
 */
import type { ReviewStatus } from "@/types/reviews";

export interface ReviewDraft {
  status: ReviewStatus;
  comment: string;
}

const KEY_PREFIX = "iris_review_draft:";

/** What the form starts as. A draft equal to this is not a draft. */
const DEFAULT_STATUS: ReviewStatus = "approved";

const VALID_STATUSES: readonly ReviewStatus[] = ["approved", "declined", "rejected"];

function keyFor(recordId: string | number): string {
  return `${KEY_PREFIX}${recordId}`;
}

/**
 * Is this the untouched form?
 *
 * Persisting "approve, no comment" would mean every record the reviewer merely
 * *opened* has a draft, which makes the presence of a draft meaningless and
 * fills storage with nothing. A chosen decision counts as content even with no
 * comment yet — picking "Request Revision" is a judgement worth keeping.
 */
function isUntouched(draft: ReviewDraft): boolean {
  return draft.status === DEFAULT_STATUS && draft.comment.trim() === "";
}

/**
 * Narrow a parsed value to a draft.
 *
 * `sessionStorage` is editable from the console, so what comes back is checked
 * rather than trusted: a bad `status` must never arrive at the form as a
 * pre-selected decision.
 */
function asDraft(value: unknown): ReviewDraft | null {
  if (typeof value !== "object" || value === null) return null;

  const { status, comment } = value as { status?: unknown; comment?: unknown };
  if (typeof comment !== "string") return null;
  if (!VALID_STATUSES.includes(status as ReviewStatus)) return null;

  return { status: status as ReviewStatus, comment };
}

/** The draft for this record, or `null` if there is not a usable one. */
export function readReviewDraft(recordId: string | number): ReviewDraft | null {
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(keyFor(recordId));
  } catch {
    // Site data blocked, or a private window where the accessor itself throws.
    // Losing the draft is a shame; losing the form would be a defect.
    return null;
  }

  if (!raw) return null;

  try {
    return asDraft(JSON.parse(raw));
  } catch {
    return null;
  }
}

/** Record this draft, or drop it if the form is back to its untouched state. */
export function writeReviewDraft(recordId: string | number, draft: ReviewDraft): void {
  if (isUntouched(draft)) {
    clearReviewDraft(recordId);
    return;
  }

  try {
    sessionStorage.setItem(keyFor(recordId), JSON.stringify(draft));
  } catch {
    // Storage refused or is full. The reviewer keeps typing either way.
  }
}

/** Forget this record's draft — call once the review is actually submitted. */
export function clearReviewDraft(recordId: string | number): void {
  try {
    sessionStorage.removeItem(keyFor(recordId));
  } catch {
    // As above.
  }
}
