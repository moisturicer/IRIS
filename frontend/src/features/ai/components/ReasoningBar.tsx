import { useEffect, useState } from "react";
import type { ReaderActivity } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";

const STEP_ICONS: Record<NonNullable<ReaderActivity["step"]>["kind"], string> = {
  read: "fas fa-book-open",
  search: "fas fa-magnifying-glass",
  catalogue: "fas fa-list-ul",
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

/** The live phase of a run: what it is doing now, how long it has been at it, and its latest step. */
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
    <section aria-label="Research progress"
      className={cn("rounded-xl border border-stone-200 bg-stone-50/80 text-stone-700 motion-safe:animate-fade-in",
        compact ? "text-[13px]" : "text-sm")}>
      <div className="flex items-center gap-2 px-3 py-2">
        <span aria-hidden className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-brand/25 border-t-brand animate-spin motion-reduce:animate-none" />
        <span role="status" aria-live="polite" className="font-semibold text-stone-900">{activity.label}…</span>
        {elapsed && <span className="tabular-nums text-stone-500">{elapsed}</span>}
        <span className="flex-1" />
        {onStop && <button type="button" onClick={onStop}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[12px] font-medium text-stone-600 hover:bg-stone-200/60 hover:text-stone-900">
          <i className="fas fa-stop text-[9px]" aria-hidden />Stop
        </button>}
      </div>
      {step && <div key={`${step.kind}:${step.label}`} className="border-t border-stone-200 px-3 py-2 motion-safe:animate-fade-in-up">
        <p className="flex items-center gap-2 font-medium text-brand">
          <i className={cn(STEP_ICONS[step.kind], "w-4 text-center text-[12px]")} aria-hidden />{step.label}
        </p>
        {step.detail.map(title => <p key={title} className="mt-0.5 pl-6 text-stone-600 [overflow-wrap:anywhere]">{title}</p>)}
      </div>}
    </section>
  );
}
