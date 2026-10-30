import type { ResearchOrigin } from "@/types/records";

/** Origin is declared metadata, never derived from the owner or author list. */
export function ResearchOriginBadge({ origin }: { origin?: ResearchOrigin }) {
  if (origin !== "imported_reference" && origin !== "synthetic") return null;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-stone-300 px-2 py-0.5 text-xs text-stone-600">
      <i className={`fas ${origin === "synthetic" ? "fa-flask" : "fa-book-open"}`} aria-hidden="true" />
      {origin === "synthetic" ? "Synthetic" : "Imported reference"}
    </span>
  );
}
