import { TONES, type Tone } from "@/components/ui/statusTones";
import type { Opportunity, OpportunityInput, OpportunityType } from "@/types/opportunities";

/** Every type, in the order the board and the form list them, with its glyph. */
export const OPPORTUNITY_TYPES: { id: OpportunityType; label: string; icon: string }[] = [
  { id: "conference",   label: "Conference",   icon: "fa-microphone-lines"      },
  { id: "congress",     label: "Congress",     icon: "fa-people-group"          },
  { id: "symposium",    label: "Symposium",    icon: "fa-comments"              },
  { id: "workshop",     label: "Workshop",     icon: "fa-screwdriver-wrench"    },
  { id: "journal",      label: "Journal",      icon: "fa-book-open"             },
  { id: "book_chapter", label: "Book chapter", icon: "fa-book"                  },
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
  return [o.title, o.location, o.description, o.type_display, ...(o.area_names ?? [])]
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

/** The form's own state: every field a string, a flag or the chosen Area ids. */
export interface OpportunityDraft {
  opportunity_type: OpportunityType | "";
  title:            string;
  description:      string;
  due_date:         string;
  location:         string;
  areas:            number[];
  external_url:     string;
  start_date:       string;
  end_date:         string;
  registration_fee: string;
  is_featured:      boolean;
}

export const EMPTY_DRAFT: OpportunityDraft = {
  opportunity_type: "",
  title:            "",
  description:      "",
  due_date:         "",
  location:         "",
  areas:            [],
  external_url:     "",
  start_date:       "",
  end_date:         "",
  registration_fee: "",
  is_featured:      false,
};

export function draftFrom(o: Opportunity): OpportunityDraft {
  return {
    opportunity_type: o.opportunity_type,
    title:            o.title,
    description:      o.description,
    due_date:         o.due_date,
    location:         o.location,
    areas:            o.areas,
    external_url:     o.external_url,
    start_date:       o.start_date ?? "",
    end_date:         o.end_date ?? "",
    registration_fee: o.registration_fee,
    is_featured:      o.is_featured,
  };
}

export type DraftField = keyof OpportunityDraft;
export type DraftErrors = Partial<Record<DraftField, string>>;

/**
 * What the browser can say before the server does: that a required field is
 * empty. It checks no date (ADR-050 decision 5) and leaves the link's form to
 * the server, whose rejection comes back through `serverErrors` on its field.
 */
export function checkDraft(d: OpportunityDraft): DraftErrors {
  const errors: DraftErrors = {};
  if (!d.opportunity_type) errors.opportunity_type = "Choose what kind of call this is.";
  if (!d.title.trim()) errors.title = "Give the call a title.";
  if (!d.description.trim()) errors.description = "Say what the call is about.";
  if (!d.due_date) errors.due_date = "Set the paper deadline.";
  if (!d.location.trim()) errors.location = "Say where it takes place, or Online.";
  if (d.areas.length === 0) errors.areas = "Choose at least one Area.";
  if (!d.external_url.trim()) errors.external_url = "Give the link to the full call.";
  return errors;
}

export function inputFrom(d: OpportunityDraft): OpportunityInput {
  return {
    opportunity_type: d.opportunity_type as OpportunityType,
    title:            d.title.trim(),
    description:      d.description.trim(),
    due_date:         d.due_date,
    location:         d.location.trim(),
    areas:            d.areas,
    external_url:     d.external_url.trim(),
    start_date:       d.start_date || null,
    end_date:         d.end_date || null,
    registration_fee: d.registration_fee.trim(),
    is_featured:      d.is_featured,
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
