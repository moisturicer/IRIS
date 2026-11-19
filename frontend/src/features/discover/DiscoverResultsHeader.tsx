interface DiscoverResultsHeaderProps {
  /** How many papers the query matches; null while it is being read or cannot be known. */
  count: number | null;
}

/**
 * The line above the results (IR-1082, spec §4.6): a live count. Sort lived on
 * its right until IR-1187 made it the toolbar's one order control
 * (`DiscoverOrderSelect`).
 *
 * The count is a polite live region, so a reader is told what a new search or
 * filter found. It says nothing over an empty list, whose own message already does.
 */
export function DiscoverResultsHeader({ count }: DiscoverResultsHeaderProps) {
  return (
    <div role="group" aria-label="Results" className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <p role="status" className="text-small text-stone-700">
        {count ? <><b className="font-semibold text-stone-900 tabular-nums">{count}</b> {count === 1 ? "paper" : "papers"}</> : null}
      </p>
    </div>
  );
}
