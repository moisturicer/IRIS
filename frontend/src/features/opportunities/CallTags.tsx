import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";
import type { Opportunity } from "@/types/opportunities";

import { countdown, eventTag, papersClosed } from "./opportunityUtils";

/** A tag: words in a pill, never colour alone. */
const TAG = "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-label font-semibold whitespace-nowrap";

/** The event's tag glyph, by state; Over and Upcoming are quiet, Happening now is not. */
const EVENT_ICON = { happening: "fa-circle-play", upcoming: "fa-calendar", over: "fa-flag-checkered" } as const;

/**
 * A Call's two tags, worded by the server (ADR-050 decision 6): the papers tag
 * ("Accepting papers", with the days left, or "Submissions closed") and the
 * event tag.
 *
 * The board shows the event tag only while the event runs (IR-764): an Over
 * Call has left it, and "Upcoming" says nothing its dates don't. My Library
 * keeps a saved Call after it leaves the board, so it shows every event state,
 * Over included (`allEvents`, IR-766).
 */
export function CallTags({ call: o, allEvents = false }: { call: Opportunity; allEvents?: boolean }) {
  const closed = papersClosed(o);
  const chip = countdown(o);
  const eventLabel = allEvents ? o.event_label : eventTag(o);
  const happening = o.event_state === "happening";

  return (
    <p className="flex flex-wrap items-center gap-2">
      <span className={cn(TAG, closed ? TONES.quiet : chip.className)}>
        <i className={cn("fas", closed ? "fa-lock" : "fa-clock")} aria-hidden="true" />
        <span>{o.papers_label}</span>
        {!closed && (
          <>
            <span aria-hidden="true">·</span>
            <span className="font-normal">{chip.label}</span>
          </>
        )}
      </span>
      {eventLabel && (
        <span className={cn(TAG, happening ? TONES.active : TONES.quiet)}>
          <i className={cn("fas", EVENT_ICON[o.event_state ?? "over"])} aria-hidden="true" />
          {eventLabel}
        </span>
      )}
    </p>
  );
}
