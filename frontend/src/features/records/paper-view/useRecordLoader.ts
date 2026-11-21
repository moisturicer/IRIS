import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { publishHref } from "@/features/publish/publishLink";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { pathFor } from "@/lib/access";
import { readFailureKind } from "@/lib/readFailure";
import { useHistoryStore } from "@/store/history.store";
import type { RecordDetail } from "@/types/records";

/**
 * Where loading the Record stands.
 *
 * - `loading`: a load is in flight. `record` may still hold the previous
 *   Record, so moving between Records keeps the page (IR-355).
 * - `ready`: `record` is the loaded Record.
 * - `failed` / `interrupted`: the last load failed for a reason other than
 *   "no such record" (an error, or no answer in time).
 * - `not_found`: missing or refused alike (IR-153). This includes a Record
 *   that became unreadable on a reload (IR-906).
 */
export type RecordLoadStatus = "loading" | "ready" | "failed" | "interrupted" | "not_found";

export interface RecordLoader {
  record: RecordDetail | null;
  status: RecordLoadStatus;
  /** The error behind `failed`, for the failure message. */
  error: unknown;
  /** Try again after a failed load. Not a second visit, so not counted again. */
  retry: () => void;
  /** Re-read the Record after something changed. A failure keeps the page as it is. */
  reload: () => Promise<void>;
  /** Replace the Record with one a save or a refresh returned. */
  replace: (record: RecordDetail) => void;
}

/**
 * Loads Paper View's Record and keeps it fresh (IR-1268, moved out of the
 * page unchanged): the first load and its outcomes, Try again, the single
 * access count per visit, the reader's history entry, reloads after a change,
 * and the live refresh on the Record's channel (ADR-073).
 */
export function useRecordLoader(id: string | undefined): RecordLoader {
  const navigate = useNavigate();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState<"failed" | "interrupted" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loadError, setLoadError] = useState<unknown>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    recordsApi
      .detail(Number(id))
      .then(({ data }) => {
        // A draft is not a paper page (IR-1227, ADR-009 decision 6). Only its
        // owner loads one, and opening it is opening the Publish form at the
        // step they left off -- an old `?section=review` link included -- over
        // My Library, where the draft lives, not Discover (IR-1258).
        if (data.pipeline_status === "draft") {
          navigate(publishHref({ pathname: pathFor("library"), search: "" }, data.id), { replace: true });
          return;
        }
        setRecord(data);
        setLoadFailed(null);
        // access_count is a global counter, so it cannot answer "what have I
        // read?". The reader's history is recorded here, on their account, by
        // an explicit call (IR-756): reading the Record above records nothing,
        // and a paused history sends nothing at all.
        void useHistoryStore.getState().recordVisit(data.id);
      })
      // A 404 is a missing record and a refused one alike (IR-153): the API
      // never says which, so neither does this page, and a 403 reads the same.
      // Any other failure is not "not found", and says so with a way to try again.
      .catch((err: unknown) => {
        const kind = readFailureKind(err);
        setLoadError(err);
        setRecord(null);
        setLoadFailed(kind === "unavailable" ? null : kind);
      })
      .finally(() => setLoading(false));
    if (attempt === 0) recordsApi.incrementAccess(Number(id)).catch(() => {});
    // `attempt` is Try again; a retry is not a second visit to count.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, attempt]);

  /**
   * Re-read the record after something changed -- the viewer's download state
   * (IR-677), a document request. A failure leaves the page as
   * it was, except one that means the viewer can no longer read the record
   * (revoked while it was open, IR-906): that becomes the same not-available
   * screen as a record that never existed.
   */
  const reload = async () => {
    if (!id) return;
    try {
      const { data } = await recordsApi.detail(Number(id));
      setRecord(data);
    } catch (err) {
      if (readFailureKind(err) === "unavailable") setRecord(null);
      // Otherwise the control keeps its last state; a reload catches up.
    }
  };
  // Live updates (ADR-073): this paper changed for someone who may see it.
  useLiveRefresh(id ? [`record:${id}`] : [], () => { void reload(); });

  const status: RecordLoadStatus = loading
    ? "loading"
    : record
      ? "ready"
      : (loadFailed ?? "not_found");

  return {
    record,
    status,
    error: loadError,
    retry: () => setAttempt((n) => n + 1),
    reload,
    replace: setRecord,
  };
}
