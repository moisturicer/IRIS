import type { ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
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
  message: ReactNode;
  onRetry: () => void;
}

/**
 * A framed section that did not load (IR-906): interrupted, with a Retry, when
 * the request timed out; otherwise a failure with Try again. One component so a
 * screen cannot show one of the two and forget the other.
 */
export function ReadFailedState({ interrupted, what, title, message, onRetry }: ReadFailedStateProps) {
  if (interrupted) return <InterruptedState framed what={what} onRetry={onRetry} />;
  return (
    <EmptyState
      framed
      tone="error"
      icon="fa-plug-circle-xmark"
      title={title}
      message={message}
      action={<button type="button" onClick={onRetry} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>}
    />
  );
}
