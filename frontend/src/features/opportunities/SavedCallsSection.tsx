import { useEffect, useId } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { Button, ButtonLink } from "@/components/ui/Button";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";
import { useSavedCallsStore, type SavedCall } from "@/store/savedCalls.store";

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
  const items = useSavedCallsStore((s) => s.items);
  const sorted = useSavedCallsStore((s) => s.sorted);
  const ensureLoaded = useSavedCallsStore((s) => s.ensureLoaded);
  const unsave = useSavedCallsStore((s) => s.unsave);

  useEffect(() => { void ensureLoaded(); }, [ensureLoaded]);

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

  // `items` is read so a change re-renders; `sorted` orders the same items.
  const list = Object.keys(items).length > 0 ? sorted() : [];
  if (list.length === 0) {
    return (
      <EmptyState
        framed
        icon="fa-bookmark"
        title="No saved calls"
        message="Use the bookmark on a call in Calls & Conferences to keep it here."
        action={<ButtonLink to="/opportunities" variant="outline">Go to Calls & Conferences</ButtonLink>}
      />
    );
  }

  return (
    <ol aria-label="Saved calls" className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
      {list.map((item) => (
        <li key={item.callId}>
          <SavedCallRow item={item} onRemove={(title) => void unsave(item.callId, title)} />
        </li>
      ))}
    </ol>
  );
}

function SavedCallRow({ item, onRemove }: { item: SavedCall; onRemove: (title: string) => void }) {
  const titleId = useId();
  const call = item.available ? item.call : undefined;

  if (!call) {
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
