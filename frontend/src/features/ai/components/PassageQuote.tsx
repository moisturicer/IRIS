import { Link } from "react-router-dom";
import type { Citation } from "@/types/ai";
import { citationHref, openCitationLabel } from "@/lib/citedPage";

/**
 * The pieces every surface that shows a Passage needs (IR-284).
 *
 * Three places quote a passage — the chat bubble, the sources panel and the
 * paper overview — and each frames it differently: one numbers it by marker,
 * one shows a page badge and a record card, one shows only the quote. The
 * *framing* is theirs. What must not be written three times is the quote
 * block and the link, because those carry the two things a reader is being
 * promised: the exact words, and a way to reach the page they sit on.
 *
 * Kept as two small components rather than one with flags: a component that
 * takes `showMarker`, `showPage`, `showCard` is three components wearing a
 * trench coat, and the next surface adds a fourth flag.
 */

/**
 * The quoted text itself.
 *
 * Clamped to three lines, with the full text on `title` so a reader can reach
 * the rest without the card growing to a paragraph. `cite` is not set: it
 * takes a URL for the *source document*, and the record page is not that.
 */
export function PassageQuote({ text, className = "" }: { text: string; className?: string }) {
  return (
    <blockquote
      title={text}
      className={
        "text-[11px] text-stone-600 leading-relaxed line-clamp-3 border-l-2 " +
        "border-[#6B0F12]/25 pl-2 italic " +
        className
      }
    >
      {text}
    </blockquote>
  );
}

/**
 * The way to the page the quote came from.
 *
 * `title` overrides the record's name when a caller holds a better one — the
 * sources panel has the record card, whose title is the canonical one, while
 * the citation carries the title retrieval saw.
 */
export function OpenPassageLink({
  citation,
  title,
  className = "",
}: {
  citation: Citation;
  title?: string;
  className?: string;
}) {
  return (
    <Link
      to={citationHref(citation)}
      className={
        "inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#6B0F12] " +
        "hover:underline " +
        className
      }
    >
      {openCitationLabel(citation, title)}
      <i className="fas fa-arrow-right text-[9px]" aria-hidden />
    </Link>
  );
}

/**
 * What a reader is told when retrieval fell back to keyword matching.
 *
 * ADR-008 promises a reader is told when an answer came the slow way. One
 * wording, in one place: two surfaces phrasing the same fact differently is
 * how one of them ends up saying something subtly untrue.
 */
export function DegradedNotice({ subject }: { subject: "answer" | "summary" }) {
  return (
    <p className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-700">
      <i className="fas fa-triangle-exclamation text-[10px] mt-0.5" aria-hidden />
      <span>
        Found by keyword matching, not meaning — the search service was unavailable, so
        weigh this {subject} accordingly.
      </span>
    </p>
  );
}
