/**
 * A record's metadata, as `MetadataForm` edits it (IR-408; spec §4.4 step 2).
 *
 * One schema for every place metadata is edited: Publish's Details step and
 * Paper View's *Edit details* dialog (IR-411). The older `recordFormSchema`
 * went with `EditRecordPage`.
 *
 * Two rules differ from that older schema, both from ADR-032 §1:
 *
 * - **The adviser is required for every type.** Every record enters with its
 *   Adviser; the old schema required one only for a Proposal.
 * - **The adviser is never the author.** Nobody reviews their own submission.
 *   The server will refuse it too (IR-260); this is the client's half.
 */
import { z } from "zod";

import type { RecordFormData } from "@/types/records";

export const ADVISER_REQUIRED = "Choose your adviser.";
export const ADVISER_IS_SELF = "You can't be your own adviser. Choose another faculty member.";

/**
 * The schema, given who is signed in, since the adviser rule depends on it.
 *
 * Once a record is `submitted` its Adviser is fixed (IR-507): shown, never
 * sent, so it is not validated either. A legacy record can be awaiting its
 * owner's revision with no Adviser recorded, and requiring one there blocked
 * Save with no field to fix and no message shown.
 */
export function metadataSchema(selfId: number | null, { submitted = false }: { submitted?: boolean } = {}) {
  const adviser = z
    .number({ required_error: ADVISER_REQUIRED, invalid_type_error: ADVISER_REQUIRED })
    .int()
    .positive(ADVISER_REQUIRED)
    .refine((id) => selfId == null || id !== selfId, ADVISER_IS_SELF);
  return z.object({
    title: z
      .string()
      .trim()
      .min(5, "Title must be at least 5 characters.")
      .max(500, "Title is too long."),

    abstract: z
      .string()
      .trim()
      .min(30, "Abstract must be at least 30 characters.")
      .max(5000, "Abstract is too long."),

    // An emptied number input is NaN, not undefined, so the type error needs
    // the message too, or Zod says "Expected number, received nan".
    year: z
      .number({ required_error: "Year is required.", invalid_type_error: "Year is required." })
      .int("Year is required.")
      .min(1990, "Year must be 1990 or later.")
      .max(new Date().getFullYear() + 1, "Year cannot be in the future."),

    // The cast keeps `MetadataValues` one type for both forms; a submitted
    // record's value is display-only and `metadataPayload` leaves it out.
    adviser: submitted ? (z.any() as unknown as typeof adviser) : adviser,

    authors: z.array(z.string().trim().min(1)).min(1, "Add at least one author."),

    classification: z.number().int().positive().optional(),
    psced:          z.number().int().positive().optional(),

    // "Flag for your adviser". Hints the Adviser sees, not routes (ADR-032).
    is_ip:                  z.boolean(),
    requires_ethics_review: z.boolean(),
    for_commercialization:  z.boolean(),
  });
}

export type MetadataValues = z.infer<ReturnType<typeof metadataSchema>>;

/** A new draft's starting values. The author line starts with the author. */
export function emptyMetadata(authorName?: string): MetadataValues {
  return {
    title: "",
    abstract: "",
    year: new Date().getFullYear(),
    // `adviser` is required by the schema, so "unchosen" is the one value it
    // refuses; the cast keeps the type honest everywhere else.
    adviser: undefined as unknown as number,
    authors: authorName ? [authorName] : [],
    classification: undefined,
    psced: undefined,
    is_ip: false,
    requires_ethics_review: false,
    for_commercialization: false,
  };
}

/**
 * The three "flag for your adviser" hints, worded once: the form's checkbox
 * label and the review summary's line both come from here.
 */
export const HINTS: ReadonlyArray<{
  field: "is_ip" | "requires_ethics_review" | "for_commercialization";
  label: string;
  summary: string;
}> = [
  { field: "is_ip", label: "This may involve intellectual property worth protecting", summary: "Possible intellectual property" },
  {
    field: "requires_ethics_review",
    label: "This involves human participants, animal subjects or sensitive personal data",
    summary: "Human participants, animal subjects or sensitive data",
  },
  { field: "for_commercialization", label: "This may have commercial potential", summary: "Commercial potential" },
];

/**
 * The form fields that are fixed once a record is submitted (IR-507, ADR-032
 * §10 Amendment): the server keeps the Adviser and the hints as they were
 * submitted, so the form shows them read-only and does not send them.
 */
export const FIXED_ONCE_SUBMITTED = ["adviser", "is_ip", "requires_ethics_review", "for_commercialization"] as const;

/**
 * The PATCH body for these values.
 *
 * The hints are sent as hints and nothing more: `requested_itso/ierc/ktto`
 * are never written here. Under ADR-032 the author picks no office; the
 * Adviser routes. Decided with the project lead on 2026-10-06 (IR-408).
 */
export function metadataPayload(
  values: MetadataValues,
  // A list that failed to load shows its field as "Not set"; sending that
  // would erase a value the draft already holds, so such a field is left out.
  unloaded: { classification?: boolean; psced?: boolean } = {},
  // A submitted record's revision: its fixed fields are left out (IR-507).
  { submitted = false }: { submitted?: boolean } = {},
): Partial<RecordFormData> {
  const payload: Partial<RecordFormData> = {
    title:                  values.title.trim(),
    abstract:               values.abstract.trim(),
    year_accomplished:      values.year,
    adviser:                values.adviser,
    authors:                values.authors,
    // null, not undefined: a cleared field must reach the server as cleared.
    classification:         values.classification ?? null,
    psced:                  values.psced ?? null,
    is_ip:                  values.is_ip,
    requires_ethics_review: values.requires_ethics_review,
    for_commercialization:  values.for_commercialization,
  };
  if (unloaded.classification) delete payload.classification;
  if (unloaded.psced) delete payload.psced;
  if (submitted) for (const field of FIXED_ONCE_SUBMITTED) delete payload[field];
  return payload;
}
