import { errorDetail } from "@/lib/errorDetail";
/**
 * The Publish dialog's pure rules (IR-408), kept out of the component so each
 * is stated once and tested as a table.
 */
import type { Classification, EmbargoAnswer, PSCEDClassification, RecordDetail, RecordType } from "@/types/records";

import { emptyMetadata, metadataSchema, type MetadataValues } from "@/features/records/metadata/metadataSchema";

/** 0 is the embargo question, which comes before the three numbered steps. */
export type PublishStep = 0 | 1 | 2 | 3;

/** Publish's first question as the dialog holds it. `null` is unanswered, not No. */
export interface EmbargoChoice {
  choice: "no" | "yes" | null;
  /** `YYYY-MM-DD`, or blank. Only a Yes uses it. */
  until:  string;
}

export const UNANSWERED: EmbargoChoice = { choice: null, until: "" };

export interface EmbargoProblem {
  /** The server's field names, so its refusals land in the same place. */
  field:   "embargoed" | "embargoed_until";
  message: string;
}

/** What is wrong with an answer, or null. The server re-checks all of it. */
export function embargoProblem(value: EmbargoChoice, today: string): EmbargoProblem | null {
  if (value.choice == null) return { field: "embargoed", message: "Say whether this paper is under embargo." };
  if (value.choice === "no") return null;
  if (!value.until) return { field: "embargoed_until", message: "Choose the date to review this embargo." };
  if (value.until < today) {
    return { field: "embargoed_until", message: "The date to review this embargo cannot be in the past." };
  }
  return null;
}

/**
 * The request body for an answer. A No sends no date, even one left from an earlier
 * Yes. Unanswered throws rather than reading as No, which can send text out.
 */
export function embargoAnswer(value: EmbargoChoice): EmbargoAnswer {
  if (value.choice == null) throw new Error("The embargo question has not been answered.");
  const embargoed = value.choice === "yes";
  return { embargoed, embargoed_until: embargoed ? value.until : null };
}

/** Is this what the server already holds? A No's leftover date does not count. */
export function sameEmbargo(saved: EmbargoChoice | null, value: EmbargoChoice): boolean {
  if (saved == null || saved.choice !== value.choice) return false;
  return value.choice !== "yes" || saved.until === value.until;
}

/**
 * What a saved draft answered. Only No and an active embargo are answers to show
 * again: anything else, a released one included, asks the question.
 */
export function embargoFromDraft(record: Pick<RecordDetail, "embargo">): EmbargoChoice {
  const embargo = record.embargo;
  if (embargo?.state === "none") return { choice: "no", until: "" };
  if (embargo?.state === "active") return { choice: "yes", until: embargo.until ?? "" };
  return UNANSWERED;
}

/** Today in Manila, where the server decides whether a date has passed. */
export function manilaToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila" }).format(new Date());
}

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
      origin: record.origin ?? "unknown",
      publication_year: record.publication_year ?? null,
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
 * The embargo question comes first; step 1 needs a type and a manuscript; step 2
 * needs metadata the schema accepts; anything past that is ready to review.
 */
export function firstIncompleteStep(
  draft: { embargo: EmbargoChoice; typeId: number | null; hasManuscript: boolean; values: MetadataValues },
  selfId: number | null,
): PublishStep {
  if (draft.embargo.choice == null) return 0;
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
      if (key === "non_field_errors") message = text;
      else if (key === "detail" || key === "code") continue;
      else fields[key] = text;
    }
  } else if (typeof data === "string" && (response.status ?? 0) < 500) {
    // A blank body or an error page is not a message, and a 5xx's text is the
    // proxy's (IR-610), so only a short plain reply from IRIS itself is shown.
    const text = data.trim();
    if (text && !text.startsWith("<") && text.length < 300) message = text;
  }

  return { message: errorDetail(err, message), fields, network: false };
}
