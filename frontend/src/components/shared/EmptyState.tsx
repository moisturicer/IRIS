import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  /** A Font Awesome icon class, e.g. `fa-inbox`. Decorative only. */
  icon?:    string;
  title:    string;
  message?: ReactNode;
  /** The next step, when there is one: a button or link the caller renders. */
  action?:  ReactNode;
  /**
   * `error` is for a load that failed, not for an empty result. It is
   * announced as an alert, and its icon sits on maroon rather than grey.
   */
  tone?:    "neutral" | "error";
  /** Draw it as a card of its own, for a feed with no other frame around it. */
  framed?:  boolean;
}

/**
 * What a list, feed or section shows when it has nothing to show (IR-405).
 *
 * One component for every screen, so "nothing here yet", "nothing matches"
 * and "this did not load" look and read alike everywhere. The title is a
 * heading, so it can be reached by heading navigation like the content it
 * stands in for.
 */
export function EmptyState({
  icon = "fa-inbox",
  title,
  message,
  action,
  tone = "neutral",
  framed = false,
}: EmptyStateProps) {
  const error = tone === "error";

  return (
    <div
      role={error ? "alert" : undefined}
      className={cn(
        "flex flex-col items-center justify-center text-center px-6 py-16",
        framed && "bg-white rounded-2xl border border-stone-200",
      )}
    >
      <div
        className={cn(
          "w-12 h-12 rounded-xl flex items-center justify-center mb-3 text-lg",
          error ? "bg-brand-50 text-brand" : "bg-stone-100 text-stone-500",
        )}
      >
        <i className={cn("fas", icon)} aria-hidden="true" />
      </div>
      <h2 className="text-heading font-semibold text-stone-900">{title}</h2>
      {message && <p className="text-small text-stone-600 mt-1 max-w-sm">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
