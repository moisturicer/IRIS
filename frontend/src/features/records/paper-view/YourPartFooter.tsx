import type { ReactNode, Ref } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import type { YourPart } from "./yourPart";

/**
 * The footer's icon in a 32 px circle, as a pull request's merge box draws it
 * (IR-1131): filled maroon where someone must act, outlined in Ink once
 * settled, quiet otherwise. Keyed by the part's own icon, so nothing here
 * decides a state.
 */
const CIRCLE: Record<string, { tone: string; glyph: string }> = {
  "fa-circle-check": { tone: "settled", glyph: "fa-check" },
  "fa-circle-xmark": { tone: "attention", glyph: "fa-xmark" },
  "fa-circle-exclamation": { tone: "attention", glyph: "fa-exclamation" },
  "fa-circle-info": { tone: "quiet", glyph: "fa-info" },
};

/**
 * The Review pane's "Your part" footer (IR-1094; spec §4.8), shaped like a
 * pull request's merge box: a status icon, one heading, one line under it and
 * the actions the server grants -- one of them filled. It replaces the
 * Readiness card and its pane-head summary; the facts behind it are in
 * Details, one tap on "See what it depends on" away.
 *
 * It words nothing: `part` is built from the server's own strings
 * (`yourPartSummary`), and `children` holds the host's real controls.
 */
export function YourPartFooter({ id, part, hasFacts, onShowFacts, footerRef, children }: {
  id: string;
  part: YourPart;
  /** The server sent facts beyond the line: offer the way to them. */
  hasFacts: boolean;
  onShowFacts: () => void;
  footerRef?: Ref<HTMLElement>;
  children?: ReactNode;
}) {
  return (
    <footer ref={footerRef} id={id} className="review-pane-foot" aria-label="Your part">
      {/* One row, as the prototype's merge box: who-and-what on the left, the
          actions on the right, wrapping under it in a narrow pane (IR-1139). */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span aria-hidden className={cn("review-mb-ic self-start", (CIRCLE[part.icon] ?? CIRCLE["fa-circle-info"]).tone)}>
          <i className={cn("fas", (CIRCLE[part.icon] ?? { glyph: part.icon }).glyph)} />
        </span>
        <div className="min-w-0 flex-1 basis-40">
          <p className="text-small font-semibold text-stone-900">{part.heading}</p>
          {part.line && <p className="text-2xs text-stone-600">{part.line}</p>}
          {hasFacts && (
            <button type="button" onClick={onShowFacts}
              className={cn("review-control -ml-2 mt-0.5 font-semibold text-brand hover:underline", FOCUS_RING)}>
              See what it depends on
            </button>
          )}
        </div>
        {children}
      </div>
    </footer>
  );
}
