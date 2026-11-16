import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";
import type { Opportunity } from "@/types/opportunities";

import { FeaturedToggle } from "./callActions";
import { CallDetails } from "./CallDetails";
import { countdown, dateParts, eventTag, formatDueDate, papersClosed } from "./opportunityUtils";

interface OpportunityRowProps {
  opportunity: Opportunity;
  saved:       boolean;
  /** The page's sentence saying saves stay in this browser, for the save button to point at. */
  savedHintId: string;
  icsBusy:     boolean;
  onToggleSave:  () => void;
  onDownloadIcs: () => void;
  onEdit:        () => void;
  onDelete:      () => void;
  /** RDCO removes an Adviser's Call with a reason (`can_remove`, IR-765). */
  onRemove:      () => void;
  /** RDCO sets or clears Featured (`can_feature`, IR-765). */
  onToggleFeatured: () => void;
  featuring:     boolean;
}

/** The outbound link: an outline pill, 44 px on touch screens, compact beside a pointer. */
const LINK =
  "inline-flex items-center gap-1.5 min-h-11 lg:min-h-8 px-3.5 rounded-full text-small font-semibold " +
  "bg-white text-stone-800 ring-1 ring-stone-300 hover:ring-brand/40 hover:text-brand";

/** A tag: words in a pill, never colour alone. */
const TAG = "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-label font-semibold whitespace-nowrap";

/**
 * One call on the deadline board (IR-530, IR-764).
 *
 * Read left to right as the question the board answers: *when* (the date
 * block), *what* (type, title, about, event dates, where, fee, which Areas),
 * then *what I can do* (save it, put the deadline in my calendar, go and
 * apply). Two tags say where it stands, worded by the server (ADR-050
 * decision 6): the papers tag always, and Happening now while the event runs.
 * Edit, delete, remove with a reason and Featured appear only when the
 * server says this viewer may (`can_*`); the row compares no role names.
 *
 * Nothing here grows when an action fails: the page says so in a toast.
 */
export function OpportunityRow({
  opportunity: o,
  saved,
  savedHintId,
  icsBusy,
  onToggleSave,
  onDownloadIcs,
  onEdit,
  onDelete,
  onRemove,
  onToggleFeatured,
  featuring,
}: OpportunityRowProps) {
  const titleId = useId();
  const closed  = papersClosed(o);
  const chip    = countdown(o);
  const date    = dateParts(o.due_date);
  const urgent  = !closed && chip.tone === "attention";
  const eventLabel = eventTag(o);

  return (
    <article
      aria-labelledby={titleId}
      className="flex flex-wrap gap-x-4 gap-y-3 p-card-compact md:p-card"
    >
      {/* ---- When ---------------------------------------------------------- */}
      <time
        dateTime={o.due_date}
        className={cn(
          // A strip on a phone, so the title gets the full width; a block
          // beside the content from `sm`, where there is room for both.
          "flex items-center justify-center self-start shrink-0 rounded-control border px-2.5 py-1",
          "sm:w-16 sm:px-0 sm:py-2 sm:text-center",
          urgent ? "border-stone-300 bg-surface" : "border-stone-200 bg-white",
        )}
      >
        {date ? (
          <span aria-hidden="true" className="flex items-baseline gap-1.5 sm:flex-col sm:items-center sm:gap-0">
            <span className={cn("text-label font-semibold", closed ? "text-stone-600" : "text-brand")}>
              {date.month}
            </span>
            <span className={cn("font-display font-semibold text-heading sm:text-display", closed ? "text-stone-600" : "text-stone-900")}>
              {date.day}
            </span>
            <span className="text-label text-stone-600">{date.weekday}</span>
          </span>
        ) : (
          <span aria-hidden="true" className="text-label text-stone-600">{o.due_date}</span>
        )}
        <span className="sr-only">
          Paper deadline {formatDueDate(o.due_date)}
        </span>
      </time>

      {/* ---- What ---------------------------------------------------------- */}
      <div className="basis-full sm:basis-0 sm:flex-1 min-w-0">
        <CallDetails call={o} titleId={titleId} muted={closed} />
      </div>

      {/* ---- What I can do ------------------------------------------------- */}
      {/* Under the content until `xl`: the sidebar takes its share from `md`,
          so at `lg` a call with no link still squeezed its title to ~240 px. */}
      <div className="w-full xl:w-auto xl:shrink-0 xl:max-w-xs flex flex-wrap xl:flex-col items-center xl:items-end justify-between xl:justify-start gap-3">
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
            <span className={cn(TAG, TONES.active)}>
              <i className="fas fa-circle-play" aria-hidden="true" />
              {eventLabel}
            </span>
          )}
        </p>

        <div className="flex flex-wrap items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onToggleSave}
            aria-pressed={saved}
            aria-label={`Save ${o.title}`}
            aria-describedby={savedHintId}
            title={saved ? "Saved in this browser. Select to remove." : "Save in this browser"}
            className={FOCUS_RING}
          >
            <i className={cn(saved ? "fas" : "far", "fa-bookmark")} aria-hidden="true" />
          </Button>

          {!closed && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onDownloadIcs}
              disabled={icsBusy}
              aria-label={`Add the ${o.title} deadline to your calendar`}
              title="Add the deadline to your own calendar (.ics)"
              className={FOCUS_RING}
            >
              <i className={cn(icsBusy ? "fas fa-spinner fa-spin" : "far fa-calendar-plus")} aria-hidden="true" />
            </Button>
          )}

          {o.external_url && (
            <a
              href={o.external_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(LINK, FOCUS_RING, COLOUR_TRANSITION, "ml-1")}
            >
              {closed ? "View call" : "View & apply"}
              <i className="fas fa-arrow-up-right-from-square text-3xs" aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          )}
        </div>
      </div>

      {/* ---- Who posted it, and the poster's own controls ----------------- */}
      {/* Last in the row, so the deadline and "View & apply" come before Delete
          in reading and tab order. From `xl` it lines up under the content. */}
      {(o.posted_by_name || o.can_edit || o.can_delete || o.can_remove || o.can_feature) && (
        <div className="basis-full xl:pl-20 flex flex-wrap items-center gap-x-1 gap-y-1 text-label text-stone-600">
          {o.posted_by_name && <span className="mr-2">Posted by {o.posted_by_name}</span>}
          {o.can_edit && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onEdit}
                aria-label={`Edit ${o.title}`}
                className={cn("min-h-11 lg:min-h-0", FOCUS_RING)}
              >
                <i className="fas fa-pen" aria-hidden="true" />
                Edit
              </Button>
          )}
          {o.can_feature && (
            <FeaturedToggle call={o} busy={featuring} onToggle={onToggleFeatured} className="min-h-11 lg:min-h-0" />
          )}
          {/* Plain delete; an Adviser's Call is removed by RDCO with a reason. */}
          {o.can_delete && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onDelete}
                aria-label={`Delete ${o.title}`}
                className={cn("min-h-11 lg:min-h-0", FOCUS_RING)}
              >
                <i className="fas fa-trash-can" aria-hidden="true" />
                Delete
              </Button>
          )}
          {o.can_remove && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onRemove}
                aria-label={`Remove ${o.title}`}
                className={cn("min-h-11 lg:min-h-0", FOCUS_RING)}
              >
                <i className="fas fa-trash-can" aria-hidden="true" />
                Remove
              </Button>
          )}
        </div>
      )}
    </article>
  );
}
