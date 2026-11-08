import { useId } from "react";

/**
 * The server's data notice and the two answers it asks for (ADR-054 decisions
 * 1-3, 5-7; IR-790). One component, so registration and the signed-in notice
 * screen show the same notice and the same questions.
 *
 * The text is shown as the server sent it, as plain text with its line breaks:
 * a notice is pasted by RDCO or the System Admin (ADR-051 decision 17), so it
 * is never parsed as markup.
 */

/** Which papers a No becoming a Yes covers (ADR-054 decision 13, IR-791). */
export type PapersChoice = "all" | "from_now";

export interface NoticeAnswers {
  agree: boolean;
  /** null until the person picks one: neither answer is preselected. */
  ai: boolean | null;
  /** Asked only when a No becomes a Yes; null until chosen, never assumed. */
  papers: PapersChoice | null;
}

export const NO_ANSWERS: NoticeAnswers = { agree: false, ai: null, papers: null };

export interface NoticeAnswerErrors {
  agree?: string;
  ai?: string;
  papers?: string;
}

export const AGREE_REQUIRED = "Agree to the data-privacy agreement to continue.";
export const AI_REQUIRED = "Choose Yes or No.";
export const PAPERS_REQUIRED = "Choose which papers your Yes covers.";

/** A No becoming a Yes, the one change that asks which papers (ADR-054 decision 13). */
export function asksWhichPapers(previousAi: boolean | null | undefined, value: NoticeAnswers): boolean {
  return previousAi === false && value.ai === true;
}

/** What a form shows when an answer is missing. */
export function missingAnswers(value: NoticeAnswers, previousAi?: boolean | null): NoticeAnswerErrors {
  return {
    ...(value.agree ? {} : { agree: AGREE_REQUIRED }),
    ...(value.ai === null ? { ai: AI_REQUIRED } : {}),
    ...(asksWhichPapers(previousAi, value) && value.papers === null ? { papers: PAPERS_REQUIRED } : {}),
  };
}


export function NoticeAnswerFields({
  value,
  onChange,
  errors = {},
  previousAi,
}: {
  value: NoticeAnswers;
  onChange: (next: NoticeAnswers) => void;
  errors?: NoticeAnswerErrors;
  /** The person's last answer on AI; a No there makes a Yes here ask which papers. */
  previousAi?: boolean | null;
}) {
  const agreeId = useId();
  const agreeErrorId = useId();
  const aiLegendId = useId();
  const aiErrorId = useId();
  const yesHelpId = useId();
  const noHelpId = useId();
  const recallId = useId();

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-start gap-2.5">
          <input
            type="checkbox"
            id={agreeId}
            checked={value.agree}
            onChange={(e) => onChange({ ...value, agree: e.target.checked })}
            aria-invalid={errors.agree ? true : undefined}
            aria-describedby={errors.agree ? agreeErrorId : undefined}
            className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-brand"
          />
          <label htmlFor={agreeId} className="flex min-h-11 cursor-pointer items-center text-small text-stone-700">
            I have read the data notice and agree to the data-privacy agreement.
          </label>
        </div>
        {errors.agree && <FieldMessage id={agreeErrorId}>{errors.agree}</FieldMessage>}
      </div>

      <fieldset
        aria-describedby={[recallId, errors.ai ? aiErrorId : ""].filter(Boolean).join(" ")}
        aria-invalid={errors.ai ? true : undefined}
      >
        <legend id={aiLegendId} className="text-small font-semibold text-stone-900">
          May AI use your papers?
        </legend>
        <div className="mt-2 space-y-2">
          <Choice
            name={aiLegendId}
            checked={value.ai === true}
            onSelect={() => onChange({ ...value, ai: true, papers: null })}
            label="Yes"
            helpId={yesHelpId}
            help="IRIS may send your papers' text to AI companies to read and index them, write their AI Overview and answer questions about them. The embargo and the IP mark still apply."
          />
          <Choice
            name={aiLegendId}
            checked={value.ai === false}
            onSelect={() => onChange({ ...value, ai: false, papers: null })}
            label="No"
            helpId={noHelpId}
            help="Your account works normally, and AI doesn't touch your papers: you fill in their details yourself. Your own Ask IRIS questions still go to AI companies."
          />
        </div>
        <p id={recallId} className="mt-2 text-label text-stone-500">
          Text already sent to an AI company can&apos;t be recalled. You can change this answer later in Settings.
        </p>
        {errors.ai && <FieldMessage id={aiErrorId}>{errors.ai}</FieldMessage>}
      </fieldset>

      {asksWhichPapers(previousAi, value) && (
        <WhichPapers
          value={value.papers}
          onChange={(papers) => onChange({ ...value, papers })}
          error={errors.papers}
        />
      )}
    </div>
  );
}

/**
 * The two choices a No becoming a Yes asks, neither preselected (ADR-054
 * decision 13). The notice screen and Settings both ask it, in these words.
 */
export function WhichPapers({
  value, onChange, error,
}: { value: PapersChoice | null; onChange: (next: PapersChoice) => void; error?: string }) {
  const name = useId();
  const errorId = useId();
  const allHelpId = useId();
  const fromNowHelpId = useId();
  return (
    <fieldset aria-describedby={error ? errorId : undefined} aria-invalid={error ? true : undefined}>
      <legend className="text-small font-semibold text-stone-900">
        You said No before. Which papers does your Yes cover?
      </legend>
      <div className="mt-2 space-y-2">
        <Choice
          name={name}
          checked={value === "all"}
          onSelect={() => onChange("all")}
          label="All my papers"
          helpId={allHelpId}
          help="Also every paper you're Contact person of that holds a No. Their text will be sent to AI companies, subject to the embargo and the IP mark, and can't be recalled."
        />
        <Choice
          name={name}
          checked={value === "from_now"}
          onSelect={() => onChange("from_now")}
          label="Only papers from now on"
          helpId={fromNowHelpId}
          help="Papers you already have keep their No."
        />
      </div>
      {error && <FieldMessage id={errorId}>{error}</FieldMessage>}
    </fieldset>
  );
}

function Choice({
  name, checked, onSelect, label, help, helpId,
}: {
  name: string; checked: boolean; onSelect: () => void; label: string; help: string; helpId: string;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-stone-200 px-3 py-2">
      <input
        type="radio"
        id={id}
        name={name}
        checked={checked}
        onChange={onSelect}
        aria-describedby={helpId}
        className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-brand"
      />
      <div>
        <label htmlFor={id} className="flex min-h-6 cursor-pointer items-center text-small font-semibold text-stone-900">
          {label}
        </label>
        <p id={helpId} className="text-label text-stone-600">{help}</p>
      </div>
    </div>
  );
}

function FieldMessage({ id, children }: { id: string; children: string }) {
  return (
    <p id={id} className="mt-1.5 flex items-start gap-1.5 text-small text-brand">
      <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
      {children}
    </p>
  );
}
