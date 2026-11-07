import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import type { SemanticSearchResult } from "@/types/ai";

import { SectionHeading } from "./headings";

// ---------------------------------------------------------------------------
// Related works — record-vector similarity (ADR-029 §5), through the same
// `visible_to` predicate as Ask IRIS. The *predicate* is shared; the retrieval
// is not — Ask IRIS ranks passages, this ranks whole records on their
// title-and-abstract vector, so it answers "broadly about the same thing?"
// and will miss two papers sharing a method described mid-document.
//
// The endpoint says why a list is empty (IR-568), and the copy below says
// only what that answer supports. In particular, "no matches" is one message
// for "nothing close" and "close, but not readable by you": IR-460 forbids
// telling a reader which, so nothing here may mention withheld papers. The one
// coverage fact stated is the paper's own, and the reader can already open it.
// ---------------------------------------------------------------------------

/** What `GET /records/<id>/similar/` says about the list it returned. */
type RelatedWorksReason = "no_matches" | "not_indexed" | "incompatible";

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: SemanticSearchResult[] }
  | { kind: RelatedWorksReason }
  | { kind: "failed" };

type SimilarAnswer = Awaited<ReturnType<typeof recordsApi.similar>>["data"];

const REASON_COPY: Record<RelatedWorksReason, string> = {
  no_matches: "No related works found for this paper.",
  not_indexed: "This paper is not indexed, so IRIS cannot compare it with others.",
  incompatible: "This paper's index is out of date, so IRIS cannot compare it with others.",
};

/**
 * Reads the answer defensively: an old or malformed one is a list when it has
 * matches and "no matches" when it does not, never a crash.
 */
function stateFrom(data: SimilarAnswer | undefined): State {
  const items = data?.results ?? [];
  if (items.length > 0) return { kind: "ready", items };
  if (data?.state === "not_indexed" || data?.state === "incompatible") return { kind: data.state };
  return { kind: "no_matches" };
}

export function RelatedWorks({ recordId }: { recordId: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    recordsApi
      .similar(recordId)
      .then(({ data }) => {
        if (alive) setState(stateFrom(data));
      })
      // A failure is not "nothing close": that would be a claim IRIS has not
      // checked. The 503 body carries `unavailable`, and a lost connection has
      // no body at all, so every rejection is the same message.
      .catch(() => {
        if (alive) setState({ kind: "failed" });
      });
    return () => {
      alive = false;
    };
  }, [recordId, attempt]);

  if (state.kind === "loading") {
    return (
      <section>
        <SectionHeading>Related works</SectionHeading>
        <div className="grid gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-28 rounded-2xl ring-1 ring-stone-200 bg-white animate-pulse motion-reduce:animate-none"
            />
          ))}
        </div>
      </section>
    );
  }

  if (state.kind === "failed") {
    return (
      <section>
        <SectionHeading>Related works</SectionHeading>
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-stone-600">Related works could not be loaded right now.</p>
          <Button type="button" variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </Button>
        </div>
      </section>
    );
  }

  if (state.kind !== "ready") {
    return (
      <section>
        <SectionHeading>Related works</SectionHeading>
        {/* Static copy, not a live update: no `status` role, which the page
            already uses for its own announcements. */}
        <p className="text-sm text-stone-500">{REASON_COPY[state.kind]}</p>
      </section>
    );
  }

  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading>Related works</SectionHeading>
        <Link to="/" className="text-sm font-semibold text-brand hover:underline">
          Explore all papers →
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {state.items.map((item) => (
          <Link
            key={item.id}
            to={`/records/${item.id}`}
            className="group bg-white ring-1 ring-stone-200 rounded-2xl p-4 hover:ring-brand/30 hover:shadow-card-md transition-all duration-200"
          >
            <p className="text-2xs font-semibold tracking-wider text-stone-500 mb-2">
              Record #{item.id}
            </p>
            <p className="font-display text-lg font-semibold text-stone-900 leading-snug line-clamp-3 group-hover:text-brand transition-colors duration-200">
              {item.title}
            </p>
            <p className="text-2xs text-stone-500 mt-2">
              {item.year ?? "—"}
              {item.classification ? ` · ${item.classification}` : ""}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}
