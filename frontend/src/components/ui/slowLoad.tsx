import { useCallback, useEffect, useState } from "react";

import { Button } from "./Button";

/** A loader says it is still working after this long (IR-1078, audit FB-02). */
export const SLOW_AFTER_MS = 2_000;
/** ...and offers Try again after this long, where the screen can read again. */
export const STUCK_AFTER_MS = 10_000;

export type LoadStage = "loading" | "slow" | "stuck";

/**
 * How long this loader has been on screen. It counts from mount, which is when
 * a screen starts waiting (every call site mounts its loader conditionally), and
 * `restart` begins the count again after the reader asks for another try.
 */
export function useLoadStage(): { stage: LoadStage; restart: () => void } {
  const [stage, setStage] = useState<LoadStage>("loading");
  const [run, setRun] = useState(0);

  useEffect(() => {
    setStage("loading");
    const slow = setTimeout(() => setStage("slow"), SLOW_AFTER_MS);
    const stuck = setTimeout(() => setStage("stuck"), STUCK_AFTER_MS);
    return () => {
      clearTimeout(slow);
      clearTimeout(stuck);
    };
  }, [run]);

  const restart = useCallback(() => setRun((n) => n + 1), []);
  return { stage, restart };
}

interface SlowLoadNoticeProps {
  stage: LoadStage;
  /** Reads again. Without it the line of text still appears and no button does. */
  onRetry?: () => void;
  onRestart: () => void;
  className?: string;
}

/**
 * The words under a loader that has gone on too long. It carries no live region
 * of its own: every caller puts it inside one (`Skeleton` and `LoadingRegion`
 * are `role="status"`, `Spinner`'s wrapper is `aria-live`), so the line is
 * announced as a change to a region the reader was already observing.
 */
export function SlowLoadNotice({ stage, onRetry, onRestart, className = "" }: SlowLoadNoticeProps) {
  if (stage === "loading") return null;
  return (
    <div className={`flex flex-col items-center gap-2 text-center text-small text-stone-700 ${className}`}>
      <p>{stage === "slow" ? "Still working…" : "This is taking too long."}</p>
      {stage === "stuck" && onRetry && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            onRestart();
            onRetry();
          }}
        >
          Try again
        </Button>
      )}
    </div>
  );
}
