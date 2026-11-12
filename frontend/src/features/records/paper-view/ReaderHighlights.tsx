/**
 * The reader's own saved highlights, drawn over a page (IR-583, ADR-065).
 *
 * Positioned in percentages of the page, like a citation's overlay, so a
 * highlight stays on its words at any zoom. Decorative: it is `aria-hidden`,
 * because a screen reader cannot read the canvas the words are drawn on; the
 * Notes list holds the same passages as text.
 */
import type { PageRegion } from "@/types/records";

export interface ReaderHighlight {
  key:     string | number;
  regions: PageRegion[];
}

export function HighlightMarks({ highlights, page }: { highlights: ReaderHighlight[]; page: number }) {
  const regions = highlights.flatMap((h) => h.regions.filter((r) => r.page === page).map((r, i) => ({ key: `${h.key}:${i}`, r })));
  if (regions.length === 0) return null;
  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
      {regions.map(({ key, r }) => (
        <span
          key={key}
          className="reader-highlight absolute rounded-sm"
          style={{
            left: `${r.left * 100}%`, top: `${r.top * 100}%`,
            width: `${(r.right - r.left) * 100}%`, height: `${(r.bottom - r.top) * 100}%`,
          }}
        />
      ))}
    </div>
  );
}
