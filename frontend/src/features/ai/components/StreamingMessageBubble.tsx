import { cn } from "@/lib/utils";
import type { StreamingState } from "../conversation/answerStream";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { ANSWER_MARKDOWN } from "./answerLayout";
import { StreamStatusRow } from "./StreamStatusRow";
import { LiveCandidates } from "./CandidateList";

/** The reply while still streaming (IR-329): any text that has arrived, then
 *  one status row (IR-596). Swapped for `ChatMessageBubble` on finish.
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
    <div className={cn("flex animate-fade-in motion-reduce:animate-none", compact ? "gap-2.5" : "gap-3")}>
      <div
        className={cn(
          "rounded-full shrink-0 flex items-center justify-center bg-brand/10 text-brand",
          compact ? "w-7 h-7" : "w-8 h-8",
        )}
      >
        <AskIrisMark className={compact ? "w-4 h-4" : "w-[18px] h-[18px]"} />
      </div>

      <div className={cn("min-w-0 flex-1 leading-relaxed", compact ? "text-sm" : "text-md")}>
        {state.candidates && <LiveCandidates candidates={state.candidates} compact={compact} />}

        {state.text && (
          <CitationText
            text={state.text}
            citations={state.citations}
            streaming
            className={ANSWER_MARKDOWN}
          />
        )}

        <StreamStatusRow state={state} onStop={onStop} className="mt-2" />
      </div>
    </div>
  );
}
