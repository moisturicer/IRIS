import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { ChatMessage } from "@/types/chat";
import { AskIrisMark, GroundedCitationIcon } from "./AskIrisIcons";
import "highlight.js/styles/github.min.css";

interface ChatMessageBubbleProps {
  message:      ChatMessage;
  showSources?: boolean;
}

export function ChatMessageBubble({ message, showSources = true }: ChatMessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-[12px]
          ${isUser ? "bg-stone-100 text-stone-500" : "bg-brand/10 text-brand"}`}
        aria-hidden
      >
        {isUser ? <i className="fas fa-user" aria-hidden /> : <AskIrisMark className="w-[18px] h-[18px]" />}
      </div>

      <div
        className={`max-w-[min(88%,40rem)] rounded-2xl px-4 py-3 text-[13px] leading-relaxed
          ${isUser
            ? "bg-brand text-white rounded-br-sm"
            : "bg-white border border-stone-200/90 text-stone-800 rounded-bl-sm shadow-sm"
          }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="chat-markdown prose prose-sm max-w-none prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-code:text-[#6B0F12] prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {!isUser && showSources && message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-100 flex flex-wrap gap-1.5">
            <span className="flex items-center gap-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wide w-full">
              <GroundedCitationIcon className="w-3.5 h-3.5" />
              Grounded in {message.citations.length} record
              {message.citations.length === 1 ? "" : "s"}
            </span>
            {message.citations.map((id) => (
              <Link
                key={id}
                to={`/records/${id}`}
                className="text-[11px] font-medium text-[#6B0F12] hover:underline px-2 py-0.5 bg-[#6B0F12]/5 rounded"
              >
                Record #{id}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
