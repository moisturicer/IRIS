import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/chat";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { AssistantMessageSkeleton } from "./AssistantMessageSkeleton";
import { AskIrisEmblem } from "./AskIrisIcons";

interface ChatMessageListProps {
  messages:           ChatMessage[];
  isLoading:          boolean;
  /** Hide citation chips in bubbles when the sources panel is open */
  showInlineSources?: boolean;
  /** Prompts built from what is actually in the corpus. */
  suggestions?:       string[];
  onSuggestion?:      (prompt: string) => void;
  /** How many readable records retrieval can draw on. */
  indexedRecords?:    number | null;
}

export function ChatMessageList({
  messages,
  isLoading,
  showInlineSources = true,
  suggestions = [],
  onSuggestion,
  indexedRecords = null,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center bg-[#FBFCFD]">
        <div className="max-w-md">
          <AskIrisEmblem className="w-14 h-14 mx-auto mb-4" />
          <h2 className="text-[16px] font-bold text-stone-900 mb-2">Ask IRIS</h2>
          <p className="text-[13px] text-stone-500 leading-relaxed">
            Every answer is grounded in published CIT-U records
            {indexedRecords != null && (
              <> — <strong className="text-stone-700">{indexedRecords}</strong> currently searchable</>
            )}
            . Sources are listed with each reply so you can open the originals.
          </p>

          {suggestions.length > 0 && (
            <div className="mt-5 flex flex-col gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">
                Try one of these
              </span>
              {suggestions.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => onSuggestion?.(prompt)}
                  className="text-left px-3.5 py-2.5 rounded-xl border border-stone-200 bg-white text-[12px] text-stone-700 hover:border-brand/40 hover:text-brand transition-colors"
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
    <div className="flex-1 overflow-y-auto scrollbar-thin px-4 sm:px-6 py-6 space-y-6 bg-[#FBFCFD]">
      {messages.map((m) => (
        <ChatMessageBubble key={m.id} message={m} showSources={showInlineSources} />
      ))}
      {isLoading && <AssistantMessageSkeleton />}
      <div ref={bottomRef} />
    </div>
  );
}
