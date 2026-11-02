import { Suspense, type ReactNode } from "react";

import { Spinner } from "@/components/ui/Spinner";

interface DeferredPageProps {
  name: string;
  children: ReactNode;
}

/**
 * Keeps the authenticated app shell visible while a route-level bundle loads.
 * The spinner owns the live announcement; the visible copy is decorative so
 * assistive technology hears the loading message once.
 */
export function DeferredPage({ name, children }: DeferredPageProps) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-stone-600">
          <Spinner size="lg" label={`Loading ${name}`} />
          <p aria-hidden="true" className="text-sm">Loading {name}…</p>
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
