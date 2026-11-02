import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface StatusScreenProps {
  /** A Font Awesome icon class, e.g. `fa-compass`. Decorative only. */
  icon:      string;
  title:     string;
  message?:  ReactNode;
  /**
   * Small print under the message, for someone reporting the problem
   * (`Error 404`). Never the headline: a status code is not the server's
   * wording and means nothing to most readers (IR-745).
   */
  code?:     string;
  /** The way out: links or buttons the caller renders, primary first. */
  actions?:  ReactNode;
  /** Anything below the actions, such as a details disclosure. */
  children?: ReactNode;
  /**
   * `error` is for something that failed rather than something that is not
   * there. It is announced as an alert, and its icon sits on maroon.
   */
  tone?:     "neutral" | "error";
  /**
   * Fill the window, for a screen drawn with no app shell around it -- the
   * last-resort fallback when the shell itself failed.
   */
  standalone?: boolean;
}

/**
 * A whole page that stands in for the page someone asked for (IR-745): Not
 * found, Access denied, Something went wrong.
 *
 * One component so the three read alike. It owns the page's `h1`, because
 * it replaces the page that would have had one. `EmptyState` is the
 * section-sized sibling, for a list or feed with nothing to show.
 */
export function StatusScreen({
  icon,
  title,
  message,
  code,
  actions,
  children,
  tone = "neutral",
  standalone = false,
}: StatusScreenProps) {
  const error = tone === "error";

  return (
    <div
      className={cn(
        "flex items-center justify-center px-4 py-16",
        standalone ? "min-h-screen bg-canvas" : "min-h-[60vh]",
      )}
    >
      <div role={error ? "alert" : undefined} className="w-full max-w-md text-center">
        <div
          className={cn(
            "mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl text-xl",
            error ? "bg-brand-50 text-brand" : "bg-stone-100 text-stone-500",
          )}
        >
          <i className={cn("fas", icon)} aria-hidden="true" />
        </div>
        <h1 className="font-display text-title font-semibold text-stone-900">{title}</h1>
        {message && <div className="mt-2 text-body text-stone-600">{message}</div>}
        {code && <p className="mt-3 text-label font-medium uppercase tracking-wide text-stone-500">{code}</p>}
        {actions && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">{actions}</div>
        )}
        {children && <div className="mt-6 text-left">{children}</div>}
      </div>
    </div>
  );
}
