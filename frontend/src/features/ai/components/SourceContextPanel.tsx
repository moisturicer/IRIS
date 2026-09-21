import type { ChatCitation, SemanticSearchResult } from "@/types/ai";
import { OpenPassageLink, PassageQuote } from "./PassageQuote";

interface SourceContextPanelProps {
  open:       boolean;
  /**
   * The Passages the latest reply cited, in marker order. A reopened
   * Conversation's reply (IR-298) carries only the pointer — record, chunk,
   * page — until IR-299 re-resolves the quote and title at read time.
   */
  citations:  ChatCitation[];
  /** The Record cards those Passages came from, as the answer returned them. */
  sources:    SemanticSearchResult[];
  onClose:    () => void;
}

/**
 * What the latest answer was grounded in: the quote, the page, and whose work
 * it is.
 *
 * **Nothing is fetched here any more (IR-284).** The panel used to request one
 * `RecordDetail` per citation, which meant a spinner, an N+1 and a card that
 * could disagree with the answer it sat beside. The ask response now carries
 * the Passages and the Record cards together, so this renders what it was
 * handed.
 *
 * A Passage is shown before its record card, deliberately: the quote is the
 * evidence, and the card is who said it.
 */
export function SourceContextPanel({ open, citations, sources, onClose }: SourceContextPanelProps) {
  if (!open) return null;

  const cardFor = (recordId: number) => sources.find((s) => s.id === recordId);

  return (
    <aside
      className="shrink-0 w-[min(100%,320px)] sm:w-[300px] flex flex-col border-l border-stone-200/80 bg-stone-50/50"
      aria-label="Referenced passages"
    >
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-stone-200/60 bg-white">
        <div>
          <h2 className="text-[12px] font-bold text-stone-800">Referenced passages</h2>
          <p className="text-[10px] text-stone-500 mt-0.5">
            The exact text behind the latest answer
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-2 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          aria-label="Hide sources panel"
        >
          <i className="fas fa-xmark text-[13px]" aria-hidden />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-3">
        {citations.length === 0 && (
          <p className="text-[12px] text-stone-500 text-center py-8 px-2">
            Ask a question to see the passages IRIS used in its answer.
          </p>
        )}

        {citations.map((citation) => {
          const card = cardFor(citation.record_id);
          const hasQuote = "text" in citation && "record_title" in citation;
          const section = hasQuote
            ? citation.context_path?.[citation.context_path.length - 1]
            : undefined;

          return (
            <article
              key={`${citation.chunk_id}-${citation.marker}`}
              className="bg-white rounded-xl border border-stone-200/90 p-4 shadow-sm hover:border-[#6B0F12]/20 transition-colors"
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B0F12]">
                  Passage {citation.marker}
                </span>
                {citation.page != null && (
                  <span className="text-[9px] font-semibold text-stone-500">
                    Page {citation.page}
                  </span>
                )}
              </div>

              {hasQuote && <PassageQuote text={citation.text} />}

              <h3 className="text-[13px] font-semibold text-stone-900 leading-snug line-clamp-2 mt-3">
                {card?.title ?? (hasQuote ? citation.record_title : "Source")}
              </h3>
              {section && (
                <p className="text-[10px] text-stone-500 mt-0.5 line-clamp-1">{section}</p>
              )}
              {card?.authors && (
                <p className="text-[11px] text-stone-500 mt-1 line-clamp-1">{card.authors}</p>
              )}

              <OpenPassageLink
                citation={citation}
                title={card?.title ?? (hasQuote ? undefined : "the source")}
                className="mt-3"
              />
            </article>
          );
        })}
      </div>
    </aside>
  );
}
