import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";
import type { WorkflowState } from "@/types/records";

/**
 * A record's workflow state, as a chip (IR-259).
 *
 * The words are the API's (`workflow_state_label`); only the tone is chosen
 * here, keyed by `workflow_state`, from the four shared status tones (IR-356,
 * IR-358). Colour is never the only signal: every chip carries its label.
 */
const { quiet: QUIET, active: ACTIVE, attention: ATTENTION, settled: SETTLED } = TONES;

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
type StatusBadgeProps = { state: WorkflowState; label: string };

/**
 * The stored-status fallback the Evaluation screen used is gone with that
 * screen (IR-274): every caller passes the server's state and its label.
 */
export function StatusBadge({ state, label }: StatusBadgeProps) {
  const color = WORKFLOW_COLORS[state] ?? NEUTRAL;
  const icon = WORKFLOW_ICONS[state];

  return (
    <span className={cn("inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-2xs font-semibold", color)}>
      {icon && <i className={cn("fas", icon)} aria-hidden />}
      {label}
    </span>
  );
}
