import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import { usePublishHref } from "@/features/publish/publishLink";
import type { MyResearchItem } from "@/types/records";

import { LibrarySearch, UnderlineFilters } from "./LibraryToolbar";
import {
  RESEARCH_FILTERS,
  groupByFilter,
  type FilterGroup,
  type ResearchFilter,
} from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/** What an empty filter says (IR-1324): every filter shows, so an empty one explains itself. */
const EMPTY_FILTER: Record<Exclude<ResearchFilter, "all">, { title: string; message: string }> = {
  waiting:  { title: "Nothing needs your action", message: "When a reviewer asks you for changes, it appears here." },
  review:   { title: "Nothing in review", message: "A paper you submit is here while your Adviser and the offices review it." },
  drafts:   { title: "No drafts", message: "A paper you start and haven’t submitted is kept here." },
  finished: { title: "Nothing finished yet", message: "Accepted, published and archived papers are kept here." },
};

/**
 * One filter's records under a plain heading (IR-1324), with the ruled rows
 * under it. Nothing folds.
 */
function Group({ group, onDeleted }: { group: FilterGroup; onDeleted?: (id: number) => void }) {
  const titleId = `research-${group.id}`;
  const waiting = group.id === "waiting";
  return (
    <section aria-labelledby={titleId}>
      <h2 id={titleId} className={cn("mb-3 inline-flex items-center gap-2 font-display text-title font-semibold", waiting ? "text-brand" : "text-stone-900")}>
        {waiting && <i className="fas fa-circle-exclamation text-small" aria-hidden />}
        {group.title}
      </h2>
      <SubmissionPanel tone={waiting ? "waiting" : "plain"}>
        {group.items.map((item) => <SubmissionRow key={item.id} item={item} onDeleted={onDeleted} />)}
      </SubmissionPanel>
    </section>
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
  /** A draft was deleted on the server. */
  onDeleted?: (id: number) => void;
}

/**
 * My submissions (IR-410; spec §4.9 as amended 2026-10-11): the owner's
 * records filed under the filters (Needs your action, In review, Drafts,
 * Finished), what waits on the owner first, each under a plain heading
 * (IR-1324). Every filter always shows, and an empty one says so when picked.
 * Picking a filter shows that group alone. Who has a record now is on its own
 * row, in the server's words. No counts.
 */
export function MyResearchList({ items, loading, failed, interrupted = false, onRetry, filter, onFilterChange, onDeleted }: MyResearchListProps) {
  const publishHref = usePublishHref();
  const [query, setQuery] = useState("");

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? items.filter((item) =>
          item.title.toLowerCase().includes(needle) ||
          item.authors.some((author) => author.name.toLowerCase().includes(needle)))
      : items;
    return groupByFilter(matched).filter((group) => filter === "all" || group.id === filter);
  }, [items, query, filter]);

  if (loading) {
    return (
      <LoadingRegion label="Loading your research…" onRetry={onRetry} className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-28 rounded-card border border-stone-200 bg-white motion-safe:animate-pulse" />
        ))}
      </LoadingRegion>
    );
  }

  if (failed) {
    return (
      <ReadFailedState
        interrupted={interrupted}
        what="research list"
        title="Could not load your research"
        lead="Nothing was changed."
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
        action={<Link to={publishHref("new")} className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>}
      />
    );
  }

  return (
    <div>
      <div className="mb-section space-y-3">
        <LibrarySearch label="Search your research" value={query} onChange={setQuery} />
        <UnderlineFilters label="Show" options={RESEARCH_FILTERS} value={filter} onChange={onFilterChange} />
      </div>

      {groups.length === 0 ? (
        <EmptyState
          framed
          icon={query.trim() ? "fa-magnifying-glass" : "fa-inbox"}
          title={query.trim() ? `Nothing matches “${query.trim()}”` : filter === "all" ? "Nothing here right now" : EMPTY_FILTER[filter].title}
          message={query.trim() ? "Search looks at titles and author names." : filter === "all" ? "Choose All to see every record." : EMPTY_FILTER[filter].message}
        />
      ) : (
        <div className="space-y-section-lg">
          {groups.map((group) => <Group key={group.id} group={group} onDeleted={onDeleted} />)}
        </div>
      )}
    </div>
  );
}
