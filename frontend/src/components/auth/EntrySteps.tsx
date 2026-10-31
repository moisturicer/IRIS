import type { MouseEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

export type EntryStepState = "completed" | "current" | "not-started";

export interface EntryStep {
  name: string;
  /** What a phone shows when the whole name does not fit; the name stays whole for a screen reader. */
  shortName?: string;
  state: EntryStepState;
}

interface EntryStepsProps {
  steps: EntryStep[];
  /**
   * Moves to a completed step. Without it the completed tabs are plain labels,
   * as on the confirmation, where nothing can be reopened (IR-704 story 48).
   */
  onSelect?: (index: number) => void;
}

/** Said after each tab's own name, so its state is heard and not only seen (IR-704 story 15). */
const STATE_WORDS: Record<EntryStepState, string> = {
  "completed":   "completed",
  "current":     "current step",
  "not-started": "not started",
};

const TAB =
  "-mb-px flex min-h-11 items-center gap-2 rounded-t-lg border border-b-0 px-3 py-2.5 text-small font-semibold sm:px-4";

/**
 * Register's folder tabs (IR-707): a stepper in a `nav` named "Registration
 * steps". The state is told by shape and outline as well as colour (story 14):
 *
 * - completed: a check and a solid outline, and a link back to that step;
 * - current: raised, joined to the sheet, `aria-current="step"`;
 * - not started: a dashed outline, `aria-disabled`, and out of the Tab order.
 *
 * Every tab is a link in the accessibility tree, so each is found and heard
 * the same way; only a completed one has an `href` and can be reached. The
 * link points at the page it is on and moves between steps in memory, so the
 * URL never changes (IR-704).
 */
export function EntrySteps({ steps, onSelect }: EntryStepsProps) {
  const { pathname } = useLocation();

  return (
    <nav aria-label="Registration steps" className="min-w-0">
      <ol className="flex gap-1">
        {steps.map((step, index) => {
          const label = (
            <>
              <StepMark state={step.state} number={index + 1} />
              <StepName step={step} />
              <span className="sr-only">, {STATE_WORDS[step.state]}</span>
            </>
          );

          if (step.state === "completed" && onSelect) {
            const select = (e: MouseEvent<HTMLAnchorElement>) => {
              e.preventDefault();
              onSelect(index);
            };
            return (
              <li key={step.name} className="flex">
                <Link
                  to={pathname}
                  onClick={select}
                  className={cn(TAB, "border-stone-300 bg-stone-100 text-stone-800 hover:bg-white", FOCUS_RING)}
                >
                  {label}
                </Link>
              </li>
            );
          }

          if (step.state === "completed") {
            return (
              <li key={step.name} className="flex">
                <span className={cn(TAB, "border-stone-300 bg-stone-100 text-stone-800")}>{label}</span>
              </li>
            );
          }

          return (
            <li key={step.name} className="flex">
              <a
                role="link"
                aria-current={step.state === "current" ? "step" : undefined}
                aria-disabled={step.state === "not-started" ? true : undefined}
                className={cn(
                  TAB,
                  step.state === "current"
                    ? "relative z-10 border-t-2 border-stone-200 border-t-brand bg-white text-brand"
                    : "border-dashed border-stone-400 text-stone-600",
                )}
              >
                {label}
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function StepName({ step }: { step: EntryStep }) {
  if (!step.shortName || !step.name.startsWith(step.shortName)) return <span>{step.name}</span>;
  // The rest of the name is visually hidden on a phone, never removed: the
  // accessible name stays "Security & agreement" at every width.
  return (
    <span>
      {/* The space sits outside the hidden part: a name computed from a
          child's text trims the child's own leading space. */}
      {step.shortName}{" "}
      <span className="sr-only sm:not-sr-only">{step.name.slice(step.shortName.length).trimStart()}</span>
    </span>
  );
}

function StepMark({ state, number }: { state: EntryStepState; number: number }) {
  if (state === "completed") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-stone-900 text-label text-white" aria-hidden>
        <i className="fas fa-check" />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-full text-label",
        state === "current" ? "bg-brand text-white" : "border border-dashed border-stone-500 text-stone-700",
      )}
      aria-hidden
    >
      {number}
    </span>
  );
}
