import { useEffect, useState } from "react";
import type { ReaderActivity, ReaderRun } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";
import { BookIcon, CheckIcon, CircleDotIcon, CircleIcon, HistoryIcon, LayersIcon, OutlineIcon, SearchIcon, WarningIcon } from "./AskIrisIcons";

const STEP_ICONS: Record<NonNullable<ReaderActivity["step"]>["kind"], OutlineIcon> = {
  read: BookIcon,
  search: SearchIcon,
  catalogue: LayersIcon,
  recall: HistoryIcon,
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

type PlanStep = NonNullable<ReaderRun["plan"]>["steps"][number];

/** What each plan status looks like: a mark that differs by shape, never by colour alone, and its word for a screen reader. */
const PLAN_STATUS: Record<PlanStep["status"], { word: string; Mark: OutlineIcon; tone: string }> = {
  done: { word: "Done", Mark: CheckIcon, tone: "text-brand" },
  in_progress: { word: "In progress", Mark: CircleDotIcon, tone: "text-brand" },
  pending: { word: "Upcoming", Mark: CircleIcon, tone: "text-stone-400" },
  blocked: { word: "Blocked", Mark: WarningIcon, tone: "text-stone-700" },
};

/**
 * One quiet block while a run is queued or running (IR-1236): a heading, then only what the run
 * reports -- its activity (the phase and latest step) and its plan. The page adds no step of its own,
 * so a run that has reported nothing shows the heading alone. Everything but the clock sits in one
 * polite live region, so an update is announced without interrupting the reader.
 */
export function ReasoningBar({ activity, plan, deep = false, runStartedAt, compact = false }: {
  activity?: ReaderActivity | null;
  plan?: ReaderRun["plan"];
  /** A thorough run says so in its heading. */
  deep?: boolean;
  /** When the run started; the clock counts the whole run, not one phase. */
  runStartedAt?: string;
  compact?: boolean;
}) {
  const elapsed = useSeconds(runStartedAt ?? activity?.since);
  const step = activity?.step;
  const steps = plan?.steps ?? [];
  const StepIcon = step ? STEP_ICONS[step.kind] : null;
  return (
    <section aria-label="Research progress" className={cn("relative pl-4", compact ? "text-small" : "text-control")}>
      {/* The thread: a quiet rule with a pulse travelling down it while IRIS works. */}
      <span aria-hidden className="absolute inset-y-0.5 left-0 w-[2px] overflow-hidden rounded-full bg-brand/15">
        <span className="absolute inset-x-0 h-1/2 bg-gradient-to-b from-transparent via-brand to-transparent motion-safe:animate-[iris-thread_1.6s_ease-in-out_infinite]" />
      </span>
      <div aria-live="polite" className="space-y-2">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span aria-hidden className="size-4 shrink-0 rounded-full border-2 border-stone-200 border-t-brand motion-safe:animate-spin" />
          <h3 className="text-body font-semibold text-stone-900">{deep ? "Thorough research…" : "Researching…"}</h3>
          {/* Decoration for sighted readers: a clock ticking in a live region would be read out every tenth of a second. */}
          {elapsed && <span aria-hidden className="font-mono text-small tabular-nums text-stone-500">{elapsed}</span>}
        </div>
        {activity && <p key={activity.label} className="text-stone-700 motion-safe:animate-fade-in">{activity.label}</p>}
        {step && <div key={`${step.kind}:${step.label}`} className="motion-safe:animate-fade-in-up">
          <span className="inline-flex items-center gap-1.5 rounded-control bg-surface px-2 py-0.5 text-small font-medium text-brand ring-1 ring-stone-300">
            {StepIcon && <StepIcon inline />}{step.label}
          </span>
          {step.detail.length > 0 && <ul className="mt-1 space-y-0.5 text-small text-stone-600">
            {step.detail.map(title => <li key={title} className="[overflow-wrap:anywhere]">{title}</li>)}
          </ul>}
        </div>}
        {steps.length > 0 && <ol aria-label="Research plan" className="space-y-1.5">
          {steps.map(item => {
            const { word, Mark, tone } = PLAN_STATUS[item.status];
            return <li key={item.id} aria-current={item.status === "in_progress" ? "step" : undefined}
              className={cn("flex items-baseline gap-2.5 break-words [overflow-wrap:anywhere]",
                item.status === "in_progress" ? "text-stone-900" : item.status === "pending" ? "text-stone-500" : "text-stone-700")}>
              <Mark inline className={cn("self-center", tone)} />
              <span className="min-w-0">{item.title}{" "}<span className={item.status === "blocked" ? "text-small text-stone-600" : "sr-only"}>{word}</span></span>
            </li>;
          })}
        </ol>}
      </div>
    </section>
  );
}
