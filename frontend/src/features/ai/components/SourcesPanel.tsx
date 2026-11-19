import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { ChatCitation, SemanticSearchResult } from "@/types/ai";
import { hasCitationQuote, useCitationLink } from "@/lib/citedPage";
import { cn } from "@/lib/utils";
import { SELECTED_RING } from "@/components/ui/highlightRoles";
import { ChatDrawer } from "./ChatDrawer";
import { withMathRendered } from "./PassageQuote";

/** Where the panel sits: beside the chat, over it (a dialog), or a phone's bottom sheet. */
export type SourcesMode = "beside" | "over" | "sheet";

interface SourcesPanelProps {
  mode: SourcesMode;
  /** The panel's id, for the header toggle's `aria-controls`. */
  id: string;
  /** The Passages the selected answer cited, in marker order. */
  citations: ChatCitation[];
  /** The Record cards those Passages came from. */
  sources: SemanticSearchResult[];
  /** The marker to highlight and scroll to, or `null` when opened from the count. */
  active: number | null;
  /** The question of the answer these passages belong to; `null` before any answer. */
  question: string | null;
  onClose: () => void;
  /** Where focus goes back to when a dialog mode closes. */
  returnTo: HTMLElement | null;
}

function titleOf(citation: ChatCitation, card?: SemanticSearchResult): string {
  return card?.title ?? ("record_title" in citation ? citation.record_title : undefined) ?? "Source";
}

/**
 * One cited passage as the reader's evidence (IR-1237): its number, the paper in
 * serif, who wrote it and when with the page, the quote, and the way into the paper.
 */
function SourceItem({ citation, card, active }: { citation: ChatCitation; card?: SemanticSearchResult; active: boolean }) {
  const { to, state } = useCitationLink(citation);
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [active]);
  const title = titleOf(citation, card);
  const byline = [card?.authors?.trim(), card?.year, citation.page != null ? `p. ${citation.page}` : null]
    .filter(Boolean).join(" · ");
  return (
    <li ref={ref} aria-label={`Source ${citation.marker}: ${title}`} aria-current={active ? "true" : undefined}
      className={cn("rounded-card border bg-surface p-3 transition-colors duration-150",
        active ? "border-stone-900 ring-1 ring-stone-900" : "border-stone-200")}>
      <div className="flex items-start gap-2.5">
        <span aria-hidden className={cn("mt-0.5 grid h-[18px] min-w-[18px] shrink-0 place-items-center rounded-control px-1 text-2xs font-semibold tabular-nums leading-none",
          active ? SELECTED_RING : "bg-stone-100 text-brand")}>
          {citation.marker}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-body font-semibold leading-snug text-stone-900">{title}</h3>
          {byline && <p className="mt-0.5 text-label text-stone-500">{byline}</p>}
          {hasCitationQuote(citation) && (
            <blockquote className="mt-2 border-l-2 border-brand/25 pl-2.5 text-small leading-relaxed text-stone-700">
              {withMathRendered(citation.text)}
            </blockquote>
          )}
          {/* The visible words are the start of the name, so a speech user can say what they see. */}
          <Link to={to} state={state}
            aria-label={`${citation.page != null ? `Open at page ${citation.page}` : "Open paper"} in ${title}`}
            className="mt-2 inline-flex items-center gap-1.5 text-small font-semibold text-brand hover:underline">
            {citation.page != null ? `Open at page ${citation.page}` : "Open paper"}
            <i className="fas fa-arrow-right text-2xs" aria-hidden />
          </Link>
        </div>
      </div>
    </li>
  );
}

function SourceList({ citations, sources, active, answered }:
  Pick<SourcesPanelProps, "citations" | "sources" | "active"> & { answered: boolean }) {
  if (citations.length === 0) {
    return <p className="px-4 py-6 text-center text-small text-stone-500">
      {answered ? "This answer cited no passages." : "Ask a question to see the passages IRIS used in its answer."}
    </p>;
  }
  return (
    <ol className="space-y-2.5 p-3">
      {citations.map((citation) => (
        <SourceItem key={`${citation.chunk_id}-${citation.marker}`} citation={citation}
          card={sources.find((s) => s.id === citation.record_id)} active={citation.marker === active} />
      ))}
    </ol>
  );
}

/**
 * The passages an answer cited, beside it, over it or as a phone's sheet (IR-1237).
 * Mounted only while open. Beside the chat it is a region the conversation stays
 * usable next to; over it and as a sheet it is a dialog.
 */
export function SourcesPanel({ mode, id, citations, sources, active, question, onClose, returnTo }: SourcesPanelProps) {
  const body = <SourceList citations={citations} sources={sources} active={active} answered={question !== null} />;
  const subtitle = question ? `For “${question}”` : "The exact text behind the answer";

  const closeNow = useRef(onClose);
  closeNow.current = onClose;
  useEffect(() => {
    // The dialog modes already close on Escape; beside the chat nothing else does.
    if (mode !== "beside") return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) closeNow.current(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mode]);

  if (mode !== "beside") {
    return (
      <ChatDrawer title="Sources" description={subtitle} side={mode === "sheet" ? "bottom" : "end"}
        closeLabel="Close sources" onClose={onClose} returnTo={returnTo}>
        <div id={id} className="min-h-0 flex-1 overflow-y-auto">{body}</div>
      </ChatDrawer>
    );
  }
  return (
    <aside id={id} aria-label="Sources"
      className="flex h-full w-[360px] shrink-0 flex-col border-l border-stone-200/80 bg-canvas">
      <div className="flex min-h-[56px] shrink-0 items-start gap-2 border-b border-stone-200/80 py-1.5 pl-4 pr-1.5">
        <div className="min-w-0 flex-1 py-2">
          <h2 className="text-heading font-semibold text-stone-900">Sources</h2>
          <p className="mt-0.5 line-clamp-2 text-2xs text-stone-500">{subtitle}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close sources"
          className="flex size-11 shrink-0 items-center justify-center rounded-control text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-800">
          <i className="fas fa-xmark text-base" aria-hidden />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">{body}</div>
    </aside>
  );
}
