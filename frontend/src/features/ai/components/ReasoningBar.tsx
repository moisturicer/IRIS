import { useEffect, useState } from "react";
import type { ReaderActivity } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";

const STEP_ICONS: Record<NonNullable<ReaderActivity["step"]>["kind"], string> = {
  read: "fas fa-book-open",
  search: "fas fa-magnifying-glass",
  catalogue: "fas fa-layer-group",
  recall: "fas fa-clock-rotate-left",
};

/** Seconds since `since`, to a tenth, refreshed while the run works. */
function useSeconds(since: string | undefined): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!since) return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [since]);
  const start = since ? Date.parse(since) : NaN;
  if (Number.isNaN(start)) return null;
  const seconds = Math.max(0, (now - start) / 1000);
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${String(Math.floor(seconds % 60)).padStart(2, "0")}s`;
}

/**
 * The live phase of a run, as a thread down the margin: what IRIS is doing now,
 * for how long, and the last thing it did. Only the phase is announced.
 */
export function ReasoningBar({ activity, runStartedAt, onStop, compact = false }: {
  activity: ReaderActivity;
  /** When the run started; the clock counts the whole run, not one phase. */
  runStartedAt?: string;
  onStop?: () => void;
  compact?: boolean;
}) {
  const elapsed = useSeconds(runStartedAt ?? activity.since);
  const step = activity.step;
  return (
    <section aria-label="Research progress" className={cn("relative pl-4", compact ? "text-[13px]" : "text-sm")}>
      {/* The thread: a quiet rule with a pulse travelling down it while IRIS works. */}
      <span aria-hidden className="absolute inset-y-0.5 left-0 w-[2px] overflow-hidden rounded-full bg-brand/15">
        <span className="absolute inset-x-0 h-1/2 bg-gradient-to-b from-transparent via-brand to-transparent motion-safe:animate-[iris-thread_1.6s_ease-in-out_infinite]" />
      </span>
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span key={activity.label} role="status" aria-live="polite"
          className={cn("font-display italic text-stone-900 motion-safe:animate-fade-in", compact ? "text-[15px]" : "text-[17px]")}>
          {activity.label}
        </span>
        {elapsed && <span className="font-mono text-[11px] tabular-nums text-stone-400">{elapsed}</span>}
        {onStop && <button type="button" onClick={onStop} aria-label="Stop research"
          className="ml-auto text-[12px] font-medium text-stone-500 underline-offset-2 hover:text-brand hover:underline">
          Stop
        </button>}
      </div>
      {step && <div key={`${step.kind}:${step.label}`} className="mt-1.5 motion-safe:animate-fade-in-up">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-50 px-2 py-0.5 text-[12px] font-medium text-brand">
          <i className={cn(STEP_ICONS[step.kind], "text-[10px]")} aria-hidden />{step.label}
        </span>
        {step.detail.length > 0 && <ul className="mt-1 space-y-0.5 text-[12px] text-stone-500">
          {step.detail.map(title => <li key={title} className="truncate">{title}</li>)}
        </ul>}
      </div>}
    </section>
  );
}
