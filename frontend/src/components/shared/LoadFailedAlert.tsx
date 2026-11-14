import { Button } from "@/components/ui/Button";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { cn } from "@/lib/utils";

interface LoadFailedAlertProps {
  /** The sentence from `failureMessage`, so it says who failed. */
  message: string;
  /** Reads again. Every list that fails offers it (IR-1078). */
  onRetry: () => void;
  className?: string;
}

/**
 * A list page's banner when its read failed, for pages that keep their header
 * and filters on screen and so cannot swap in a whole-section `EmptyState`.
 */
export function LoadFailedAlert({ message, onRetry, className }: LoadFailedAlertProps) {
  return (
    <div role="alert" className={cn(LOAD_ERROR, "items-center", className)}>
      <i className="fas fa-circle-exclamation" aria-hidden />
      <span className="flex-1">{message}</span>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>Try again</Button>
    </div>
  );
}
