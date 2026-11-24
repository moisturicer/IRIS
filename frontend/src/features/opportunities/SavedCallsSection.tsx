import { useEffect, useId, useMemo, useState } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { Button, ButtonLink } from "@/components/ui/Button";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import { savedInOrder, useSavedCallsStore, type SavedCall } from "@/store/savedCalls.store";

import { LibrarySearch } from "@/features/library/LibraryToolbar";

import { CallDetails } from "./CallDetails";
import { CallTags } from "./CallTags";
import { formatDueDate } from "./opportunityUtils";

/**
 * My Library's Saved calls (IR-766, ADR-050 decision 13 as amended
 * 2026-11-16): every Call the reader saved, newest first, apart from their
 * saved papers.
 *
 * A Call stays here, with its tags, Over included, until the reader removes
 * it or RDCO deletes it; the board's Saved filter shows only those still on
 * the board. One sent back to RDCO or rejected is listed as unavailable, with
 * nothing more about it, and can still be removed. Saves follow the account
 * (`store/savedCalls.store.ts`); a removal that fails comes back and a toast
 * says so.
 */
export function SavedCallsSection() {
  const load = useSavedCallsStore((s) => s.load);
  const interrupted = useSavedCallsStore((s) => s.interrupted);
  const items = useSavedCallsStore((s) => s.items);
  const order = useSavedCallsStore((s) => s.order);
  const ensureLoaded = useSavedCallsStore((s) => s.ensureLoaded);
  const unsave = useSavedCallsStore((s) => s.unsave);

  const [query, setQuery] = useState("");
  useEffect(() => { void ensureLoaded(); }, [ensureLoaded]);
  const list = useMemo(() => savedInOrder(items, order), [items, order]);
  /* Search reads what a row shows (IR-1324); an unavailable call shows nothing, so it never matches. */
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((item) => item.available && [item.call.title, item.call.location].some((text) => (text ?? "").toLowerCase().includes(needle)));
  }, [list, query]);

  if (load === "idle" || load === "loading") {
    return (
      <LoadingRegion label="Loading your saved calls…">
        <div className="bg-white rounded-card border border-stone-200 p-card space-y-2.5">
          <SkeletonBlock className="h-3 w-28" />
          <SkeletonBlock tone="strong" className="h-5 w-3/4" />
        </div>
      </LoadingRegion>
    );
  }
  if (load === "error" && interrupted) {
    return <InterruptedState framed what="saved calls" onRetry={() => void ensureLoaded(true)} />;
  }
  if (load === "error") {
    return (
      <EmptyState
        framed
        tone="error"
        icon="fa-triangle-exclamation"
        title="Could not load your saved calls"
        message="The list did not load. Your saves are kept with your account."
        action={<Button variant="outline" onClick={() => void ensureLoaded(true)}>Try again</Button>}
      />
    );
  }

  if (list.length === 0) {
    return (
      <EmptyState
        framed
        icon="fa-bookmark"
        title="No saved calls right now"
        message="Use the bookmark on a call in Calls & Conferences to keep it here."
        action={<ButtonLink to="/opportunities" variant="outline">Go to Calls & Conferences</ButtonLink>}
      />
    );
  }

  return (
    <div>
      <LibrarySearch label="Search your saved calls" value={query} onChange={setQuery} placeholder="Search by title or place" className="mb-section" />
      {shown.length === 0 ? (
        <EmptyState
          framed
          icon="fa-magnifying-glass"
          title={`No saved calls match “${query.trim()}”`}
          message="Search looks at call titles and places."
        />
      ) : (
        <ol aria-label="Saved calls" className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
          {shown.map((item) => (
            <li key={item.callId}>
              <SavedCallRow item={item} onRemove={(title) => void unsave({ id: item.callId, title })} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function SavedCallRow({ item, onRemove }: { item: SavedCall; onRemove: (title: string) => void }) {
  const titleId = useId();

  if (!item.available) {
    // Sent back to RDCO or rejected: nothing more is shown about it (IR-649).
    return (
      <article aria-labelledby={titleId} className="p-card-compact md:p-card flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id={titleId} className="font-display font-semibold text-title text-stone-600">Unavailable call</h3>
          <p className="text-small text-stone-600">This call is no longer on Calls & Conferences.</p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={() => onRemove("this call")} aria-label="Remove unavailable call">
          <i className="fas fa-bookmark" aria-hidden="true" /> Remove
        </Button>
      </article>
    );
  }

  const { call } = item;
  return (
    <article aria-labelledby={titleId} className="p-card-compact md:p-card space-y-3">
      <CallTags call={call} allEvents />
      <div className="min-w-0">
        <CallDetails call={call} titleId={titleId} />
      </div>
      <p className="text-small text-stone-600">Paper deadline {formatDueDate(call.due_date)}</p>
      <div className="flex flex-wrap items-center gap-2">
        {call.external_url && (
          <a
            href={call.external_url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn("inline-flex items-center gap-1.5 text-small font-semibold text-brand underline underline-offset-2", FOCUS_RING, COLOUR_TRANSITION)}
          >
            View call
            <i className="fas fa-arrow-up-right-from-square text-3xs" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
        <Button type="button" variant="ghost" size="sm" onClick={() => onRemove(call.title)} aria-label={`Remove ${call.title}`}>
          <i className="fas fa-bookmark" aria-hidden="true" /> Remove
        </Button>
      </div>
    </article>
  );
}
