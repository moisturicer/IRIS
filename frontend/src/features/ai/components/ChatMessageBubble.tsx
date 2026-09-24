import type { ChatMessage } from "@/types/chat";
import { cn } from "@/lib/utils";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { CopyButton } from "./CopyButton";
import { DegradedNotice, PartialAnswerNotice, ScopeNotice } from "./PassageQuote";
import "highlight.js/styles/github.min.css";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  /**
   * The narrow Paper Chat panel's density (IR-356): smaller avatar and type,
   * and the reader's own question in a soft brand bubble. Ask IRIS's
   * full-width transcript keeps the default.
   */
  compact?: boolean;
}

/**
 * One turn of the transcript. Citations render as inline chips via
 * `CitationText` (IR-329), not a repeated card list below the message.
 *
 * User turns sit in a flat, borderless bar; assistant turns flow as plain
 * text with no card/border/shadow, closer to a read surface than a chat
 * widget — the avatar is still what tells the two apart.
 */
export function ChatMessageBubble({ message, compact = false }: ChatMessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "group flex animate-fade-in-up motion-reduce:animate-none",
        compact ? "gap-2.5" : "gap-3",
        isUser && "flex-row-reverse",
      )}
    >
      <div
        className={cn(
          "rounded-full shrink-0 flex items-center justify-center",
          compact ? "w-7 h-7 text-2xs" : "w-8 h-8 text-xs",
          isUser ? "bg-stone-100 text-stone-500" : "bg-brand/10 text-brand",
        )}
        aria-hidden
      >
        {isUser ? (
          <i className="fas fa-user" aria-hidden />
        ) : (
          <AskIrisMark className={compact ? "w-4 h-4" : "w-[18px] h-[18px]"} />
        )}
      </div>

      <div
        className={cn(
          compact ? "text-sm leading-relaxed" : "text-md leading-relaxed",
          isUser
            ? cn(
                "max-w-[85%] rounded-2xl",
                compact ? "bg-brand-50 rounded-tr-md px-3.5 py-2.5" : "bg-stone-100 px-4 py-3",
              )
            : "min-w-0 flex-1",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-stone-800">{message.content}</p>
        ) : (
          <CitationText
            text={message.content}
            citations={message.citations ?? []}
            className="chat-markdown prose prose-sm max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-code:text-brand prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none"
          />
        )}

        {!isUser && message.degraded && <DegradedNotice subject="answer" />}
        {!isUser && message.widened && <ScopeNotice />}
        {!isUser && message.partial && <PartialAnswerNotice />}

        {!isUser && (
          <div className="mt-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
            <CopyButton text={message.content} label="Copy answer" />
          </div>
        )}
      </div>
    </div>
  );
}
