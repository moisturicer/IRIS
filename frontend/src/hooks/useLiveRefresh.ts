import { useEffect } from "react";
import { onLiveHint, onLiveResync } from "@/lib/live";
import { REFRESH_COALESCE_MS, useCoalescedReload, useTabShown } from "./useFocusRefresh";

/** Bursts of hints within this window refetch once (ADR-073 decision 8). */
export const LIVE_COALESCE_MS = REFRESH_COALESCE_MS;

/**
 * Run `reload` when a hint names one of `topics`, when the live stream
 * reconnects, or when the tab is shown again (ADR-073 decisions 6 and 8).
 * The tab-shown half is `useFocusRefresh`'s (IR-1351), so the two can't drift
 * apart, and all three reasons share one coalescing timer.
 *
 * `reload` should refetch what the page already shows, quietly: no spinner,
 * no reset of what the reader is doing. Pass `enabled: false` to pause it.
 */
export function useLiveRefresh(topics: readonly string[], reload: () => void, enabled = true): void {
  const key = topics.join("|");
  const active = enabled && Boolean(key);
  const { schedule, cancel } = useCoalescedReload(reload);
  useTabShown(schedule, active);

  useEffect(() => {
    if (!active) return;
    const wanted = new Set(key.split("|"));
    const offHint = onLiveHint((hint) => { if (hint.some((topic) => wanted.has(topic))) schedule(); });
    const offResync = onLiveResync(schedule);
    return () => {
      cancel();
      offHint();
      offResync();
    };
  }, [key, active, schedule, cancel]);
}
