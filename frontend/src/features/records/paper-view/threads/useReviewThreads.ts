import { useCallback, useEffect, useMemo, useState } from "react";

import { recordsApi } from "@/api/records";
import type { ReviewComment } from "@/types/records";

import { groupThreads } from "./threadModel";

/**
 * The review threads the viewer may see (IR-875): every sent one and their own
 * drafts, read from `GET /records/<id>/review-comments/`, and read again after
 * anything changes them. The workspace holds one of these, so the Threads tab
 * and the reader's pins agree.
 */
export function useReviewThreads(recordId: number, enabled: boolean) {
  const [comments, setComments] = useState<ReviewComment[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setFailed(false);
    // Through a promise, so a failure of any kind lands in `catch`.
    Promise.resolve()
      .then(() => recordsApi.reviewComments(recordId))
      .then(({ data }) => {
        if (!cancelled) setComments(data);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, enabled, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const grouped = useMemo(() => groupThreads(comments ?? []), [comments]);

  return { loaded: comments !== null, failed, ...grouped, reload };
}

export type ReviewThreadsState = ReturnType<typeof useReviewThreads>;
