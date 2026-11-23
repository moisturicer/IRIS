import { useEffect, useState } from "react";
import type { ReaderActivity, ReaderRun } from "@/api/runtimeReader";
import { IrisLoader } from "@/components/brand/IrisBrand";
import { cn } from "@/lib/utils";

const STEP_ICONS: Record<NonNullable<ReaderActivity["step"]>["kind"], string> = {
  read: "fas fa-book-open",
  search: "fas fa-magnifying-glass",
  catalogue: "fas fa-layer-group",
  recall: "fas fa-clock-rotate-left",
};

/**
 * What the heading says IRIS is doing (IR-1306), in the library's own words.
 * Each set describes only the kind of step the run reported, so turning
 * through it never claims work the run is not doing.
 */
const VERBS = {
  waiting:   ["Waiting for a reading desk"],
  starting:  ["Reading your question", "Planning where to look"],
  search:    ["Searching the stacks", "Scanning the shelves", "Pulling likely papers"],
  read:      ["Reading the pages", "Following the passage", "Reading closely"],
  catalogue: ["Consulting the catalogue", "Checking the records"],
  recall:    ["Rereading earlier answers", "Recalling this conversation"],
} as const;

/** How long one verb stays before the next in its set. */
const VERB_MS = 3200;

function verbsFor(activity?: ReaderActivity | null): readonly string[] {
  if (!activity) return VERBS.starting;
  if (activity.step) return VERBS[activity.step.kind];
  return activity.phase === "waiting" ? VERBS.waiting : VERBS.starting;
}

/** Turns through `verbs`, starting again whenever the set changes. */
function useVerb(verbs: readonly string[]): string {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    setIndex(0);
    if (verbs.length < 2) return;
    const timer = setInterval(() => setIndex(i => (i + 1) % verbs.length), VERB_MS);
    return () => clearInterval(timer);
  }, [verbs]);
  return verbs[index % verbs.length];
}

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
const PLAN_STATUS: Record<PlanStep["status"], { word: string; mark: string }> = {
  done: { word: "Done", mark: "fas fa-check text-brand" },
  in_progress: { word: "In progress", mark: "fas fa-circle text-brand" },
  pending: { word: "Upcoming", mark: "far fa-circle text-stone-400" },
  blocked: { word: "Blocked", mark: "fas fa-triangle-exclamation text-stone-700" },
};

/**
 * One quiet block while a run is queued or running (IR-1236): a heading, then only what the run
 * reports -- its activity (the phase and latest step) and its plan. The page adds no step of its own,
 * so a run that has reported nothing shows the heading alone. Everything but the clock and the
 * turning verb sits in one polite live region, so an update is announced without interrupting.
 *
 * IR-1306: the Folio Ribbon mark opens and closes in place of a spinner, and the heading names the
 * kind of step in library words, one rising into view after another. A screen reader hears one
 * steady heading instead, since a verb changing every few seconds would be read out each time.
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
  const verb = useVerb(verbsFor(activity));
  const step = activity?.step;
  const steps = plan?.steps ?? [];
  return (
    <section aria-label="Research progress" className={cn("relative pl-4", compact ? "text-small" : "text-control")}>
      {/* The ribbon: a quiet rule with a marker travelling down it while IRIS works. */}
      <span aria-hidden className="absolute inset-y-0.5 left-0 w-[2px] overflow-hidden rounded-full bg-brand/15">
        <span className="absolute inset-x-0 h-1/2 bg-gradient-to-b from-transparent via-brand to-transparent motion-safe:animate-[iris-thread_1.6s_ease-in-out_infinite]" />
      </span>
      <div aria-live="polite" className="space-y-2">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <IrisLoader className="size-[18px] shrink-0 text-brand" />
          <h3 className="text-body font-semibold text-stone-900">
            <span className="sr-only">{deep ? "Thorough research…" : "Researching…"}</span>
            <span aria-hidden className="inline-block overflow-hidden align-bottom">
              <span key={verb} className="inline-block motion-safe:animate-verb-in">{verb}…</span>
            </span>
          </h3>
          {deep && <span className="rounded-full px-2 py-px text-label font-medium text-stone-600 ring-1 ring-stone-300">Thorough</span>}
          {/* Decoration for sighted readers: a clock ticking in a live region would be read out every tenth of a second. */}
          {elapsed && <span aria-hidden className="text-small tabular-nums text-stone-500">{elapsed}</span>}
        </div>
        {activity && <p key={activity.label} className="text-stone-700 motion-safe:animate-fade-in">{activity.label}</p>}
        {step && <div key={`${step.kind}:${step.label}`} className="space-y-1">
          <p className="inline-flex items-center gap-2 text-small font-medium text-stone-800 motion-safe:animate-fade-in-up">
            <i className={cn(STEP_ICONS[step.kind], "w-4 text-center text-label text-brand")} aria-hidden />{step.label}
          </p>
          {/* Paper titles, so in the titles' own Garamond, pulled out one after another. */}
          {step.detail.length > 0 && <ul className="space-y-0.5 pl-6">
            {step.detail.map((title, index) => <li key={title}
              style={{ animationDelay: `${Math.min(index, 5) * 70}ms` }}
              className="font-display text-body leading-snug text-stone-700 [overflow-wrap:anywhere] motion-safe:animate-shelf-in">
              {title}
            </li>)}
          </ul>}
        </div>}
        {steps.length > 0 && <ol aria-label="Research plan" className="space-y-1.5">
          {steps.map(item => {
            const { word, mark } = PLAN_STATUS[item.status];
            return <li key={item.id} aria-current={item.status === "in_progress" ? "step" : undefined}
              className={cn("flex items-baseline gap-2.5 break-words [overflow-wrap:anywhere]",
                item.status === "in_progress" ? "text-stone-900" : item.status === "pending" ? "text-stone-500" : "text-stone-700")}>
              <i aria-hidden className={cn(mark, "w-4 shrink-0 text-center text-small")} />
              <span className="min-w-0">{item.title}{" "}<span className={item.status === "blocked" ? "text-small text-stone-600" : "sr-only"}>{word}</span></span>
            </li>;
          })}
        </ol>}
      </div>
    </section>
  );
}
