/**
 * Landing on the page a citation points at (IR-284).
 *
 * A citation links to `/records/<id>?page=<n>`, and the record view turns that
 * into a link that opens the PDF at that page. Two small decisions live here
 * rather than inside the view, so they can be tested without standing up a
 * screen that fetches a record, a review history and a similarity list:
 *
 * * **what counts as a page** — the query string is whatever was typed into
 *   the address bar, so anything that is not a positive whole number is
 *   ignored rather than passed through to the viewer;
 * * **how a page is asked for** — `#page=N`, the fragment every browser PDF
 *   viewer understands. A viewer that does not simply opens at page 1, which
 *   is a worse landing and never a broken link.
 *
 * The other end of that link — building it from a citation — lives here too,
 * so the two halves of one URL cannot drift apart.
 */
import type { Citation } from "@/types/ai";

/** The page a citation asked for, or null when it named none we can use. */
export function citedPage(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const page = Number(raw);
  return Number.isInteger(page) && page > 0 ? page : null;
}

/** The paper's URL, opened at `page` when there is one to open it at. */
export function paperHrefAtPage(url: string | null, page: number | null): string | null {
  if (!url) return null;
  return page == null ? url : `${url}#page=${page}`;
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
