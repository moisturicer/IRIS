/**
 * *+ Add a colleague* (IR-1340): a link under the viewer's own office in
 * Details → Reviewers, where it left the footer's menu. It opens the same
 * *Add reviewer* dialog (ADR-032 §4) and says the outcome beside itself. The
 * host draws it only when the server grants `add_reviewer`.
 */
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { useReviewActionRunner } from "./ReviewActionBar";
import { ADD_COLLEAGUE } from "./reviewActions";

export function AddColleagueLink({ record, office, onChanged }: {
  record: RecordDetail;
  /** The office's label, e.g. "ITSO", which names the link for a screen reader. */
  office: string;
  onChanged: () => void;
}) {
  const runner = useReviewActionRunner(record, onChanged);
  const [action] = ADD_COLLEAGUE;
  if (!action) return null;
  return (
    <div className="pl-8 pt-1">
      <button type="button" aria-label={`Add a colleague to ${office}`} onClick={() => runner.start(action)}
        className={cn("inline-flex items-center gap-1 rounded-control text-2xs font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
        <i className="fas fa-plus text-2xs" aria-hidden />
        Add a colleague
      </button>
      <p role="status" aria-live="polite" className={cn("text-2xs text-stone-900", !runner.outcome && "sr-only")}>
        {runner.outcome}
      </p>
      {runner.portal}
    </div>
  );
}
