/**
 * A record's metadata fields (IR-408; spec §4.4 step 2, §4.12).
 *
 * The one place a record's title, abstract, adviser, authors and hints are
 * edited. Publish's Details step renders it now; Paper View's *Edit details*
 * dialog will render the same component (F5), so the two cannot drift.
 *
 * It renders fields only, inside the caller's `react-hook-form` provider: the
 * caller owns saving, and so decides what "Continue" or "Save" means.
 *
 * Less-common fields sit behind **More details**, closed by default, so the
 * step stays short. Validation errors are linked to their fields with
 * `aria-describedby` and carry a glyph, not only a colour.
 */
import { useState, type ReactNode } from "react";
import { Controller, useFormContext, type FieldErrors } from "react-hook-form";

import { FieldError } from "@/components/ui/FieldError";
import { CHECKBOX, LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";
import type { Classification, PSCEDClassification } from "@/types/records";

import { AdviserCombobox } from "./AdviserCombobox";
import { HINTS, type MetadataValues } from "./metadataSchema";
import { personName } from "./personName";

/** Each field's element id, so a caller can move focus to the first invalid one. */
export const METADATA_FIELD_IDS: Record<keyof MetadataValues, string> = {
  title: "metadata-title",
  abstract: "metadata-abstract",
  adviser: "metadata-adviser",
  authors: "metadata-author-input",
  year: "metadata-year",
  classification: "metadata-classification",
  psced: "metadata-psced",
  is_ip: "metadata-is-ip",
  requires_ethics_review: "metadata-ethics",
  for_commercialization: "metadata-commercialization",
};

/** The order fields appear in, which is the order focus should try them. */
export const METADATA_FIELD_ORDER: Array<keyof MetadataValues> = [
  "title", "abstract", "adviser", "authors", "year", "classification", "psced",
];

/** Fields that live inside More details, which must be open to be focused. */
export const MORE_DETAILS_FIELDS: Array<keyof MetadataValues> = [
  "classification", "psced", "is_ip", "requires_ethics_review", "for_commercialization",
];

/** Server field → form field, so a refusal's field errors land in place. */
export const FORM_FIELD: Record<string, keyof MetadataValues> = {
  title: "title",
  abstract: "abstract",
  adviser: "adviser",
  authors: "authors",
  year_accomplished: "year",
  classification: "classification",
  psced: "psced",
};

/**
 * Move focus to the first invalid field. A field inside More details is
 * focused after `openMore` has opened it, on the next frame.
 */
export function focusFirstInvalid(errors: FieldErrors<MetadataValues>, openMore: () => void) {
  const field = METADATA_FIELD_ORDER.find((name) => errors[name]);
  if (!field) return;
  if (MORE_DETAILS_FIELDS.includes(field)) openMore();
  requestAnimationFrame(() => document.getElementById(METADATA_FIELD_IDS[field])?.focus());
}

interface MetadataFormProps {
  advisers:        User[];
  classifications: Classification[];
  psceds:          PSCEDClassification[];
  /** Who is signed in, so they can be shown but not chosen as adviser. */
  selfId:          number | null;
  loadError?:      boolean;
  /** More details is controlled, so a summary's "Edit hints" can open it. */
  moreOpen:        boolean;
  onMoreOpenChange: (open: boolean) => void;
  /**
   * The record has been submitted, so its Adviser and hints are fixed
   * (IR-507): they are shown, not edited, and the caller does not send them.
   */
  submitted?:      boolean;
}

const MAX_ABSTRACT = 5000;

export function MetadataForm({
  advisers,
  classifications,
  psceds,
  selfId,
  loadError = false,
  moreOpen,
  onMoreOpenChange,
  submitted = false,
}: MetadataFormProps) {
  const {
    register,
    control,
    watch,
    setValue,
    formState: { errors },
  } = useFormContext<MetadataValues>();

  const abstract = watch("abstract") ?? "";
  const authors = watch("authors") ?? [];
  const adviserId = watch("adviser");
  const adviser = advisers.find((a) => a.id === adviserId);
  const flagged = HINTS.filter(({ field }) => watch(field));
  const [authorInput, setAuthorInput] = useState("");

  const ids = METADATA_FIELD_IDS;
  const errorId = (field: keyof MetadataValues) => `${ids[field]}-error`;
  const describedBy = (field: keyof MetadataValues, hint?: string) =>
    [errors[field] ? errorId(field) : null, hint].filter(Boolean).join(" ") || undefined;

  function addAuthor() {
    const name = authorInput.trim();
    if (name && !authors.includes(name)) {
      setValue("authors", [...authors, name], { shouldValidate: true, shouldDirty: true });
    }
    setAuthorInput("");
  }

  function removeAuthor(name: string) {
    setValue("authors", authors.filter((a) => a !== name), { shouldValidate: true, shouldDirty: true });
  }

  return (
    <div className="flex flex-col gap-section-sm">
      {loadError && (
        <p className={LOAD_ERROR} role="alert">
          <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
          We couldn't load the adviser and classification lists. Close this and try again.
        </p>
      )}

      <Field label="Title" htmlFor={ids.title} required error={errors.title?.message} errorId={errorId("title")}>
        <input
          id={ids.title}
          {...register("title")}
          aria-invalid={Boolean(errors.title) || undefined}
          aria-describedby={describedBy("title")}
          className={fieldClasses(Boolean(errors.title))}
        />
      </Field>

      <div>
        <div className="flex items-baseline justify-between gap-3">
          <label htmlFor={ids.abstract} className={LABEL}>
            Abstract <RequiredMark />
          </label>
          <span id={`${ids.abstract}-count`} className="text-small text-stone-600 tabular-nums">
            {abstract.length} / {MAX_ABSTRACT}
          </span>
        </div>
        <textarea
          id={ids.abstract}
          {...register("abstract")}
          rows={4}
          maxLength={MAX_ABSTRACT}
          aria-invalid={Boolean(errors.abstract) || undefined}
          aria-describedby={describedBy("abstract")}
          className={cn(fieldClasses(Boolean(errors.abstract)), "resize-y")}
        />
        {errors.abstract && <FieldError id={errorId("abstract")}>{errors.abstract.message}</FieldError>}
      </div>

      <div className="grid gap-section-sm sm:grid-cols-[minmax(0,1fr)_9rem]">
        {submitted ? (
          <div>
            <p className={LABEL}>Adviser</p>
            <p id={ids.adviser} tabIndex={-1} aria-describedby={`${ids.adviser}-hint`} className="py-2 text-body text-stone-800">
              {adviser ? personName(adviser) : "Your adviser"}
            </p>
            <p id={`${ids.adviser}-hint`} className="mt-1 text-small text-stone-600">
              Your adviser can't be changed once the record is submitted.
            </p>
          </div>
        ) : (
        <div>
          <label htmlFor={ids.adviser} className={LABEL}>
            Adviser <RequiredMark />
          </label>
          <Controller
            control={control}
            name="adviser"
            render={({ field }) => (
              <AdviserCombobox
                id={ids.adviser}
                advisers={advisers}
                value={field.value}
                onChange={(id) => field.onChange(id)}
                onBlur={field.onBlur}
                selfId={selfId}
                invalid={Boolean(errors.adviser)}
                describedBy={describedBy("adviser", `${ids.adviser}-hint`)}
              />
            )}
          />
          {errors.adviser ? (
            <FieldError id={errorId("adviser")}>{errors.adviser.message}</FieldError>
          ) : null}
          <p id={`${ids.adviser}-hint`} className="mt-1 text-small text-stone-600">
            The faculty member who supervised this work. They review it first.
          </p>
        </div>
        )}

        <Field label="Year" htmlFor={ids.year} required error={errors.year?.message} errorId={errorId("year")}>
          <input
            id={ids.year}
            type="number"
            inputMode="numeric"
            {...register("year", { valueAsNumber: true })}
            aria-invalid={Boolean(errors.year) || undefined}
            aria-describedby={describedBy("year")}
            className={fieldClasses(Boolean(errors.year))}
          />
        </Field>
      </div>

      <div>
        <label htmlFor={ids.authors} className={LABEL}>
          Authors <RequiredMark />
        </label>
        <div className="flex gap-2">
          <input
            id={ids.authors}
            value={authorInput}
            onChange={(e) => setAuthorInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addAuthor();
              }
            }}
            aria-invalid={Boolean(errors.authors) || undefined}
            aria-describedby={describedBy("authors", `${ids.authors}-hint`)}
            placeholder="Full name, then Enter"
            className={fieldClasses(Boolean(errors.authors))}
          />
          <button type="button" onClick={addAuthor} className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-0 shrink-0 px-4")}>
            Add
          </button>
        </div>
        <p id={`${ids.authors}-hint`} className="mt-1 text-small text-stone-600">
          Yourself and every co-author, in the order they should be credited.
        </p>
        {authors.length > 0 && (
          <ul aria-label="Authors added" className="mt-2 flex flex-wrap gap-2">
            {authors.map((name) => (
              <li
                key={name}
                className="inline-flex items-center gap-1.5 rounded-full bg-stone-100 py-1 pl-3 pr-1 text-small text-stone-800"
              >
                {name}
                <button
                  type="button"
                  onClick={() => removeAuthor(name)}
                  aria-label={`Remove ${name}`}
                  className={cn("rounded-full p-1 text-stone-600 hover:text-stone-900", FOCUS_RING)}
                >
                  <i className="fas fa-xmark text-label" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {errors.authors && (
          <FieldError id={errorId("authors")}>
            {errors.authors.message ?? "Add at least one author."}
          </FieldError>
        )}
      </div>

      <details
        open={moreOpen}
        onToggle={(e) => onMoreOpenChange((e.currentTarget as HTMLDetailsElement).open)}
        className="rounded-xl border border-stone-200"
      >
        <summary className={cn("cursor-pointer select-none rounded-xl px-4 py-3 text-body font-medium text-stone-800", FOCUS_RING)}>
          More details
          <span className="ml-2 font-normal text-stone-600">Field, PSCED and hints for your adviser</span>
        </summary>
        <div className="flex flex-col gap-section border-t border-stone-200 px-4 py-4">
          <div className="grid gap-section sm:grid-cols-2">
            <div>
              <label htmlFor={ids.classification} className={LABEL}>Field of research</label>
              <select
                id={ids.classification}
                {...register("classification", { setValueAs: (v) => (v === "" || v == null ? undefined : Number(v)) })}
                className={fieldClasses(false)}
              >
                <option value="">Not set</option>
                {classifications.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={ids.psced} className={LABEL}>PSCED classification</label>
              <select
                id={ids.psced}
                {...register("psced", { setValueAs: (v) => (v === "" || v == null ? undefined : Number(v)) })}
                className={fieldClasses(false)}
              >
                <option value="">Not set</option>
                {psceds.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          </div>

          {submitted ? (
            <div>
              <p className="text-body font-medium text-stone-800">Flagged for your adviser</p>
              <p className="mt-1 text-small text-stone-600">
                These can't be changed once the record is submitted.
              </p>
              {flagged.length > 0 ? (
                <ul aria-label="Flagged for your adviser" className="mt-3 flex flex-col gap-1.5">
                  {flagged.map(({ field, summary }) => (
                    <li key={field} className="text-body text-stone-700">{summary}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-body text-stone-700">Nothing was flagged.</p>
              )}
            </div>
          ) : (
          <fieldset aria-describedby="metadata-hints-note">
            <legend className="text-body font-medium text-stone-800">Flag for your adviser</legend>
            <p id="metadata-hints-note" className="mt-1 text-small text-stone-600">
              Your adviser sees these. They decide which offices, if any, review your work.
            </p>
            <div className="mt-3 flex flex-col gap-2.5">
              {HINTS.map(({ field, label }) => (
                <div key={field} className="flex items-start gap-2.5">
                  <input id={ids[field]} type="checkbox" {...register(field)} className={cn(CHECKBOX, "mt-1")} />
                  <label htmlFor={ids[field]} className="text-body text-stone-700">{label}</label>
                </div>
              ))}
            </div>
          </fieldset>
          )}
        </div>
      </details>
    </div>
  );
}

function RequiredMark() {
  return (
    <>
      <span className="text-brand" aria-hidden>*</span>
      <span className="sr-only">(required)</span>
    </>
  );
}

function Field({
  label,
  htmlFor,
  required,
  error,
  errorId,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  error?: string;
  errorId: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className={LABEL}>
        {label} {required && <RequiredMark />}
      </label>
      {children}
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </div>
  );
}
