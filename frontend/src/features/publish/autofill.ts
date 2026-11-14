/**
 * Autofill: which values from the PDF go into Details, and which wait for the
 * author (IR-833; IR-830 decisions 15–17).
 *
 * Each field's *decision* is tracked apart from its value, and saved with the
 * draft as `metadata_sources`, so a late or repeated reading never overwrites
 * what the author did and a reopened draft does not mistake the title made
 * from the file name for the author's own:
 *
 * - `placeholder` — the dialog wrote it (that provisional title).
 * - `automatic`   — filled in from the PDF; Undo restores `previous`.
 * - `accepted`    — the author chose a value the PDF offered.
 * - `authored`    — the author typed or cleared it; `source_revision` names the
 *                   file whose value they edited, if they edited one.
 * - `dismissed`   — the author turned the PDF's value down, or undid it.
 *
 * Only a title or abstract the server marks `auto_apply` is filled in unasked,
 * and only into an empty or placeholder field, or one still holding the
 * previous file's automatic value. Authors, keywords and publication year are
 * offered; the author accepts them. Nothing here touches owners, the adviser,
 * origin, embargo, the hints or the completion year.
 */
import type { MetadataValues } from "@/features/records/metadata/metadataSchema";
import { withoutPdfExtension } from "./draft";
import type { FieldDecision, MetadataSources, MetadataSuggestions, SuggestionEntry, SuggestionFields } from "@/types/records";

export const AUTOFILL_FIELDS = ["title", "abstract", "authors", "keywords", "publication_year"] as const;
export type AutofillField = (typeof AUTOFILL_FIELDS)[number];

/** A field's value as the form holds it: keywords are one comma-separated line. */
export type FormValue = MetadataValues[AutofillField];

export const NO_FIELDS: SuggestionFields = {
  title: null, abstract: null, authors: null, keywords: null, publication_year: null,
};

/**
 * The reply's fields. A server from before IR-833 sends only the legacy title
 * and abstract, which were always the auto-applicable two.
 */
export function fieldsOf(data: MetadataSuggestions): SuggestionFields {
  if (data.fields) return { ...data.fields, title: untitled(data.fields.title) };
  const legacy = (value: string | null): SuggestionEntry<string> | null =>
    value == null ? null : { value, basis: "document_title", page: null, region: null, auto_apply: true, exceeds_limit: false };
  return { ...NO_FIELDS, title: untitled(legacy(data.suggestions.title)), abstract: legacy(data.suggestions.abstract) };
}

/**
 * A suggested title never ends in ".pdf" (IR-1084). The server declines a
 * title that is only the manuscript's stored file name, but storage may
 * rename a file ("My_Thesis_k3Jx.pdf"), so the extractor's file-name fallback
 * can slip through; stripped, it reads as the placeholder it is. A title that
 * was only an extension is not offered.
 */
function untitled(entry: SuggestionEntry<string> | null): SuggestionEntry<string> | null {
  if (entry == null) return null;
  const value = withoutPdfExtension(entry.value);
  if (!value) return null;
  return value === entry.value ? entry : { ...entry, value };
}

/** A suggestion's value as the form would hold it. */
export function formValueOf(field: AutofillField, entry: SuggestionEntry<unknown>): FormValue {
  if (field === "keywords") return (entry.value as string[]).join(", ");
  return entry.value as FormValue;
}

export function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) return JSON.stringify(a ?? []) === JSON.stringify(b ?? []);
  return (a ?? "") === (b ?? "") || (a == null && b === "") || (a === "" && b == null);
}

function isEmpty(value: unknown): boolean {
  if (Array.isArray(value)) return value.length === 0;
  return value == null || (typeof value === "string" && value.trim() === "");
}

export interface Fill {
  field:    AutofillField;
  value:    FormValue;
  decision: FieldDecision;
}

/**
 * What to fill in now from a reading of `revision`.
 *
 * An `automatic` value from an earlier revision is still the system's, since
 * any edit would have made it `authored`, so a new file's value replaces it.
 */
export function planAutofill(
  fields: SuggestionFields,
  revision: string | null,
  decisions: MetadataSources,
  values: Pick<MetadataValues, AutofillField>,
): Fill[] {
  const fills: Fill[] = [];
  for (const field of ["title", "abstract"] as const) {
    const entry = fields[field];
    if (!entry?.auto_apply) continue;
    const decision = decisions[field];
    const current = values[field] ?? "";
    let previous: string | undefined;
    if (decision == null && isEmpty(current)) previous = current;
    else if (decision?.state === "placeholder") previous = current;
    else if (decision?.state === "automatic" && decision.source_revision !== revision) previous = decision.previous ?? "";
    if (previous === undefined || sameValue(current, entry.value)) continue;
    fills.push({ field, value: entry.value, decision: { state: "automatic", source_revision: revision, previous } });
  }
  return fills;
}

/** What a field shows under it once the PDF has been read. */
export type FieldOffer =
  | { kind: "filled"; page: number | null; entry: SuggestionEntry<unknown> | null }
  | { kind: "stale" }
  | { kind: "offer"; value: FormValue; entry: SuggestionEntry<unknown>; replaces: boolean }
  | null;

export function offerFor(
  field: AutofillField,
  fields: SuggestionFields,
  revision: string | null,
  decision: FieldDecision | undefined,
  current: unknown,
): FieldOffer {
  const entry = fields[field] as SuggestionEntry<unknown> | null;
  if (decision?.state === "automatic") {
    if (decision.source_revision === revision) return { kind: "filled", page: entry?.page ?? null, entry };
    // The previous file's value, which this file did not replace.
    return entry == null ? { kind: "stale" } : null;
  }
  if (entry == null) return null;
  const sameSource = decision?.source_revision === revision;
  // Turned down, taken, or taken and then edited: not offered again for this file.
  if (decision != null && decision.state !== "placeholder" && sameSource) return null;
  const value = formValueOf(field, entry);
  if (sameValue(current, value)) return null;
  const replaces = !isEmpty(current) && decision?.state !== "placeholder";
  return { kind: "offer", value, entry, replaces };
}
