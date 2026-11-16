import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";

/** What a failed act on a Call means, and how to say it (IR-765). */
export interface CallFailure {
  message: string;
  /**
   * The Call changed, was decided, or is gone since the screen read it (a
   * 409 or a 404). Trying the same act again can't work: the screen reloads
   * and says the server's words instead.
   */
  stale: boolean;
}

/**
 * Read a failed act on a Call. A stale decision shows the server's own
 * refusal ("This call was changed after you opened it…") rather than
 * pretending it worked; anything else says what failed, led by `lead`.
 */
export function callFailure(err: unknown, lead: string): CallFailure {
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  if (status === 409) return { stale: true, message: errorDetail(err, `${lead} The call changed since you opened it.`) };
  if (status === 404) return { stale: true, message: `${lead} The call is no longer there.` };
  return { stale: false, message: failureMessage(err, { lead }) };
}
