import { cn, pipelineLabel } from "@/lib/utils";
import type { PipelineStatus } from "@/lib/constants";
import type { WorkflowState } from "@/types/records";

/**
 * A record's workflow state, as a coloured chip (IR-259).
 *
 * The words are the API's (`workflow_state_label`); only the colour is chosen
 * here, keyed by `workflow_state`. The palette carries over from the stored
 * stages each state replaces, so a record reads in the same colour it did.
 */
const WORKFLOW_COLORS: Record<string, string> = {
  draft:                 "bg-gray-100 text-gray-600",
  submitted:             "bg-orange-100 text-orange-700",
  in_review:             "bg-blue-100 text-blue-700",
  awaiting_document:     "bg-amber-100 text-amber-700",
  awaiting_resubmission: "bg-amber-100 text-amber-700", // revision requested
  final_review:          "bg-purple-100 text-purple-700",
  approved:              "bg-teal-100 text-teal-700",    // proposal approved — ongoing
  completed:             "bg-emerald-100 text-emerald-700", // proposal research finished
  published:             "bg-green-100 text-green-700",
  rejected:              "bg-red-100 text-red-700",       // terminal rejection
  pending_delete:        "bg-rose-100 text-rose-700",
};

const NEUTRAL = "bg-gray-100 text-gray-600";

type StatusBadgeProps =
  | { state: WorkflowState; label: string; status?: never }
  /** Evaluation screen only, until IR-268 passes it a workflow state. */
  | { status: PipelineStatus; state?: never; label?: never };

export function StatusBadge(props: StatusBadgeProps) {
  const [text, color] =
    props.state !== undefined
      ? [props.label, WORKFLOW_COLORS[props.state] ?? NEUTRAL]
      : [pipelineLabel(props.status), LEGACY_COLORS[props.status] ?? NEUTRAL];

  return (
    <span className={cn("inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold", color)}>
      {text}
    </span>
  );
}

// IR-274: delete from here. The stored-stage colours below serve only the
// `status` form above, which the Evaluation screen uses until IR-268 moves it
// onto `workflow_state`. Nothing else may add a caller.
const LEGACY_COLORS: Record<string, string> = {
  draft:           "bg-gray-100 text-gray-600",
  adviser_review:  "bg-yellow-100 text-yellow-700",
  approved:        "bg-teal-100 text-teal-700",
  completed:       "bg-emerald-100 text-emerald-700",
  rdco_intake:     "bg-orange-100 text-orange-700",
  itso_review:     "bg-indigo-100 text-indigo-700",
  ktto_review:     "bg-blue-100 text-blue-700",
  parallel_review: "bg-blue-100 text-blue-700",
  rdco_review:     "bg-purple-100 text-purple-700",
  published:       "bg-green-100 text-green-700",
  declined:        "bg-amber-100 text-amber-700",
  rejected:        "bg-red-100 text-red-700",
  pending_delete:  "bg-rose-100 text-rose-700",
};
