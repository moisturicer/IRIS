import { useCallback, useEffect, useRef, useState } from "react";

import { libraryApi } from "@/api/library";
import { useAuthStore } from "@/store/auth.store";

import type { ReadingAnchor } from "./readerGeometry";

/** A save waits until the reader has been still this long... */
export const SAVE_AFTER_MS = 1500;
/** ...but no longer than this while they keep moving: the debounce is bounded. */
export const SAVE_AT_MOST_MS = 10_000;

/** Where a paper opens with nothing put back: the top of its first page. */
const START: ReadingAnchor = { page: 1, fraction: 0 };

/** Four places of a page's height: well under a pixel at any zoom the reader allows. */
const round = (fraction: number) => Math.round(fraction * 10_000) / 10_000;

const same = (a: ReadingAnchor | null, b: ReadingAnchor | null) =>
  a !== null && b !== null && a.page === b.page && round(a.fraction) === round(b.fraction);

interface ReadingResumeOptions {
  recordId: number;
  /** Whether this reader keeps a place at all: only the current paper does. */
  enabled: boolean;
  /** A citation, a highlight or `?page=` is landing. It wins over resuming. */
  explicitLanding: boolean;
  /** The revision the server said the bytes shown are; without one, nothing is kept. */
  revision: string | null;
  /** The document is open, so `pageCount` is known. */
  ready: boolean;
  pageCount: number;
}

export interface ReadingResume {
  /** Where to put the reader back, once that page is painted; null when nothing waits. */
  target: ReadingAnchor | null;
  /** The reader is at `target` now. */
  landed: () => void;
  /** Where the reader is, each time the reader measures it. Stable. */
  report: (anchor: ReadingAnchor) => void;
}

type Stored = (ReadingAnchor & { revision: string }) | null;

/**
 * The reader's place in a paper, kept on their account (IR-573).
 *
 * On opening, it asks where they left off. The place is put back only if it
 * was read on the very bytes shown (`revision`), no explicit landing is under
 * way, and the reader has not moved first; otherwise the paper opens as it
 * would have. Either way nothing is saved until the reader moves, so a failed
 * read never overwrites a place with page 1.
 *
 * After that, where they are is saved `SAVE_AFTER_MS` after they stop, at most
 * `SAVE_AT_MOST_MS` apart while they keep going, and at once when they leave:
 * the page is hidden or the reader unmounts. A save started in one session is
 * never sent in the next (`sessionEpoch`), a refused one (the paper was
 * replaced, or can no longer be read) stops saving, and any failure leaves the
 * reader as it was.
 */
export function useReadingResume({
  recordId,
  enabled,
  explicitLanding,
  revision,
  ready,
  pageCount,
}: ReadingResumeOptions): ReadingResume {
  // Asked only when the paper opened with nothing else to land on.
  const [asks] = useState(() => enabled && !explicitLanding);
  const [stored, setStored] = useState<Stored | undefined>(asks ? undefined : null);
  const [settled, setSettled] = useState(!asks);

  const epoch = useRef(useAuthStore.getState().sessionEpoch);
  const sameSession = () => useAuthStore.getState().sessionEpoch === epoch.current;

  /** Where the reader was before they moved: the start, or the place put back. */
  const baseline = useRef<ReadingAnchor>(START);
  const latest = useRef<ReadingAnchor | null>(null);
  const saved = useRef<ReadingAnchor | null>(null);
  const refused = useRef(false);
  const timer = useRef<number | null>(null);
  const pendingSince = useRef<number | null>(null);

  // Read by the stable callbacks below, so they see this render's values.
  const live = useRef({ recordId, enabled, revision, settled });
  live.current = { recordId, enabled, revision, settled };

  useEffect(() => {
    if (!asks) return;
    let current = true;
    libraryApi.position(recordId).then(
      ({ data }) => {
        if (!current || !sameSession()) return;
        // Anything but a well-formed place opens the paper at its start.
        const p = data?.position;
        const valid =
          p && Number.isInteger(p.page) && p.page >= 1 && typeof p.fraction === "number"
          && p.fraction >= 0 && p.fraction <= 1 && typeof p.manuscript_revision === "string";
        setStored(valid ? { page: p.page, fraction: p.fraction, revision: p.manuscript_revision } : null);
      },
      () => {
        if (current) setStored(null);
      },
    );
    return () => {
      current = false;
    };
    // The reader remounts for another Record or session; one ask per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const putBack =
    !settled && enabled && !explicitLanding && ready && stored && stored.revision === revision && stored.page <= pageCount
      ? stored
      : null;

  // Nothing to put back, or something else came first: the paper stays where it is.
  const gaveUp =
    !settled && (!enabled || explicitLanding || stored === null || (ready && stored !== undefined && putBack === null));
  useEffect(() => {
    if (gaveUp) setSettled(true);
  }, [gaveUp]);

  const flush = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
    pendingSince.current = null;
    const { recordId: id, enabled: keeps, revision: shown, settled: open } = live.current;
    const at = latest.current;
    if (!keeps || !open || !shown || !at || refused.current || !sameSession()) return;
    if (same(at, saved.current ?? baseline.current)) return;
    saved.current = at;
    libraryApi.savePosition(id, { manuscript_revision: shown, page: at.page, fraction: round(at.fraction) }).catch(
      (error: { response?: { status?: number } }) => {
        // Replaced while open, or no longer readable: no more places are taken.
        const code = error?.response?.status;
        if (code === 409 || code === 404) refused.current = true;
        else saved.current = null;
      },
    );
    // `live` and the refs are read at call time, so it never changes.
  }, []);

  const schedule = useCallback(() => {
    const now = Date.now();
    pendingSince.current ??= now;
    if (timer.current !== null) window.clearTimeout(timer.current);
    const wait = Math.max(0, Math.min(SAVE_AFTER_MS, SAVE_AT_MOST_MS - (now - pendingSince.current)));
    timer.current = window.setTimeout(flush, wait);
  }, [flush]);

  const report = useCallback(
    (anchor: ReadingAnchor) => {
      latest.current = anchor;
      if (!live.current.settled) {
        if (same(anchor, START)) return;
        // The reader moved before their place came back: theirs wins, and is kept.
        live.current.settled = true;
        setSettled(true);
      }
      if (!same(anchor, saved.current ?? baseline.current)) schedule();
    },
    [schedule],
  );

  const landed = useCallback(() => {
    if (putBack) baseline.current = { page: putBack.page, fraction: putBack.fraction };
    setSettled(true);
  }, [putBack]);

  // Leaving saves at once: hiding the tab, closing it, or leaving the paper.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") flush();
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [flush]);

  return { target: putBack ? { page: putBack.page, fraction: putBack.fraction } : null, landed, report };
}
