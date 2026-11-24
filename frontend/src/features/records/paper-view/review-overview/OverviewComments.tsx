import { useEffect, useId, useRef } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import type { ReviewTarget } from "../reviewTarget";
import { SEVERITY_WORDS, countLabel, isOpen, threadStatus, type Thread } from "../threads/threadModel";
import { useReviewThreads } from "../threads/useReviewThreads";

/** What still asks something of someone first: an unanswered Must fix, then other Must fix, then the rest. */
const rank = ({ root }: Thread) => (root.severity === "must_fix" ? (root.answer ? 1 : 0) : 2);

/** Where the comment is about: its page and Version, or its document. */
function place({ root }: Thread): string | null {
  if (root.document) return root.document.slot;
  if (!root.anchor) return null;
  return `Page ${root.anchor.page}, v${root.anchor.version}`;
}

/**
 * Every open review comment, whole, on the Overview. Each row is a link to
 * that thread in Review, where it is answered, replied to and resolved:
 * nothing is acted on here. Draws nothing while none is open, or to a viewer
 * who may not read the review (`readiness` is null then).
 */
export function OverviewComments({ record, version, onOpenReview }: {
  record: RecordDetail;
  /** Bumped when something about the review changed. */
  version: number;
  onOpenReview: (target: ReviewTarget) => void;
}) {
  const headingId = useId();
  const threads = useReviewThreads(record.id, record.readiness != null);
  const { reload } = threads;
  const seen = useRef(version);
  useEffect(() => {
    if (seen.current === version) return;
    seen.current = version;
    reload();
  }, [version, reload]);

  const open = threads.sent.filter(isOpen).sort((a, b) => rank(a) - rank(b));
  if (threads.failed && !threads.loaded) {
    return (
      <p className="text-small text-stone-700">
        Could not load the review comments.{" "}
        <button type="button" onClick={reload} className={cn("min-h-11 rounded-control font-semibold text-brand hover:underline", FOCUS_RING)}>
          Try again
        </button>
      </p>
    );
  }
  if (open.length === 0) return null;

  return (
    <section aria-labelledby={headingId} className="pt-3">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 id={headingId} className="font-display text-section font-semibold text-stone-900">Comments</h3>
        <p className="text-small text-stone-600">{countLabel(threads.sent)}</p>
      </div>
      <ul aria-labelledby={headingId} className="divide-y divide-stone-200 overflow-hidden rounded-card border border-stone-300 bg-surface">
        {open.map((thread) => {
          const { root } = thread;
          const where = place(thread);
          const status = threadStatus(root);
          const from = root.party_label ?? root.author_name ?? "A reviewer";
          return (
            <li key={root.id} className={cn("group relative flex items-start gap-3 px-5 py-3.5 hover:bg-brand/[0.07]", COLOUR_TRANSITION)}>
              <span aria-hidden className="mt-0.5 inline-grid size-5 shrink-0 place-items-center rounded-full bg-pen text-2xs font-semibold text-white">{thread.pin}</span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-small text-stone-600">
                  <span className="font-semibold text-stone-900">{from}</span>
                  {root.severity && (
                    <span className={cn("font-semibold", root.severity === "must_fix" ? "text-brand" : "text-stone-700")}>
                      {root.severity === "must_fix" && <i className="fas fa-triangle-exclamation mr-1 text-2xs" aria-hidden />}
                      {SEVERITY_WORDS[root.severity]}
                    </span>
                  )}
                  {where && <span>{where}</span>}
                  {status && <span>{status}</span>}
                </p>
                <p className="text-justified mt-0.5 whitespace-pre-line break-words text-body text-stone-800">{root.body}</p>
              </div>
              {/* The whole row opens the thread; the button is its name and its focus. */}
              <button
                type="button"
                onClick={() => onOpenReview({ tab: "threads", party: null, thread: root.id })}
                aria-label={`Open ${from}'s comment ${thread.pin} in Review`}
                className={cn("mt-0.5 shrink-0 rounded-control text-small text-stone-500 group-hover:text-brand after:absolute after:inset-0 after:content-['']", FOCUS_RING)}
              >
                <i className="fas fa-arrow-right text-2xs" aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
