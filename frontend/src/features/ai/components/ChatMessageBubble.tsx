import { Link } from "react-router-dom";
import type { ChatMessage } from "@/types/chat";
import { cn } from "@/lib/utils";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { ANSWER_MARKDOWN } from "./answerLayout";
import { CandidateList } from "./CandidateList";
import { ComparisonTable } from "./ComparisonTable";
import { CopyButton } from "./CopyButton";
import {
  DegradedNotice,
  PartialAnswerNotice,
  ResolvedQuestionNotice,
  ScopeNotice,
} from "./PassageQuote";
import { ReasoningSummary } from "./ReasoningSummary";
import "highlight.js/styles/github.min.css";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  /**
   * The narrow Paper Chat panel's density (IR-356): smaller avatar and type,
   * and the reader's own question in a soft brand bubble. Ask IRIS's
   * full-width transcript keeps the default.
   */
  compact?: boolean;
  /** Disables Retry while another answer is in flight. */
  retryDisabled?: boolean;
  /** Ask a run that ended without its answer again (IR-548). */
  onRetry?: (message: ChatMessage) => void;
  /** Whether the sources panel is describing this answer (IR-562). */
  sourcesSelected?: boolean;
  /** Show this answer's sources. Absent where there is no sources panel. */
  onSelectSources?: (message: ChatMessage) => void;
}

/**
 * Which answer the sources panel describes, chosen on the answer itself: the
 * panel follows the latest answer until the reader picks an earlier one.
 */
function SourcesButton({ count, selected, onSelect }: { count: number; selected: boolean; onSelect: () => void }) {
  const label = `${count} ${count === 1 ? "source" : "sources"}`;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${label} for this answer`}
      className={cn(
        "inline-flex items-center gap-1.5 min-h-8 px-2 -ml-2 rounded-md text-[13px] font-medium transition-colors",
        selected ? "text-brand" : "text-stone-500 hover:text-stone-900 hover:bg-stone-100",
      )}
    >
      <i className="fas fa-quote-left text-[10px]" aria-hidden />
      {label}
    </button>
  );
}

/** A queued question that ended unanswered, and the way to ask it again. */
function RunEndedNotice({ onRetry, disabled }: { onRetry?: () => void; disabled?: boolean }) {
  if (!onRetry) return null;
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={onRetry}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5
          text-[13px] font-medium text-stone-700 hover:border-brand/40 hover:text-brand
          disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <i className="fas fa-rotate-right text-[11px]" aria-hidden />
        Retry
      </button>
    </div>
  );
}

/**
 * One turn of the transcript. Citations render as inline chips via
 * `CitationText` (IR-329), not a repeated card list below the message.
 *
 * User turns sit in a flat, borderless bar; assistant turns flow as plain
 * text with no card/border/shadow, closer to a read surface than a chat
 * widget — the avatar is still what tells the two apart.
 */
export function ChatMessageBubble({
  message, compact = false, retryDisabled, onRetry, sourcesSelected = false, onSelectSources,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const cited = message.citations?.length ?? 0;

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
        {!isUser && <ReasoningSummary summary={message.reasoningSummary} compact={compact} />}
        {!isUser && message.comparison && <ComparisonTable comparison={message.comparison} />}
        {isUser ? (
          <p className="whitespace-pre-wrap text-stone-800">{message.content}</p>
        ) : !message.listing || message.listing.count ? (
          <CitationText
            text={message.content}
            citations={message.citations ?? []}
            className={ANSWER_MARKDOWN}
          />
        ) : null}

        {!isUser && message.listing?.candidates && <CandidateList listing={message.listing} />}
        {!isUser && message.listing && !message.listing.count && !message.listing.candidates && (
          <div className="mt-3">
            <p className="text-sm text-stone-600">{message.listing.wording}</p>
            {message.listing.records.length === 0 && <p className="mt-2">No papers are listed for this answer.</p>}
            <ul className="mt-2 space-y-1">
              {message.listing.records.map((record) => (
                <li key={record.record_id}>
                  <Link to={`/records/${record.record_id}`} className="text-brand hover:underline">{record.title}</Link>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!isUser && message.resolvedQuestion && (
          <ResolvedQuestionNotice question={message.resolvedQuestion} />
        )}
        {!isUser && message.degraded && <DegradedNotice subject="answer" />}
        {!isUser && message.widened && <ScopeNotice />}
        {!isUser && message.partial && !message.endedRun && <PartialAnswerNotice />}
        {!isUser && message.endedRun && (
          <RunEndedNotice
            onRetry={onRetry ? () => onRetry(message) : undefined}
            disabled={retryDisabled}
          />
        )}

        {!isUser && (
          <div className="mt-1.5 flex items-center gap-2">
            {onSelectSources && cited > 0 && (
              <SourcesButton
                count={cited}
                selected={sourcesSelected}
                onSelect={() => onSelectSources(message)}
              />
            )}
            <div className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
              <CopyButton text={message.content} label="Copy answer" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
