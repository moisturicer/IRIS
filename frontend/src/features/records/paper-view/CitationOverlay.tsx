import type { Region } from "@/types/ai";

/**
 * The rectangles a citation highlights, drawn over one rendered PDF page
 * (IR-334, IR-335).
 *
 * Positioned entirely in percentages of the page's own container — never
 * pixels — so a highlight stays aligned with the text under it at any zoom
 * without this component knowing the current scale at all: the container it
 * sits in (the page's canvas wrapper) already scales, and a percentage of a
 * scaled box scales with it for free.
 *
 * Renders nothing for an empty `regions` list, which is the honest state for
 * a passage extraction recovered no rectangle for — the page still opens,
 * nothing is drawn on it (see `apps/ai/regions.py`'s withholding rules).
 */
export function CitationOverlay({ regions }: { regions: Region[] }) {
  if (regions.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
      {regions.map((region, index) => (
        <div
          key={index}
          className="absolute rounded-[2px] bg-amber-300/35 ring-2 ring-amber-500/80 motion-safe:animate-citation-flash"
          style={{
            left:   `${region.left * 100}%`,
            top:    `${region.top * 100}%`,
            width:  `${(region.right - region.left) * 100}%`,
            height: `${(region.bottom - region.top) * 100}%`,
          }}
        />
      ))}
    </div>
  );
}
