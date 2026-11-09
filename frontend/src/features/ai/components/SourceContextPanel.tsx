import type { ChatCitation, SemanticSearchResult } from "@/types/ai";
import { hasCitationQuote, openCitationLabel, useCitationLink } from "@/lib/citedPage";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { withMathRendered } from "./PassageQuote";
import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";

interface SourceContextPanelProps {
  open:       boolean;
  /**
   * The question of the answer these passages belong to: the selected one,
   * which is the latest until the reader picks another (IR-562). `null`
   * before anything has been answered.
   */
  question?:  string | null;
  /**
   * The Passages the selected reply cited, in marker order. A reopened
   * Conversation's reply (IR-298) carries only the pointer — record, chunk,
   * page — until IR-299 re-resolves the quote and title at read time.
   */
  citations:  ChatCitation[];
  /** The Record cards those Passages came from, as the answer returned them. */
  sources:    SemanticSearchResult[];
  onClose:    () => void;
}

/**
 * What the selected answer was grounded in: the quote, the page, and whose
 * work it is. It names the answer it describes, so it can never be read as
 * evidence for a different one (IR-562).
 *
 * **Nothing is fetched here any more (IR-284).** The panel used to request one
 * `RecordDetail` per citation, which meant a spinner, an N+1 and a card that
 * could disagree with the answer it sat beside. The ask response now carries
 * the Passages and the Record cards together, so this renders what it was
 * handed.
 *
 * A Passage is shown before its record card, deliberately: the quote is the
 * evidence, and the card is who said it.
 *
 * Lightened for IR-329: flat list rows, not bordered cards -- chips in the
 * answer text carry citation detail now, this is just a reference list.
 */
export function SourceContextPanel({ open, question = null, citations, sources, onClose }: SourceContextPanelProps) {
  return (
    <aside
      // Collapses by width, matching `ConversationSidebar`'s own transition,
      // rather than mounting/unmounting instantly.
      className={`shrink-0 flex flex-col border-l border-stone-200/80 bg-canvas
        overflow-hidden transition-[width] duration-200 ease-out
        ${open ? "w-[min(100%,320px)] sm:w-[300px]" : "w-0 border-l-0 invisible"}`}
      aria-label="Referenced passages"
      aria-hidden={!open}
    >
      <div className="w-[min(100vw,320px)] sm:w-[300px] flex flex-col h-full">
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-stone-200/60">
        <div className="min-w-0">
          <h2 className="text-[14px] font-bold text-stone-800">Referenced passages</h2>
          <p className="text-[12px] text-stone-500 mt-0.5 line-clamp-2">
            {question ? <>For “{question}”</> : "The exact text behind the answer"}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-2 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          aria-label="Hide sources panel"
        >
          <i className="fas fa-xmark text-[14px]" aria-hidden />
        </button>
      </div>

      <SourcePassages citations={citations} sources={sources} answered={question !== null} />
      </div>
    </aside>
  );
}

/** One cited passage: its marker, a two-line quote, and its page; the whole row opens the paper there. */
function PassageRow({ citation, title }: { citation: ChatCitation; title: string }) {
  const { to, state } = useCitationLink(citation);
  const quote = hasCitationQuote(citation) ? citation.text.replace(/\s+/g, " ").trim() : "";
  return (
    <Link to={to} state={state} title={quote || undefined}
      aria-label={openCitationLabel(citation, title)}
      className="group/row grid grid-cols-[1.375rem_minmax(0,1fr)_auto] items-start gap-x-2.5 rounded-lg px-2 py-1.5 transition-colors duration-150 hover:bg-stone-100">
      <span aria-hidden className="mt-0.5 grid h-[18px] place-items-center rounded-md bg-brand-50 text-2xs font-semibold tabular-nums leading-none text-brand">
        {citation.marker}
      </span>
      <span className="line-clamp-2 min-w-0 text-[13px] leading-[1.45] text-stone-700">
        {quote ? withMathRendered(quote) : <span className="italic text-stone-500">Open the passage</span>}
      </span>
      <span className="mt-0.5 flex items-center gap-1.5 text-[11px] font-medium tabular-nums text-stone-500">
        {citation.page != null && <>p. {citation.page}</>}
        <i aria-hidden className="fas fa-arrow-right text-[9px] opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 group-focus-visible/row:opacity-100" />
      </span>
    </Link>
  );
}

/**
 * The passages one answer cited, grouped by paper: the paper once, then a row
 * per passage. A row opens the paper at that page, highlighted.
 */
export function SourcePassages({
  citations,
  sources,
  answered = false,
  className = "p-2",
}: Pick<SourceContextPanelProps, "citations" | "sources"> & {
  className?: string;
  /** Whether there is an answer at all: one that cited nothing says so. */
  answered?: boolean;
}) {
  if (citations.length === 0) {
    return (
      <p className={cn("px-2 py-4 text-center text-[13px] text-stone-500", className)}>
        {answered ? "This answer cited no passages." : "Ask a question to see the passages IRIS used in its answer."}
      </p>
    );
  }
  const groups = new Map<number, ChatCitation[]>();
  for (const citation of citations) groups.set(citation.record_id, [...(groups.get(citation.record_id) ?? []), citation]);

  return (
    <div className={cn("divide-y divide-stone-200/70", className)}>
      {[...groups].map(([recordId, passages]) => {
        const card = sources.find((s) => s.id === recordId);
        const title = card?.title ?? "Source";
        const byline = [card?.authors?.trim(), card?.year].filter(Boolean).join(" · ");
        return (
          <section key={recordId} aria-label={title} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-baseline gap-2 px-2">
              <Link to={`/records/${recordId}`} className="min-w-0 truncate text-[13px] font-semibold text-stone-900 hover:text-brand hover:underline">
                {title}
              </Link>
              <ResearchOriginBadge origin={card?.origin} />
            </div>
            {byline && <p className="truncate px-2 text-[12px] text-stone-500">{byline}</p>}
            <div className="mt-1">
              {passages.map((citation) => <PassageRow key={`${citation.chunk_id}-${citation.marker}`} citation={citation} title={title} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
