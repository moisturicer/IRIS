import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { SearchGlyph } from "@/components/brand/IrisBrand";
import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

import { FilterChips } from "./FilterChips";
import {
  RESEARCH_FILTERS,
  groupByFilter,
  type FilterGroup,
  type ResearchFilter,
} from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/**
 * One filter's records, folded like a chapter: a summary line with the
 * group's name and what it means, and the ruled rows under it.
 */
function Group({ group, open }: { group: FilterGroup; open: boolean }) {
  const titleId = `research-${group.id}`;
  const waiting = group.id === "waiting";
  return (
    <details open={open} className="group/fold">
      <summary className={cn("grid cursor-pointer list-none grid-cols-[0.75rem_minmax(0,1fr)] items-start gap-x-3 rounded-lg py-1 [&::-webkit-details-marker]:hidden", FOCUS_RING)}>
        <i
          className="fas fa-chevron-right row-span-2 mt-2 w-3 text-label text-stone-500 transition-transform duration-200 group-open/fold:rotate-90 motion-reduce:transition-none"
          aria-hidden
        />
        <h2 id={titleId} className={cn("inline-flex items-center gap-2 font-display text-title font-semibold", waiting ? "text-brand" : "text-stone-900")}>
          {waiting && <i className="fas fa-circle-exclamation text-small" aria-hidden />}
          {group.title}
        </h2>
        <span className="col-start-2 text-small text-stone-600">{group.note}</span>
      </summary>
      <div className="mt-3">
        <SubmissionPanel tone={waiting ? "waiting" : "plain"}>
          {group.items.map((item) => <SubmissionRow key={item.id} item={item} />)}
        </SubmissionPanel>
      </div>
    </details>
  );
}

interface MyResearchListProps {
  items:    MyResearchItem[];
  loading:  boolean;
  failed:   boolean;
  /** The read timed out (IR-906): Retry, not a refusal. */
  interrupted?: boolean;
  onRetry:  () => void;
  filter:   ResearchFilter;
  onFilterChange: (filter: ResearchFilter) => void;
}

/**
 * My submissions (IR-410; spec §4.9 as amended 2026-10-11): the owner's
 * records filed under the filters (Needs your action, In review, Drafts,
 * Finished), what waits on the owner first. Each group folds; Finished
 * starts folded. Picking a filter shows that group alone, open. Who has a
 * record now is on its own row, in the server's words. No counts.
 */
export function MyResearchList({ items, loading, failed, interrupted = false, onRetry, filter, onFilterChange }: MyResearchListProps) {
  const [query, setQuery] = useState("");

  const all = useMemo(() => groupByFilter(items), [items]);
  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? items.filter((item) =>
          item.title.toLowerCase().includes(needle) ||
          item.authors.some((author) => author.name.toLowerCase().includes(needle)))
      : items;
    return groupByFilter(matched).filter((group) => filter === "all" || group.id === filter);
  }, [items, query, filter]);

  // Offer only the filters that would show something, plus All.
  const filters = RESEARCH_FILTERS.filter((f) => f.value === "all" || f.value === filter || all.some((g) => g.id === f.value));

  if (loading) {
    return (
      <div className="space-y-3" role="status">
        <span className="sr-only">Loading your research…</span>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 rounded-2xl border border-stone-200 bg-white motion-safe:animate-pulse" aria-hidden />
        ))}
      </div>
    );
  }

  if (failed) {
    return (
      <ReadFailedState
        interrupted={interrupted}
        what="research list"
        title="Could not load your research"
        message="Nothing was changed. Check your connection and try again."
        onRetry={onRetry}
      />
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        framed
        icon="fa-feather-pointed"
        title="You haven’t published anything yet"
        message="Publish a paper and it will appear here, grouped by who is reviewing it."
        action={<Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>}
      />
    );
  }

  return (
    <div>
      <div className="mb-section rounded-2xl border border-stone-200 bg-white p-card-compact md:p-card">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <label className="relative block lg:w-80">
            <span className="sr-only">Search your research</span>
            <SearchGlyph className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-500" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title or author"
              className="w-full rounded-lg border border-stone-300 bg-white py-2 pl-10 pr-3 text-body placeholder:text-stone-500 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            />
          </label>
          <FilterChips label="Show" options={filters} value={filter} onChange={onFilterChange} />
        </div>
      </div>

      {groups.length === 0 ? (
        <EmptyState
          framed
          icon="fa-magnifying-glass"
          title={query.trim() ? `Nothing matches “${query.trim()}”` : "Nothing here right now"}
          message={query.trim() ? "Search looks at titles and author names." : "Choose All to see every record."}
        />
      ) : (
        <div className="space-y-section-lg">
          {groups.map((group) => (
            // Keyed on the filter so a group re-opens when it is picked alone.
            <Group key={`${filter}-${group.id}`} group={group} open={filter !== "all" || group.id !== "finished"} />
          ))}
        </div>
      )}
    </div>
  );
}
