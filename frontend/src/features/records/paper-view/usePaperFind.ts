import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { pageText, type PdfPage, type TextRun } from "@/lib/pdf";
import { findMatches, firstMatchFrom, hitsOnPage, isSearchable, type FindHit } from "./findInPaper";
import type { FindStatus } from "./PaperFind";
import type { RegionBand } from "./readerGeometry";

/** Moves the reader to a band of a page, only if it is out of view. */
type LandOnMatch = (page: number, region: RegionBand) => void;

interface UsePaperFindOptions {
  ready: boolean;
  pages: PdfPage[];
  /** The page being read: where a first search starts from. */
  currentPage: number;
  /** The reader's whole pane, to know where focus returns to on close. */
  paneRef: RefObject<HTMLElement>;
  land: LandOnMatch;
}

/**
 * Find in this paper's state (IR-353): the query, each page's text as it is
 * extracted, the matches, which one is current, and moving between them.
 *
 * The text is pdf.js's own, extracted page by page in the browser. Typing
 * never waits on it: matches fill in as each page's text arrives, and a
 * query typed before its first match exists goes there once it does.
 */
export function usePaperFind({ ready, pages, currentPage, paneRef, land }: UsePaperFindOptions) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  /** Each page's text, or `undefined` until it is extracted. */
  const [texts, setTexts] = useState<(TextRun[] | undefined)[]>([]);
  /** The current match, as an index into `matches`. */
  const [active, setActive] = useState(0);
  /** Bumped for every move to a match: what lands the reader on it. */
  const [moves, setMoves] = useState(0);
  /** The query changed, and its first match is still to be gone to. */
  const jumpPendingRef = useRef(false);
  /** The page of the match find last went to: where a refined query starts. */
  const lastPageRef = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  // Read when a move lands, not a reason to land: the reader makes a new
  // one every render.
  const landRef = useRef(land);
  landRef.current = land;

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setTexts(pages.map(() => undefined));
    (async () => {
      for (let i = 0; i < pages.length; i += 1) {
        let runs: TextRun[];
        try {
          runs = await pageText(pages[i]);
        } catch {
          // A page pdf.js cannot read text from is searched as empty.
          runs = [];
        }
        if (cancelled) return;
        setTexts((previous) => {
          const next = [...previous];
          next[i] = runs;
          return next;
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, pages]);

  const matches = useMemo(() => findMatches(texts, query), [texts, query]);
  const activeIndex = Math.min(active, matches.length - 1);
  const extracting = texts.length < pages.length || texts.some((runs) => runs === undefined);
  const searchable = extracting || isSearchable(texts as TextRun[][]);

  // A new query goes to its first match from where find last was, or from
  // the page being read.
  useEffect(() => {
    if (!jumpPendingRef.current || matches.length === 0) return;
    jumpPendingRef.current = false;
    setActive(firstMatchFrom(matches, lastPageRef.current ?? currentPage));
    setMoves((n) => n + 1);
    // `currentPage` is read, not a trigger: reading on does not move find.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matches]);

  useEffect(() => {
    const match = matches[activeIndex];
    if (moves === 0 || !match) return;
    lastPageRef.current = match.page;
    landRef.current(match.page, match.region);
    // Only a move to a match lands, not later matches filling in behind it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moves]);

  /** Each page's hits while find is open; a page with none is absent. */
  const hitsByPage = useMemo(() => {
    const byPage = new Map<number, FindHit[]>();
    if (!open) return byPage;
    for (const page of new Set(matches.map((match) => match.page))) {
      byPage.set(page, hitsOnPage(matches, page, activeIndex));
    }
    return byPage;
  }, [open, matches, activeIndex]);

  let status: FindStatus;
  if (!searchable) status = { kind: "no-text" };
  else if (query.trim() === "") status = { kind: "idle" };
  else if (matches.length > 0)
    status = { kind: "found", current: activeIndex + 1, total: matches.length, searching: extracting };
  else status = extracting ? { kind: "searching" } : { kind: "none" };

  const openFind = () => {
    if (!open) {
      const focused = document.activeElement;
      returnFocusRef.current =
        focused instanceof HTMLElement && paneRef.current?.contains(focused) ? focused : null;
      setOpen(true);
    }
    // Once the bar is in the document; selected, so a second Ctrl+F types
    // over the last query as a browser's find does.
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  };

  const closeFind = () => {
    setOpen(false);
    setQuery("");
    setActive(0);
    lastPageRef.current = null;
    jumpPendingRef.current = false;
    const back = returnFocusRef.current;
    (back?.isConnected ? back : toggleRef.current)?.focus();
  };

  const changeQuery = (next: string) => {
    setQuery(next);
    jumpPendingRef.current = true;
  };

  const step = (by: 1 | -1) => {
    if (matches.length === 0) return;
    setActive((activeIndex + by + matches.length) % matches.length);
    setMoves((n) => n + 1);
  };

  /**
   * Ctrl/Cmd+F while the reader has focus finds in the paper: the
   * browser's own find cannot see text drawn on a canvas, and could not
   * scroll the reader's pane to what it found. Esc anywhere in the reader
   * closes it.
   */
  const onReaderKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!ready) return;
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      openFind();
    } else if (event.key === "Escape" && open && !event.defaultPrevented) {
      event.preventDefault();
      closeFind();
    }
  };

  return {
    open,
    query,
    status,
    hitsByPage,
    inputRef,
    toggleRef,
    openFind,
    closeFind,
    changeQuery,
    next: () => step(1),
    previous: () => step(-1),
    onReaderKeyDown,
  };
}
