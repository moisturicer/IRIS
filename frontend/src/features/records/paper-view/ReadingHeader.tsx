import type { KeyboardEvent, ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import type { PaperSection } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";

import { CONTROL_SHAPE, CONTROL_SIZE, CONTROL_TEXT } from "./controls";

const SECTION_LABELS: Record<PaperSection, string> = {
  overview: "Overview",
  paper: "Paper",
  review: "Review",
};

interface ReadingHeaderProps {
  sections: PaperSection[];
  section: PaperSection;
  onSelect: (section: PaperSection) => void;
  onTabKeyDown: (e: KeyboardEvent<HTMLDivElement>) => void;
  tabId: (section: PaperSection) => string;
  /** The tab panel's id, or undefined while there is none. */
  panelId?: string;
  onBack: () => void;
  /** Back to the answer a citation was followed from (IR-578); absent when there is none. */
  onBackToAnswer?: () => void;
  /** The paper in one line; null while it loads, absent where the page heads itself. */
  title?: string | null;
  version?: ReactNode;
  inert?: boolean;
  className?: string;
}

/**
 * The record bar (IR-569): Back, the paper in one line, its version and the
 * sections, in one 56px row. On a phone (below `reading-split`, IR-1092) Back
 * is its icon, the sections take the rest of the row and the title is not
 * drawn (it stays as the heading for screen readers). The page then leaves the
 * version out of this bar and hands it to the reader's toolbar. Notes and Ask IRIS are the two round icons at the bottom right,
 * Notes above Ask IRIS, not tools here.
 */
export function ReadingHeader({
  sections,
  section,
  onSelect,
  onTabKeyDown,
  tabId,
  panelId,
  onBack,
  onBackToAnswer,
  title,
  version,
  inert = false,
  className,
}: ReadingHeaderProps) {
  return (
    <div
      // React 18 has no `inert` prop; an empty string sets the attribute.
      {...(inert ? { inert: "" } : {})}
      className={cn(
        // One 56px row at every width (IR-1092): never wrapped onto a second.
        "flex flex-nowrap items-center gap-x-2 h-14 px-3 reading-split:gap-x-3 reading-split:px-5",
        "bg-stone-100 border-b border-stone-200",
        className,
      )}
    >
      <button
        type="button"
        onClick={onBack}
        title="Back"
        className={cn(
          // Icon only on a phone, 44px square; the label stays for screen readers.
          "shrink-0 inline-flex items-center justify-center gap-1.5 -ml-1 min-w-11 px-2 text-small text-stone-600 hover:text-brand",
          "reading-split:min-w-0 reading-split:justify-start",
          CONTROL_SIZE,
          CONTROL_SHAPE,
          FOCUS_RING,
        )}
      >
        <i className="fas fa-chevron-left text-2xs" aria-hidden />
        <span className="sr-only reading-split:not-sr-only">Back</span>
      </button>
      {onBackToAnswer && (
        <button
          type="button"
          onClick={onBackToAnswer}
          title="Back to answer"
          className={cn(
            "shrink-0 inline-flex items-center justify-center gap-1.5 min-w-11 px-2 text-small font-semibold text-brand hover:bg-brand-50",
            "reading-split:min-w-0 reading-split:justify-start",
            CONTROL_SIZE,
            CONTROL_SHAPE,
            FOCUS_RING,
          )}
        >
          <i className="fas fa-reply text-2xs" aria-hidden />
          <span className="sr-only reading-split:not-sr-only">Back to answer</span>
        </button>
      )}
      <span aria-hidden className="hidden reading-split:block w-px h-5 bg-stone-300 shrink-0" />

      {/* On a phone the section control takes this room, so the title is for
          screen readers only and the version waits for Overview (IR-1092).
          `contents` keeps the heading in the tree without a box of its own. */}
      <div className="contents reading-split:flex reading-split:items-center reading-split:gap-2.5 reading-split:min-w-0 reading-split:flex-1">
        {title === null ? (
          <span aria-hidden className="hidden reading-split:block h-4 w-48 max-w-full rounded bg-stone-200 animate-pulse motion-reduce:animate-none" />
        ) : title === undefined ? null : (
          <h1
            title={title}
            className="sr-only reading-split:not-sr-only min-w-0 truncate font-display text-xl font-semibold text-stone-900"
          >
            {title}
          </h1>
        )}
        {title != null && version && <div className="hidden reading-split:flex items-center">{version}</div>}
      </div>

      {/* A recessed track with a thumb that slides to the chosen section. */}
      <div
        role="tablist"
        aria-label="Paper view"
        onKeyDown={onTabKeyDown}
        className={cn(
          // A phone gives it every pixel Back leaves; from reading-split it is
          // as wide as its labels.
          "relative grid grid-flow-col auto-cols-fr flex-1 min-w-0 p-0.5 rounded-lg bg-stone-200",
          "shadow-[inset_0_1px_3px_rgb(41_37_36/0.28),inset_0_0_0_1px_rgb(41_37_36/0.07)]",
          "reading-split:flex-none reading-split:shrink-0",
        )}
      >
        <span
          aria-hidden
          className={cn(
            // One step in from the track's radius, so the two are concentric.
            "absolute inset-y-0.5 left-0.5 rounded-md bg-brand",
            "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
          )}
          style={{
            width: `calc((100% - 4px) / ${sections.length})`,
            transform: `translateX(${Math.max(0, sections.indexOf(section)) * 100}%)`,
          }}
        />
        {sections.map((s) => (
          <button
            key={s}
            id={tabId(s)}
            type="button"
            role="tab"
            aria-selected={section === s}
            aria-controls={panelId}
            tabIndex={section === s ? 0 : -1}
            onClick={() => onSelect(s)}
            className={cn(
              "relative z-10 min-w-0 truncate px-1.5 reading-split:px-5 rounded-md",
              CONTROL_SIZE,
              CONTROL_TEXT,
              "transition-colors duration-300",
              FOCUS_RING,
              section === s ? "text-white" : "text-stone-600 hover:text-brand",
            )}
          >
            {SECTION_LABELS[s]}
          </button>
        ))}
      </div>
    </div>
  );
}
