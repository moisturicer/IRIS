import type { ComponentPropsWithoutRef } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { ChatCitation } from "@/types/ai";
import { citationHref, citationNavigationState, hasCitationQuote, openCitationLabel } from "@/lib/citedPage";

/**
 * An answer's text with citation markers rendered as inline chips (IR-329).
 *
 * The trick: rewrite `[1]` to `[1](iris-citation:1)` before markdown
 * parsing, then intercept that scheme in a custom `a` renderer -- a link is
 * already inline, unlike splitting across several `<ReactMarkdown>` calls.
 *
 * While streaming, markers may still be raw/unparsed (lenticular, multi-
 * number); `parse_citations` only canonicalizes to `[n]` once the stream ends.
 */

const CITATION_SCHEME = "iris-citation:";
const PENDING = "pending";

/** Canonical, post-`parse_citations` markers: `[1]`, never `[1,2]` or `【1】`. */
const RESOLVED_MARKER = /\[(\d+)\]/g;

/** A citation-shaped span in raw streaming text -- mirrors (not shares code
 *  with) `_MARKER` in `apps/ai/answers/citations.py`. Display heuristic only. */
const STREAMING_MARKER =
  /\[\s*\d+(?:\s*,\s*\d+)*[^[\]【】［］\n]{0,64}\]|【\s*\d+(?:\s*,\s*\d+)*[^[\]【】［］\n]{0,64}】|［\s*\d+(?:\s*,\s*\d+)*[^[\]【】［］\n]{0,64}］/g;

/** `react-markdown` sanitizes unknown link schemes away by default -- pass
 *  ours through, everything else still gets the library's own sanitizing. */
function urlTransform(url: string): string {
  return url.startsWith(CITATION_SCHEME) ? url : defaultUrlTransform(url);
}

function toMarkdownLinks(text: string, streaming: boolean): string {
  if (streaming) {
    return text.replace(STREAMING_MARKER, () => `[·](${CITATION_SCHEME}${PENDING})`);
  }
  return text.replace(RESOLVED_MARKER, (_match, marker: string) => `[${marker}](${CITATION_SCHEME}${marker})`);
}

/** A marker still streaming in, not yet resolved to a citation. */
function CitationPlaceholder() {
  return (
    <span
      aria-hidden
      className="inline-block w-[7px] h-[7px] rounded-full bg-stone-300 align-middle mx-0.5 animate-pulse motion-reduce:animate-none"
    />
  );
}

/** A resolved citation, as a small clickable pill sitting inline in the text. */
function CitationChip({ citation }: { citation: ChatCitation }) {
  const label = openCitationLabel(
    citation,
    hasCitationQuote(citation) ? undefined : "the source",
  );
  return (
    <Link
      to={citationHref(citation)}
      // The citation itself, regions included -- so the paper view can draw
      // the highlight without a second fetch (IR-335). See
      // `citationNavigationState`'s own doc for the graceful fallback.
      state={citationNavigationState(citation)}
      title={label}
      aria-label={label}
      className="inline-flex items-center justify-center w-[15px] h-[15px] rounded-full
        bg-[#6B0F12]/10 text-[8px] font-bold text-[#6B0F12] align-super leading-none
        no-underline hover:bg-[#6B0F12]/20 mx-px"
    >
      {citation.marker}
    </Link>
  );
}

interface CitationTextProps {
  text: string;
  citations: ChatCitation[];
  /** True while this message is still streaming in -- see the module doc. */
  streaming?: boolean;
  className?: string;
}

export function CitationText({ text, citations, streaming = false, className }: CitationTextProps) {
  const byMarker = new Map(citations.map((citation) => [citation.marker, citation]));

  function CitationLink({ href, children }: ComponentPropsWithoutRef<"a">) {
    if (!href?.startsWith(CITATION_SCHEME)) {
      return (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    }

    const key = href.slice(CITATION_SCHEME.length);
    if (key === PENDING) return <CitationPlaceholder />;

    const citation = byMarker.get(Number(key));
    // An unresolved or invented marker resolves to nothing -- no visible
    // gap, no dangling chip (IR-329).
    if (!citation) return null;

    return <CitationChip citation={citation} />;
  }

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{ a: CitationLink }}
        urlTransform={urlTransform}
      >
        {toMarkdownLinks(text, streaming)}
      </ReactMarkdown>
    </div>
  );
}
