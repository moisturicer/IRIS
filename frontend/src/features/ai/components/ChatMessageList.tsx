import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/chat";
import type { StreamingState } from "../conversation/answerStream";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { AssistantMessageSkeleton } from "./AssistantMessageSkeleton";
import { StreamingMessageBubble } from "./StreamingMessageBubble";
import { CHAT_COLUMN } from "./answerLayout";
import { AskIrisEmblem } from "./AskIrisIcons";

interface ChatMessageListProps {
  messages:           ChatMessage[];
  isLoading:          boolean;
  /**
   * The in-flight answer's live progress (IR-329) — rendered in place of
   * the old fixed skeleton whenever it is set. `isLoading` can still be
   * true with this `null` for the brief gap before the first stream event
   * lands, which is what the skeleton fallback below still covers.
   */
  streaming?:         StreamingState | null;
  /** Prompts built from what is actually in the corpus. */
  suggestions?:       string[];
  onSuggestion?:      (prompt: string) => void;
  /** How many readable records retrieval can draw on. */
  indexedRecords?:    number | null;
  /** Retry a queued question that ended unanswered (IR-548). */
  onRetry?:           (message: ChatMessage) => void;
  /** Cancel the queued run in flight (IR-548). */
  onStop?:            () => void;
  /** The answer whose sources are showing (IR-562). */
  selectedId?:        string | null;
  /** Show the sources of `message` rather than another answer's. */
  onSelectSources?:   (message: ChatMessage) => void;
  /**
   * The answer a reader came back to from a citation (IR-578): shown once,
   * where it is, instead of the transcript's end.
   */
  anchorTurn?:        number | null;
}

export function ChatMessageList({
  messages,
  isLoading,
  streaming = null,
  suggestions = [],
  onSuggestion,
  indexedRecords = null,
  onRetry,
  onStop,
  selectedId = null,
  onSelectSources,
  anchorTurn = null,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const columnRef = useRef<HTMLDivElement>(null);
  const anchored = useRef<number | null>(null);

  useEffect(() => {
    if (anchorTurn != null && anchored.current !== anchorTurn) {
      const answer = columnRef.current?.querySelector(`[data-turn="${anchorTurn}"]`);
      if (answer) {
        anchored.current = anchorTurn;
        answer.scrollIntoView({ block: "start" });
        return;
      }
    }
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, streaming, anchorTurn]);

  if (messages.length === 0 && !isLoading) {
    return (
      // `m-auto`, not `justify-center`: centred content taller than a phone's
      // screen would overflow upward and clip its top; this scrolls (IR-570).
      <div className="flex-1 overflow-y-auto flex flex-col p-8 text-center">
        <div className="m-auto max-w-xl w-full animate-fade-in-up motion-reduce:animate-none">
          <AskIrisEmblem className="w-16 h-16 mx-auto mb-5" />
          <h2 className="text-[26px] font-bold text-stone-900 mb-2">What do you want to ask?</h2>
          <p className="text-[15px] text-stone-500 leading-relaxed">
            Every answer is grounded in published CIT-U records
            {indexedRecords != null && (
              <> — <strong className="text-stone-700">{indexedRecords}</strong> currently searchable</>
            )}
            . Sources are listed with each reply so you can open the originals.
          </p>

          {suggestions.length > 0 && (
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
              {suggestions.map((prompt, i) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onSuggestion?.(prompt)}
                  style={{ animationDelay: `${i * 60}ms` }}
                  className="px-4 py-3.5 rounded-xl border border-stone-200 text-[14px] text-stone-700
                    hover:border-brand/40 hover:text-brand hover:shadow-sm transition-all duration-200
                    animate-fade-in-up motion-reduce:animate-none [animation-fill-mode:backwards]"
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin px-4 sm:px-6 py-6">
      {/* One shared column with ChatInput below it -- see CHAT_COLUMN. */}
      <div ref={columnRef} className={`${CHAT_COLUMN} space-y-6`}>
        {messages.map((m) => (
          <ChatMessageBubble
            key={m.id}
            message={m}
            retryDisabled={isLoading}
            onRetry={onRetry}
            sourcesSelected={m.id === selectedId}
            onSelectSources={onSelectSources}
          />
        ))}
        {isLoading && (streaming ? <StreamingMessageBubble state={streaming} onStop={onStop} /> : <AssistantMessageSkeleton />)}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
