import { TONES, type Tone } from "@/components/ui/statusTones";
import type {
  Opportunity,
  OpportunityInput,
  OpportunitySource,
  OpportunityType,
} from "@/types/opportunities";

/** Every type, in the order the board and the form list them, with its glyph. */
export const OPPORTUNITY_TYPES: { id: OpportunityType; label: string; icon: string }[] = [
  { id: "internal_call",       label: "Internal call",       icon: "fa-building-columns"    },
  { id: "conference_deadline", label: "Conference deadline", icon: "fa-microphone-lines"    },
  { id: "funding_window",      label: "Funding window",      icon: "fa-hand-holding-dollar" },
  { id: "institutional_grant", label: "Institutional grant", icon: "fa-award"               },
];

export function typeMeta(type: OpportunityType) {
  return OPPORTUNITY_TYPES.find((t) => t.id === type) ?? OPPORTUNITY_TYPES[0];
}

/**
 * The board's sections, in reading order (IR-530).
 *
 * The page answers one question -- "what can I still apply to, and by when"
 * -- so it is grouped by how soon each call closes rather than laid out as a
 * grid the reader has to scan and sort in their head. Closed calls stay in a
 * last section, findable by someone mid-application, until the server drops
 * them a month after their deadline.
 */
export type DeadlineGroup = "week" | "month" | "later" | "closed";

export const DEADLINE_GROUPS: { id: DeadlineGroup; title: string }[] = [
  { id: "week",   title: "Closes within a week"  },
  { id: "month",  title: "Closes within a month" },
  { id: "later",  title: "Closes later"          },
  { id: "closed", title: "Recently closed"       },
];

/** Uses the server's `days_left`, never the viewer's clock. */
export function deadlineGroup(o: Opportunity): DeadlineGroup {
  if (o.is_closed) return "closed";
  if (o.days_left <= 7) return "week";
  if (o.days_left <= 30) return "month";
  return "later";
}

/**
 * The countdown chip: a word and a tone, never a colour alone.
 *
 * The palette has no red or amber (01-design-system §0), so urgency uses the
 * four tones by meaning: a week or less is `attention` (act now), three weeks
 * or less is `active`, anything further off and anything closed is `quiet`.
 */
export function countdown(o: Opportunity): { label: string; tone: Tone; className: string } {
  const tone: Tone = o.is_closed || o.days_left > 21 ? "quiet" : o.days_left <= 7 ? "attention" : "active";
  let label: string;
  if (o.is_closed) label = "Closed";
  else if (o.days_left === 0) label = "Due today";
  else if (o.days_left === 1) label = "1 day left";
  else label = `${o.days_left} days left`;
  return { label, tone, className: TONES[tone] };
}

/** Peso ceiling, or null when there is none. */
export function formatCeiling(value: string | null): string | null {
  if (value === null || value === "") return null;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  return `₱${amount.toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
}

function parseDay(iso: string): Date | null {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDueDate(iso: string): string {
  const d = parseDay(iso);
  if (!d) return iso;
  return d.toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });
}

/** The date block's three lines. Null for a date the server should never send. */
export function dateParts(iso: string): { month: string; day: string; weekday: string } | null {
  const d = parseDay(iso);
  if (!d) return null;
  return {
    month:   d.toLocaleDateString("en-PH", { month: "short" }),
    day:     String(d.getDate()),
    weekday: d.toLocaleDateString("en-PH", { weekday: "short" }),
  };
}

/** Case-insensitive match across the fields a reader would actually search. */
export function matchesQuery(o: Opportunity, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [o.title, o.posting_office, o.audience, o.description, o.type_display, ...o.tags]
    .some((field) => (field ?? "").toLowerCase().includes(q));
}

/**
 * Soonest deadline first, featured first only among calls due the same day.
 *
 * Deliberately not the server's order (featured first overall): on a board
 * grouped by date, a featured call due in four weeks sitting above one due in
 * twelve days reads as a mistake. Featuring marks a call with a star; it does
 * not reorder time. Applied after every load, add and edit, so the board is
 * always in the order a reload would show.
 */
export function byBoardOrder(a: Opportunity, b: Opportunity): number {
  if (a.due_date !== b.due_date) return a.due_date < b.due_date ? -1 : 1;
  if (a.is_featured !== b.is_featured) return a.is_featured ? -1 : 1;
  return a.id - b.id;
}

// ---- The post / edit form ------------------------------------------------

/** The form's own state: every field a string or a flag, as inputs hold them. */
export interface OpportunityDraft {
  opportunity_type: OpportunityType | "";
  title:            string;
  posting_office:   string;
  audience:         string;
  description:      string;
  funding_ceiling:  string;
  external_url:     string;
  due_date:         string;
  is_featured:      boolean;
  tags:             string;
  source:           OpportunitySource;
}

export const EMPTY_DRAFT: OpportunityDraft = {
  opportunity_type: "",
  title:            "",
  posting_office:   "",
  audience:         "",
  description:      "",
  funding_ceiling:  "",
  external_url:     "",
  due_date:         "",
  is_featured:      false,
  tags:             "",
  source:           "internal",
};

export function draftFrom(o: Opportunity): OpportunityDraft {
  return {
    opportunity_type: o.opportunity_type,
    title:            o.title,
    posting_office:   o.posting_office,
    audience:         o.audience,
    description:      o.description,
    // DRF sends "150000.00"; a person typed 150000.
    funding_ceiling:  o.funding_ceiling === null ? "" : String(Number(o.funding_ceiling)),
    external_url:     o.external_url,
    due_date:         o.due_date,
    is_featured:      o.is_featured,
    tags:             o.tags.join(", "),
    source:           o.source,
  };
}

export type DraftField = keyof OpportunityDraft;
export type DraftErrors = Partial<Record<DraftField, string>>;

/**
 * What the browser can say before the server does. The server still decides:
 * anything it rejects comes back through `serverErrors` against its field.
 */
export function checkDraft(d: OpportunityDraft): DraftErrors {
  const errors: DraftErrors = {};
  if (!d.opportunity_type) errors.opportunity_type = "Choose what kind of call this is.";
  if (!d.title.trim()) errors.title = "Give the call a title.";
  if (!d.posting_office.trim()) errors.posting_office = "Name the office or body posting it.";
  if (!d.due_date) errors.due_date = "Set the deadline.";
  if (d.funding_ceiling.trim()) {
    const amount = Number(d.funding_ceiling.replace(/,/g, ""));
    if (!Number.isFinite(amount) || amount < 0) {
      errors.funding_ceiling = "Enter an amount in pesos, digits only, or leave it blank.";
    }
  }
  return errors;
}

export function inputFrom(d: OpportunityDraft): OpportunityInput {
  const ceiling = d.funding_ceiling.replace(/,/g, "").trim();
  return {
    opportunity_type: d.opportunity_type as OpportunityType,
    title:            d.title.trim(),
    posting_office:   d.posting_office.trim(),
    audience:         d.audience.trim(),
    description:      d.description.trim(),
    funding_ceiling:  ceiling === "" ? null : ceiling,
    external_url:     d.external_url.trim(),
    due_date:         d.due_date,
    is_featured:      d.is_featured,
    tags:             d.tags.split(",").map((t) => t.trim()).filter(Boolean),
    source:           d.source,
  };
}

const DRAFT_FIELDS = new Set<string>(Object.keys(EMPTY_DRAFT));

/**
 * A DRF 400 body split into field errors and one form-level sentence.
 *
 * DRF sends `{field: ["message", ...]}`, plus `non_field_errors` or `detail`
 * for anything not tied to a field. A field the form does not show is folded
 * into the form-level sentence rather than dropped, so no rejection is silent.
 */
export function serverErrors(body: unknown): { fields: DraftErrors; form: string | null } {
  const fields: DraftErrors = {};
  const loose: string[] = [];
  if (body && typeof body === "object" && !Array.isArray(body)) {
    for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
      const message = Array.isArray(value) ? value.map(String).join(" ") : String(value);
      if (DRAFT_FIELDS.has(key)) fields[key as DraftField] = message;
      else loose.push(message);
    }
  }
  return { fields, form: loose.length > 0 ? loose.join(" ") : null };
}
