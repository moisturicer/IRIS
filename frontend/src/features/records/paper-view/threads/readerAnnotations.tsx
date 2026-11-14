/**
 * What the review workspace draws on the reader and asks of it (ADR-032 §7,
 * 2026-11-04; IR-875): each thread's highlight and numbered pin, a Comment
 * control armed by a selection or the current find match, and a thread to
 * land on.
 *
 * A context rather than reader props, because the page builds the reader and
 * hands it to the workspace as a node: whatever wraps it where it is rendered
 * provides this. Outside Review nothing does, and the reader is unchanged.
 */
import { createContext, useContext } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { PageRegion } from "@/types/records";

import type { Passage } from "./passage";

export interface ReaderMark {
  key:        string;
  /** "3", or "D1" for a draft. */
  pin:        string;
  /** The Version the passage was quoted from: drawn only on that Version. */
  version:    number;
  regions:    PageRegion[];
  /** The pin's accessible name, e.g. "Thread 3, ITSO, Must fix". */
  label:      string;
  /** A draft: the quiet pin. */
  pending:    boolean;
  /** The thread open in the Threads tab: its passage reads stronger (IR-1097). */
  open:       boolean;
  onActivate: () => void;
}

export interface ReaderAnnotations {
  /** The Version the reader shows when it is given none: the latest. */
  currentVersion: number | null;
  marks:          ReaderMark[];
  /** Comment on a passage of the Version shown; null where the viewer may not comment. */
  onComment:      ((passage: Passage, version: number) => void) | null;
  /** Bumped key: land the reader on this page's band. */
  landing:        { page: number; top: number; bottom: number; key: number } | null;
}

export const ReaderAnnotationsContext = createContext<ReaderAnnotations | null>(null);

export const useReaderAnnotations = () => useContext(ReaderAnnotationsContext);

/** The marks on one page: a highlight per region, the pin at the first. */
export function ThreadMarks({ marks, page }: { marks: ReaderMark[]; page: number }) {
  if (marks.length === 0) return null;
  return (
    <div className="absolute inset-0 pointer-events-none">
      {marks.map((mark) => {
        const regions = mark.regions.filter((r) => r.page === page);
        if (regions.length === 0) return null;
        // The end of the passage on this page: its last line, read top to bottom.
        const last = [...regions].sort((a, b) => a.top - b.top || a.left - b.left)[regions.length - 1];
        return (
          <div key={mark.key}>
            {regions.map((r, i) => (
              <span
                key={i}
                aria-hidden
                className={cn(
                  "absolute rounded-sm",
                  mark.pending ? "thread-mark-pending" : "thread-mark",
                  mark.open && "thread-mark-open",
                )}
                style={{
                  left: `${r.left * 100}%`, top: `${r.top * 100}%`,
                  width: `${(r.right - r.left) * 100}%`, height: `${(r.bottom - r.top) * 100}%`,
                }}
              />
            ))}
            <button
              type="button"
              onClick={mark.onActivate}
              aria-label={mark.label}
              className={cn(
                "thread-pin absolute pointer-events-auto -translate-y-1/2 inline-grid place-items-center rounded-full font-semibold leading-none",
                mark.pending ? "bg-white text-pen ring-1 ring-pen" : "bg-pen text-white",
                FOCUS_RING,
              )}
              style={{
                left: `calc(${Math.min(last.right, 0.97) * 100}% + 2px)`,
                top: `${((last.top + last.bottom) / 2) * 100}%`,
              }}
            >
              {mark.pin}
            </button>
          </div>
        );
      })}
    </div>
  );
}
