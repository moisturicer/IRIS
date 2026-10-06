/**
 * One card for a research record (IR-405; spec §4.12).
 *
 * It replaces four renderings of a record as each screen adopts it: Discover's
 * card (F2), My Library's rows and My Workspace's case card (F4), and the
 * review queue's rows (IR-268). It is presentation only. Every slot is filled
 * by the caller, so the card never fetches, never decides what a viewer may
 * do, and never words a status: that wording comes from the server.
 *
 * The title is the card's one link. It is stretched over the whole card, so
 * the card is a single large target without an `onClick` on the article.
 * Only `status` and `actions` sit above that link, so **only they may hold
 * controls**. Everything else is text: a link put in the byline or summary
 * would sit under the stretched link and could not be clicked.
 */
import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

interface ResearchCardProps {
  /** Where the title leads: the record's Paper View. */
  href:      string;
  title:     string;
  /** `list` is a full-width row for feeds; `grid` a compact tile. */
  layout?:   "list" | "grid";
  /** The line above the title: category and record type. */
  eyebrow?:  ReactNode;
  /** Set at the end of the eyebrow line, e.g. the year. */
  meta?:     ReactNode;
  /** Authors. */
  byline?:   ReactNode;
  /** The abstract or a summary, clamped. */
  summary?:  ReactNode;
  /** The status line: typically a `StatusBadge` and where the record is. */
  status?:   ReactNode;
  /** What happens next, for whoever is looking. Prefixed "Next step:". */
  nextStep?: ReactNode;
  /** Passive facts in the footer: views, files, dates. */
  footer?:   ReactNode;
  /** Buttons and menus in the footer: Save, Cite, Continue. */
  actions?:  ReactNode;
  /** The title's heading level; 2 under a page's `h1`, 3 inside a section. */
  headingLevel?: 2 | 3;
}

export function ResearchCard({
  href,
  title,
  layout = "list",
  eyebrow,
  meta,
  byline,
  summary,
  status,
  nextStep,
  footer,
  actions,
  headingLevel = 2,
}: ResearchCardProps) {
  const titleId = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const grid = layout === "grid";
  const hasFooter = Boolean(footer || actions);

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        "group relative flex flex-col bg-white rounded-xl border border-stone-200",
        COLOUR_TRANSITION,
        "hover:border-stone-400",
        "focus-within:border-stone-400",
        grid && "h-full",
      )}
    >
      <div className={cn("flex-1 p-card-compact md:p-card", grid && "flex flex-col")}>
        {(eyebrow || meta) && (
          <div className="flex items-start justify-between gap-3 mb-1.5 text-label font-medium text-stone-600">
            {eyebrow && <span className="min-w-0">{eyebrow}</span>}
            {meta && <span className="shrink-0 whitespace-nowrap ml-auto">{meta}</span>}
          </div>
        )}

        <Heading
          id={titleId}
          className={cn(
            "font-display font-semibold text-stone-900",
            grid ? "text-title line-clamp-3" : "text-title md:text-display",
          )}
        >
          <Link
            to={href}
            className={cn(
              "rounded-sm hover:text-brand",
              COLOUR_TRANSITION,
              FOCUS_RING,
              // The stretched target: the whole card follows the title link.
              "after:absolute after:inset-0 after:rounded-xl after:content-['']",
            )}
          >
            {title}
          </Link>
        </Heading>

        {byline && <p className="mt-1 text-small font-medium text-brand truncate">{byline}</p>}

        {summary && (
          <p className={cn("mt-2 text-body text-stone-600", grid ? "line-clamp-4" : "line-clamp-3")}>
            {summary}
          </p>
        )}

        {(status || nextStep) && (
          <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1.5 text-small", grid ? "mt-auto pt-4" : "mt-3")}>
            {status && <span className="relative z-10 inline-flex items-center gap-2">{status}</span>}
            {nextStep && (
              <p className="inline-flex items-start gap-1.5 text-stone-700">
                <i className="fas fa-arrow-right mt-1 text-stone-500" aria-hidden="true" />
                <span>
                  <span className="font-semibold">Next step:</span> {nextStep}
                </span>
              </p>
            )}
          </div>
        )}
      </div>

      {hasFooter && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-stone-100 px-card-compact md:px-card py-3">
          {footer && <div className="flex flex-wrap items-center gap-4 text-small text-stone-600">{footer}</div>}
          {actions && <div className="relative z-10 ml-auto flex items-center gap-1.5">{actions}</div>}
        </div>
      )}
    </article>
  );
}
