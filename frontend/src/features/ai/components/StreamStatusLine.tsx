import type { StreamingState } from "../hooks/useAskStream";
import { cn } from "@/lib/utils";
import { stepLabel } from "./ResearchSteps";

/** Honest progress copy (IR-329) -- one deterministic pipeline stage per
 *  line, never phrasing that reads as parallel agents (ADR-028). */
export function statusLineText(state: StreamingState): string | null {
  // The research lane names the planner's current step instead (IR-504).
  const current = [...(state.steps ?? [])].reverse().find((step) => step.status === "running");
  if (current && state.stage !== "answering") return `${stepLabel(current)}…`;
  // A listing names how far screening has got, from the candidates themselves (IR-546).
  const total = state.candidates?.length ?? 0;
  const waiting = state.candidates?.filter((row) => row.state === "pending").length ?? 0;
  if (total > 0 && waiting > 0 && state.stage !== "answering") {
    return `Screening ${total} candidate ${total === 1 ? "paper" : "papers"} (${total - waiting} checked)…`;
  }
  switch (state.stage) {
    case "queued":
      return "Waiting to start…";
    case "searching":
      return "Searching the repository…";
    case "found": {
      if (!state.foundInfo) return null;
      const { passageCount, recordCount } = state.foundInfo;
      const passages = passageCount === 1 ? "passage" : "passages";
      const papers = recordCount === 1 ? "paper" : "papers";
      return `Found ${passageCount} ${passages} from ${recordCount} ${papers}`;
    }
    case "thinking":
      return "Thinking…";
    case "answering":
      // The answer itself is rendering now -- a status line above it would
      // be a stale caption competing with the thing it announced.
      return null;
  }
}

/**
 * The stream's one live line (IR-570). It stays mounted while it has nothing
 * to say: a live region added at the moment its text changes is often not
 * announced at all, so an empty one waits for the next stage.
 */
export function StreamStatusLine({ state, className }: { state: StreamingState; className?: string }) {
  const text = statusLineText(state);

  return (
    <p aria-live="polite" className={cn("flex items-center gap-2 text-[14px] font-medium text-stone-500", className)}>
      {text && (
        <>
          <span
            aria-hidden
            className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse motion-reduce:animate-none"
          />
          {text}
        </>
      )}
    </p>
  );
}
