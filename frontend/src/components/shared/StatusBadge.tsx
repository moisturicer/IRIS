import { cn, pipelineLabel } from "@/lib/utils";
import type { PipelineStatus } from "@/lib/constants";
import type { WorkflowState } from "@/types/records";

/**
 * A record's workflow state, as a chip (IR-259).
 *
 * The words are the API's (`workflow_state_label`); only the tone is chosen
 * here, keyed by `workflow_state`. Four tones, in the IRIS palette of white,
 * grey, black and maroon (IR-356). Colour is never the only signal: every
 * chip carries its label.
 */
const QUIET     = "bg-stone-100 text-stone-700 ring-1 ring-stone-200"; // not yet with a reviewer
const ACTIVE    = "bg-brand-50 text-brand ring-1 ring-brand-200";     // with a reviewer, moving
const ATTENTION = "bg-brand text-white";                              // stopped: someone must act
const SETTLED   = "bg-stone-900 text-white";                          // finished

const WORKFLOW_COLORS: Record<string, string> = {
  draft:                 QUIET,
  submitted:             QUIET,
  in_review:             ACTIVE,
  awaiting_document:     ACTIVE,
  awaiting_resubmission: ACTIVE,    // revision requested: recoverable, so soft; the icon marks it
  final_review:          ACTIVE,
  approved:              ACTIVE,    // proposal approved -- ongoing
  completed:             SETTLED,   // proposal research finished
  published:             SETTLED,
  rejected:              ATTENTION, // terminal rejection
  pending_delete:        ATTENTION,
};

const NEUTRAL = QUIET;

/**
 * The states that stop a record carry a shape as well as a word, so that a
 * recoverable one never reads like a terminal one at a glance: resubmission
 * is the thesis contribution (01-design-system.md section 7).
 */
const WORKFLOW_ICONS: Record<string, string> = {
  awaiting_resubmission: "fa-rotate-left", // revision requested: recoverable
  rejected:              "fa-ban",         // terminal
  pending_delete:        "fa-trash-can",
};
const LEGACY_ICONS: Record<string, string> = {
  declined:       "fa-rotate-left",
  rejected:       "fa-ban",
  pending_delete: "fa-trash-can",
};

type StatusBadgeProps =
  | { state: WorkflowState; label: string; status?: never }
  /** Evaluation screen only, until IR-268 passes it a workflow state. */
  | { status: PipelineStatus; state?: never; label?: never };

export function StatusBadge(props: StatusBadgeProps) {
  const [text, color, icon] =
    props.state !== undefined
      ? [props.label, WORKFLOW_COLORS[props.state] ?? NEUTRAL, WORKFLOW_ICONS[props.state]]
      : [pipelineLabel(props.status), LEGACY_COLORS[props.status] ?? NEUTRAL, LEGACY_ICONS[props.status]];

  return (
    <span className={cn("inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-2xs font-semibold", color)}>
      {icon && <i className={cn("fas", icon)} aria-hidden />}
      {text}
    </span>
  );
}

// IR-274: delete from here. The stored-stage colours below serve only the
// `status` form above, which the Evaluation screen uses until IR-268 moves it
// onto `workflow_state`. Nothing else may add a caller.
const LEGACY_COLORS: Record<string, string> = {
  draft:           QUIET,
  adviser_review:  ACTIVE,
  approved:        ACTIVE,
  completed:       SETTLED,
  rdco_intake:     QUIET,
  itso_review:     ACTIVE,
  ktto_review:     ACTIVE,
  parallel_review: ACTIVE,
  rdco_review:     ACTIVE,
  published:       SETTLED,
  declined:        ACTIVE,
  rejected:        ATTENTION,
  pending_delete:  ATTENTION,
};
