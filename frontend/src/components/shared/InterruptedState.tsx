import { Button } from "@/components/ui/Button";

import { EmptyState } from "./EmptyState";

interface InterruptedStateProps {
  /** What was being loaded, in the reader's words: "delete requests". */
  what: string;
  onRetry: () => void;
}

/**
 * A read that got no answer in time (IR-914, ADR-061). It is not a refusal and
 * not an empty result: nothing is known about the server, so the one thing
 * offered is another try. The reader chooses it; nothing retries on its own.
 */
export function InterruptedState({ what, onRetry }: InterruptedStateProps) {
  return (
    <EmptyState
      tone="error"
      icon="fa-hourglass-half"
      title="This took too long"
      message={`The ${what} did not finish loading. Your connection or the server may be slow.`}
      action={<Button type="button" variant="outline" size="sm" onClick={onRetry}>Retry</Button>}
    />
  );
}
