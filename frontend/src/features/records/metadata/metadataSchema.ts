/**
 * A record's metadata, as `MetadataForm` edits it (IR-408; spec §4.4 step 2).
 *
 * One schema for every place metadata is edited: Publish's Details step now,
 * Paper View's *Edit details* dialog when F5 lands. `recordFormSchema` stays
 * only for `EditRecordPage`, which F5 deletes.
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

/** The schema, given who is signed in, since the adviser rule depends on it. */
export function metadataSchema(selfId: number | null) {
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

    adviser: z
      .number({ required_error: ADVISER_REQUIRED, invalid_type_error: ADVISER_REQUIRED })
      .int()
      .positive(ADVISER_REQUIRED)
      .refine((id) => selfId == null || id !== selfId, ADVISER_IS_SELF),

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
 * The PATCH body for these values.
 *
 * Each hint also sets its office's `requested_*` flag. Until IR-260 cuts over,
 * the live backend still routes on those flags after intake
 * (`lifecycle._resolve_enter_clearance_stage`), and the old wizard pre-checked
 * them from the same three answers. Sending the hint without the flag would
 * quietly drop every Publish submission's office review. Under ADR-032 the
 * Adviser decides routing and the flags become hints only. The form's copy
 * says both: a hint may bring in an office, and reviewers confirm which.
 */
export function metadataPayload(
  values: MetadataValues,
  // A list that failed to load shows its field as "Not set"; sending that
  // would erase a value the draft already holds, so such a field is left out.
  unloaded: { classification?: boolean; psced?: boolean } = {},
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
    requested_itso:         values.is_ip,
    requested_ierc:         values.requires_ethics_review,
    requested_ktto:         values.for_commercialization,
  };
  if (unloaded.classification) delete payload.classification;
  if (unloaded.psced) delete payload.psced;
  return payload;
}
