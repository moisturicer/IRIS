import { useId, useState } from "react";
import type { AgentStepEvent, CoverageNote } from "@/types/ai";
import { cn } from "@/lib/utils";

/** Running and finished wording for each planner tool (IR-504). */
const TOOL_LABELS: Record<string, [string, string]> = {
  plan_research:        ["Planning the research", "Planned the research"],
  continue_plan:        ["Moving to the next sub-task", "Moved to the next sub-task"],
  subtask_done:         ["Checking the evidence so far", "Checked the evidence so far"],
  finish:               ["Finishing the search", "Finished gathering evidence"],
  search_passages:      ["Searching passages", "Searched passages"],
  find_records:         ["Finding papers", "Found papers"],
  read_record_sections: ["Reading paper sections", "Read paper sections"],
  count_records:        ["Counting papers", "Counted papers"],
  corpus_facets:        ["Summarising the collection", "Summarised the collection"],
  screen_records:       ["Screening papers", "Screened papers"],
};

const COVERAGE_LABELS: Record<string, string> = {
  exhaustive:    "complete",
  screened:      "screened",
  matches_found: "matches found",
  sample:        "a sample",
};

const OK = new Set(["ok", "empty", "degraded", "generated", "fallback"]);

export function stepLabel(step: AgentStepEvent): string {
  const running = step.status === "running";
  if (step.kind === "plan") {
    if (running) return "Deciding the next step";
    return step.status === "unavailable" ? "The planner was unavailable" : "Planning failed";
  }
  if (step.kind === "answer") return running ? "Writing the answer" : "Wrote the answer";
  if (step.tool === "invalid") return "Rejected a malformed step";
  const [active, done] = TOOL_LABELS[step.tool] ?? ["Using a research tool", "Used a research tool"];
  return running ? active : done;
}

function stepDetail(step: AgentStepEvent): string | null {
  if (step.status === "running") return null;
  const parts: string[] = [];
  if (step.found !== null && step.found !== undefined) parts.push(`${step.found} found`);
  if (step.coverage) parts.push(COVERAGE_LABELS[step.coverage] ?? step.coverage);
  if (step.duplicate) parts.push("repeat");
  if (step.status === "rejected") parts.push("rejected");
  if (step.status === "refused") parts.push("stopped by a limit");
  if (step.status === "failed") parts.push("failed");
  return parts.length ? parts.join(" · ") : null;
}

/** Finished model calls are noise in the trail; a failed one is not. */
export function visibleSteps(steps: AgentStepEvent[]): AgentStepEvent[] {
  return steps.filter((step) => !(step.kind === "plan" && step.status === "ok"));
}

function StepIcon({ status }: { status: string }) {
  if (status === "running") {
    return (
      <i aria-hidden className="fas fa-circle-notch animate-spin motion-reduce:animate-none text-brand text-2xs" />
    );
  }
  if (OK.has(status)) return <i aria-hidden className="fas fa-check text-stone-500 text-2xs" />;
  return <i aria-hidden className="fas fa-triangle-exclamation text-brand text-2xs" />;
}

/**
 * The research planner's steps (IR-504): a live trail while the run goes,
 * and a collapsed summary on the finished answer, opened by the reader.
 * Names and counts only -- the planner's arguments are never shown.
 */
export function ResearchSteps({
  steps,
  live = false,
  compact = false,
}: {
  steps: AgentStepEvent[];
  live?: boolean;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const shown = visibleSteps(steps);
  if (shown.length === 0) return null;

  const seconds = steps
    .filter((step) => step.status !== "running")
    .reduce((total, step) => total + step.latency_ms, 0) / 1000;
  const expanded = live || open;

  return (
    <div className={compact ? "mt-1 mb-2" : "mt-1 mb-3"}>
      {live ? (
        <p className="text-xs font-medium text-stone-500">Research steps</p>
      ) : (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((wasOpen) => !wasOpen)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 -ml-1.5",
            "text-xs font-medium text-stone-500 transition-colors",
            "hover:text-stone-700 hover:bg-stone-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
          )}
        >
          <i
            aria-hidden
            className={cn(
              "fas fa-chevron-right text-2xs transition-transform duration-200 motion-reduce:transition-none",
              open && "rotate-90",
            )}
          />
          {`Researched in ${shown.length} ${shown.length === 1 ? "step" : "steps"} · ${seconds.toFixed(1)} s`}
        </button>
      )}

      {expanded && (
        <ol id={listId} aria-label="Research steps" className="mt-1.5 ml-1 border-l border-stone-200 pl-3.5 space-y-1.5">
          {shown.map((step) => {
            const detail = stepDetail(step);
            return (
              <li key={step.position} className="relative flex items-baseline gap-2 text-xs">
                <span className="absolute -left-[22px] top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white">
                  <StepIcon status={step.status} />
                </span>
                <span className={step.status === "running" ? "text-stone-800 font-medium" : "text-stone-600"}>
                  {stepLabel(step)}
                  {step.status === "running" && "…"}
                </span>
                {detail && <span className="text-stone-400">{detail}</span>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/** What a research answer could not cover, kept apart from its text (IR-504). */
export function CoverageNotes({ notes }: { notes: CoverageNote[] }) {
  if (notes.length === 0) return null;
  return (
    <aside
      aria-label="Coverage"
      className="mt-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs text-stone-700"
    >
      <p className="flex items-center gap-1.5 font-medium text-brand">
        <i aria-hidden className="fas fa-triangle-exclamation text-2xs" />
        Coverage
      </p>
      <ul className="mt-1 space-y-1">
        {notes.map((note) => (
          <li key={note.code}>{note.text}</li>
        ))}
      </ul>
    </aside>
  );
}
