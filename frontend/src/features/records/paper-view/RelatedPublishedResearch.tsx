import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { recordsApi } from "@/api/records";
import type { SemanticSearchResult } from "@/types/ai";

import { SectionHeading } from "./headings";

// ---------------------------------------------------------------------------
// Related published research — the Novelty check (IR-312, ADR-029 §2 and its
// 2026-09-26 amendment, item 9). Shown on the owner's own Proposal only, and
// recomputed on every view, so a figure is never months stale. It reads only
// published work, which is why it needs no consent.
//
// The similarity is shown as a percentage so a proposer can tell a
// near-duplicate from a loose thematic overlap and judge for themselves.
// ---------------------------------------------------------------------------

type State =
  | { kind: "loading" }
  | { kind: "unchecked" }
  | { kind: "ready"; items: SemanticSearchResult[]; threshold: number }
  | { kind: "failed" };

export function RelatedPublishedResearch({ recordId }: { recordId: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    recordsApi
      .relatedResearch(recordId)
      .then(({ data }) => {
        if (!alive) return;
        setState(
          data.checked
            ? { kind: "ready", items: data.results ?? [], threshold: data.threshold }
            : { kind: "unchecked" },
        );
      })
      .catch(() => {
        if (alive) setState({ kind: "failed" });
      });
    return () => {
      alive = false;
    };
  }, [recordId]);

  return (
    <section>
      <SectionHeading>Related published research</SectionHeading>
      {state.kind === "loading" && (
        <div
          className="h-16 rounded-2xl ring-1 ring-stone-200 bg-white animate-pulse motion-reduce:animate-none"
          aria-hidden
        />
      )}
      {/* A failure is not "nothing close": that would be a claim IRIS has
          not checked. */}
      {state.kind === "failed" && (
        <p className="text-sm text-stone-500">
          Related research could not be checked right now.
        </p>
      )}
      {/* Not indexed yet -- every Proposal, until IR-250. Nothing was
          compared, so nothing can be said about what is close. */}
      {state.kind === "unchecked" && (
        <p className="text-sm text-stone-500">
          This proposal has not been compared yet. It is compared with published research
          once it has been indexed.
        </p>
      )}
      {state.kind === "ready" && state.items.length === 0 && (
        <p className="text-sm text-stone-500">
          No published research here is {Math.round(state.threshold * 100)}% or more similar
          to this proposal. This compares indexed records only, so it is not a guarantee the
          idea is new.
        </p>
      )}
      {state.kind === "ready" && state.items.length > 0 && (
        <>
          <p className="text-sm text-stone-600 mb-3">
            Published work at CIT-U that is close to this proposal. Read it to judge whether
            your idea has already been done here.
          </p>
          <ul className="space-y-2">
            {state.items.map((item) => (
              <li key={item.id}>
                <Link
                  to={`/records/${item.id}`}
                  className="group flex items-baseline justify-between gap-3 bg-white ring-1 ring-stone-200 rounded-2xl p-4 hover:ring-brand/30 transition-colors duration-200"
                >
                  <span className="min-w-0">
                    <span className="block font-semibold text-stone-900 leading-snug group-hover:text-brand">
                      {item.title}
                    </span>
                    <span className="block text-2xs text-stone-500 mt-1">
                      {item.year ?? "—"}
                      {item.classification ? ` · ${item.classification}` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs font-semibold text-stone-700">
                    {Math.round(item.score * 100)}% similar
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
