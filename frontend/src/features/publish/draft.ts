/**
 * The Publish dialog's pure rules (IR-408), kept out of the component so each
 * is stated once and tested as a table.
 */
import type { Classification, PSCEDClassification, RecordDetail, RecordType } from "@/types/records";

import { emptyMetadata, metadataSchema, type MetadataValues } from "@/features/records/metadata/metadataSchema";

export type PublishStep = 1 | 2 | 3;

/**
 * A record type's name reduced to a stable key ("Thesis / Research" →
 * "thesis/research"), so copy keyed by type survives spacing and case. The
 * one place the client compares type names.
 */
export function typeKey(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "");
}

export const isProposal = (typeName: string): boolean => typeKey(typeName) === "proposal";

/**
 * A draft's provisional title, from the manuscript's file name.
 *
 * Title is the only field a Record requires, so the draft is created with
 * this the moment a file is chosen. Separators become spaces, the same
 * normalisation the metadata-suggestions endpoint applies when it declines to
 * suggest a title that is only the file name (`records/metadata_suggestions`).
 */
export function provisionalTitle(fileName: string): string {
  const stem = fileName.replace(/\.[^./\\]+$/, "");
  const title = stem.replace(/[\s_-]+/g, " ").trim();
  return title || "Untitled manuscript";
}

export interface ReferenceLists {
  recordTypes:     RecordType[];
  classifications: Classification[];
  psceds:          PSCEDClassification[];
}

/**
 * What a saved draft holds, as the dialog's state.
 *
 * The detail payload names its record type, classification and PSCED rather
 * than giving their ids (they are `StringRelatedField`s), so each is looked up
 * by name in the lists the dialog already loaded.
 */
export function stateFromDraft(
  record: RecordDetail,
  lists: ReferenceLists,
): { typeId: number | null; values: MetadataValues } {
  const byName = <T extends { id: number; name: string }>(items: T[], name: string | null) =>
    name == null ? undefined : items.find((item) => item.name === name)?.id;

  const blank = emptyMetadata();
  return {
    typeId: byName(lists.recordTypes, record.record_type) ?? null,
    values: {
      ...blank,
      title: record.title ?? "",
      abstract: record.abstract ?? "",
      year: record.year_accomplished ?? blank.year,
      adviser: (record.adviser ?? undefined) as number,
      authors: (record.authors ?? []).map((a) => a.name).filter(Boolean),
      keywords: (record.keywords ?? []).join(", "),
      owner_emails: record.owners?.map((owner) => owner.email).join(", "),
      classification: byName(lists.classifications, record.classification),
      psced: byName(lists.psceds, record.psced),
      is_ip: Boolean(record.is_ip),
      requires_ethics_review: Boolean(record.requires_ethics_review),
      for_commercialization: Boolean(record.for_commercialization),
    },
  };
}

/**
 * Where a reopened draft resumes: the first step with something missing.
 *
 * Step 1 needs a type and a manuscript; step 2 needs metadata the schema
 * accepts; anything past that is ready to review.
 */
export function firstIncompleteStep(
  draft: { typeId: number | null; hasManuscript: boolean; values: MetadataValues },
  selfId: number | null,
): PublishStep {
  if (draft.typeId == null || !draft.hasManuscript) return 1;
  if (!metadataSchema(selfId).safeParse(draft.values).success) return 2;
  return 3;
}

/** What an API failure says, split into one message and any per-field errors. */
export interface ApiFailure {
  message:  string;
  fields:   Record<string, string>;
  /** True when the server never answered, so retrying may simply work. */
  network:  boolean;
}

const NETWORK_MESSAGE = "We couldn't reach IRIS. Check your connection and try again.";
const SERVER_MESSAGE = "IRIS isn't responding right now. Try again in a few minutes.";
const TOO_LARGE_MESSAGE = "This is too large for the server to accept.";

/**
 * What to say when the body has nothing readable (IR-610): a proxy's empty 5xx
 * or HTML error page means the server failed, not whatever the caller was sending.
 */
function statusMessage(status: number | undefined, fallback: string): string {
  if (status === 413) return TOO_LARGE_MESSAGE;
  if (status != null && status >= 500) return SERVER_MESSAGE;
  return fallback;
}

export function describeFailure(err: unknown, fallback: string): ApiFailure {
  const response = (err as { response?: { status?: number; data?: unknown } })?.response;
  if (!response) return { message: NETWORK_MESSAGE, fields: {}, network: true };

  const data = response.data;
  const fields: Record<string, string> = {};
  let message = statusMessage(response.status, fallback);

  if (data && typeof data === "object" && !Array.isArray(data)) {
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const text = Array.isArray(value) ? value.filter((v) => typeof v === "string").join(" ") : value;
      if (typeof text !== "string" || !text) continue;
      if (key === "detail" || key === "non_field_errors") message = text;
      else fields[key] = text;
    }
  } else if (typeof data === "string" && (response.status ?? 0) < 500) {
    // A blank body or an error page is not a message, and a 5xx's text is the
    // proxy's (IR-610), so only a short plain reply from IRIS itself is shown.
    const text = data.trim();
    if (text && !text.startsWith("<") && text.length < 300) message = text;
  }

  return { message, fields, network: false };
}
