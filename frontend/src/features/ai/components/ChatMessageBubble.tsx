import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ChatMessage } from "@/types/chat";
import { CitationPanelContext, CitationTurnContext } from "@/lib/citedPage";
import { cn } from "@/lib/utils";
import type { ChatCitation } from "@/types/ai";
import { AskIrisMark } from "./AskIrisIcons";
import { CitationText } from "./CitationText";
import { ANSWER_MARKDOWN } from "./answerLayout";
import { CandidateList } from "./CandidateList";
import { ComparisonTable } from "./ComparisonTable";
import { CopyButton, MESSAGE_ACTION } from "./CopyButton";
import {
  DegradedNotice,
  PartialAnswerNotice,
  ResolvedQuestionNotice,
  ScopeNotice,
} from "./PassageQuote";
import { ReasoningSummary } from "./ReasoningSummary";
import { SourcePassages } from "./SourceContextPanel";
import "highlight.js/styles/github.min.css";
import { SELECTED_RING } from "@/components/ui/highlightRoles";

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
  /** The sources open beneath the answer itself, rather than in a panel. */
  inlineSources?: boolean;
  /**
   * A Sources panel sits beside the chat (IR-1237): the answer's count and chips
   * open it, at a marker or at none, and `openMarker` is the one it highlights.
   * Ask again then belongs to the answer, and the question keeps Edit and Copy.
   */
  onOpenSources?: (message: ChatMessage, marker: number | null) => void;
  openMarker?: number | null;
  /** Send this question again as a new Turn (IR-1162). */
  onAskAgain?: (question: string) => void;
  /** Put this question in the input to change and send (IR-1162). */
  onEdit?: (question: string) => void;
  /** Disables Ask again and Edit while a run is active. */
  controlsDisabled?: boolean;
}

/**
 * Which answer the sources panel describes, chosen on the answer itself: the
 * panel follows the latest answer until the reader picks an earlier one.
 */
function SourcesButton({ markers, selected, onSelect }: { markers: number[]; selected: boolean; onSelect: () => void }) {
  const count = markers.length;
  const label = `${count} ${count === 1 ? "source" : "sources"}`;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-expanded={selected}
      aria-label={`${label} for this answer`}
      className={cn(
        "inline-flex items-center gap-2 min-h-8 px-2 -ml-2 rounded-control text-small font-medium transition-colors",
        selected ? "text-brand" : "text-stone-600 hover:text-stone-900 hover:bg-stone-100",
      )}
    >
      {/* The same numbers the answer's text cites, so the two read as one set. */}
      <span aria-hidden className="flex -space-x-1">
        {markers.slice(0, 3).map((marker) => (
          <span
            key={marker}
            className={cn(
              "grid h-[18px] min-w-[18px] place-items-center rounded-full px-1 text-2xs font-semibold leading-none tabular-nums ring-2 ring-surface",
              selected ? SELECTED_RING : "bg-stone-100 text-stone-700",
            )}
          >
            {marker}
          </span>
        ))}
      </span>
      {label}
      <i aria-hidden className={cn("fas fa-chevron-down text-label transition-transform duration-200", selected && "rotate-180")} />
    </button>
  );
}

/** "3 passages from 2 papers": the answer's evidence in one count, and the way to the panel (IR-1237). */
function PassageCount({ citations, open, onOpen }: { citations: ChatCitation[]; open: boolean; onOpen: () => void }) {
  const papers = new Set(citations.map((citation) => citation.record_id)).size;
  const label = `${citations.length} ${citations.length === 1 ? "passage" : "passages"} from ${papers} ${papers === 1 ? "paper" : "papers"}`;
  return (
    <button type="button" onClick={onOpen} aria-expanded={open}
      className={cn("inline-flex min-h-8 items-center gap-1.5 rounded-control px-2 -ml-2 text-small font-medium transition-colors",
        open ? "text-brand" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900")}>
      {label}
    </button>
  );
}

/**
 * Ask a question again, or edit it and send it (IR-1162). Neither replaces
 * anything: the earlier Turn stays and a new one follows.
 */
export function QuestionControls({
  question, disabled, onAskAgain, onEdit, className,
}: {
  question: string;
  disabled?: boolean;
  onAskAgain?: (question: string) => void;
  onEdit?: (question: string) => void;
  className?: string;
}) {
  if (!onAskAgain && !onEdit) return null;
  return (
    <div className={cn("flex items-center gap-0.5", className)}>
      {onAskAgain && (
        <button type="button" disabled={disabled} onClick={() => onAskAgain(question)}
          aria-label="Ask again" title="Ask again" className={MESSAGE_ACTION}>
          <i className="fas fa-rotate-right text-label" aria-hidden />
        </button>
      )}
      {onEdit && (
        <button type="button" disabled={disabled} onClick={() => onEdit(question)}
          aria-label="Edit" title="Edit" className={MESSAGE_ACTION}>
          <i className="fas fa-pen text-label" aria-hidden />
        </button>
      )}
      <CopyButton text={question} label="Copy question" />
    </div>
  );
}

/** Message actions fade in on hover or focus; touch has no hover, so they stay shown there. */
const REVEAL_ON_HOVER =
  "opacity-0 group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100 transition-opacity duration-150 motion-reduce:transition-none";

/**
 * The way to ask a question again: for a queued run that ended unanswered
 * (IR-548), and for an answer that was cut off before it finished (IR-907).
 */
function RetryButton({ onRetry, disabled }: { onRetry?: () => void; disabled?: boolean }) {
  if (!onRetry) return null;
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={onRetry}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-control border border-stone-200 px-3 py-1.5
          text-small font-medium text-stone-700 hover:bg-stone-100 hover:text-stone-900
          disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <i className="fas fa-rotate-right text-label" aria-hidden />
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
  message, compact = false, retryDisabled, onRetry, sourcesSelected = false, onSelectSources, inlineSources = false,
  onOpenSources, openMarker = null, onAskAgain, onEdit, controlsDisabled,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const [expanded, setExpanded] = useState(false);
  const markers = [...new Set((message.citations ?? []).map((citation) => citation.marker))];
  const inPanelMode = !!onOpenSources;
  const panel = useMemo(() => onOpenSources
    ? { active: sourcesSelected ? openMarker : null, open: (marker: number) => onOpenSources(message, marker) }
    : null, [onOpenSources, sourcesSelected, openMarker, message]);

  return (
    // Its citations name this answer, the way back to it (IR-578).
    <CitationTurnContext.Provider value={message.turnId ?? null}>
    <CitationPanelContext.Provider value={panel}>
    <div
      data-turn={isUser ? undefined : message.turnId}
      className={cn(
        // An answer arrived by streaming, so only the question enters: moving
        // the whole answer here would make it jump as the stream finishes.
        "group flex",
        compact ? "gap-2.5" : "gap-3",
        isUser && "flex-row-reverse animate-fade-in-up motion-reduce:animate-none",
      )}
    >
      <div
        className={cn(
          "rounded-full shrink-0 flex items-center justify-center",
          compact ? "w-7 h-7 text-2xs" : "w-8 h-8 text-xs",
          isUser ? "bg-stone-100 text-stone-600" : "bg-stone-100 text-brand",
        )}
        aria-hidden
      >
        {isUser ? (
          <i className="fas fa-user" aria-hidden />
        ) : (
          <AskIrisMark className={compact ? "w-4 h-4" : "w-[18px] h-[18px]"} />
        )}
      </div>

      {isUser && (
        <div className="flex max-w-[85%] flex-col items-end">
          <div className={cn(
            "rounded-card bg-stone-100",
            compact ? "text-sm leading-relaxed rounded-tr-none px-3.5 py-2.5" : "text-md leading-relaxed px-4 py-3",
          )}>
            <p className="whitespace-pre-wrap text-stone-800">{message.content}</p>
          </div>
          <QuestionControls
            question={message.content}
            disabled={controlsDisabled}
            onAskAgain={inPanelMode ? undefined : onAskAgain}
            onEdit={onEdit}
            className={cn("mt-1 -mr-1", REVEAL_ON_HOVER)}
          />
        </div>
      )}

      {!isUser && (
      <div className={cn(compact ? "text-sm leading-relaxed" : "text-md leading-relaxed", "min-w-0 flex-1")}>
        <ReasoningSummary summary={message.reasoningSummary} compact={compact} />
        {message.comparison && <ComparisonTable comparison={message.comparison} />}
        {!message.listing || message.listing.count ? (
          <CitationText
            text={message.content}
            citations={message.citations ?? []}
            papers={message.papers}
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
        {!isUser && message.partial && !message.endedRun && (
          <>
            <PartialAnswerNotice />
            {/* Only a reply that knows its question can be asked again. */}
            {message.question && (
              <RetryButton onRetry={onRetry ? () => onRetry(message) : undefined} disabled={retryDisabled} />
            )}
          </>
        )}
        {!isUser && message.endedRun && (
          <RetryButton
            onRetry={onRetry ? () => onRetry(message) : undefined}
            disabled={retryDisabled}
          />
        )}

        {!isUser && (
          <div className="mt-1.5 flex items-center gap-2 motion-safe:animate-fade-in-up">
            {inPanelMode && markers.length > 0 && (
              <PassageCount citations={message.citations ?? []} open={sourcesSelected && openMarker === null}
                onOpen={() => onOpenSources(message, null)} />
            )}
            {!inPanelMode && inlineSources && markers.length > 0 && (
              <SourcesButton markers={markers} selected={expanded} onSelect={() => setExpanded(v => !v)} />
            )}
            {!inPanelMode && !inlineSources && onSelectSources && markers.length > 0 && (
              <SourcesButton
                markers={markers}
                selected={sourcesSelected}
                onSelect={() => onSelectSources(message)}
              />
            )}
            <CopyButton text={message.content} label="Copy answer" className={cn(!markers.length && "-ml-1.5")} />
            {inPanelMode && onAskAgain && message.question && (
              <button type="button" disabled={controlsDisabled} onClick={() => onAskAgain(message.question as string)}
                aria-label="Ask again" title="Ask again" className={MESSAGE_ACTION}>
                <i className="fas fa-rotate-right text-label" aria-hidden />
              </button>
            )}
          </div>
        )}
        {!isUser && !inPanelMode && inlineSources && expanded && (
          <div className="mt-2 origin-top border-t border-stone-200 pt-2.5 motion-safe:animate-[sources-open_260ms_cubic-bezier(0.2,0.8,0.2,1)]">
            <SourcePassages citations={message.citations ?? []} sources={message.sources ?? []} answered
              className="-mx-2" />
          </div>
        )}
      </div>
      )}
    </div>
    </CitationPanelContext.Provider>
    </CitationTurnContext.Provider>
  );
}
