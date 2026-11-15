import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui/Button";
import { FieldError } from "@/components/ui/FieldError";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { CHECKBOX, LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { failureMessage } from "@/lib/readFailure";
import type { Opportunity } from "@/types/opportunities";
import type { Classification } from "@/types/records";

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
  "opportunity_type", "title", "description", "due_date", "location", "areas",
  "external_url", "start_date", "end_date", "registration_fee", "is_featured",
];

/**
 * Post a call, or edit one (IR-530).
 *
 * A sheet rather than a page: posting is a short task done from the board, and
 * the board should still be there, unchanged, when it is done. The same form
 * edits, opened on the call's saved values.
 *
 * The browser checks only that the required fields are filled (IR-760). The
 * server decides; whatever it rejects comes back against its field. Whether
 * this viewer may post or edit at all is the server's `can_post` / `can_edit`, read by the page before offering this.
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
    descError: useId(),
    areasHint: useId(),
    areasError: useId(),
  };

  // The Areas a Call can carry: Classifications only (ADR-050 amendment 1).
  const [areas, setAreas] = useState<Classification[] | null | "failed">(null);
  useEffect(() => {
    let cancelled = false;
    // A wrong-shaped answer reads as a failure, never as a form stuck loading.
    recordsApi.classifications()
      .then(({ data }) => { if (!cancelled) setAreas(data?.results ?? []); })
      .catch(() => { if (!cancelled) setAreas("failed"); });
    return () => { cancelled = true; };
  }, []);

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
          `${failureMessage(err, { lead: `Could not ${editing ? "save your changes" : "post the call"}.` })} Nothing has been lost.`,
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
      size="lg"
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

        <Select
          id={ids.type}
          name="opportunity_type"
          label="Type"
          required
          value={draft.opportunity_type}
          onChange={(e) => set("opportunity_type", e.target.value as OpportunityDraft["opportunity_type"])}
          error={errors.opportunity_type}
        >
          <option value="" disabled>Choose a type</option>
          {OPPORTUNITY_TYPES.map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </Select>

        <Input
          id={`${ids.form}-title`}
          name="title"
          label="Title"
          required
          value={draft.title}
          maxLength={300}
          onChange={(e) => set("title", e.target.value)}
          error={errors.title}
        />

        <div className="flex flex-col gap-1">
          <FieldLabel htmlFor={ids.desc} label="About" />
          <textarea
            id={ids.desc}
            name="description"
            rows={4}
            aria-required="true"
            value={draft.description}
            onChange={(e) => set("description", e.target.value)}
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={errors.description ? ids.descError : ids.descHint}
            className={`${fieldClasses(Boolean(errors.description))} resize-y`}
          />
          {errors.description
            ? <FieldError id={ids.descError}>{errors.description}</FieldError>
            : <p id={ids.descHint} className="text-small text-stone-600">The board shows the first two lines.</p>}
        </div>

        <div className="grid gap-section-sm sm:grid-cols-3">
          <Input
            id={`${ids.form}-due`}
            name="due_date"
            type="date"
            label="Paper deadline"
            required
            value={draft.due_date}
            onChange={(e) => set("due_date", e.target.value)}
            error={errors.due_date}
          />
          <div className="sm:col-span-2">
            <Input
              id={`${ids.form}-location`}
              name="location"
              label="Location"
              required
              placeholder="e.g. Cebu City, Philippines, or Online"
              value={draft.location}
              maxLength={300}
              onChange={(e) => set("location", e.target.value)}
              error={errors.location}
            />
          </div>
        </div>

        <fieldset aria-describedby={errors.areas ? ids.areasError : ids.areasHint}>
          <legend className={LABEL}>Areas</legend>
          <p id={ids.areasHint} className="text-small text-stone-600 mb-1">Choose at least one.</p>
          {areas === "failed" ? (
            <p className={LOAD_ERROR}>
              <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
              The Areas could not be loaded. Close this and try again.
            </p>
          ) : areas === null ? (
            <p className="text-small text-stone-600">Loading Areas…</p>
          ) : (
            <div className="grid gap-x-section gap-y-1 sm:grid-cols-2">
              {areas.map((area, i) => (
                <label key={area.id} className="flex items-center gap-2 min-h-11 sm:min-h-0 text-small text-stone-700">
                  <input
                    type="checkbox"
                    // The first box carries the field's name, so a missing
                    // Area can take focus like any other field.
                    name={i === 0 ? "areas" : undefined}
                    checked={draft.areas.includes(area.id)}
                    onChange={(e) => set(
                      "areas",
                      e.target.checked
                        ? [...draft.areas, area.id]
                        : draft.areas.filter((id) => id !== area.id),
                    )}
                    aria-invalid={errors.areas ? true : undefined}
                    className={CHECKBOX}
                  />
                  {area.name}
                </label>
              ))}
            </div>
          )}
          {errors.areas && <FieldError id={ids.areasError}>{errors.areas}</FieldError>}
        </fieldset>

        <Input
          id={`${ids.form}-url`}
          name="external_url"
          type="url"
          label="Link"
          required
          placeholder="https://"
          value={draft.external_url}
          maxLength={500}
          onChange={(e) => set("external_url", e.target.value)}
          error={errors.external_url}
          hint="Where to read the full call and submit."
        />

        <div className="grid gap-section-sm sm:grid-cols-2">
          <Input
            id={`${ids.form}-start`}
            name="start_date"
            type="date"
            label="Start date"
            optional
            value={draft.start_date}
            onChange={(e) => set("start_date", e.target.value)}
            error={errors.start_date}
          />
          <Input
            id={`${ids.form}-end`}
            name="end_date"
            type="date"
            label="End date"
            optional
            value={draft.end_date}
            onChange={(e) => set("end_date", e.target.value)}
            error={errors.end_date}
            hint="A journal or book chapter keeps no dates."
          />
        </div>

        <Input
          id={`${ids.form}-fee`}
          name="registration_fee"
          label="Registration fee"
          optional
          placeholder="e.g. PHP 5,000; students PHP 3,000"
          value={draft.registration_fee}
          maxLength={200}
          onChange={(e) => set("registration_fee", e.target.value)}
          error={errors.registration_fee}
        />

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
