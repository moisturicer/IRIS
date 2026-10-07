import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { AskIrisMark } from "@/features/ai/components/AskIrisIcons";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { PANE_HEIGHT, PANE_TOP } from "./paneLayout";
import { ReviewActionBar } from "./ReviewActionBar";
import { ReviewTimeline } from "./ReviewTimeline";

interface ReviewSectionProps {
  record: RecordDetail;
  /** What the capabilities adapter grants this viewer. */
  can: ReadonlySet<Capability>;
  /** The paper, as the Paper tab's reader; null when there is none to read. */
  reader: ReactNode;
  /** Bumped when the review changed, so the timeline re-reads the tracker. */
  timelineVersion: number;
  /** Something changed: re-read the record and the timeline. */
  onChanged: () => void;
  /** Go to the Paper tab with Ask IRIS open. Absent when there is no paper. */
  onAskAboutPaper?: () => void;
}

/**
 * The Review section (IR-412; spec §4.6, §4.7): the paper on the left and,
 * on the right, the review pane -- the timeline, with the action bar under
 * it. Like a pull request: the work, what has happened to it, and what you
 * may do next.
 *
 * At `lg` the pane is a sticky column the reader's height, beside the reader
 * and never over it, sharing the Paper tab's pane geometry (IR-352). Below
 * `lg` the paper stacks above the pane, and the action bar sticks to the
 * bottom of the screen the whole way down, paper included.
 *
 * **No Ask IRIS here** (spec §4.6, decided 2026-09-26): *Ask about this
 * paper* goes to the Paper tab, where the conversation is waiting.
 *
 * Until IR-260 cuts over, a decision is recorded on the current review form,
 * linked from the bar; its replacements arrive as entries in `REVIEW_ACTIONS`.
 */
export function ReviewSection({
  record,
  can,
  reader,
  timelineVersion,
  onChanged,
  onAskAboutPaper,
}: ReviewSectionProps) {
  const decisionForm = can.has("decide") ? (
    <Link
      to={`/review/${record.id}/evaluate`}
      className={cn(
        "inline-flex items-center min-h-11 px-2 text-small font-semibold text-brand hover:underline",
        FOCUS_RING,
      )}
    >
      Record a decision (current form)
    </Link>
  ) : null;

  return (
    <div className={cn("lg:flex lg:gap-6 lg:items-start", !reader && "max-w-3xl mx-auto")}>
      {reader && <div className="min-w-0 lg:flex-1">{reader}</div>}

      {/* The pane and its bar. One column at `lg`; below it this box is
          `contents`, so the bar's sticky range is the whole section, paper
          and all, rather than the pane alone. */}
      <div
        className={cn(
          "contents lg:flex lg:flex-col lg:shrink-0 lg:overflow-hidden",
          "lg:rounded-2xl lg:bg-white lg:ring-1 lg:ring-stone-200",
          reader ? cn("lg:sticky lg:w-[26rem] xl:w-[30rem]", PANE_TOP, PANE_HEIGHT) : "lg:w-full",
        )}
      >
        <div
          className={cn(
            "mt-6 rounded-2xl bg-white ring-1 ring-stone-200 p-card space-y-4",
            "lg:mt-0 lg:rounded-none lg:ring-0 lg:flex-1 lg:min-h-0 lg:overflow-y-auto",
          )}
        >
          {onAskAboutPaper && (
            <button
              type="button"
              onClick={onAskAboutPaper}
              className={cn(
                "inline-flex items-center gap-2 min-h-11 text-small font-semibold text-brand hover:underline",
                FOCUS_RING,
              )}
            >
              <AskIrisMark className="w-4 h-4" />
              Ask about this paper
            </button>
          )}
          <ReviewTimeline key={timelineVersion} recordId={record.id} />
        </div>

        <ReviewActionBar
          record={record}
          can={can}
          secondary={decisionForm}
          onChanged={onChanged}
          className={cn(
            "sticky bottom-0 z-20 mt-4 rounded-t-2xl bg-white ring-1 ring-stone-200 shadow-card-md px-3 py-2",
            "lg:static lg:z-auto lg:mt-0 lg:rounded-none lg:ring-0 lg:shadow-none",
            "lg:border-t lg:border-stone-200 lg:px-5 lg:py-3",
          )}
        />
      </div>
    </div>
  );
}
