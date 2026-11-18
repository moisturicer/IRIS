import { useId } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { ORDER_OPTIONS, type DiscoverOrder } from "./discoverQuery";

interface DiscoverOrderSelectProps {
  value: DiscoverOrder;
  onChange: (next: DiscoverOrder) => void;
}

/**
 * How Discover is ordered: Best, Newest, Most viewed or Trending, in one
 * compact control (IR-1187). It replaced the For you / Latest / Trending tabs
 * and the separate Sort select. A native select, so the keyboard and screen
 * readers get the platform's own control; its label "Sort" is its name, drawn
 * from `sm` and screen-reader-only on a phone, where one row has no room (IR-1190).
 *
 * Always shown, even over an empty or failed list: an empty Best is left by
 * choosing another order here.
 */
export function DiscoverOrderSelect({ value, onChange }: DiscoverOrderSelectProps) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-initial">
      {/* The word is the control's name; a phone has no room to draw it (IR-1190). */}
      <label htmlFor={id} className="sr-only text-small font-medium text-stone-700 sm:not-sr-only">Sort</label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value as DiscoverOrder)}
        className={cn("h-11 min-w-0 flex-1 rounded-control border border-field bg-white px-2 text-small font-medium text-stone-800 hover:border-stone-500 sm:flex-initial sm:px-3", COLOUR_TRANSITION, FOCUS_RING)}
      >
        {ORDER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </div>
  );
}
