import { useEffect, useState } from "react";
import type { StreamingState } from "../hooks/useAskStream";
import { cn } from "@/lib/utils";

/** "12s", "1m 05s": time since submission, truthfully and without decimals. */
export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

function useElapsed(startedAt: number | undefined): string | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt === undefined) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  return startedAt === undefined || now - startedAt < 1000 ? null : formatElapsed(now - startedAt);
}

/**
 * The one status row while an answer is being prepared (IR-596): the
 * server's lifecycle state, the time since submission and Stop. Only the
 * label sits in the polite live region, so a ticking clock is not announced.
 */
export function StreamStatusRow({
  state,
  onStop,
  className,
}: {
  state: StreamingState;
  /** Cancel the queued run being followed (IR-548); offered only for one. */
  onStop?: () => void;
  className?: string;
}) {
  const elapsed = useElapsed(state.startedAt);

  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[14px] font-medium text-stone-500", className)}>
      <span className="inline-flex items-center gap-2">
        <span
          aria-hidden
          className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse motion-reduce:animate-none"
        />
        <span role="status" aria-live="polite">{state.label}</span>
      </span>
      {elapsed && <span className="font-normal tabular-nums">{elapsed}</span>}
      {onStop && state.runId && (
        <button
          type="button"
          onClick={onStop}
          className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5
            text-[13px] font-medium text-stone-600 hover:border-stone-300 hover:text-stone-900"
        >
          <i className="fas fa-stop text-[10px]" aria-hidden />
          Stop answering
        </button>
      )}
    </div>
  );
}
