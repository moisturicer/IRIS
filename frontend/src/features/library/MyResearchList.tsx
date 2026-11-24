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

import { LibrarySearch } from "./LibrarySearch";
import { groupByFilter, type FilterGroup, type ResearchFilter } from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/** What an empty filter says, so the reader knows the list is right, not broken. */
const EMPTY: Record<Exclude<ResearchFilter, "all">, { title: string; message: string }> = {
  waiting:  { title: "Nothing is waiting on you", message: "When a reviewer asks you for a revision or a document, it appears here." },
  review:   { title: "Nothing in review", message: "Papers you submit appear here while your Adviser or an office reviews them." },
  drafts:   { title: "No drafts", message: "A paper you start in Publish waits here until you submit it." },
  finished: { title: "Nothing finished yet", message: "Accepted, published and unlisted papers appear here." },
};

/**
 * One group of All research, folded like a chapter. Finished starts folded.
 */
function Group({ group, onDeleted }: { group: FilterGroup; onDeleted?: (id: number) => void }) {
  const waiting = group.id === "waiting";
  return (
    <details open={group.id !== "finished"} className="group/fold">
      <summary className={cn("flex cursor-pointer list-none items-center gap-3 rounded-control py-1 [&::-webkit-details-marker]:hidden", FOCUS_RING)}>
        <i
          className="fas fa-chevron-right w-3 text-label text-stone-500 transition-transform duration-200 group-open/fold:rotate-90 motion-reduce:transition-none"
          aria-hidden
        />
        <h3 className={cn("inline-flex items-center gap-2 font-display text-title font-semibold", waiting ? "text-brand" : "text-stone-900")}>
          {waiting && <i className="fas fa-circle-exclamation text-small" aria-hidden />}
          {group.title}
        </h3>
      </summary>
      <div className="mt-3">
        <SubmissionPanel>
          {group.items.map((item) => <SubmissionRow key={item.id} item={item} onDeleted={onDeleted} />)}
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
  /** Chosen in the rail (IR-1311). */
  filter:   ResearchFilter;
  /** A draft was deleted on the server. */
  onDeleted?: (id: number) => void;
}

/**
 * The owner's research (IR-410; spec §4.9 as amended 2026-10-11). All
 * research files every record under Needs your action, In review, Drafts and
 * Finished, what waits on the owner first, each group folding; a filter picked
 * in the rail shows that group's rows alone. Who has a record now is on its
 * own row, in the server's words. No counts.
 */
export function MyResearchList({ items, loading, failed, interrupted = false, onRetry, filter, onDeleted }: MyResearchListProps) {
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

  const searching = query.trim() !== "";
  return (
    <div>
      <div className="mb-section">
        <LibrarySearch label="Search your research" value={query} onChange={setQuery} />
      </div>

      {groups.length === 0 ? (
        <EmptyState
          framed
          icon={searching ? "fa-magnifying-glass" : "fa-folder-open"}
          title={searching ? `Nothing matches “${query.trim()}”` : filter === "all" ? "Nothing here right now" : EMPTY[filter].title}
          message={searching ? "Search looks at titles and author names." : filter === "all" ? "" : EMPTY[filter].message}
        />
      ) : filter === "all" ? (
        <div className="space-y-section-lg">
          {groups.map((group) => <Group key={group.id} group={group} onDeleted={onDeleted} />)}
        </div>
      ) : (
        <SubmissionPanel>
          {groups[0].items.map((item) => <SubmissionRow key={item.id} item={item} onDeleted={onDeleted} />)}
        </SubmissionPanel>
      )}
    </div>
  );
}
