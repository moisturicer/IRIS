import type { KeyboardEvent, ReactNode, Ref } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import type { PaperSection } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";

const SECTION_LABELS: Record<PaperSection, string> = {
  overview: "Overview",
  paper: "Paper",
  review: "Review",
  files: "Files",
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
  /** The paper in one line; null while it loads, absent where the page heads itself. */
  title?: string | null;
  version?: ReactNode;
  /** The Ask IRIS tool, where the section offers it. */
  askIris?: { open: boolean; onToggle: () => void; buttonRef?: Ref<HTMLButtonElement> };
  inert?: boolean;
  className?: string;
}

/**
 * The record bar (IR-569): Back, the paper in one line, its version, the
 * sections and Ask IRIS. One 56px row from `reading-split`; the tabs take a
 * second row below it.
 */
export function ReadingHeader({
  sections,
  section,
  onSelect,
  onTabKeyDown,
  tabId,
  panelId,
  onBack,
  title,
  version,
  askIris,
  inert = false,
  className,
}: ReadingHeaderProps) {
  return (
    <div
      // React 18 has no `inert` prop; an empty string sets the attribute.
      {...(inert ? { inert: "" } : {})}
      className={cn(
        "flex flex-wrap items-center gap-x-3 px-3 reading-split:px-5 bg-canvas border-b border-stone-200",
        "reading-split:flex-nowrap reading-split:h-14",
        className,
      )}
    >
      <button
        type="button"
        onClick={onBack}
        className={cn(
          "shrink-0 inline-flex items-center gap-1.5 h-11 -ml-1 px-1 rounded-md text-small text-stone-500 hover:text-brand",
          FOCUS_RING,
        )}
      >
        <i className="fas fa-chevron-left text-2xs" aria-hidden />
        <span className="sr-only reading-split:not-sr-only">Back</span>
      </button>
      <span aria-hidden className="hidden reading-split:block w-px h-5 bg-stone-300 shrink-0" />

      <div className="flex items-center gap-2.5 min-w-0 flex-1 h-14 reading-split:h-auto">
        {title === null ? (
          <span aria-hidden className="h-4 w-48 max-w-full rounded bg-stone-200 animate-pulse motion-reduce:animate-none" />
        ) : title === undefined ? null : (
          <h1 title={title} className="min-w-0 truncate font-display text-[19px] font-semibold text-stone-900">
            {title}
          </h1>
        )}
        {title != null && version}
      </div>

      {askIris && (
        <button
          ref={askIris.buttonRef}
          type="button"
          onClick={askIris.onToggle}
          aria-pressed={askIris.open}
          title="Ask IRIS about this paper"
          className={cn(
            "shrink-0 inline-flex items-center gap-1.5 h-9 px-3 rounded-md border text-small font-semibold",
            "transition-colors duration-200 reading-split:order-last",
            // Open is a quiet pressed state, so the section tab stays the one fill.
            askIris.open
              ? "bg-brand-50 border-brand-200 text-brand"
              : "border-brand text-brand hover:bg-brand-50",
            FOCUS_RING,
          )}
        >
          <AskIrisMark className="w-4 h-4" />
          {/* The label is the name (WCAG 2.5.3); on a phone, only to a screen reader. */}
          <span className="sr-only reading-split:not-sr-only">Ask IRIS</span>
        </button>
      )}

      <div
        role="tablist"
        aria-label="Paper view"
        onKeyDown={onTabKeyDown}
        className={cn(
          "flex items-center gap-0.5 w-full -mx-1 pb-2 overflow-x-auto",
          "reading-split:w-auto reading-split:mx-0 reading-split:pb-0 reading-split:shrink-0",
        )}
      >
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
              "shrink-0 h-9 px-3 rounded-md text-small transition-colors duration-200",
              FOCUS_RING,
              section === s ? "bg-brand text-white font-semibold" : "text-stone-600 hover:text-brand hover:bg-stone-100",
            )}
          >
            {SECTION_LABELS[s]}
          </button>
        ))}
      </div>
    </div>
  );
}
