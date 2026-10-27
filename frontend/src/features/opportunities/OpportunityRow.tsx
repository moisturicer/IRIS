import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { Opportunity } from "@/types/opportunities";

import { countdown, dateParts, formatCeiling, formatDueDate, typeMeta } from "./opportunityUtils";

interface OpportunityRowProps {
  opportunity: Opportunity;
  saved:       boolean;
  /** The page's sentence saying saves stay in this browser, for the save button to point at. */
  savedHintId: string;
  icsBusy:     boolean;
  icsFailed:   boolean;
  onToggleSave:  () => void;
  onDownloadIcs: () => void;
  onEdit:        () => void;
  onDelete:      () => void;
}

/** The outbound link: an outline pill, 44 px on touch screens, compact beside a pointer. */
const LINK =
  "inline-flex items-center gap-1.5 min-h-11 lg:min-h-8 px-3.5 rounded-full text-small font-semibold " +
  "bg-white text-stone-800 ring-1 ring-stone-300 hover:ring-brand/40 hover:text-brand";

/**
 * One call on the deadline board (IR-530).
 *
 * Read left to right as the question the board answers: *when* (the date
 * block), *what* (type, title, who posts it, who may apply), then *what I can
 * do* (save it, put the deadline in my calendar, go and apply). Edit and
 * delete appear only when the server says this viewer may (`can_edit`).
 */
export function OpportunityRow({
  opportunity: o,
  saved,
  savedHintId,
  icsBusy,
  icsFailed,
  onToggleSave,
  onDownloadIcs,
  onEdit,
  onDelete,
}: OpportunityRowProps) {
  const titleId = useId();
  const type    = typeMeta(o.opportunity_type);
  const chip    = countdown(o);
  const ceiling = formatCeiling(o.funding_ceiling);
  const date    = dateParts(o.due_date);
  const urgent  = !o.is_closed && chip.tone === "attention";

  // The ceiling is the one figure a reader compares across calls, so it is
  // the one part of the line set heavier.
  const meta = [
    { text: o.posting_office, strong: false },
    { text: o.audience, strong: false },
    { text: ceiling ? `Up to ${ceiling}` : "", strong: true },
  ].filter((part) => part.text);

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
          "flex items-center justify-center self-start shrink-0 rounded-lg border px-2.5 py-1",
          "sm:w-16 sm:px-0 sm:py-2 sm:text-center",
          urgent ? "border-brand-200 bg-brand-50" : "border-stone-200 bg-white",
        )}
      >
        {date ? (
          <span aria-hidden="true" className="flex items-baseline gap-1.5 sm:flex-col sm:items-center sm:gap-0">
            <span className={cn("text-label font-semibold", o.is_closed ? "text-stone-600" : "text-brand")}>
              {date.month}
            </span>
            <span className={cn("font-display font-semibold text-heading sm:text-display", o.is_closed ? "text-stone-600" : "text-stone-900")}>
              {date.day}
            </span>
            <span className="text-label text-stone-600">{date.weekday}</span>
          </span>
        ) : (
          <span aria-hidden="true" className="text-label text-stone-600">{o.due_date}</span>
        )}
        <span className="sr-only">
          {o.is_closed ? "Closed" : "Due"} {formatDueDate(o.due_date)}
        </span>
      </time>

      {/* ---- What ---------------------------------------------------------- */}
      <div className="basis-full sm:basis-0 sm:flex-1 min-w-0">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-label text-stone-600">
          <span className="inline-flex items-center gap-1.5 font-semibold text-stone-700">
            <i className={cn("fas", type.icon, "text-stone-500")} aria-hidden="true" />
            {type.label}
          </span>
          {o.is_featured && (
            <span className="inline-flex items-center gap-1 font-semibold text-brand">
              <i className="fas fa-star" aria-hidden="true" />
              Featured
            </span>
          )}
          {o.source === "external" && (
            <span className="inline-flex items-center gap-1">
              <i className="fas fa-globe" aria-hidden="true" />
              From an outside body
            </span>
          )}
        </p>

        <h3
          id={titleId}
          className={cn(
            "font-display font-semibold text-title mt-1 break-words text-pretty",
            o.is_closed ? "text-stone-600" : "text-stone-900",
          )}
        >
          {o.title}
        </h3>

        {meta.length > 0 && (
          <p className="text-small text-stone-600 mt-1">
            {meta.map((part, i) => (
              <span key={i}>
                {i > 0 && <span aria-hidden="true" className="mx-1.5 text-stone-400">·</span>}
                <span className={part.strong ? "font-semibold text-stone-800 tabular-nums" : undefined}>
                  {part.text}
                </span>
              </span>
            ))}
          </p>
        )}

        {o.description && (
          <p className="text-small text-stone-600 mt-2 line-clamp-2 max-w-prose">{o.description}</p>
        )}

        {o.tags.length > 0 && (
          <ul className="flex flex-wrap gap-1.5 mt-2.5" aria-label="Tags">
            {o.tags.map((tag) => (
              <li key={tag} className="px-2 py-0.5 rounded-md bg-stone-100 text-label text-stone-700">
                {tag}
              </li>
            ))}
          </ul>
        )}

      </div>

      {/* ---- What I can do ------------------------------------------------- */}
      {/* Under the content until `xl`: the sidebar takes its share from `md`,
          so at `lg` a call with no link still squeezed its title to ~240 px. */}
      <div className="w-full xl:w-auto xl:shrink-0 xl:max-w-xs flex flex-wrap xl:flex-col items-center xl:items-end justify-between xl:justify-start gap-3">
        <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-label font-semibold whitespace-nowrap", chip.className)}>
          <i className={cn("fas", o.is_closed ? "fa-lock" : "fa-clock")} aria-hidden="true" />
          {chip.label}
        </span>

        <div className="flex items-center gap-1">
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

          {!o.is_closed && (
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

          {o.external_url ? (
            <a
              href={o.external_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(LINK, FOCUS_RING, COLOUR_TRANSITION, "ml-1")}
            >
              {o.is_closed ? "View call" : "View & apply"}
              <i className="fas fa-arrow-up-right-from-square text-3xs" aria-hidden="true" />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          ) : (
            // No link means the poster gave none: say who to ask rather than
            // draw a button that goes nowhere.
            <span className="ml-1 text-small text-stone-600 xl:max-w-56 xl:text-right">
              No link given. Ask {o.posting_office.split("(")[0].trim() || "the posting office"}.
            </span>
          )}
        </div>

        {icsFailed && (
          <p role="alert" className="w-full xl:w-auto xl:max-w-64 xl:text-right flex items-start gap-1.5 text-small text-brand">
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden="true" />
            Could not build the calendar file. Try again.
          </p>
        )}
      </div>

      {/* ---- Who posted it, and the poster's own controls ----------------- */}
      {/* Last in the row, so the deadline and "View & apply" come before Delete
          in reading and tab order. From `xl` it lines up under the content. */}
      {(o.posted_by_name || o.can_edit) && (
        <div className="basis-full xl:pl-20 flex flex-wrap items-center gap-x-1 gap-y-1 text-label text-stone-600">
          {o.posted_by_name && <span className="mr-2">Posted by {o.posted_by_name}</span>}
          {o.can_edit && (
            <>
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
            </>
          )}
        </div>
      )}
    </article>
  );
}
