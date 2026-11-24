import { SearchGlyph } from "@/components/brand/IrisBrand";

/** My Library's one search field: titles and author names in the list below it. */
export function LibrarySearch({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="relative block w-full min-w-0 sm:max-w-sm">
      <span className="sr-only">{label}</span>
      <SearchGlyph className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-500" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search by title or author"
        className="min-h-10 w-full rounded-control border border-field bg-white py-2 pl-10 pr-3 text-control placeholder:text-stone-600 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      />
    </label>
  );
}
