import { useId, useRef, useState, type FormEvent } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { Button } from "@/components/ui/Button";
import { FieldError } from "@/components/ui/FieldError";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { CHECKBOX, LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import type { Opportunity } from "@/types/opportunities";

import {
  EMPTY_DRAFT,
  OPPORTUNITY_TYPES,
  checkDraft,
  draftFrom,
  inputFrom,
  serverErrors,
  type DraftErrors,
  type DraftField,
  type OpportunityDraft,
} from "./opportunityUtils";

interface OpportunityFormDialogProps {
  /** The call being edited, or null to post a new one. */
  opportunity: Opportunity | null;
  onClose: () => void;
  /** The saved call as the server returned it. */
  onSaved: (saved: Opportunity, created: boolean) => void;
}

/** Closing is refused while saving, so a half-sent change is never abandoned. */
const STAY_OPEN = () => {};

/** The fields in the order they appear, so the first error can take focus. */
const FIELD_ORDER: DraftField[] = [
  "opportunity_type", "title", "posting_office", "due_date", "audience",
  "description", "funding_ceiling", "external_url", "tags", "source", "is_featured",
];

/**
 * Post a call, or edit one (IR-530).
 *
 * A sheet rather than a page: posting is a short task done from the board, and
 * the board should still be there, unchanged, when it is done. The same form
 * edits, opened on the call's saved values.
 *
 * The browser checks only what it can be sure of (the four required fields,
 * a number for the ceiling). The server decides; whatever it rejects comes
 * back against its field. Whether this viewer may post or edit at all is the
 * server's `can_post` / `can_edit`, read by the page before offering this.
 */
export function OpportunityFormDialog({ opportunity, onClose, onSaved }: OpportunityFormDialogProps) {
  const editing = opportunity !== null;
  const [draft, setDraft] = useState<OpportunityDraft>(() =>
    opportunity ? draftFrom(opportunity) : EMPTY_DRAFT,
  );
  const [errors, setErrors] = useState<DraftErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const ids = {
    form:  useId(),
    type:  useId(),
    desc:  useId(),
    descHint: useId(),
    typeError: useId(),
    descError: useId(),
    source: useId(),
  };

  const set = <K extends DraftField>(field: K, value: OpportunityDraft[K]) => {
    setDraft((d) => ({ ...d, [field]: value }));
    // An error describes the value that was there; once it changes, the
    // message is stale until the next submit says otherwise.
    if (errors[field]) setErrors((e) => ({ ...e, [field]: undefined }));
  };

  const focusFirstError = (found: DraftErrors) => {
    const first = FIELD_ORDER.find((f) => found[f]);
    if (!first) return;
    // Every field carries its draft key as `name`, so the first invalid one
    // can be found without a ref per field.
    requestAnimationFrame(() => {
      formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;

    const found = checkDraft(draft);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length > 0) {
      focusFirstError(found);
      return;
    }

    setSaving(true);
    try {
      const input = inputFrom(draft);
      const { data } = opportunity
        ? await opportunitiesApi.update(opportunity.id, input)
        : await opportunitiesApi.create(input);
      onSaved(data, !editing);
    } catch (err) {
      // Read structurally, as PublishDialog does: anything with a response
      // carries the server's verdict, and a network failure has none.
      const response = (err as { response?: { status?: number; data?: unknown } })?.response;
      const status = response?.status;
      if (status === 400) {
        const { fields, form } = serverErrors(response?.data);
        setErrors(fields);
        setFormError(form ?? (Object.keys(fields).length > 0 ? null : "The server refused these details."));
        focusFirstError(fields);
      } else if (status === 403 || status === 404) {
        setFormError(
          editing
            ? "You can no longer change this call. It may have been removed, or your role may have changed."
            : "Your account can no longer post calls. If that seems wrong, ask RDCO.",
        );
      } else {
        setFormError(
          `Could not ${editing ? "save your changes" : "post the call"}. Check your connection and try again; nothing has been lost.`,
        );
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      sheet
      displayTitle
      size="md:max-w-2xl"
      title={editing ? "Edit call" : "Post a call"}
      onClose={saving ? STAY_OPEN : onClose}
      footer={
        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form={ids.form} loading={saving}>
            {saving ? "Saving…" : editing ? "Save changes" : "Post call"}
          </Button>
        </div>
      }
    >
      <form
        id={ids.form}
        ref={formRef}
        onSubmit={(e) => void submit(e)}
        noValidate
        className="space-y-section-sm"
      >
        {formError && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
            {formError}
          </p>
        )}

        <div>
          <label htmlFor={ids.type} className={LABEL}>Type</label>
          <select
            id={ids.type}
            name="opportunity_type"
            value={draft.opportunity_type}
            onChange={(e) => set("opportunity_type", e.target.value as OpportunityDraft["opportunity_type"])}
            aria-invalid={errors.opportunity_type ? true : undefined}
            aria-describedby={errors.opportunity_type ? ids.typeError : undefined}
            className={fieldClasses(Boolean(errors.opportunity_type))}
          >
            <option value="" disabled>Choose a type</option>
            {OPPORTUNITY_TYPES.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
          {errors.opportunity_type && <FieldError id={ids.typeError}>{errors.opportunity_type}</FieldError>}
        </div>

        <Input
          id={`${ids.form}-title`}
          name="title"
          label="Title"
          value={draft.title}
          maxLength={300}
          onChange={(e) => set("title", e.target.value)}
          error={errors.title}
        />

        <div className="grid gap-section-sm sm:grid-cols-3">
          <div className="sm:col-span-2">
            <Input
              id={`${ids.form}-office`}
              name="posting_office"
              label="Posting office"
              placeholder="e.g. Research & Development Coordinating Office (RDCO)"
              value={draft.posting_office}
              maxLength={200}
              onChange={(e) => set("posting_office", e.target.value)}
              error={errors.posting_office}
            />
          </div>
          <Input
            id={`${ids.form}-due`}
            name="due_date"
            type="date"
            label="Deadline"
            value={draft.due_date}
            onChange={(e) => set("due_date", e.target.value)}
            error={errors.due_date}
          />
        </div>

        <Input
          id={`${ids.form}-audience`}
          name="audience"
          label="Who can apply (optional)"
          placeholder="e.g. Faculty researchers and graduate students"
          value={draft.audience}
          maxLength={300}
          onChange={(e) => set("audience", e.target.value)}
          error={errors.audience}
        />

        <div>
          <label htmlFor={ids.desc} className={LABEL}>Description (optional)</label>
          <textarea
            id={ids.desc}
            name="description"
            rows={4}
            value={draft.description}
            onChange={(e) => set("description", e.target.value)}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={errors.description ? ids.descError : ids.descHint}
            className={`${fieldClasses(Boolean(errors.description))} resize-y`}
          />
          {errors.description
            ? <FieldError id={ids.descError}>{errors.description}</FieldError>
            : <p id={ids.descHint} className="text-small text-stone-600 mt-1">The board shows the first two lines.</p>}
        </div>

        <div className="grid gap-section-sm sm:grid-cols-2">
          <Input
            id={`${ids.form}-ceiling`}
            name="funding_ceiling"
            inputMode="decimal"
            label="Funding ceiling in pesos (optional)"
            placeholder="e.g. 150000"
            value={draft.funding_ceiling}
            onChange={(e) => set("funding_ceiling", e.target.value)}
            error={errors.funding_ceiling}
            hint="Leave blank when there is no funding."
          />
          <Input
            id={`${ids.form}-url`}
            name="external_url"
            type="url"
            label="Link (optional)"
            placeholder="https://"
            value={draft.external_url}
            maxLength={500}
            onChange={(e) => set("external_url", e.target.value)}
            error={errors.external_url}
            hint="Where to read the full call and apply."
          />
        </div>

        <Input
          id={`${ids.form}-tags`}
          name="tags"
          label="Tags (optional)"
          placeholder="e.g. Seed grant, AI and robotics"
          value={draft.tags}
          onChange={(e) => set("tags", e.target.value)}
          error={errors.tags}
          hint="Separate tags with commas."
        />

        <fieldset aria-describedby={errors.source ? `${ids.source}-error` : undefined}>
          <legend className={LABEL}>Source</legend>
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-section">
            {([
              ["internal", "Posted by a CIT-U office"],
              ["external", "Reposted from an outside body"],
            ] as const).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 min-h-11 sm:min-h-0 text-small text-stone-700">
                <input
                  type="radio"
                  name="source"
                  value={value}
                  checked={draft.source === value}
                  onChange={() => set("source", value)}
                  className={CHECKBOX}
                />
                {label}
              </label>
            ))}
          </div>
          {errors.source && <FieldError id={`${ids.source}-error`}>{errors.source}</FieldError>}
        </fieldset>

        <label className="flex items-start gap-2 min-h-11 sm:min-h-0 text-small text-stone-700">
          <input
            type="checkbox"
            name="is_featured"
            checked={draft.is_featured}
            onChange={(e) => set("is_featured", e.target.checked)}
            className={`${CHECKBOX} mt-0.5`}
          />
          <span>
            <span className="font-medium text-stone-900">Feature this call</span>
            <span className="block text-stone-600">Marks it with a star on the board.</span>
          </span>
        </label>
      </form>
    </Modal>
  );
}
