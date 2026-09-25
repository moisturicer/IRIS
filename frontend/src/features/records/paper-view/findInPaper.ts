/**
 * Find in this paper's matching (IR-353), kept apart from the reader so it
 * can be tested without pdf.js or layout.
 *
 * It searches the text pdf.js extracts from the paper itself, in the
 * browser. Not the backend's chunk text: that exists only for indexed
 * records, which on a live deployment is none yet (IR-250).
 */
import type { TextRun } from "@/lib/pdf";

/** Part of one run a match covers: characters `start` to `end` of its string. */
export interface MatchPiece {
  run: number;
  start: number;
  end: number;
}

export interface FindMatch {
  /** 1-based, like the reader's pages. */
  page: number;
  /** In reading order; more than one when a match crosses runs or lines. */
  pieces: MatchPiece[];
  /** The band of the page the match occupies, as fractions of its height. */
  region: { top: number; bottom: number };
}

/** One match to highlight on a page, as the page's text layer paints it. */
export interface FindHit {
  pieces: MatchPiece[];
  current: boolean;
}

const WHITESPACE = /\s/;

/** How a query is compared: trimmed, lowercased, whitespace collapsed. */
function normalize(query: string): string {
  return query.trim().replace(/\s+/g, " ").toLowerCase();
}

/**
 * A page's text as find reads it, with each character traced back to the
 * run and offset it came from, so a match can be highlighted in place.
 *
 * Runs are joined as they are laid out, a line's end reads as a space, and
 * any stretch of whitespace as one -- so a phrase that wraps, or that the
 * PDF spaced out, is still found.
 */
function pageIndex(runs: TextRun[]) {
  let text = "";
  const origin: { run: number; offset: number }[] = [];
  const push = (chars: string, run: number, offset: number) => {
    for (const char of chars) {
      text += char;
      origin.push({ run, offset });
    }
  };
  runs.forEach((run, index) => {
    for (let offset = 0; offset < run.str.length; offset += 1) {
      const char = run.str[offset];
      if (WHITESPACE.test(char)) {
        if (text !== "" && !text.endsWith(" ")) push(" ", index, offset);
      } else {
        push(char.toLowerCase(), index, offset);
      }
    }
    if (run.eol && text !== "" && !text.endsWith(" ")) push(" ", index, run.str.length);
  });
  return { text, origin };
}

/** The runs and characters behind `text[from..to)`, one piece per run. */
function piecesFor(origin: { run: number; offset: number }[], from: number, to: number): MatchPiece[] {
  const pieces: MatchPiece[] = [];
  for (let i = from; i < to; i += 1) {
    const { run, offset } = origin[i];
    const last = pieces[pieces.length - 1];
    if (last && last.run === run) last.end = offset + 1;
    else pieces.push({ run, start: offset, end: offset + 1 });
  }
  return pieces;
}

/**
 * Every match of `query` in the paper, in reading order. `pages` holds each
 * page's runs, or `undefined` for a page not extracted yet -- which is
 * skipped, so the search fills in as extraction finishes.
 */
export function findMatches(pages: (TextRun[] | undefined)[], query: string): FindMatch[] {
  const needle = normalize(query);
  if (needle === "") return [];

  const matches: FindMatch[] = [];
  pages.forEach((runs, index) => {
    if (!runs) return;
    const { text, origin } = pageIndex(runs);
    for (let at = text.indexOf(needle); at !== -1; at = text.indexOf(needle, at + needle.length)) {
      // A line-end space carries an offset past its run's text; it is never
      // drawn, so it is left out of what is highlighted.
      const pieces = piecesFor(origin, at, at + needle.length)
        .map((piece) => ({ ...piece, end: Math.min(piece.end, runs[piece.run].str.length) }))
        .filter((piece) => piece.end > piece.start);
      const covered = pieces.map((piece) => runs[piece.run]);
      matches.push({
        page: index + 1,
        pieces,
        region: {
          top: Math.min(...covered.map((run) => run.top)),
          bottom: Math.max(...covered.map((run) => run.bottom)),
        },
      });
    }
  });
  return matches;
}

/**
 * Where find starts: the first match on or after the page being read, as a
 * browser's find does from where the reader is, wrapping to the first.
 */
export function firstMatchFrom(matches: FindMatch[], page: number): number {
  const index = matches.findIndex((match) => match.page >= page);
  return index === -1 ? 0 : index;
}

/** The matches on `page`, with the one at `current` (an index into `matches`) marked. */
export function hitsOnPage(matches: FindMatch[], page: number, current: number): FindHit[] {
  const hits: FindHit[] = [];
  matches.forEach((match, index) => {
    if (match.page === page) hits.push({ pieces: match.pieces, current: index === current });
  });
  return hits;
}

/**
 * Whether the paper has any text to search. A scanned PDF has none, and
 * says so, rather than answering every query with "no matches".
 */
export function isSearchable(pages: TextRun[][]): boolean {
  return pages.some((runs) => runs.some((run) => run.str.trim() !== ""));
}
