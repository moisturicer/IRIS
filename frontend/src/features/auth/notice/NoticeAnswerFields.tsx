import { useId } from "react";
import type { DataNotice } from "@/types/notice";
import { formatDate } from "@/lib/utils";

/**
 * The server's data notice and the two answers it asks for (ADR-054 decisions
 * 1-3, 5-7; IR-790). One component, so registration and the signed-in notice
 * screen show the same notice and the same questions.
 *
 * The text is shown as the server sent it, as plain text with its line breaks:
 * a notice is pasted by RDCO or the System Admin (ADR-051 decision 17), so it
 * is never parsed as markup.
 */

export interface NoticeAnswers {
  agree: boolean;
  /** null until the person picks one: neither answer is preselected. */
  ai: boolean | null;
}

export const NO_ANSWERS: NoticeAnswers = { agree: false, ai: null };

export interface NoticeAnswerErrors {
  agree?: string;
  ai?: string;
}

export const AGREE_REQUIRED = "Agree to the data-privacy agreement to continue.";
export const AI_REQUIRED = "Choose Yes or No.";

/** What a form shows when one of the two answers is missing. */
export function missingAnswers(value: NoticeAnswers): NoticeAnswerErrors {
  return {
    ...(value.agree ? {} : { agree: AGREE_REQUIRED }),
    ...(value.ai === null ? { ai: AI_REQUIRED } : {}),
  };
}

export function NoticeText({ notice, headingLevel = 2 }: { notice: DataNotice; headingLevel?: 2 | 3 }) {
  const Heading = `h${headingLevel}` as "h2";
  const Section = `h${headingLevel + 1}` as "h3";
  return (
    <div className="space-y-4 text-small text-stone-700">
      <div>
        <Heading className="text-body font-bold text-stone-900">{notice.title}</Heading>
        {notice.subtitle && <p className="mt-1 whitespace-pre-line">{notice.subtitle}</p>}
        <p className="mt-1 text-label text-stone-500">
          Version {notice.version} · published {formatDate(notice.published_at)}
        </p>
      </div>
      {notice.sections.map((section, i) => (
        <section key={`${i}-${section.title}`}>
          <Section className="font-semibold text-stone-900">{section.title}</Section>
          {section.body && <p className="mt-1 whitespace-pre-line leading-relaxed">{section.body}</p>}
          {section.list && section.list.length > 0 && (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {section.list.map((item, j) => (
                <li key={j} className="whitespace-pre-line leading-relaxed">{item}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

export function NoticeAnswerFields({
  value,
  onChange,
  errors = {},
}: {
  value: NoticeAnswers;
  onChange: (next: NoticeAnswers) => void;
  errors?: NoticeAnswerErrors;
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
            onSelect={() => onChange({ ...value, ai: true })}
            label="Yes"
            helpId={yesHelpId}
            help="IRIS may send your papers' text to AI companies to read and index them, write their AI Overview and answer questions about them. The embargo and the IP mark still apply."
          />
          <Choice
            name={aiLegendId}
            checked={value.ai === false}
            onSelect={() => onChange({ ...value, ai: false })}
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
    </div>
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
