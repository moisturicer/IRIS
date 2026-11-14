import { Button } from "@/components/ui/Button";
import { RequestTimeoutError } from "@/api/requestPolicy";
import { failureMessage } from "@/lib/readFailure";

import { EmptyState } from "./EmptyState";

interface InterruptedStateProps {
  /** What was being loaded, in the reader's words: "delete requests". */
  what: string;
  onRetry: () => void;
  /** Draw it as a card of its own, as `EmptyState` does for a feed. */
  framed?: boolean;
}

/**
 * A read that got no answer in time (IR-914, ADR-061). It is not a refusal and
 * not an empty result: nothing is known about the server, so the one thing
 * offered is another try. The reader chooses it; nothing retries on its own.
 */
export function InterruptedState({ what, onRetry, framed }: InterruptedStateProps) {
  return (
    <EmptyState
      framed={framed}
      tone="error"
      icon="fa-hourglass-half"
      title="This took too long"
      message={failureMessage(new RequestTimeoutError(0), { lead: `The ${what} did not finish loading.` })}
      action={<Button type="button" variant="outline" size="sm" onClick={onRetry}>Try again</Button>}
    />
  );
}
