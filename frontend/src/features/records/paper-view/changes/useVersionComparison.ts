import { useCallback, useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import { errorDetail } from "@/lib/errorDetail";
import type { VersionComparisonPayload } from "@/types/records";

import { readComparison } from "./changesModel";

/** How often a comparison still being prepared is asked for again. */
export const PREPARING_POLL_MS = 3000;

export type ComparisonLoad =
  | { status: "loading" }
  | { status: "failed"; message: string }
  | { status: "loaded"; data: VersionComparisonPayload };

const FAILED = "Couldn't load the comparison. Please try again.";

/**
 * One comparison, fetched for the pair given (or the server's default pair
 * when none is), asked for again while it is still being prepared, and
 * dropped when the pair changes or the tab unmounts.
 */
export function useVersionComparison(recordId: number, pair: { from: number; to: number } | null) {
  const [load, setLoad] = useState<ComparisonLoad>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const timer = useRef<number | null>(null);
  const from = pair?.from ?? null;
  const to = pair?.to ?? null;

  useEffect(() => {
    const controller = new AbortController();
    const fetchOnce = () => {
      recordsApi.compareVersions(recordId, from != null && to != null ? { from, to } : undefined, { signal: controller.signal })
        .then(({ data }) => {
          const body = readComparison(data);
          if (!body) { setLoad({ status: "failed", message: FAILED }); return; }
          setLoad({ status: "loaded", data: body });
          if (body.state === "preparing") {
            timer.current = window.setTimeout(fetchOnce, PREPARING_POLL_MS);
          }
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          setLoad({ status: "failed", message: errorDetail(error, FAILED) });
        });
    };
    setLoad({ status: "loading" });
    fetchOnce();
    return () => {
      controller.abort();
      if (timer.current != null) window.clearTimeout(timer.current);
    };
  }, [recordId, from, to, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { load, retry };
}
