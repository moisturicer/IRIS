import { isAxiosError } from "axios";
import { useCallback, useEffect, useRef, useState } from "react";

import { libraryApi, type HighlightEntry } from "@/api/library";

import type { Passage } from "./threads/passage";

/** A highlight the reader may read now: the unavailable kind never reaches this page. */
export type ReadableHighlight = Extract<HighlightEntry, { available: true }>;

export type HighlightsPhase = "idle" | "loading" | "ready" | "load_failed";

/** What the last save said, in words the reader can act on. */
export interface HighlightNotice {
  kind: "saved" | "failed" | "changed" | "unidentified";
  text: string;
}

export interface ReadingHighlightsState {
  phase: HighlightsPhase;
  /** Newest first, as the server lists them. */
  items: ReadableHighlight[];
  notice: HighlightNotice | null;
  /** The highlight whose removal last failed, so it can say so beside itself. */
  removeFailed: number | null;
  /** Save the selected passage, with the revision the paper was opened at. */
  save: (passage: Passage, manuscriptRevision: string | null) => Promise<void>;
  remove: (id: number) => Promise<void>;
  reload: () => void;
  dismissNotice: () => void;
}

/** How long a save's message stays up before it clears itself. */
export const NOTICE_MS = 6000;

const isReadable = (entry: HighlightEntry): entry is ReadableHighlight => entry.available;

/**
 * The reader's highlights on one Record (IR-583, ADR-065), held by the page so
 * the reader draws them and Notes lists them from one place.
 *
 * Two rules matter here. **A highlight is never saved without the revision the
 * paper was opened at**: with none, nothing is sent, because the server could
 * only guess which bytes it was made on. And **a replaced paper saves nothing**:
 * the server's `409 manuscript_changed` is shown as such rather than retried.
 * Nothing is read from or kept in `localStorage` (ADR-044 §7).
 */
export function useReadingHighlights(recordId: number, enabled: boolean): ReadingHighlightsState {
  const [phase, setPhase] = useState<HighlightsPhase>("idle");
  const [items, setItems] = useState<ReadableHighlight[]>([]);
  const [notice, setNotice] = useState<HighlightNotice | null>(null);
  const [removeFailed, setRemoveFailed] = useState<number | null>(null);
  const [loadTry, setLoadTry] = useState(0);
  // A different Record is a different list: a result for the one left is dropped.
  const gen = useRef(0);

  useEffect(() => {
    gen.current += 1;
    setPhase("idle");
    setItems([]);
    setNotice(null);
    setRemoveFailed(null);
  }, [recordId]);

  useEffect(() => {
    if (!enabled) return;
    const mine = gen.current;
    setPhase("loading");
    libraryApi
      .highlights(recordId)
      .then(({ data }) => {
        if (mine !== gen.current) return;
        setItems((data.results ?? []).filter(isReadable));
        setPhase("ready");
      })
      .catch(() => {
        if (mine === gen.current) setPhase("load_failed");
      });
  }, [enabled, recordId, loadTry]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const save = useCallback(
    async (passage: Passage, manuscriptRevision: string | null) => {
      if (manuscriptRevision === null) {
        setNotice({
          kind: "unidentified",
          text: "This paper can't be highlighted yet: its file has no recorded identity to tie the highlight to.",
        });
        return;
      }
      const mine = gen.current;
      try {
        const { data } = await libraryApi.saveHighlight(recordId, {
          manuscript_revision: manuscriptRevision,
          page: passage.page,
          quote: passage.quote,
          prefix: passage.prefix,
          suffix: passage.suffix,
          regions: passage.regions,
        });
        if (mine !== gen.current || !isReadable(data)) return;
        setItems((previous) => [data, ...previous.filter((h) => h.id !== data.id)]);
        setNotice({ kind: "saved", text: "Highlight saved." });
      } catch (err) {
        if (mine !== gen.current) return;
        const changed =
          isAxiosError(err) && err.response?.status === 409 &&
          (err.response.data as { code?: string } | undefined)?.code === "manuscript_changed";
        setNotice(
          changed
            ? {
                kind: "changed",
                text: "This paper was replaced while you were reading, so nothing was saved. Reload it, then select the passage again.",
              }
            : { kind: "failed", text: "Could not save the highlight. Select the passage and try again." },
        );
      }
    },
    [recordId],
  );

  const remove = useCallback(
    async (id: number) => {
      const mine = gen.current;
      setRemoveFailed(null);
      try {
        await libraryApi.deleteHighlight(recordId, id);
        if (mine === gen.current) setItems((previous) => previous.filter((h) => h.id !== id));
      } catch {
        if (mine === gen.current) setRemoveFailed(id);
      }
    },
    [recordId],
  );

  return {
    phase, items, notice, removeFailed, save, remove,
    reload: () => setLoadTry((n) => n + 1),
    dismissNotice: () => setNotice(null),
  };
}
