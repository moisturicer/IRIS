// Which forced-state test proves each cell of docs/ui-ux/17-ui-states-matrix.md (IR-907).
//
// forced-coverage.spec.ts reads the matrix and holds this table equal to it: a
// cell the document does not mark N/A needs a proof here, and a cell it does mark
// N/A must have none. A proof is one of
//   catalogue  a state in support/states.ts, which forced-states.spec.ts runs through
//              loading / empty / error / interrupted / revoked
//   test       a test written out by hand, found in `file` by a fragment of its title
import type { MatrixState } from "./states";

export type Proof =
  | { catalogue: { screen: string; variant?: string; read?: string } }
  | { test: { file: "forced-states.spec.ts" | "forced-cells.spec.ts" | "ask-iris-stream.spec.ts"; title: string } };

export type Surface =
  | "discover" | "paper-view" | "my-library" | "ask-iris" | "my-reviews" | "office-console" | "review-panels";

/** How a row of the matrix names its surface in the document's first column. */
export const SURFACE_ROWS: { surface: Surface; matches: RegExp }[] = [
  // Order matters: the panels' row also says "Paper View", the office row also says "Review".
  { surface: "review-panels", matches: /workspace panels/ },
  { surface: "office-console", matches: /Office console/ },
  { surface: "my-reviews", matches: /My Reviews/ },
  { surface: "ask-iris", matches: /Ask IRIS/ },
  { surface: "my-library", matches: /My Library/ },
  { surface: "paper-view", matches: /Paper View/ },
  { surface: "discover", matches: /Discover/ },
];

const cat = (screen: string, rest: { variant?: string; read?: string } = {}): Proof => ({ catalogue: { screen, ...rest } });
const hand = (file: Extract<Proof, { test: unknown }>["test"]["file"], title: string): Proof => ({ test: { file, title } });

const library = (...variants: string[]) => variants.map((variant) => cat("my-library", { variant }));
const ALL_VIEWS = ["overview", "my research", "saved", "download requests"];

export const PROOFS: Record<Surface, Partial<Record<MatrixState, Proof[]>>> = {
  discover: {
    loading: [cat("discover")],
    empty: [cat("discover"), hand("forced-cells.spec.ts", "a filter that matches nothing says so")],
    error: [cat("discover"), hand("forced-cells.spec.ts", "Load more that fails keeps the list")],
    interrupted: [cat("discover"), hand("forced-cells.spec.ts", "Load more that times out")],
  },
  "paper-view": {
    loading: [cat("paper-view", { read: "/records/101/" })],
    error: [cat("paper-view", { read: "/records/101/" })],
    interrupted: [cat("paper-view", { read: "/records/101/" })],
    revoked: [
      cat("paper-view", { read: "/records/101/" }),
      hand("forced-states.spec.ts", "a Record withdrawn after it was listed lands on the same not-available screen"),
    ],
  },
  "my-library": {
    loading: library(...ALL_VIEWS),
    // Saved has no catalogue entry for empty (its read answers a list the page filters), so a test of its own.
    empty: [...library("overview", "my research", "download requests"), hand("forced-cells.spec.ts", "nothing saved says so")],
    error: library(...ALL_VIEWS),
    interrupted: library(...ALL_VIEWS),
    revoked: [hand("forced-cells.spec.ts", "a saved paper the reader can no longer read is reported, not hidden")],
  },
  "ask-iris": {
    loading: [
      cat("ask-iris-conversation"),
      hand("ask-iris-stream.spec.ts", "shows that IRIS is working while the stream is held"),
    ],
    empty: [
      hand("forced-cells.spec.ts", "a new chat opens on its opening question"),
      hand("forced-cells.spec.ts", "an answer with nothing to cite says no sources matched"),
    ],
    error: [
      cat("ask-iris-conversation"),
      hand("forced-cells.spec.ts", "a conversation list that fails to load says so in place"),
      hand("ask-iris-stream.spec.ts", "the request fails with a server error"),
    ],
    interrupted: [
      cat("ask-iris-conversation"),
      hand("forced-cells.spec.ts", "a conversation list that times out says it took too long"),
      hand("ask-iris-stream.spec.ts", "cut off after some text"),
      hand("ask-iris-stream.spec.ts", "a run that ${state} says so, and Retry starts a new run that answers"),
    ],
    revoked: [
      cat("ask-iris-conversation"),
      hand("forced-states.spec.ts", "a Conversation whose access is withdrawn after it was opened reads as not available"),
    ],
  },
  "my-reviews": {
    loading: [cat("my-reviews")],
    empty: [cat("my-reviews"), hand("forced-cells.spec.ts", "tab with nothing in it says what arrives there")],
    error: [cat("my-reviews")],
    interrupted: [cat("my-reviews")],
    revoked: [cat("my-reviews")],
  },
  "office-console": {
    loading: [cat("office-console")],
    empty: [cat("office-console")],
    error: [cat("office-console")],
    interrupted: [cat("office-console")],
    revoked: [cat("office-console")],
  },
  "review-panels": {
    loading: [cat("paper-view", { variant: "review tracker" }), cat("paper-view", { variant: "review timeline" })],
    empty: [
      hand("forced-cells.spec.ts", "a timeline with nothing in it says nothing has happened yet"),
      hand("forced-cells.spec.ts", "a tracker nobody has acted on says no routing is recorded yet"),
    ],
    error: [cat("paper-view", { variant: "review tracker" }), cat("paper-view", { variant: "review timeline" })],
    interrupted: [cat("paper-view", { variant: "review tracker" }), cat("paper-view", { variant: "review timeline" })],
  },
};
