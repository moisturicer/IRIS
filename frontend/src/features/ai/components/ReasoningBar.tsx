import { useEffect, useState } from "react";
import type { ReaderActivity, ReaderRun } from "@/api/runtimeReader";
import { IrisLoader } from "@/components/brand/IrisBrand";
import { cn } from "@/lib/utils";

/**
 * What the heading says IRIS is doing (IR-1306), chosen from the phase and the
 * tool the run reported, never guessed. The server names a model phase
 * (Thinking, Writing the answer, Checking the answer) and each tool step
 * (`TOOL_STEPS` in `ai/runs/public.py`); every set below describes only that.
 */
const VERBS: Record<string, readonly string[]> = {
  waiting:    ["Waiting for a reading desk"],
  thinking:   ["Reading your question", "Planning where to look"],
  writing:    ["Writing the answer", "Setting down the citations"],
  checking:   ["Checking each citation", "Checking the figures"],
  search:     ["Searching the stacks", "Scanning the shelves"],
  lookup:     ["Finding the paper you named"],
  catalogue:  ["Consulting the catalogue"],
  count:      ["Counting the records"],
  details:    ["Reading the record's details"],
  read:       ["Reading the pages", "Reading closely"],
  outline:    ["Reading the table of contents"],
  recall:     ["Recalling this conversation"],
  reread:     ["Rereading an earlier answer"],
};

function verbKey(activity?: ReaderActivity | null): string {
  if (!activity) return "thinking";
  if (activity.phase === "waiting") return "waiting";
  const label = activity.label.toLowerCase();
  if (label.startsWith("writing")) return "writing";
  if (label.startsWith("checking")) return "checking";
  const step = activity.step;
  if (!step) return "thinking";
  const said = step.label.toLowerCase();
  if (step.kind === "recall") return said.includes("earlier answer") ? "reread" : "recall";
  if (step.kind === "catalogue") return said.includes("count") ? "count" : said.includes("details") ? "details" : "catalogue";
  if (step.kind === "search") return said.includes("looked up") ? "lookup" : "search";
  return said.includes("section") || said.includes("outline") ? "outline" : "read";
}

/** How long one verb stays before the next in its set. */
const VERB_MS = 3200;

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
 * IR-1306: the Folio Ribbon mark opens and closes in place of a spinner, and the heading names what the
 * run is doing in library words, from the phase and tool it reported, one rising into view after another.
 * The step chip and the titles under it are gone: the verb alone says what is happening. A screen reader hears one
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
  const verb = useVerb(VERBS[verbKey(activity)]);
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
        {/* What the run reported, for a screen reader: sighted readers have the verb. */}
        {activity && <p className="sr-only">{activity.step ? `${activity.label}. ${activity.step.label}` : activity.label}</p>}
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
