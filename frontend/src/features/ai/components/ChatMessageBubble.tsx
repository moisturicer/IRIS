import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { ChatMessage } from "@/types/chat";
import type { ChatCitation, Citation } from "@/types/ai";
import { AskIrisMark, GroundedCitationIcon } from "./AskIrisIcons";
import { DegradedNotice, OpenPassageLink, PassageQuote, ScopeNotice } from "./PassageQuote";
import "highlight.js/styles/github.min.css";

/** Whether `citation` carries the quote and title a live answer has, rather
 * than only the pointer a replayed Turn has until IR-299 re-resolves them. */
function hasQuote(citation: ChatCitation): citation is Citation {
  return "text" in citation;
}

/**
 * One citation: the quote, the page, and a way to go and read it.
 *
 * The quote is the point (IR-284). A chip reading "Record #7" asked a reader
 * to go and find the supporting sentence themselves in a fifty-page PDF,
 * which is the verifiability chunk-level retrieval was built for and did not
 * deliver.
 *
 * The link carries `?page=` so the record view can open the paper *at* that
 * page rather than at its first. A passage whose page could not be recovered
 * during extraction links to the record without one, rather than guessing a
 * page number, which would send a reader to the wrong place confidently.
 *
 * A **replayed** citation (from a reopened Conversation, IR-298) carries the
 * record id and page but not the quote or the record's title — a stored
 * citation is a pointer, never text, so there is nothing to quote until
 * IR-299 re-resolves it at read time. That case renders the pointer alone:
 * no blockquote, no invented title.
 */
function PassageCitation({ citation }: { citation: ChatCitation }) {
  if (!hasQuote(citation)) {
    return (
      <div className="rounded-lg bg-[#6B0F12]/[0.04] border border-[#6B0F12]/10 px-2.5 py-2">
        <div className="flex items-baseline gap-1.5 flex-wrap">
          <span className="text-[10px] font-bold text-[#6B0F12]">[{citation.marker}]</span>
          <span className="text-[11px] font-semibold text-stone-700">Source</span>
        </div>
        <OpenPassageLink citation={citation} title="the source" className="mt-1.5" />
      </div>
    );
  }

  const section = citation.context_path?.[citation.context_path.length - 1];

  return (
    <div className="rounded-lg bg-[#6B0F12]/[0.04] border border-[#6B0F12]/10 px-2.5 py-2">
      <div className="flex items-baseline gap-1.5 flex-wrap">
        <span className="text-[10px] font-bold text-[#6B0F12]">[{citation.marker}]</span>
        <span className="text-[11px] font-semibold text-stone-700 min-w-0 truncate">
          {citation.record_title}
        </span>
        {section && (
          <span className="text-[10px] text-stone-500 truncate">· {section}</span>
        )}
      </div>

      <PassageQuote text={citation.text} className="mt-1" />
      <OpenPassageLink citation={citation} className="mt-1.5" />
    </div>
  );
}

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

        {!isUser && message.degraded && <DegradedNotice subject="answer" />}
        {!isUser && message.widened && <ScopeNotice />}

        {!isUser && showSources && message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-gray-100 space-y-2">
            <span className="flex items-center gap-1.5 text-[10px] font-semibold text-stone-400 uppercase tracking-wide">
              <GroundedCitationIcon className="w-3.5 h-3.5" />
              Grounded in {message.citations.length} passage
              {message.citations.length === 1 ? "" : "s"}
            </span>
            <ol className="space-y-2 list-none pl-0">
              {message.citations.map((citation) => (
                <li key={`${citation.chunk_id}-${citation.marker}`}>
                  <PassageCitation citation={citation} />
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
