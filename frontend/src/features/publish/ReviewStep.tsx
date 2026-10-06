/**
 * Publish, step 3: exactly what will be submitted, then consent (spec §4.4).
 *
 * Every value entered is shown, grouped as Manuscript · Details · Hints, and
 * each group's Edit goes back to the step that owns it. Consent is given here,
 * where the submission happens, with the full terms readable in place.
 */
import type { ReactNode } from "react";

import { DpaConsentInline } from "@/components/compliance";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";

import type { ApiFailure } from "./draft";

/** The server's names for the fields the Details step edits. */
const DETAIL_FIELDS: Record<string, true> = {
  title: true, abstract: true, adviser: true, authors: true,
  year_accomplished: true, classification: true, psced: true,
};

export interface ReviewSummary {
  typeName:       string;
  fileName:       string | null;
  title:          string;
  abstract:       string;
  adviserName:    string;
  authors:        string[];
  year:           number;
  classification: string | null;
  psced:          string | null;
  hints:          string[];
}

interface ReviewStepProps {
  summary:          ReviewSummary;
  dpaAccepted:      boolean;
  onDpaChange:      (accepted: boolean) => void;
  failure:          ApiFailure | null;
  /** Submit again, offered when the server never answered. */
  onRetry:          () => void;
  /** Back to Details, offered when the server faults a Details field. */
  onFixDetails:     () => void;
  /** Labels for the server's field names, so an error reads as the form does. */
  fieldLabels:      Record<string, string>;
  onEditManuscript: () => void;
  onEditDetails:    () => void;
  onEditHints:      () => void;
}

export function ReviewStep({
  summary,
  dpaAccepted,
  onDpaChange,
  failure,
  onRetry,
  onFixDetails,
  fieldLabels,
  onEditManuscript,
  onEditDetails,
  onEditHints,
}: ReviewStepProps) {
  return (
    <div className="flex flex-col gap-section">
      <Group title="Manuscript" editLabel="Edit manuscript" onEdit={onEditManuscript}>
        <Row term="Type">{summary.typeName}</Row>
        {/* A resumed draft's file name is not kept: the server stores a random one. */}
        <Row term="File">{summary.fileName ?? "Uploaded earlier"}</Row>
      </Group>

      <Group title="Details" editLabel="Edit details" onEdit={onEditDetails}>
        <Row term="Title">{summary.title}</Row>
        <Row term="Abstract">
          <span className="whitespace-pre-line">{summary.abstract}</span>
        </Row>
        <Row term="Adviser">{summary.adviserName}</Row>
        <Row term="Authors">{summary.authors.join(", ")}</Row>
        <Row term="Year">{String(summary.year)}</Row>
      </Group>

      <Group title="Hints" editLabel="Edit hints" onEdit={onEditHints}>
        <Row term="Field of research">{summary.classification ?? "Not set"}</Row>
        <Row term="PSCED">{summary.psced ?? "Not set"}</Row>
        <Row term="Flagged for your adviser">
          {summary.hints.length > 0 ? summary.hints.join("; ") : "Nothing flagged"}
        </Row>
      </Group>

      <DpaConsentInline accepted={dpaAccepted} onAcceptedChange={onDpaChange} />

      {failure && (
        <div role="alert" className="rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-body text-brand">
          <p className="flex items-start gap-2">
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
            <span>{failure.message}</span>
          </p>
          {Object.keys(failure.fields).length > 0 && (
            <ul className="mt-2 list-disc pl-8">
              {Object.entries(failure.fields).map(([field, message]) => (
                <li key={field}>
                  {fieldLabels[field] ?? field}: {message}
                </li>
              ))}
            </ul>
          )}
          {/* Spec §4.4 jumps back to Details when a field is at fault; the
              ticket keeps step 3. Both hold: the errors are listed here and
              already set on the Details fields, one press away. */}
          {(failure.network || Object.keys(failure.fields).some((f) => f in DETAIL_FIELDS)) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {failure.network && (
                <button type="button" onClick={onRetry} className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-4")}>
                  Try again
                </button>
              )}
              {Object.keys(failure.fields).some((f) => f in DETAIL_FIELDS) && (
                <button type="button" onClick={onFixDetails} className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-4")}>
                  Fix in Details
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Group({
  title,
  editLabel,
  onEdit,
  children,
}: {
  title: string;
  editLabel: string;
  onEdit: () => void;
  children: ReactNode;
}) {
  const id = `publish-review-${title.toLowerCase()}`;
  return (
    <section aria-labelledby={id} className="rounded-xl border border-stone-200 p-card-compact">
      <div className="flex items-center justify-between gap-3">
        <h3 id={id} className="text-heading font-semibold text-stone-900">{title}</h3>
        <button
          type="button"
          onClick={onEdit}
          aria-label={editLabel}
          className={cn("rounded px-1 text-body font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}
        >
          Edit
        </button>
      </div>
      <dl className="mt-2 grid gap-x-4 gap-y-2 sm:grid-cols-[10rem_minmax(0,1fr)]">{children}</dl>
    </section>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-small text-stone-600">{term}</dt>
      <dd className="break-words text-body text-stone-900">{children}</dd>
    </>
  );
}
