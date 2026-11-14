import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { SELECTED_RING } from "@/components/ui/highlightRoles";

interface FilterChipsProps<T extends string> {
  label:    string;
  options:  { value: T; label: string }[];
  value:    T | null;
  onChange: (value: T) => void;
}

/**
 * A row of filter controls (DESIGN.md control-outline / control-on): 36 px,
 * the control radius, an Ink outline when on (IR-1097). A plain group of toggle buttons,
 * so a screen reader hears which one is pressed.
 */
export function FilterChips<T extends string>({ label, options, value, onChange }: FilterChipsProps<T>) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1">
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(option.value)}
            className={cn(
              "min-h-9 rounded-lg px-3 text-small font-semibold",
              COLOUR_TRANSITION,
              FOCUS_RING,
              on ? SELECTED_RING : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
