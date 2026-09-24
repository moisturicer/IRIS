import { cn } from "@/lib/utils";
import type { StreamingState } from "../hooks/useAskStream";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { StreamStatusLine } from "./StreamStatusLine";

/** The reply while still streaming (IR-329) -- status line, then text
 *  rendering progressively. Swapped for `ChatMessageBubble` on finish.
 *  No card/border -- matches the finished bubble's plain-text flow.
 *  `compact` matches `ChatMessageBubble`'s Paper Chat density (IR-356). */
export function StreamingMessageBubble({
  state,
  compact = false,
}: {
  state: StreamingState;
  compact?: boolean;
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
        <StreamStatusLine state={state} />

        {state.text && (
          <CitationText
            text={state.text}
            citations={state.citations}
            streaming
            className="chat-markdown prose prose-sm max-w-none prose-p:my-1.5"
          />
        )}
      </div>
    </div>
  );
}
