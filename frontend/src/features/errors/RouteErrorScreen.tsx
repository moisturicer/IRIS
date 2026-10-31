import { useState } from "react";
import { isRouteErrorResponse, useLocation, useNavigate, useRouteError } from "react-router-dom";

import { StatusScreen } from "@/components/shared/StatusScreen";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";

import { NotFoundScreen } from "./NotFoundScreen";

/** Router state key counting how many times Try again has re-rendered this address. */
const RETRIES = "irisCrashRetries";

interface RouteErrorScreenProps {
  /**
   * Drawn with no app shell around it: the last-resort fallback for a crash
   * in the shell itself. Its links are full page loads, because the router
   * tree that would handle a client-side one is the thing that failed.
   */
  standalone?: boolean;
}

function describe(error: unknown): string {
  if (isRouteErrorResponse(error)) return `${error.status} ${error.statusText}`.trim();
  if (error instanceof Error) return error.message || error.name;
  if (typeof error === "string") return error;
  return "Unknown error";
}

/**
 * A page that failed while rendering (IR-745), placed as a route's
 * `errorElement`.
 *
 * Inside the shell it replaces only the page, so the sidebar and everything
 * held in memory survive. Try again first re-renders the same address in
 * place, which keeps that memory; if the page fails again, Reload page is
 * offered too, which costs it.
 *
 * There is no reference number. IRIS sends crashes nowhere, so a number would
 * point at nothing (PRODUCT.md: never invent what the system cannot supply).
 * What a reader can pass on is the details below, copied by hand.
 */
export function RouteErrorScreen({ standalone = false }: RouteErrorScreenProps) {
  const error = useRouteError();
  const location = useLocation();
  const navigate = useNavigate();
  const [occurredAt] = useState(() => new Date());
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  // A loader or the router itself saying 404 is a missing page, not a crash.
  if (isRouteErrorResponse(error) && error.status === 404 && !standalone) {
    return <NotFoundScreen />;
  }

  const state = (location.state ?? {}) as Record<string, unknown>;
  const retries = typeof state[RETRIES] === "number" ? (state[RETRIES] as number) : 0;
  const address = `${location.pathname}${location.search}${location.hash}`;
  const details = [
    `Address: ${address}`,
    `Time: ${occurredAt.toISOString()}`,
    `Error: ${describe(error)}`,
  ].join("\n");

  const tryAgain = () => {
    if (standalone) {
      window.location.reload();
      return;
    }
    // Navigating to the same address clears the route's error and renders
    // the page afresh; the counter rides in router state so a second failure
    // can tell it was retried.
    navigate(address, { replace: true, state: { ...state, [RETRIES]: retries + 1 } });
  };

  const copyDetails = async () => {
    try {
      await navigator.clipboard.writeText(details);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };

  const discover = pathFor("discover");

  return (
    <StatusScreen
      tone="error"
      standalone={standalone}
      icon="fa-triangle-exclamation"
      title="Something went wrong"
      message={
        retries > 0
          ? "This page failed again. Reloading starts IRIS afresh, which clears anything you had typed but not saved."
          : "IRIS couldn't show this page. Nothing you saved has been lost."
      }
      actions={
        <>
          <button type="button" onClick={tryAgain} className={cn(PILL_PRIMARY, FOCUS_RING)}>
            Try again
          </button>
          {retries > 0 && !standalone && (
            <button type="button" onClick={() => window.location.reload()} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Reload page
            </button>
          )}
          {standalone ? (
            <a href={discover} className={cn(PILL_SECONDARY, FOCUS_RING)}>Go to Discover</a>
          ) : (
            <button type="button" onClick={() => navigate(discover)} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Go to Discover
            </button>
          )}
        </>
      }
    >
      <details className="rounded-xl border border-stone-200 bg-surface px-4 py-3 text-small text-stone-700">
        <summary className={cn("cursor-pointer font-semibold text-stone-800 rounded", FOCUS_RING)}>
          Details for RDCO
        </summary>
        <p className="mt-2 text-stone-600">
          If this keeps happening, send these details to the Research and Development Coordinating Office.
        </p>
        <pre className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-stone-100 p-3 font-mono text-label text-stone-800">
          {details}
        </pre>
        <div className="mt-3 flex items-center gap-3">
          <button type="button" onClick={copyDetails} className={cn(PILL_SECONDARY, FOCUS_RING)}>
            Copy details
          </button>
          <span role="status" className="text-small text-stone-600">
            {copy === "copied" && "Copied."}
            {copy === "failed" && "Couldn't copy. Select the text above instead."}
          </span>
        </div>
      </details>
    </StatusScreen>
  );
}
