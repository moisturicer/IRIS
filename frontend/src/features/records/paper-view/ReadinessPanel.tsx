import { useId } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { Readiness, ReadinessItem, ReadinessVerdict } from "@/types/records";

import { RailHeading } from "./headings";

/** A glyph beside the server's verdict, never instead of it. */
const VERDICT_ICON: Record<ReadinessVerdict, string> = {
  ready: "fa-circle-check",
  blocked: "fa-circle-xmark",
  waiting_on_you: "fa-circle-exclamation",
  none: "fa-circle-info",
};

/** The words on an item's link. The act behind it is the host's existing control. */
const ACTION_WORDS: Record<string, string> = {
  open_review: "Open review",
  claim: "Claim review",
  withdraw_revision: "Withdraw request",
  open_documents: "Open Documents",
  show_party: "Show reviewers",
  route: "Request review",
};

/**
 * Readiness (ADR-032 §10 Amendment, IR-681): the server's verdict in words,
 * then each fact behind it. Blockers are maroon and marked "Blocker";
 * information has an outline. The browser words no verdict, no blocker and no
 * status sentence: every string here is the server's, and an offered action
 * dispatches to a control the page already has.
 */
export function ReadinessPanel({ readiness, onAction }: {
  readiness: Readiness;
  onAction: (action: NonNullable<ReadinessItem["action"]>) => void;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <RailHeading id={headingId}>Readiness</RailHeading>
      <p
        role="status"
        className={cn(
          "flex items-center gap-2 rounded-lg px-3 py-2 text-small font-semibold",
          readiness.verdict === "ready" ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-900",
        )}
      >
        <i className={cn("fas", VERDICT_ICON[readiness.verdict])} aria-hidden />
        {readiness.headline}
      </p>
      {readiness.items.length > 0 && (
        <ul aria-label="What readiness depends on" className="space-y-2">
          {readiness.items.map((item, i) => (
            <li
              key={`${item.kind}-${i}`}
              className={cn(
                "rounded-lg px-3 py-2 text-small",
                item.severity === "blocker"
                  ? "border-l-[3px] border-brand bg-stone-100 text-stone-900"
                  : "border border-stone-300 text-stone-700",
              )}
            >
              <p>
                {item.severity === "blocker" && (
                  <span className="mr-1.5 font-semibold text-brand">
                    <i className="fas fa-ban mr-1 text-2xs" aria-hidden />
                    Blocker:
                  </span>
                )}
                {item.severity === "blocker" && " "}
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
      )}
    </section>
  );
}
