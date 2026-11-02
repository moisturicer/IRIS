/**
 * Publish's first question: is this paper under an embargo? (ADR-052 decision 2)
 *
 * Its own screen, before the type and the file, because the answer has to reach
 * the server before the manuscript does: nothing that runs at upload may act on
 * a paper whose answer isn't known yet.
 *
 * It starts unanswered, on purpose. "No" can send the paper's text to outside AI
 * companies once it is submitted, so it is always something a person chose and
 * never a default. Built to work; the project lead may restyle it.
 */
import { FieldError } from "@/components/ui/FieldError";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { fieldClasses } from "@/components/ui/fieldClasses";
import { cn } from "@/lib/utils";

import type { EmbargoChoice, EmbargoProblem } from "./draft";

/** Each field's element id, so the dialog can move focus to the one at fault. */
export const EMBARGO_FIELD_IDS: Record<EmbargoProblem["field"], string> = {
  embargoed: "publish-embargo-no",
  embargoed_until: "publish-embargo-until",
};

const NOTE_ID = "publish-embargo-note";
const CHOICE_ERROR_ID = "publish-embargo-error";
const DATE_HINT_ID = "publish-embargo-until-hint";
const DATE_ERROR_ID = "publish-embargo-until-error";

interface EmbargoStepProps {
  value:    EmbargoChoice;
  onChange: (value: EmbargoChoice) => void;
  problem:  EmbargoProblem | null;
  /** The earliest date to offer, as `YYYY-MM-DD`. */
  today:    string;
}

export function EmbargoStep({ value, onChange, problem, today }: EmbargoStepProps) {
  const choiceProblem = problem?.field === "embargoed" ? problem.message : null;
  const dateProblem = problem?.field === "embargoed_until" ? problem.message : null;

  return (
    <fieldset
      role="radiogroup"
      aria-required
      aria-invalid={Boolean(choiceProblem) || undefined}
      aria-describedby={[NOTE_ID, choiceProblem ? CHOICE_ERROR_ID : null].filter(Boolean).join(" ")}
    >
      <legend className="text-heading font-semibold text-stone-900">Is this paper under an embargo?</legend>
      <div id={NOTE_ID} className="mt-2 flex flex-col gap-2 text-body text-stone-700">
        <p>
          An embargo keeps this paper's text from going to outside AI companies. It doesn't hide
          the paper from people who can read it in IRIS.
        </p>
        <p>
          With no embargo, its text can be sent to those companies once you submit, and text already
          sent can't be recalled.
        </p>
      </div>

      <div className="mt-section-sm flex flex-col gap-2">
        <Choice
          id={EMBARGO_FIELD_IDS.embargoed}
          label="No"
          sentence="Nothing is holding this paper back."
          checked={value.choice === "no"}
          onSelect={() => onChange({ ...value, choice: "no" })}
        />
        <Choice
          id="publish-embargo-yes"
          label="Yes"
          sentence="A patent or an agreement is pending, or you may want to patent or protect this work. IRIS won't read a title or abstract out of the PDF for you, so you'll type those yourself."
          checked={value.choice === "yes"}
          onSelect={() => onChange({ ...value, choice: "yes" })}
        />
      </div>
      {choiceProblem && <FieldError id={CHOICE_ERROR_ID}>{choiceProblem}</FieldError>}

      {value.choice === "yes" && (
        <div className="mt-section-sm">
          <FieldLabel htmlFor={EMBARGO_FIELD_IDS.embargoed_until} label="Date to review the embargo" required />
          <input
            id={EMBARGO_FIELD_IDS.embargoed_until}
            type="date"
            min={today}
            value={value.until}
            onChange={(e) => onChange({ ...value, until: e.target.value })}
            aria-required
            aria-invalid={Boolean(dateProblem) || undefined}
            aria-describedby={[dateProblem ? DATE_ERROR_ID : null, DATE_HINT_ID].filter(Boolean).join(" ")}
            className={fieldClasses(Boolean(dateProblem))}
          />
          {dateProblem && <FieldError id={DATE_ERROR_ID}>{dateProblem}</FieldError>}
          <p id={DATE_HINT_ID} className="mt-1 text-small text-stone-600">
            This date doesn't end the embargo.
          </p>
        </div>
      )}
    </fieldset>
  );
}

function Choice({
  id,
  label,
  sentence,
  checked,
  onSelect,
}: {
  id:       string;
  label:    string;
  sentence: string;
  checked:  boolean;
  onSelect: () => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border p-card-compact transition-colors",
        "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2",
        checked ? "border-brand bg-brand-50" : "border-stone-200 bg-white hover:border-stone-400",
      )}
    >
      <input
        id={id}
        type="radio"
        name="publish-embargo"
        checked={checked}
        onChange={onSelect}
        className="mt-1 h-4 w-4 shrink-0 accent-brand focus:outline-none"
      />
      <span>
        <span className="block text-body font-semibold text-stone-900">{label}</span>
        <span className="mt-0.5 block text-small text-stone-600">{sentence}</span>
      </span>
    </label>
  );
}
