import { useId } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { SORT_OPTIONS, type DiscoverSort } from "./DiscoverFilterBar";

interface DiscoverResultsHeaderProps {
  /** How many papers the query matches; null while it is being read or cannot be known. */
  count: number | null;
  /** Latest only: recommendations and Trending have an order of their own. */
  showSort: boolean;
  sort: DiscoverSort;
  onSort: (next: DiscoverSort) => void;
}

/**
 * The line above the results (IR-1082, spec §4.6): a live count on the left, Sort
 * on the right. Sort used to hide inside the Filters panel, though it changes how
 * the list reads, not what is in it.
 *
 * The count is a polite live region, so a reader is told what a new search or
 * filter found. It says nothing over an empty list, whose own message already does.
 */
export function DiscoverResultsHeader({ count, showSort, sort, onSort }: DiscoverResultsHeaderProps) {
  const sortId = useId();
  return (
    <div role="group" aria-label="Results" className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <p role="status" className="text-small text-stone-700">
        {count ? <><b className="font-semibold text-stone-900 tabular-nums">{count}</b> {count === 1 ? "paper" : "papers"}</> : null}
      </p>
      {showSort && (
        <div className="flex items-center gap-2">
          <label htmlFor={sortId} className="text-small font-medium text-stone-700">Sort</label>
          <select
            id={sortId}
            value={sort}
            onChange={(event) => onSort(event.target.value as DiscoverSort)}
            className={cn("h-11 rounded-lg border border-stone-300 bg-white px-3 text-small font-medium text-stone-800 hover:border-stone-500", COLOUR_TRANSITION, FOCUS_RING)}
          >
            {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
      )}
    </div>
  );
}
