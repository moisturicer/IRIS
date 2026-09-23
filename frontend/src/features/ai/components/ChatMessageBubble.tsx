import type { ChatMessage } from "@/types/chat";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { DegradedNotice, PartialAnswerNotice, ScopeNotice } from "./PassageQuote";
import "highlight.js/styles/github.min.css";

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

/**
 * One turn of the transcript. Citations render as inline chips via
 * `CitationText` (IR-329), not a repeated card list below the message.
 *
 * User turns sit in a flat, borderless bar; assistant turns flow as plain
 * text with no card/border/shadow, closer to a read surface than a chat
 * widget — the avatar is still what tells the two apart.
 */
export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className="flex gap-3">
      <div
        className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-[12px]
          ${isUser ? "bg-stone-100 text-stone-500" : "bg-brand/10 text-brand"}`}
        aria-hidden
      >
        {isUser ? <i className="fas fa-user" aria-hidden /> : <AskIrisMark className="w-[18px] h-[18px]" />}
      </div>

      <div className={`min-w-0 flex-1 text-[15px] leading-relaxed ${isUser ? "bg-stone-100 rounded-2xl px-4 py-3" : ""}`}>
        {isUser ? (
          <p className="whitespace-pre-wrap text-stone-800">{message.content}</p>
        ) : (
          <CitationText
            text={message.content}
            citations={message.citations ?? []}
            className="chat-markdown prose prose-sm max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-code:text-[#6B0F12] prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
          />
        )}

        {!isUser && message.degraded && <DegradedNotice subject="answer" />}
        {!isUser && message.widened && <ScopeNotice />}
        {!isUser && message.partial && <PartialAnswerNotice />}
      </div>
    </div>
  );
}
