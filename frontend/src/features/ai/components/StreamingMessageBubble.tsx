import { RoutingDecisionPanel } from "./RoutingDecisionPanel";
import { cn } from "@/lib/utils";
import type { StreamingState } from "../hooks/useAskStream";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { ANSWER_MARKDOWN } from "./answerLayout";
import { ReasoningPanel } from "./ReasoningPanel";
import { StreamStatusLine } from "./StreamStatusLine";
import { LiveCandidates } from "./CandidateList";
import { ResearchSteps } from "./ResearchSteps";

/** The reply while still streaming (IR-329) -- the collapsed reasoning panel
 *  (IR-381), then text rendering progressively, then the status line under it
 *  (IR-570). Swapped for
 *  `ChatMessageBubble` on finish, which renders the same panel from the
 *  stored text, so the swap is not where the panel disappears.
 *  No card/border -- matches the finished bubble's plain-text flow.
 *  `compact` matches `ChatMessageBubble`'s Paper Chat density (IR-356). */
export function StreamingMessageBubble({
  state,
  compact = false,
  onStop,
}: {
  state: StreamingState;
  compact?: boolean;
  /** Cancel the queued run being followed (IR-548); offered only for one. */
  onStop?: () => void;
}) {
  return (
    <div className={cn("flex animate-fade-in motion-reduce:animate-none", compact ? "gap-2.5" : "gap-3")} aria-busy="true">
      <div
        className={cn(
          "rounded-full shrink-0 flex items-center justify-center bg-brand/10 text-brand",
          compact ? "w-7 h-7" : "w-8 h-8",
        )}
      >
        <AskIrisMark className={compact ? "w-4 h-4" : "w-[18px] h-[18px]"} />
      </div>

      <div className={cn("min-w-0 flex-1 leading-relaxed", compact ? "text-sm" : "text-md")}>
        {state.routing && <RoutingDecisionPanel decision={state.routing} />}
        {state.steps && <ResearchSteps steps={state.steps} live compact={compact} />}
        {state.candidates && <LiveCandidates candidates={state.candidates} compact={compact} />}

        <ReasoningPanel reasoning={state.reasoning} streaming compact={compact} />

        {state.text && (
          <CitationText
            text={state.text}
            citations={state.citations}
            streaming
            className={ANSWER_MARKDOWN}
          />
        )}

        {/* What it is doing now, in one polite live line under the answer
            (IR-570), with Stop beside it while a queued run is followed. */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mt-2">
          <StreamStatusLine state={state} />
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
      </div>
    </div>
  );
}
