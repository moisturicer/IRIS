import { Suspense, type ReactNode } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { reloadPage } from "@/lib/readFailure";

interface DeferredPageProps {
  /**
   * What is loading, in the reader's words and without the ellipsis: "Opening
   * the paper", not a component's name (IR-1098, audit US-09).
   */
  message: string;
  children: ReactNode;
}

/**
 * Keeps the authenticated app shell visible while a route-level bundle loads.
 * The spinner owns the live announcement; the visible copy is decorative so
 * assistive technology hears the loading message once.
 */
export function DeferredPage({ message, children }: DeferredPageProps) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-stone-600">
          <Spinner size="lg" label={message} onRetry={reloadPage} />
          <p aria-hidden="true" className="text-sm">{message}…</p>
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
