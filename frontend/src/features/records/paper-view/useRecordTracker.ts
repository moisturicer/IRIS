import { useCallback, useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import { isRequestTimeout } from "@/api/requestPolicy";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import type { RecordTracker } from "@/types/records";

/**
 * `GET /records/<id>/tracker/`, read again live (ADR-073, IR-1287) and
 * whenever `version` changes. Both re-reads are quiet: what is shown stays,
 * and stays if the read fails. `failed` says why a first read failed (IR-906).
 */
export function useRecordTracker(recordId: number, version = 0) {
  const [data, setData] = useState<RecordTracker | null>(null);
  const [failed, setFailed] = useState<"failed" | "interrupted" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const quiet = useRef(false);
  const read = useRef<{ recordId: number; version: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const bumped = read.current?.recordId === recordId && read.current.version !== version;
    read.current = { recordId, version };
    const isQuiet = quiet.current || bumped;
    quiet.current = false;
    if (!isQuiet) {
      setData(null);
      setFailed(null);
    }
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (cancelled) return;
        setData(payload);
        setFailed(null);
      })
      .catch((error: unknown) => {
        if (!cancelled && !isQuiet) setFailed(isRequestTimeout(error) ? "interrupted" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, version, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const reloadQuietly = useCallback(() => {
    quiet.current = true;
    setAttempt((n) => n + 1);
  }, []);
  useLiveRefresh([`record:${recordId}`], reloadQuietly);

  return { data, failed, retry };
}
