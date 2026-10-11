import { useId, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { errorDetail } from "@/features/document-requests/errorDetail";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { REVIEW_ACTIONS, type ReviewAction, type TerminalReviewAction } from "./reviewActions";

interface ReviewActionBarProps {
  record: RecordDetail;
  /** What the capabilities adapter grants this viewer on this record. */
  can: ReadonlySet<Capability>;
  /** The actions on offer; `REVIEW_ACTIONS` unless a test hands it others. */
  actions?: readonly ReviewAction[];
  /** Something changed: the page re-reads the record and the timeline. */
  onChanged: () => void;
  /** The bar's own box, where the host places it; drawn only when there is a bar. */
  className?: string;
}

/** The controls the arrow keys move between: enabled buttons and links. */
const CONTROLS = "button:not(:disabled), a[href]";

/**
 * The Review section's action bar (IR-412; spec §4.7): a `toolbar` landmark
 * whose buttons come from the capabilities adapter only.
 *
 * One button per action in `actions` whose capability is granted -- an
 * action the viewer was not granted is absent, never shown disabled. A granted
 * action that is blocked is disabled, with its reason beside it and as its
 * description. Actions that end the review come last and ask first. The bar
 * knows no action by name, so an ADR-032 action (IR-261, 269–273) arrives as
 * an entry in `REVIEW_ACTIONS` and this file does not change.
 *
 * The bar renders nothing at all when it would hold nothing.
 */
export function ReviewActionBar({
  record,
  can,
  actions = REVIEW_ACTIONS,
  onChanged,
  className,
}: ReviewActionBarProps) {
  const ids = useId();
  const [openDialog, setOpenDialog] = useState<ReviewAction | null>(null);
  const [confirming, setConfirming] = useState<TerminalReviewAction | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState("");

  const granted = actions.filter((a) => can.has(a.capability));
  // Terminal last (spec §4.7); `filter` keeps each group's own order.
  const ordered = [
    ...granted.filter((a) => a.kind !== "terminal"),
    ...granted.filter((a) => a.kind === "terminal"),
  ];
  if (ordered.length === 0) return null;

  // Two actions may share a capability and a reason (*Clear* and *Record
  // finding*, IR-269). Adjacent actions blocked for the same reason state it
  // once, after the last of them, and each names that one sentence.
  const blockedOf = ordered.map((a) => a.blockedReason?.(record) ?? null);
  const reasonAt = (i: number) => {
    let last = i;
    while (last + 1 < ordered.length && blockedOf[last + 1] === blockedOf[i]) last += 1;
    return last;
  };

  const done = (message: string) => {
    setOpenDialog(null);
    setConfirming(null);
    setOutcome(message);
    onChanged();
  };

  const confirm = async () => {
    if (!confirming) return;
    setRunning(true);
    setRunError(null);
    try {
      done(await confirming.run(record));
    } catch (err) {
      setRunError(errorDetail(err, "Something went wrong. Please try again."));
    } finally {
      setRunning(false);
    }
  };

  // A toolbar moves between its controls with the arrow keys (APG toolbar
  // pattern). Tab still reaches each one too: the bar is short.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    const controls = Array.from(e.currentTarget.querySelectorAll<HTMLElement>(CONTROLS));
    const at = controls.indexOf(document.activeElement as HTMLElement);
    if (at === -1) return;
    e.preventDefault();
    controls[(at + step + controls.length) % controls.length].focus();
  };

  const Dialog = openDialog?.kind === "dialog" ? openDialog.Dialog : null;

  return (
    <>
      <div className={className}>
        <div
          role="toolbar"
          aria-label="Review actions"
          onKeyDown={onKeyDown}
          className="flex flex-wrap items-center gap-2"
        >
          {ordered.map((action, i) => {
            const blocked = blockedOf[i];
            const reasonId = `${ids}-blocked-${reasonAt(i)}`;
            return (
              <span key={action.label} className="contents">
                <button
                  type="button"
                  disabled={blocked != null}
                  aria-describedby={blocked ? reasonId : undefined}
                  onClick={() => {
                    setOutcome("");
                    setRunError(null);
                    if (action.kind === "terminal") setConfirming(action);
                    else setOpenDialog(action);
                  }}
                  // The first action is the filled one: the bar's primary, as
                  // the header has its own (01-design-system §0).
                  className={cn(i === 0 ? PILL_PRIMARY : PILL_SECONDARY, FOCUS_RING)}
                >
                  <i className={cn("fas text-2xs", action.icon)} aria-hidden />
                  {action.label}
                </button>
                {blocked && reasonAt(i) === i && (
                  <span id={reasonId} className="basis-full text-2xs text-stone-600">
                    {blocked}
                  </span>
                )}
              </span>
            );
          })}
        </div>

        <p
          role="status"
          aria-live="polite"
          className={cn("mt-2 text-small text-stone-900", !outcome && "sr-only")}
        >
          {outcome}
        </p>
      </div>

      {/* Into <body>: the host keeps this bar sticky below `lg`, and a
          sticky box with a z-index is its own stacking context, which would
          put a dialog drawn inside it under the page's section switch. */}
      {createPortal(
        <>
          {Dialog && openDialog && (
            <Dialog record={record} onClose={() => setOpenDialog(null)} onDone={done} />
          )}

          <ConfirmDialog
            open={confirming != null}
            title={confirming?.confirm.title ?? ""}
            message={confirming?.confirm.consequence ?? ""}
            confirmLabel={confirming?.confirm.confirmLabel}
            danger={confirming?.confirm.danger}
            confirming={running}
            error={runError}
            onConfirm={confirm}
            onCancel={() => {
              setConfirming(null);
              setRunError(null);
            }}
          />
        </>,
        document.body,
      )}
    </>
  );
}
