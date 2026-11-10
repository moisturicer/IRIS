// The states of docs/ui-ux/17-ui-states-matrix.md (IR-906) that axe scans (IR-908)
// and that forced-states.spec.ts forces and asserts on (IR-907).
//
// Each entry takes a screen from screens.ts as the page's ordinary mocks and
// replaces the one read that decides the state. The matrix's five states are:
//   loading     the read is never answered, so the placeholder stays on screen
//   empty       the read worked and returned nothing
//   error       the read failed outright (500)
//   interrupted the read got no answer in time (ADR-061); see `timeOut`
//   revoked     the server answered 403 or 404, which read alike (IR-153)
// A cell the matrix marks N/A has no entry here, and neither has a state a
// surface does not have. The extra cells whose scans need a second interaction
// or a different response shape live in AXE_STATES below; forced-cells.spec.ts
// still proves their behavior and recovery.
//
// `shows` finds the thing that proves the screen is in the state and not in
// the one before it; without it a scan could run on the wrong screen.
import type { Locator, Page, Request, Route } from "@playwright/test";
import { hang, makeLaterReadsTimeOut } from "./open-screen";
import type { MockApi } from "./mock-api";
import { PAPER, PAPER_DETAIL, RUNTIME_CONVERSATION, RUNTIME_CONVERSATION_PATH, paginated } from "./fixtures";

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
  // The three fields below are what forced-states.spec.ts (IR-907) adds to the
  // catalogue: the axe scan needs only the state, the forced-state tests also
  // need to answer the same read again and say what the reader does next.
  /** The one read that decides the state, so a test can answer it differently. */
  read: { method: string; path: string };
  /** What that read answers when it works. */
  ok: unknown;
  /** Visible once the read has worked: proof the screen left the state for its content. */
  recovered: (page: Page) => Locator;
  /** A way on that is not a retry: the state's own next step, when it offers one (empty, revoked). */
  next?: (page: Page) => Locator;
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
    /** What the read answers when it works, and what then proves the screen drew it. */
    ok: unknown;
    recovered: (page: Page) => Locator;
    /** Mocks that put the screen where the read happens, applied before the read's own. */
    also?: (api: MockApi) => void;
    /** What an interrupted read says, when it is not the shared "This took too long". */
    interrupted?: string;
    /** What the reader can do from an empty or a refused screen, when it offers anything. */
    emptyNext?: (page: Page) => Locator;
    revokedNext?: (page: Page) => Locator;
  },
): UiState[] {
  const also = options.also ?? (() => undefined);
  const base = {
    screen, path: options.path, variant: options.variant,
    read: { method, path }, ok: options.ok, recovered: options.recovered,
  };
  const states: UiState[] = [
    { ...base, state: "loading", override: (api) => { also(api); api.on(method, path, hang); }, shows: options.loading },
    { ...base, state: "error", override: (api) => { also(api); api.on(method, path, failed, 500); }, shows: text(copy.error) },
    { ...base, state: "interrupted", override: (api) => { also(api); api.on(method, path, hang); }, timeOut: true, shows: options.interrupted ? text(options.interrupted) : TOOK_TOO_LONG },
  ];
  if (copy.empty) {
    const { reply, shows } = copy.empty;
    states.push({ ...base, state: "empty", override: (api) => { also(api); api.on(method, path, reply); }, shows: text(shows), next: options.emptyNext });
  }
  if (copy.revoked) {
    for (const status of [403, 404]) {
      states.push({
        ...base, state: "revoked", variant: [options.variant, String(status)].filter(Boolean).join(" "),
        override: (api) => { also(api); api.on(method, path, failed, status); }, shows: text(copy.revoked!),
        next: options.revokedNext,
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

/** The tracker as the review panels read it: nobody has acted yet, a viewer who may not read the review gets nulls. */
export const TRACKER = {
  record_id: PAPER.id, record_type: "Thesis / Research", workflow_state: "published", workflow_state_label: "Published",
  current_holders: [{ party: "rdco", label: "RDCO" }], parties: [], routing_history: [], routing_recorded_from: null,
  reviews: [], versions: [], review_comments: [], resubmissions: [],
};

export const EMPTY_REVIEWS = { rows: [], counts: { to_review: 0, in_review: 0, done: 0 }, next: null };
export const EMPTY_CONSOLE = { office: "rdco", office_label: "RDCO", rows: [], load: [] };

export const STATES: UiState[] = [
  // Discover: nothing to revoke (the list is read under the visibility predicate every time).
  ...reads("discover", "GET", "/records/", {
    error: "We couldn't load research",
    empty: { reply: paginated([]), shows: "Nothing has been published yet." },
  }, {
    loading: announced("Loading research"),
    ok: paginated([PAPER]), recovered: text(PAPER.title),
    emptyNext: (page) => page.getByRole("button", { name: "Publish" }).first(),
  }),

  // Paper View: one Record that exists, so no empty state. A hidden Record and a missing id read alike.
  ...reads("paper-view", "GET", "/records/101/", {
    error: "We couldn't load this record",
    revoked: "Record not available",
  }, {
    loading: (page) => page.locator(".animate-pulse").first(),
    ok: PAPER_DETAIL, recovered: (page) => page.getByRole("heading", { name: PAPER.title }),
    revokedNext: (page) => page.getByRole("link", { name: "Go to Discover" }),
  }),

  // Review panels in Paper View. Both read the record's tracker. The matrix marks their refused
  // cell N/A (a 403 or 404 reads as an ordinary failure, a known gap), so there is no entry for it.
  ...reads("paper-view", "GET", "/records/101/tracker/", {
    error: "Could not load the review tracker.",
  }, {
    variant: "review tracker", also: asParticipant, interrupted: "The review tracker took too long to load.",
    ok: TRACKER, recovered: text("Currently with"),
    loading: (page) => page.getByRole("region", { name: /Review & Routing/ }).locator(".animate-pulse").first(),
  }),
  ...reads("paper-view", "GET", "/records/101/tracker/", {
    error: "Could not load the review timeline.",
  }, {
    variant: "review timeline", path: "/records/101?section=review", also: asParticipant,
    interrupted: "The review timeline took too long to load.",
    ok: TRACKER, recovered: text("Nothing has happened in this review yet."),
    loading: (page) => page.getByRole("region", { name: "Timeline" }).locator(".animate-pulse").first(),
  }),

  // My Library's views.
  ...reads("my-library", "GET", "/records/mine/", {
    error: "Could not load your research",
    empty: { reply: [], shows: "You haven’t published anything yet" },
  }, {
    variant: "overview", loading: announced("Loading your research"),
    ok: [], recovered: text("You haven’t published anything yet"),
  }),
  ...reads("my-library", "GET", "/records/mine/", {
    error: "Could not load your research",
    empty: { reply: [], shows: "You haven’t published anything yet" },
  }, {
    variant: "my research", path: "/records/mine?section=research", loading: announced("Loading your research"),
    ok: [], recovered: text("You haven’t published anything yet"),
  }),
  ...reads("my-library", "GET", "/library/saves/", {
    error: /Could not load/,
  }, {
    variant: "saved", path: "/records/mine?section=saved", loading: announced("Loading saved papers"),
    ok: { results: [] }, recovered: text("No saved papers yet"),
  }),
  ...reads("my-library", "GET", "/records/download-requests/mine/", {
    error: "Could not load your download requests",
    empty: { reply: [], shows: "No download requests yet" },
  }, {
    variant: "download requests", path: "/records/mine?section=downloads", loading: announced("Loading your download requests"),
    ok: [], recovered: text("No download requests yet"),
  }),

  // Ask IRIS on the runtime: an address that cannot be read says the conversation is not available.
  ...reads("ask-iris-conversation", "GET", RUNTIME_CONVERSATION_PATH, {
    error: "Could not load this conversation",
    revoked: "This conversation is not available.",
  }, {
    loading: announced("Loading this conversation"),
    ok: RUNTIME_CONVERSATION, recovered: text("What would you like to investigate?"),
    revokedNext: (page) => page.getByRole("link", { name: "Start a new chat" }),
  }),

  // Review.
  ...reads("my-reviews", "GET", "/reviews/mine/", {
    error: "Could not load My Reviews",
    empty: { reply: EMPTY_REVIEWS, shows: "Nothing to review" },
    revoked: "My Reviews isn't available to you",
  }, {
    loading: (page) => page.locator('[aria-busy="true"]').first(),
    ok: EMPTY_REVIEWS, recovered: text("Nothing to review"),
  }),
  ...reads("office-console", "GET", "/reviews/office/", {
    error: "Could not load the console",
    empty: { reply: EMPTY_CONSOLE, shows: /Nothing open at/ },
    revoked: "This console is for coordinators",
  }, {
    loading: (page) => page.locator('[aria-busy="true"]').first(),
    ok: EMPTY_CONSOLE, recovered: text(/Nothing open at/),
  }),
];

/** Matrix cells whose axe scan needs a second interaction or a specialized fixture. */
export interface AxeState {
  id: string;
  screen: string;
  path?: string;
  override?: (api: MockApi) => void;
  prepare?: (page: Page) => Promise<void>;
  shows: (page: Page) => Locator;
}

const pageNumber = (request: Request) => new URL(request.url()).searchParams.get("page");

export const AXE_STATES: AxeState[] = [
  {
    id: "discover · filtered empty", screen: "discover", path: "/?q=flood",
    override: (api) => api.on("GET", "/records/", paginated([])),
    shows: (page) => page.getByRole("heading", { name: "No research matches these filters" }),
  },
  {
    id: "discover · load more timed out", screen: "discover",
    override: (api) => api.on("GET", "/records/", async (route: Route, request: Request) => {
      if (pageNumber(request) === "2") {
        // Let the browser's capped XHR timeout produce the interrupted state,
        // then settle the route so Chromium can close cleanly after the scan.
        await new Promise<void>((resolve) => setTimeout(resolve, 1_000));
        return route.fulfill({ status: 503, json: failed });
      }
      return route.fulfill({ json: { count: 2, next: "/records/?page=2", previous: null, results: [PAPER] } });
    }),
    prepare: async (page) => {
      const loadMore = page.getByRole("button", { name: "Load more (1 left)" });
      await loadMore.waitFor();
      await makeLaterReadsTimeOut(page, "/records/");
      await loadMore.click();
    },
    shows: (page) => page.getByText("More results didn't load."),
  },
  {
    id: "saved · empty", screen: "my-library", path: "/records/mine?section=saved",
    shows: (page) => page.getByText("No saved papers yet"),
  },
  {
    id: "saved · no longer available", screen: "my-library", path: "/records/mine?section=saved",
    override: (api) => api.on("GET", "/library/saves/", { results: [{ record_id: 999, available: false }] }),
    shows: (page) => page.getByText(/1 saved paper is no longer available to you/),
  },
  ...([
    ["to_review", "Nothing to review"],
    ["in_review", "Nothing in review"],
    ["done", "No decisions yet"],
  ] as const).map(([tab, title]) => ({
    id: `my reviews · ${tab.replace("_", " ")} empty`, screen: "my-reviews", path: `/review?tab=${tab}`,
    override: (api: MockApi) => api.on("GET", "/reviews/mine/", EMPTY_REVIEWS),
    shows: (page: Page) => page.getByText(title),
  })),
  // Ask IRIS on the AI runtime (IR-957): the history failing leaves the chat usable.
  {
    id: "ask iris · history failure", screen: "ask-iris",
    override: (api) => api.on("GET", "/ai/runtime/conversations", failed, 500),
    shows: (page) => page.getByText("What would you like to investigate?"),
  },
  {
    id: "ask iris · no sources", screen: "ask-iris-conversation",
    override: (api) => api.on("GET", RUNTIME_CONVERSATION_PATH, {
      ...RUNTIME_CONVERSATION, revision: 1, runs: [{
        protocol: "runs-reader-1", id: "00000000-0000-4000-8000-000000000001", conversation_id: RUNTIME_CONVERSATION.id,
        state: "completed", question: "What about the moon?", base_revision: 0, version: 3,
        turn_id: "00000000-0000-4000-8000-000000000003", depth: "ordinary", awaiting_reader: false,
        created_at: "2026-11-05T00:00:00+00:00", finished_at: "2026-11-05T00:00:00+00:00", kind: "ask",
        plan: null, context: null, compaction: null, cursor: 2, retry_of: null, retried_by: null,
        sources_available: true, capabilities: { manual_compaction: false },
      }], turns: [{
        id: "00000000-0000-4000-8000-000000000003", run_id: "00000000-0000-4000-8000-000000000001", ordinal: 1,
        question: "What about the moon?", answer: "The sources IRIS read do not establish an answer to this question.",
        kind: "answer", created_at: "2026-11-05T00:00:00+00:00", citations: [],
      }],
    }),
    shows: (page) => page.getByText("The sources IRIS read do not establish an answer to this question."),
  },
  {
    id: "review tracker · empty", screen: "paper-view",
    override: (api) => {
      asParticipant(api);
      api.on("GET", "/records/101/tracker/", { ...TRACKER, current_holders: [] });
    },
    shows: (page) => page.getByText("No routing recorded yet."),
  },
  {
    id: "review timeline · empty", screen: "paper-view", path: "/records/101?section=review",
    override: (api) => { asParticipant(api); api.on("GET", "/records/101/tracker/", TRACKER); },
    shows: (page) => page.getByText("Nothing has happened in this review yet."),
  },
];

/** A stable name for the results and the test title. */
export const stateId = (s: UiState) =>
  [s.screen, s.variant, s.state].filter(Boolean).join(" · ");
