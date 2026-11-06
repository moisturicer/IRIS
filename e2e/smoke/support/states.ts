// The states of docs/ui-ux/17-ui-states-matrix.md (IR-906) that axe scans (IR-908).
//
// Each entry takes a screen from screens.ts as the page's ordinary mocks and
// replaces the one read that decides the state. The matrix's five states are:
//   loading     the read is never answered, so the placeholder stays on screen
//   empty       the read worked and returned nothing
//   error       the read failed outright (500)
//   interrupted the read got no answer in time (ADR-061); see `timeOut`
//   revoked     the server answered 403 or 404, which read alike (IR-153)
// A cell the matrix marks N/A has no entry here, and neither has a state a
// surface does not have.
//
// `shows` finds the thing that proves the screen is in the state and not in
// the one before it; without it a scan could run on the wrong screen.
import type { Locator, Page } from "@playwright/test";
import { hang } from "./open-screen";
import type { MockApi } from "./mock-api";
import { PAPER, PAPER_DETAIL, paginated } from "./fixtures";

export type MatrixState = "loading" | "empty" | "error" | "interrupted" | "revoked";

export interface UiState {
  /** The screen in screens.ts whose mocks the state starts from, and whose address it opens. */
  screen: string;
  state: MatrixState;
  /** Overrides the address, for a screen with several views (My Library). */
  path?: string;
  /** What this variant is, when a surface has more than one view or refusal. */
  variant?: string;
  override: (api: MockApi) => void;
  /** Reads the test never answers time out (the interrupted state). */
  timeOut?: boolean;
  shows: (page: Page) => Locator;
}

const failed = { detail: "smoke: the read failed" };
/** A loading placeholder that announces itself: `role="status"` carrying the given words. */
const announced = (words: string | RegExp) => (page: Page) => page.getByRole("status").filter({ hasText: words }).first();
const text = (value: string | RegExp) => (page: Page) => page.getByText(value).first();
const TOOK_TOO_LONG = text("This took too long");

/** Overrides one read with each of the four answers that are not a success. */
function reads(
  screen: string,
  method: string,
  path: string,
  copy: { error: string | RegExp; revoked?: string | RegExp; empty?: { reply: unknown; shows: string | RegExp } },
  options: {
    variant?: string;
    path?: string;
    loading: (page: Page) => Locator;
    /** Mocks that put the screen where the read happens, applied before the read's own. */
    also?: (api: MockApi) => void;
    /** What an interrupted read says, when it is not the shared "This took too long". */
    interrupted?: string;
  },
): UiState[] {
  const also = options.also ?? (() => undefined);
  const base = { screen, path: options.path, variant: options.variant };
  const states: UiState[] = [
    { ...base, state: "loading", override: (api) => { also(api); api.on(method, path, hang); }, shows: options.loading },
    { ...base, state: "error", override: (api) => { also(api); api.on(method, path, failed, 500); }, shows: text(copy.error) },
    { ...base, state: "interrupted", override: (api) => { also(api); api.on(method, path, hang); }, timeOut: true, shows: options.interrupted ? text(options.interrupted) : TOOK_TOO_LONG },
  ];
  if (copy.empty) {
    const { reply, shows } = copy.empty;
    states.push({ ...base, state: "empty", override: (api) => { also(api); api.on(method, path, reply); }, shows: text(shows) });
  }
  if (copy.revoked) {
    for (const status of [403, 404]) {
      states.push({
        ...base, state: "revoked", variant: [options.variant, String(status)].filter(Boolean).join(" "),
        override: (api) => { also(api); api.on(method, path, failed, status); }, shows: text(copy.revoked!),
      });
    }
  }
  return states;
}

/**
 * A Record the signed-in reader takes part in, so Paper View draws the review
 * panels that read the tracker. Only the read under test is mocked after it.
 */
const asParticipant = (api: MockApi) => api.on("GET", `/records/${PAPER.id}/`, { ...PAPER_DETAIL, is_participant: true });

export const STATES: UiState[] = [
  // Discover: nothing to revoke (the list is read under the visibility predicate every time).
  ...reads("discover", "GET", "/records/", {
    error: "We couldn't load research",
    empty: { reply: paginated([]), shows: "Nothing has been published yet." },
  }, { loading: announced("Loading research") }),

  // Paper View: one Record that exists, so no empty state. A hidden Record and a missing id read alike.
  ...reads("paper-view", "GET", "/records/101/", {
    error: "We couldn't load this record",
    revoked: "Record not available",
  }, { loading: (page) => page.locator(".animate-pulse").first() }),

  // Review panels in Paper View. Both read the record's tracker, and a 403 or 404 there reads as
  // an ordinary failure (the matrix's known gap), so the refusal cells expect the failure copy.
  ...reads("paper-view", "GET", "/records/101/tracker/", {
    error: "Could not load the review tracker.",
    revoked: "Could not load the review tracker.",
  }, {
    variant: "review tracker", also: asParticipant, interrupted: "The review tracker took too long to load.",
    loading: (page) => page.getByRole("region", { name: /Review & Routing/ }).locator(".animate-pulse").first(),
  }),
  ...reads("paper-view", "GET", "/records/101/tracker/", {
    error: "Could not load the review timeline.",
    revoked: "Could not load the review timeline.",
  }, {
    variant: "review timeline", path: "/records/101?section=review", also: asParticipant,
    interrupted: "The review timeline took too long to load.",
    loading: (page) => page.getByRole("region", { name: "Timeline" }).locator(".animate-pulse").first(),
  }),

  // My Library's views.
  ...reads("my-library", "GET", "/records/mine/", {
    error: "Could not load your research",
  }, { variant: "overview", loading: announced("Loading your research") }),
  ...reads("my-library", "GET", "/records/mine/", {
    error: "Could not load your research",
  }, { variant: "my research", path: "/records/mine?section=research", loading: announced("Loading your research") }),
  ...reads("my-library", "GET", "/library/saves/", {
    error: /Could not load/,
  }, { variant: "saved", path: "/records/mine?section=saved", loading: announced("Loading saved papers") }),
  ...reads("my-library", "GET", "/records/download-requests/mine/", {
    error: "Could not load your download requests",
    empty: { reply: [], shows: "No download requests yet" },
  }, { variant: "download requests", path: "/records/mine?section=downloads", loading: announced("Loading your download requests") }),

  // Ask IRIS, Django path: an address that cannot be read says the conversation is not available.
  ...reads("ask-iris-conversation", "GET", "/ai/conversations/1/", {
    error: "Could not load this conversation",
    revoked: "This conversation is not available.",
  }, { loading: announced("Loading this conversation") }),

  // Review.
  ...reads("my-reviews", "GET", "/reviews/mine/", {
    error: "Could not load My Reviews",
    revoked: "My Reviews isn't available to you",
  }, { loading: (page) => page.locator('[aria-busy="true"]').first() }),
  ...reads("office-console", "GET", "/reviews/office/", {
    error: "Could not load the console",
    revoked: "This console is for coordinators",
  }, { loading: (page) => page.locator('[aria-busy="true"]').first() }),
];

/** A stable name for the results and the test title. */
export const stateId = (s: UiState) =>
  [s.screen, s.variant, s.state].filter(Boolean).join(" · ");
