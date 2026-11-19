import { useEffect, useRef } from "react";
import { onLiveHint, onLiveResync } from "@/lib/live";

/** Bursts of hints within this window refetch once (ADR-073 decision 8). */
export const LIVE_COALESCE_MS = 500;

/**
 * Run `reload` when a hint names one of `topics`, when the live stream
 * reconnects, or when the tab is shown again (ADR-073 decisions 6 and 8).
 *
 * `reload` should refetch what the page already shows, quietly: no spinner,
 * no reset of what the reader is doing. Pass `enabled: false` to pause it.
 */
export function useLiveRefresh(topics: readonly string[], reload: () => void, enabled = true): void {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const key = topics.join("|");

  useEffect(() => {
    if (!enabled || !key) return;
    const wanted = new Set(key.split("|"));
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = undefined; reloadRef.current(); }, LIVE_COALESCE_MS);
    };
    const offHint = onLiveHint((hint) => { if (hint.some((topic) => wanted.has(topic))) schedule(); });
    const offResync = onLiveResync(schedule);
    const onShown = () => { if (document.visibilityState === "visible") schedule(); };
    window.addEventListener("focus", onShown);
    document.addEventListener("visibilitychange", onShown);
    return () => {
      if (timer) clearTimeout(timer);
      offHint();
      offResync();
      window.removeEventListener("focus", onShown);
      document.removeEventListener("visibilitychange", onShown);
    };
  }, [key, enabled]);
}
