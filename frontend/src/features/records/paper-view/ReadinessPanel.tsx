import { useId } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { Readiness, ReadinessItem } from "@/types/records";

import { RailHeading } from "./headings";
import { VERDICT_ICON } from "./yourPart";

/** The words on an item's link. The act behind it is the host's existing control. */
const ACTION_WORDS: Record<string, string> = {
  open_review: "Open review",
  claim: "Claim review",
  withdraw_revision: "Withdraw request",
  open_documents: "Open Documents",
  show_party: "Show reviewers",
  route: "Request review",
  show_threads: "Show threads",
};

/**
 * Readiness (ADR-032 §10 Amendment, IR-681): the server's verdict in words,
 * then each fact behind it. Blockers are maroon and marked "Blocker";
 * information has an outline. The browser words no verdict, no blocker and no
 * status sentence: every string here is the server's, and an offered action
 * dispatches to a control the page already has.
 */
export function ReadinessPanel({ readiness, onAction, id }: {
  readiness: Readiness;
  onAction: (action: NonNullable<ReadinessItem["action"]>) => void;
  /** Where the pane head's summary jumps to. */
  id?: string;
}) {
  const headingId = useId();
  return (
    <section id={id} tabIndex={-1} aria-labelledby={headingId} className={cn("space-y-3 rounded", FOCUS_RING)}>
      <RailHeading id={headingId}>Readiness</RailHeading>
      {/* No side stripe: the icon and the words carry the verdict (IR-1094, spec §4.9). */}
      <p
        role="status"
        className="flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-small font-semibold text-stone-900"
      >
        <i className={cn("fas", VERDICT_ICON[readiness.verdict])} aria-hidden />
        {readiness.headline}
      </p>
      <ReadinessFacts items={readiness.items} onAction={onAction} />
    </section>
  );
}

/**
 * Each fact behind a verdict, in the server's words: a blocker is marked
 * "Blocker" in words and an icon; information has an outline. The offered
 * action dispatches to a control the page already has. The review workspace
 * lists these under Details (IR-1094); the author's pane lists them in its
 * Readiness card.
 */
export function ReadinessFacts({ items, onAction }: {
  items: readonly ReadinessItem[];
  onAction: (action: NonNullable<ReadinessItem["action"]>) => void;
}) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="What readiness depends on" className="space-y-2">
      {items.map((item, i) => (
        <li
          key={`${item.kind}-${i}`}
          className={cn(
            "rounded-lg px-3 py-2 text-small",
            item.severity === "blocker" ? "bg-stone-100 text-stone-900" : "border border-stone-300 text-stone-700",
          )}
        >
          <p>
            {item.severity === "blocker" && (
              <span className="mr-1.5 font-semibold text-brand">
                <i className="fas fa-ban mr-1 text-2xs" aria-hidden />
                Blocker:
              </span>
            )}
            {item.severity === "blocker" ? " " : <i className="fas fa-circle-info mr-1.5 text-2xs text-stone-500" aria-hidden />}
            {item.label}
          </p>
          {(item.actor_name || item.since || item.paused || item.action) && (
            <p className="mt-0.5 text-2xs text-stone-600">
              {[
                item.actor_name,
                item.since && `since ${formatDate(item.since)}`,
                item.paused && "clock paused",
              ].filter(Boolean).join(" · ")}
              {item.action && ACTION_WORDS[item.action.kind] && (
                <button
                  type="button"
                  onClick={() => onAction(item.action!)}
                  className={cn("ml-2 font-semibold text-brand hover:underline", FOCUS_RING)}
                >
                  {ACTION_WORDS[item.action.kind]}
                </button>
              )}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
