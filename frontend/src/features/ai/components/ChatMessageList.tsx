import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/chat";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { AssistantMessageSkeleton } from "./AssistantMessageSkeleton";

interface ChatMessageListProps {
  messages:           ChatMessage[];
  isLoading:          boolean;
  /** Hide citation chips in bubbles when the sources panel is open */
  showInlineSources?: boolean;
}

export function ChatMessageList({ messages, isLoading, showInlineSources = true }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center">
        <div className="max-w-md">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-[#6B0F12]/10 flex items-center justify-center mb-4">
            <i className="fas fa-brain text-[#6B0F12] text-xl" aria-hidden />
          </div>
          <h2 className="text-[16px] font-bold text-stone-900 mb-2">Start a conversation</h2>
          <p className="text-[13px] text-stone-500 leading-relaxed">
            Ask about published research at CIT-U. IRIS searches the corpus and grounds answers in
            real records—you can review sources anytime with the Sources button.
          </p>
          <ul className="mt-4 text-left text-[12px] text-gray-500 space-y-1.5">
            <li>• &quot;What IP projects focus on renewable energy?&quot;</li>
            <li>• &quot;Summarize recent community extension research&quot;</li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin px-4 sm:px-6 py-6 space-y-6 bg-[#FAFAF9]">
      {messages.map((m) => (
        <ChatMessageBubble key={m.id} message={m} showSources={showInlineSources} />
      ))}
      {isLoading && <AssistantMessageSkeleton />}
      <div ref={bottomRef} />
    </div>
  );
}
