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
import { createContext, useContext } from "react";
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

/**
 * A positive whole number read off the address, or null: a page, or the id
 * of a Conversation, Turn or citation marker (IR-578). Anything typed into
 * the address bar that is not one is ignored rather than passed on.
 */
export function addressNumber(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

/** The page a citation asked for, or null when it named none we can use. */
export function citedPage(raw: string | null): number | null {
  return addressNumber(raw);
}

/**
 * Where a citation sends a reader.
 *
 * A passage whose page extraction could not recover links to the record with
 * no page, rather than guessing one: landing confidently on the wrong page is
 * worse than landing on the first.
 */
export function citationHref(
  citation: Pick<Citation, "record_id" | "page"> & { marker?: number },
  { origin = null, answer = null }: { origin?: CitationOrigin | null; answer?: AnswerTurn | null } = {},
): string {
  const params = new URLSearchParams();
  if (citation.page != null) params.set("page", String(citation.page));
  // Ids only (IR-578): the question and the quote never go in an address.
  if (answer) {
    params.set("conversation", String(answer.conversationId));
    params.set("turn", String(answer.turnId));
    if (citation.marker) params.set("cite", String(citation.marker));
    if (origin === "paper-chat") params.set("from", "paper");
  }
  if (origin === "overview") params.set("context", "page");
  const query = params.toString();
  return `/records/${citation.record_id}${query ? `?${query}` : ""}`;
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
  /**
   * Where the citation was followed from, when that matters to the screen
   * it lands on (IR-355). Absent everywhere but Paper Chat and the Overview.
   */
  origin?: CitationOrigin;
  /** The answer it was followed from (IR-578). */
  answer?: AnswerTurn;
  /**
   * The page load that wrote this state (IR-578). A reload keeps router
   * state, so state from another load is stale: the paper view re-resolves
   * the citation from the address, or highlights nothing.
   */
  load?: string;
}

/**
 * A surface whose citations the paper view treats differently. Paper Chat
 * keeps its conversation open on the paper a citation lands on (IR-355); the
 * Overview cites whole pages, which land as page context (IR-578).
 */
export type CitationOrigin = "paper-chat" | "overview";

/** One answer in one of the reader's own Conversations (IR-578). */
export interface AnswerTurn {
  conversationId: number;
  turnId: number;
}

/** A request to show that answer again; `key` makes a repeat a request again. */
export type AnswerReturn = AnswerTurn & { key: number };

/** This page load. Router state from another one is not trusted. */
const PAGE_LOAD = crypto.randomUUID();

export function citationNavigationState(
  citation: ChatCitation,
  origin?: CitationOrigin | null,
  answer?: AnswerTurn | null,
): CitationNavigationState {
  // Stamped wherever a reload would otherwise keep an unchecked highlight:
  // an answer's citation, or an Overview page.
  const stamped = answer != null || origin === "overview";
  return {
    citation,
    ...(origin ? { origin } : {}),
    ...(answer ? { answer } : {}),
    ...(stamped ? { load: PAGE_LOAD } : {}),
  };
}

/**
 * Which transcript the citations below were rendered in. The citation links
 * read it, so a transcript marks its own citations without every component
 * between it and the link passing the mark down; outside any provider it is
 * `null`, and a citation carries no origin.
 */
export const CitationOriginContext = createContext<CitationOrigin | null>(null);

/**
 * Whether this navigation followed a citation inside Paper Chat (IR-355).
 * `state` is `useLocation().state`: whatever the navigation that got here
 * left behind, which on a typed URL or a link elsewhere is nothing at all.
 */
export function followedFromPaperChat(state: unknown): boolean {
  return (state as CitationNavigationState | null)?.origin === "paper-chat";
}

/**
 * The Conversation the citations below belong to, and the answer, set by
 * the transcript and by each answer in it (IR-578). Either `null` and a
 * citation carries no way back to its answer.
 */
export const CitationConversationContext = createContext<number | null>(null);
export const CitationTurnContext = createContext<number | null>(null);

/**
 * Where a citation rendered here links to, and the router state it carries.
 * The one place a citation link is built, so every surface carries its
 * origin and its answer the same way.
 */
export function useCitationLink(
  citation: ChatCitation | (Pick<Citation, "record_id" | "page"> & Partial<Pick<Citation, "record_title">>),
  /** False where the marker is not one of the answer's citations: no `cite` to re-read. */
  { resolvable = true }: { resolvable?: boolean } = {},
) {
  const origin = useContext(CitationOriginContext);
  const conversationId = useContext(CitationConversationContext);
  const turnId = useContext(CitationTurnContext);
  const answer = conversationId != null && turnId != null ? { conversationId, turnId } : null;
  return {
    to: citationHref(
      resolvable ? citation : { record_id: citation.record_id, page: citation.page },
      { origin, answer },
    ),
    state: isChatCitation(citation) ? citationNavigationState(citation, origin, answer) : undefined,
    /** An Overview page, which the paper lands as page context. */
    pageContext: origin === "overview",
  };
}

function isChatCitation(citation: object): citation is ChatCitation {
  return "marker" in citation;
}

/**
 * The answer a paper was opened from, read off its address (IR-578). `null`
 * unless it names a Conversation and a Turn; `marker` is null when the link
 * named no citation to re-resolve (a comparison's page link).
 */
export interface AnswerReference extends AnswerTurn {
  marker: number | null;
  from: "ask" | "paper-chat";
}

export function answerReference(params: URLSearchParams): AnswerReference | null {
  const conversationId = addressNumber(params.get("conversation"));
  const turnId = addressNumber(params.get("turn"));
  if (conversationId == null || turnId == null) return null;
  return {
    conversationId,
    turnId,
    marker: addressNumber(params.get("cite")),
    from: params.get("from") === "paper" ? "paper-chat" : "ask",
  };
}

/**
 * The citation this navigation carried, when it can be trusted as it is:
 * written by this page load for the answer the address names. Anything else
 * -- a reload, a restored tab -- is re-resolved from the address.
 */
export function trustedCitation(state: unknown, reference: AnswerReference | null): ChatCitation | null {
  const carried = state as CitationNavigationState | null;
  if (!carried?.citation) return null;
  const thisLoad = carried.load === PAGE_LOAD;
  if (!reference) {
    // An Overview page cannot be re-read from its address, so a stale one
    // highlights nothing; a plain link's state is used as it always was.
    return carried.origin === "overview" && !thisLoad ? null : carried.citation;
  }
  const answer = carried.answer;
  return thisLoad &&
    answer?.conversationId === reference.conversationId &&
    answer.turnId === reference.turnId
    ? carried.citation
    : null;
}

/** Whether the address says this is the Overview's page context (IR-578). */
export function landedAsPageContext(params: URLSearchParams, state: unknown): boolean {
  return params.get("context") === "page" || (state as CitationNavigationState | null)?.origin === "overview";
}
