import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import type { ReviewComment } from "@/types/records";

import { groupThreads } from "./threadModel";

/**
 * The review threads the viewer may see (IR-875): every sent one and their own
 * drafts, read from `GET /records/<id>/review-comments/`, and read again after
 * anything changes them. The workspace holds one of these, so the Threads tab
 * and the reader's pins agree.
 *
 * Live (ADR-073, IR-1284): someone else's comment, reply or thread act on this
 * record publishes `record:<id>` to everyone who may read the review, and the
 * list is read again quietly -- also on reconnect and when the tab is shown.
 * A quiet read that fails keeps the list already shown; only a first load or
 * an explicit reload reports "could not load".
 */
export function useReviewThreads(recordId: number, enabled: boolean) {
  const [comments, setComments] = useState<ReviewComment[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const quiet = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const isQuiet = quiet.current;
    quiet.current = false;
    if (!isQuiet) setFailed(false);
    // Through a promise, so a failure of any kind lands in `catch`.
    Promise.resolve()
      .then(() => recordsApi.reviewComments(recordId))
      .then(({ data }) => {
        if (cancelled) return;
        // A shape we don't know degrades to "could not load", never a throw (F1).
        if (Array.isArray(data)) {
          setComments(data);
          setFailed(false);
        } else if (!isQuiet) setFailed(true);
      })
      .catch(() => {
        if (!cancelled && !isQuiet) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, enabled, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const refreshQuietly = useCallback(() => {
    quiet.current = true;
    setAttempt((n) => n + 1);
  }, []);
  useLiveRefresh([`record:${recordId}`], refreshQuietly, enabled && comments !== null);

  const grouped = useMemo(() => groupThreads(comments ?? []), [comments]);

  return { loaded: comments !== null, failed, ...grouped, reload };
}

export type ReviewThreadsState = ReturnType<typeof useReviewThreads>;
