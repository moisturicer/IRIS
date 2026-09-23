import type { StreamingState } from "../hooks/useAskStream";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { StreamStatusLine } from "./StreamStatusLine";

/** The reply while still streaming (IR-329) -- status line, then text
 *  rendering progressively. Swapped for `ChatMessageBubble` on finish.
 *  No card/border -- matches the finished bubble's plain-text flow. */
export function StreamingMessageBubble({ state }: { state: StreamingState }) {
  return (
    <div className="flex gap-3 animate-fade-in motion-reduce:animate-none" aria-busy="true">
      <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-brand/10 text-brand">
        <AskIrisMark className="w-[18px] h-[18px]" />
      </div>

      <div className="min-w-0 flex-1 text-[15px] leading-relaxed">
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
