import React from "react";
import { parseISO, isValid, format } from "date-fns";
import type { Author, RecordListItem } from "@/types/records";
import { IP_TYPE_LABELS, type IpType } from "@/types/records";

/* ────────────────────────────────────────────────────────────────────────────
 * Author formatting
 * ──────────────────────────────────────────────────────────────────────────*/

/**
 * Render an author list as a readable byline.
 * `RecordListItem.authors` is `Author[]`, but records imported from Excel can
 * arrive with bare strings, so both shapes are tolerated.
 */
export function formatAuthorList(
  authors: (Author | string)[] | undefined,
  max = 4,
): string {
  if (!authors || authors.length === 0) return "Institutional Author";

  const names = authors
    .map((a) => (typeof a === "string" ? a : a?.name))
    .filter((n): n is string => Boolean(n && n.trim()));

  if (names.length === 0) return "Institutional Author";
  if (names.length <= max) return names.join(", ");
  return `${names.slice(0, max).join(", ")} +${names.length - max} more`;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Search-term highlighting
 * ──────────────────────────────────────────────────────────────────────────*/

/** Escape a user-typed query so it can be embedded in a RegExp safely. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Wrap every case-insensitive occurrence of `query` inside `text` in a <mark>.
 * Returns the plain string when there is nothing to highlight so callers can
 * still render it directly.
 */
export function highlightMatch(
  text: string | null | undefined,
  query: string,
): React.ReactNode {
  const source = text ?? "";
  const needle = query.trim();
  if (!needle) return source;

  const parts = source.split(new RegExp(`(${escapeRegExp(needle)})`, "gi"));
  return React.createElement(
    React.Fragment,
    null,
    ...parts.map((part, i) =>
      part.toLowerCase() === needle.toLowerCase()
        ? React.createElement(
            "mark",
            {
              key: i,
              className: "bg-amber-100 text-slate-900 rounded-sm px-0.5 font-bold",
            },
            part,
          )
        : part,
    ),
  );
}

/* ────────────────────────────────────────────────────────────────────────────
 * Date / year parsing
 * ──────────────────────────────────────────────────────────────────────────*/

/** Best-effort publication year: the declared year, else the year it was indexed. */
export function recordYear(record: RecordListItem): number | null {
  if (record.year_accomplished) return record.year_accomplished;
  const created = parseISO(record.created_at);
  return isValid(created) ? created.getFullYear() : null;
}

export function recordYearLabel(record: RecordListItem): string {
  return recordYear(record)?.toString() ?? "—";
}

/** "Indexed Mar 4, 2026" — used in the card footer. */
export function indexedOnLabel(record: RecordListItem): string {
  const created = parseISO(record.created_at);
  return isValid(created) ? `Indexed ${format(created, "MMM d, yyyy")}` : "Recently indexed";
}

/**
 * Descending year options derived from the records actually loaded, so the
 * dropdown never offers a year with zero results. Falls back to the current
 * year when the feed is empty.
 */
export function buildYearOptions(records: RecordListItem[]): string[] {
  const years = new Set<number>();
  for (const record of records) {
    const year = recordYear(record);
    if (year) years.add(year);
  }
  if (years.size === 0) years.add(new Date().getFullYear());
  return [...years].sort((a, b) => b - a).map(String);
}

/* ────────────────────────────────────────────────────────────────────────────
 * Badges
 * ──────────────────────────────────────────────────────────────────────────*/

/**
 * Badges carry meaning through four fixed roles, so a card is scannable at a
 * glance: what field it belongs to, what kind of work it is, whether it is
 * protected, and what programmes it is flagged for.
 */
export type BadgeTone = "topic" | "type" | "ip" | "commercial" | "extension";

/** Which icon component the card should render, if any. */
export type BadgeIcon = "ip" | "commercial" | "extension";

export interface MetaBadge {
  label: string;
  icon?: BadgeIcon;
  tone: BadgeTone;
}

export const BADGE_TONE_CLASS: Record<BadgeTone, string> = {
  // Field of research — outlined, uppercase, the quietest but most frequent
  topic:      "border border-brand-200 text-brand bg-white uppercase tracking-wider text-[10px]",
  // Kind of work (Thesis / Project / Proposal) — solid dark, high contrast
  type:       "bg-slate-900 text-white",
  // Pill colour matches its icon so the two never disagree
  ip:         "bg-blue-50 text-blue-700 border border-blue-200",
  commercial: "bg-amber-50 text-amber-800 border border-amber-200",
  extension:  "bg-emerald-50 text-emerald-700 border border-emerald-200",
};

/** Human label for an IP type code, driven by the backend enum. */
export function ipTypeLabel(ipType: IpType): string {
  if (!ipType) return "IP Protected";
  return IP_TYPE_LABELS[ipType] ?? "IP Protected";
}

/**
 * Metadata badges for a card, in reading order. Derived only from fields the
 * list serializer actually returns — no invented citation or file counts.
 */
export function metaBadges(record: RecordListItem): MetaBadge[] {
  const badges: MetaBadge[] = [];

  if (record.classification_name) {
    badges.push({ label: record.classification_name, tone: "topic" });
  }

  if (record.record_type_name) {
    badges.push({ label: record.record_type_name, tone: "type" });
  }

  if (record.is_ip) {
    badges.push({ label: ipTypeLabel(record.ip_type), icon: "ip", tone: "ip" });
  }

  if (record.for_commercialization) {
    badges.push({ label: "Commercialization", icon: "commercial", tone: "commercial" });
  }

  if (record.community_extension) {
    badges.push({ label: "Community Extension", icon: "extension", tone: "extension" });
  }

  return badges;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Per-browser starred papers and collections
 *
 * Owned by `lib/recordLibrary` and re-exported here so the Discover save
 * dropdown and My Library read and write exactly the same state. There is no
 * server-side bookmark endpoint — see that module for why.
 * ──────────────────────────────────────────────────────────────────────────*/

export {
  DEFAULT_COLLECTIONS,
  getStarredIds,
  isStarred,
  toggleStarred,
  getCollections,
  saveCollections,
  toggleRecordInCollection,
  addCollection,
} from "@/lib/recordLibrary";
export type { Collection } from "@/lib/recordLibrary";

/* ────────────────────────────────────────────────────────────────────────────
 * Citation building
 * ──────────────────────────────────────────────────────────────────────────*/

export type CitationStyle = "APA" | "MLA" | "BibTeX";

export const CITATION_STYLES: CitationStyle[] = ["APA", "MLA", "BibTeX"];

const INSTITUTION = "Cebu Institute of Technology – University";

function authorNames(record: RecordListItem): string[] {
  return (record.authors ?? [])
    .map((a) => (typeof a === "string" ? a : a?.name))
    .filter((n): n is string => Boolean(n && n.trim()));
}

/** "Dela Cruz, J." from "Juan Dela Cruz" — last token is treated as the surname. */
function toApaName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0];
  const surname = parts[parts.length - 1];
  const initials = parts
    .slice(0, -1)
    .map((p) => `${p[0].toUpperCase()}.`)
    .join(" ");
  return `${surname}, ${initials}`;
}

function bibtexKey(record: RecordListItem): string {
  const first = authorNames(record)[0] ?? "citu";
  const surname = first.trim().split(/\s+/).pop() ?? "citu";
  return `${surname.toLowerCase().replace(/[^a-z]/g, "")}${recordYear(record) ?? ""}`;
}

/** Build a citation string for a record in the requested style. */
export function buildCitation(record: RecordListItem, style: CitationStyle): string {
  const names = authorNames(record);
  const year = recordYear(record) ?? "n.d.";
  const title = record.title.trim();

  if (style === "APA") {
    const authors =
      names.length === 0
        ? INSTITUTION
        : names.length === 1
          ? toApaName(names[0])
          : `${names.slice(0, -1).map(toApaName).join(", ")}, & ${toApaName(names[names.length - 1])}`;
    return `${authors} (${year}). ${title}. ${INSTITUTION}.`;
  }

  if (style === "MLA") {
    const authors =
      names.length === 0
        ? INSTITUTION
        : names.length === 1
          ? names[0]
          : `${names[0]}, et al.`;
    return `${authors}. "${title}." ${INSTITUTION}, ${year}.`;
  }

  return [
    `@misc{${bibtexKey(record)},`,
    `  title        = {${title}},`,
    `  author       = {${names.length > 0 ? names.join(" and ") : INSTITUTION}},`,
    `  year         = {${year}},`,
    `  institution  = {${INSTITUTION}},`,
    `  note         = {IRIS record ${record.id}}`,
    `}`,
  ].join("\n");
}
