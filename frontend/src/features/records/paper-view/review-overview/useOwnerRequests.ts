import { useCallback, useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { errorDetail } from "@/lib/errorDetail";
import type { DocumentRequest } from "@/types/records";

/**
 * The document requests an owner is shown (IR-262, ADR-022 §3): every open
 * one, and one they fulfil during this visit, so the last upload visibly lands
 * somewhere. A withdrawn request is never shown (IR-263).
 *
 * A first read that fails is `failed`: an empty list would read as "nothing
 * required". A refresh that fails keeps the list on screen and is
 * `refreshFailed`, so an upload still running in a row stays in view (IR-471).
 */
export function useOwnerRequests(recordId: number, enabled: boolean) {
  const [requests, setRequests] = useState<DocumentRequest[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [refreshFailed, setRefreshFailed] = useState<string | null>(null);
  const hasList = useRef(false);
  /** Ids of requests seen open since this mounted. */
  const seenOpen = useRef<Set<number>>(new Set());

  const load = useCallback(async (quiet = false) => {
    try {
      const { data } = await recordsApi.documentRequests(recordId);
      data.filter((r) => r.state === "open").forEach((r) => seenOpen.current.add(r.id));
      hasList.current = true;
      setRequests(data);
      setFailed(null);
      setRefreshFailed(null);
    } catch (error) {
      if (quiet && hasList.current) return;
      if (hasList.current) {
        setRefreshFailed(errorDetail(error, "Could not refresh the documents reviewers asked for. Reload the page to see the latest."));
      } else {
        setFailed(errorDetail(error, "Could not load the documents reviewers asked for. Reload the page to try again."));
      }
    }
  }, [recordId]);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);
  useLiveRefresh([`record:${recordId}`], () => { void load(true); }, enabled);

  const shown = (requests ?? []).filter(
    (r) => r.state === "open" || (r.state === "fulfilled" && seenOpen.current.has(r.id)),
  );
  return { shown, failed, refreshFailed, reload: load };
}
