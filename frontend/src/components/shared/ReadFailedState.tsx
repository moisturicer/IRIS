import type { ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { failureMessage } from "@/lib/readFailure";
import { cn } from "@/lib/utils";

import { EmptyState } from "./EmptyState";
import { InterruptedState } from "./InterruptedState";

interface ReadFailedStateProps {
  /** The read got no answer in time (`readFailureKind` said `interrupted`). */
  interrupted: boolean;
  /** What was being loaded, in the reader's words: "your research". */
  what: string;
  /** The headline for a read that failed outright: "Could not load your research". */
  title: string;
  /** Overrides the sentence `failureMessage` would pick, for a screen with its own reassurance to give. */
  message?: ReactNode;
  /** What was or was not done, put in front of the cause: "Nothing was changed." */
  lead?: string;
  /** The failure, when the screen kept it; the cause is read from it. */
  error?: unknown;
  onRetry: () => void;
}

/**
 * A framed section that did not load (IR-906): interrupted, with a Retry, when
 * the request timed out; otherwise a failure with Try again. One component so a
 * screen cannot show one of the two and forget the other.
 */
export function ReadFailedState({ interrupted, what, title, message, lead, error, onRetry }: ReadFailedStateProps) {
  if (interrupted) return <InterruptedState framed what={what} onRetry={onRetry} />;
  return (
    <EmptyState
      framed
      tone="error"
      icon="fa-plug-circle-xmark"
      title={title}
      message={message ?? failureMessage(error, { lead })}
      action={<button type="button" onClick={onRetry} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>}
    />
  );
}
