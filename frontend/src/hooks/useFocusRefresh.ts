import { useCallback, useEffect, useRef } from "react";

/** Bursts of reasons to reload within this window reload once (ADR-073 decision 8). */
export const REFRESH_COALESCE_MS = 500;

/**
 * `schedule` runs `reload` once, about 500 ms after the last call; `cancel`
 * drops a pending run. Both are stable, and a pending run is dropped on unmount.
 */
export function useCoalescedReload(reload: () => void): { schedule: () => void; cancel: () => void } {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const cancel = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = undefined;
  }, []);
  const schedule = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { timer.current = undefined; reloadRef.current(); }, REFRESH_COALESCE_MS);
  }, []);
  useEffect(() => cancel, [cancel]);

  return { schedule, cancel };
}

/** Call `onShown` whenever the tab is shown again: the window gains focus, or the page becomes visible. */
export function useTabShown(onShown: () => void, enabled = true): void {
  const onShownRef = useRef(onShown);
  onShownRef.current = onShown;

  useEffect(() => {
    if (!enabled) return;
    const handler = () => { if (document.visibilityState === "visible") onShownRef.current(); };
    window.addEventListener("focus", handler);
    document.addEventListener("visibilitychange", handler);
    return () => {
      window.removeEventListener("focus", handler);
      document.removeEventListener("visibilitychange", handler);
    };
  }, [enabled]);
}

/**
 * Run `reload` when the tab is shown again, and never on a live hint
 * (ADR-073 amendment 2026-11-28, IR-1351). For pages that show what other
 * people change but nobody acts on together, or that change on almost every
 * act: they are current whenever someone looks again, without a hint making
 * every open tab read.
 *
 * `reload` should refetch what the page already shows, quietly: no spinner,
 * and the reader's filters, page and scroll stay. Pass `enabled: false` to pause it.
 */
export function useFocusRefresh(reload: () => void, enabled = true): void {
  const { schedule, cancel } = useCoalescedReload(reload);
  useTabShown(schedule, enabled);
  useEffect(() => { if (!enabled) cancel(); }, [enabled, cancel]);
}
