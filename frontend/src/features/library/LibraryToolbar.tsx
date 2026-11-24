import { SearchGlyph } from "@/components/brand/IrisBrand";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

/**
 * My Library's search field (IR-1324): one long field, the same on My
 * Submissions, Saved Papers and Saved Calls, set on the page rather than in a
 * box.
 */
export function LibrarySearch({ label, value, onChange, placeholder = "Search by title or author", className }: {
  /** Read to a screen reader; the placeholder says what is searched. */
  label:        string;
  value:        string;
  onChange:     (value: string) => void;
  placeholder?: string;
  className?:   string;
}) {
  return (
    <label className={cn("relative block min-w-0 flex-1", className)}>
      <span className="sr-only">{label}</span>
      <SearchGlyph className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-500" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-control border border-field bg-white py-2 pl-10 pr-3 text-body placeholder:text-stone-600 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      />
    </label>
  );
}

/**
 * Filters as underlined words on a ruled line (IR-1324), like the page's own
 * tabs one size down. A group of toggle buttons, so a screen reader hears
 * which one is pressed. Every option always shows; on a phone the row
 * scrolls sideways rather than wrapping.
 */
export function UnderlineFilters<T extends string>({ label, options, value, onChange, className }: {
  label:      string;
  options:    { value: T; label: string }[];
  value:      T | null;
  onChange:   (value: T) => void;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("flex gap-6 overflow-x-auto border-b border-stone-200 scrollbar-none", className)}>
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(option.value)}
            className={cn(
              "min-h-10 shrink-0 whitespace-nowrap border-b-2 px-0.5 text-small font-semibold",
              COLOUR_TRANSITION,
              FOCUS_RING,
              on ? "border-brand text-brand" : "border-transparent text-stone-600 hover:text-stone-900",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
