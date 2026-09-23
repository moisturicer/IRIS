/**
 * Landing on the page a citation points at (IR-284, revised IR-335).
 *
 * A citation links to `/records/<id>?page=<n>`, and the paper view reads that
 * to open its embedded reader at that page. What counts as a page lives here
 * — the query string is whatever was typed into the address bar, so anything
 * that is not a positive whole number is ignored rather than passed through
 * to the reader — and so does the other end of the link, building it from a
 * citation, so the two halves cannot drift apart.
 *
 * **`paperHrefAtPage` (the `#page=N` fragment link to a raw PDF URL) is
 * gone, not merely renamed.** It stopped being just outdated and became
 * actively wrong once IR-334 put the manuscript behind `IsAuthenticated`: a
 * plain `<a href>` navigation carries no `Authorization` header — the bearer
 * token lives in memory, never a cookie — so a link built from it now 401s.
 * `PaperPdfReader` fetches the file through `apiClient` instead, and a
 * citation's job is to say which page and which chunk, not to shape a URL to
 * the file at all.
 */
import type { ChatCitation, Citation } from "@/types/ai";

/**
 * Whether `citation` carries the quote and title a live answer has, rather
 * than only the pointer a replayed Turn has until IR-299 re-resolves them.
 *
 * The one check both citation-rendering surfaces (the chat bubble and the
 * sources panel) need to decide whether there is a quote to show at all —
 * kept here, next to the other citation-shape helpers, so the two renderers
 * cannot drift into checking this differently.
 */
export function hasCitationQuote(citation: ChatCitation): citation is Citation {
  return "text" in citation;
}

/** The page a citation asked for, or null when it named none we can use. */
export function citedPage(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const page = Number(raw);
  return Number.isInteger(page) && page > 0 ? page : null;
}

/**
 * Where a citation sends a reader.
 *
 * A passage whose page extraction could not recover links to the record with
 * no page, rather than guessing one: landing confidently on the wrong page is
 * worse than landing on the first.
 */
export function citationHref(citation: Pick<Citation, "record_id" | "page">): string {
  return citation.page != null
    ? `/records/${citation.record_id}?page=${citation.page}`
    : `/records/${citation.record_id}`;
}

/**
 * What that link says.
 *
 * The record's name is in the link text rather than only beside it, so the
 * accessible name of every citation link is distinct — "Open" repeated eight
 * times tells a screen-reader user nothing about which source is which.
 *
 * `citation.record_title` is optional because a replayed citation (IR-298)
 * is a stored pointer with no title of its own — a caller in that position
 * always supplies `title` explicitly, and the fallback below only exists so
 * this never renders "Open undefined" if one somehow does not.
 */
export function openCitationLabel(
  citation: Pick<Citation, "page"> & Partial<Pick<Citation, "record_title">>,
  title?: string,
): string {
  const name = title ?? citation.record_title ?? "the source";
  return citation.page != null ? `Open ${name} at page ${citation.page}` : `Open ${name}`;
}

/**
 * Router `state` for a `<Link>` built from `citationHref` (IR-335).
 *
 * Carries the citation itself, regions included, so the paper view can draw
 * the highlight the moment it renders — no second fetch per citation, the
 * same rule `apps/ai/presentation.py`'s module docstring already states for
 * the record card riding alongside an answer. A replayed citation with no
 * regions of its own still carries its page through the URL; this just adds
 * nothing to highlight with.
 *
 * A caller reads it back with `useLocation().state as CitationNavigationState
 * | null` — `null` on any navigation this link did not originate (a typed
 * URL, a bookmark, a page refresh), which is the graceful case `PaperPdfReader`
 * already handles: no regions, open the page anyway.
 */
export interface CitationNavigationState {
  citation: ChatCitation;
}

export function citationNavigationState(citation: ChatCitation): CitationNavigationState {
  return { citation };
}
