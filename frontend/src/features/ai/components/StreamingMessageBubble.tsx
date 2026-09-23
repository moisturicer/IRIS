import type { StreamingState } from "../hooks/useAskStream";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { StreamStatusLine } from "./StreamStatusLine";

/** The reply bubble while still streaming (IR-329) -- status line, then
 *  text rendering progressively. Swapped for `ChatMessageBubble` on finish. */
export function StreamingMessageBubble({ state }: { state: StreamingState }) {
  return (
    <div className="flex gap-3 max-w-[min(88%,40rem)]" aria-busy="true">
      <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center bg-brand/10 text-brand">
        <AskIrisMark className="w-[18px] h-[18px]" />
      </div>

      <div className="flex-1 bg-white border border-stone-200/90 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
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
