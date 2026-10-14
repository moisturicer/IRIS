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
  /** Paper mode's identity: Back, the one-line title (null while loading) and the version. */
  identity?: { title: string | null; version: ReactNode; onBack: () => void };
  /** The Ask IRIS tool, where the section offers it. */
  askIris?: { open: boolean; onToggle: () => void; buttonRef?: Ref<HTMLButtonElement> };
  /** While Ask IRIS covers the paper, the header waits too. */
  inert?: boolean;
}

/**
 * The record page's one header (IR-569): the section switch and the tools,
 * and in Paper mode the paper itself in one line.
 *
 * From `reading-split` up it is one sticky 56px row. Narrower, `contents`
 * lets the identity row scroll away while the 56px tab row sticks.
 */
export function ReadingHeader({
  sections,
  section,
  onSelect,
  onTabKeyDown,
  tabId,
  panelId,
  identity,
  askIris,
  inert = false,
}: ReadingHeaderProps) {
  return (
    <div
      // React 18 has no `inert` prop; an empty string sets the attribute.
      {...(inert ? { inert: "" } : {})}
      className={cn(
        "contents",
        "reading-split:sticky reading-split:top-0 reading-split:z-30 reading-split:flex reading-split:items-center",
        "reading-split:gap-3 reading-split:h-14 reading-split:mb-3 reading-split:bg-canvas",
        "reading-split:border-b reading-split:border-stone-200",
      )}
    >
      {identity && (
        <div className="flex items-center gap-2 h-12 min-w-0 reading-split:h-auto reading-split:flex-1">
          <button
            type="button"
            onClick={identity.onBack}
            aria-label="Back"
            title="Back"
            className={cn(
              "shrink-0 w-11 h-11 -ml-2 rounded-full flex items-center justify-center text-stone-500 hover:text-brand",
              FOCUS_RING,
            )}
          >
            <i className="fas fa-arrow-left text-sm" aria-hidden />
          </button>
          {/* One line; the whole title stays in the heading and its tooltip. */}
          {identity.title == null ? (
            <span aria-hidden className="h-4 w-48 max-w-full rounded bg-stone-200 animate-pulse motion-reduce:animate-none" />
          ) : (
            <>
              <h1 title={identity.title} className="min-w-0 truncate font-display text-lg font-semibold text-stone-900">
                {identity.title}
              </h1>
              {identity.version}
            </>
          )}
        </div>
      )}

      <div
        className={cn(
          "sticky top-0 z-30 flex items-center justify-between gap-2 h-14 mb-3 bg-canvas border-b border-stone-200",
          "reading-split:static reading-split:z-auto reading-split:h-auto reading-split:mb-0",
          "reading-split:border-0 reading-split:bg-transparent",
          !identity && "reading-split:flex-1",
        )}
      >
        <div
          role="tablist"
          aria-label="Paper view"
          onKeyDown={onTabKeyDown}
          className="flex gap-1 min-w-0 overflow-x-auto rounded-full p-0.5 ring-1 ring-stone-300"
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
                "shrink-0 min-h-11 px-3 reading-split:px-4 rounded-full text-small font-semibold transition-colors duration-200",
                FOCUS_RING,
                section === s ? "bg-brand text-white" : "text-stone-600 hover:text-brand",
              )}
            >
              {SECTION_LABELS[s]}
            </button>
          ))}
        </div>

        {askIris && (
          <button
            ref={askIris.buttonRef}
            type="button"
            onClick={askIris.onToggle}
            aria-pressed={askIris.open}
            title="Ask IRIS about this paper"
            className={cn(
              "shrink-0 inline-flex items-center gap-2 min-h-11 px-3 rounded-full text-small font-semibold",
              "ring-1 transition-colors duration-200",
              askIris.open
                ? "bg-brand-50 text-brand ring-brand-200"
                : "text-stone-700 ring-stone-300 hover:text-brand hover:ring-brand/40",
              FOCUS_RING,
            )}
          >
            <AskIrisMark className="w-4 h-4 text-brand" />
            {/* The label is the name (WCAG 2.5.3); on a phone, only to a screen reader. */}
            <span className="sr-only reading-split:not-sr-only">Ask IRIS</span>
          </button>
        )}
      </div>
    </div>
  );
}
