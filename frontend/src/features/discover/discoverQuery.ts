import type { FeedQuery, FeedStale } from "@/api/library";
import { IP_TYPE_LABELS } from "@/types/records";

import { EMPTY_FILTERS, HAS_IP, SORT_OPTIONS, type DiscoverFilters, type DiscoverSort } from "./DiscoverFilterBar";
import { ALL_VALUE, type FilterOption } from "./DiscoverFilterDropdown";

/**
 * Discover's query -- search text, filters and sort -- in one parsed shape
 * that round-trips through the URL (IR-560). The URL is the only copy, so Back,
 * reload and a copied link all restore the same catalogue view, and IR-557's
 * saved feeds can store exactly this.
 *
 * Anything the parser does not recognise falls back to that field's default
 * rather than reaching the API: a hand-edited `?sort=bogus` means Newest, and
 * `?college=4,x` means college 4.
 */
export interface DiscoverQuery {
  q: string;
  filters: DiscoverFilters;
  sort: DiscoverSort;
  feed: "for_you" | "latest" | "trending";
}

export const DEFAULT_QUERY: DiscoverQuery = { q: "", filters: EMPTY_FILTERS, sort: "newest", feed: "latest" };

/** The URL keys Discover owns. Any other key (`publish`) is left alone. */
const KEYS = ["q", "type", "college", "classification", "year", "ip", "sort", "feed"] as const;

const ORDERING: Record<DiscoverSort, string> = {
  newest: "-created_at",
  viewed: "-access_count",
};

const ID = /^\d+$/;
const YEAR = /^\d{4}$/;

function single(value: string | null, valid: (v: string) => boolean): string {
  return value !== null && valid(value) ? value : ALL_VALUE;
}

function ids(value: string | null): string[] {
  if (!value) return [];
  const kept = value.split(",").filter((part) => ID.test(part));
  return [...new Set(kept)].sort((a, b) => Number(a) - Number(b));
}

function isIp(value: string): boolean {
  return value === HAS_IP || Object.prototype.hasOwnProperty.call(IP_TYPE_LABELS, value);
}

export function parseDiscoverQuery(params: URLSearchParams): DiscoverQuery {
  const sort = params.get("sort");
  return {
    q: (params.get("q") ?? "").trim(),
    filters: {
      recordType: single(params.get("type"), (v) => ID.test(v)),
      colleges: ids(params.get("college")),
      classifications: ids(params.get("classification")),
      year: single(params.get("year"), (v) => YEAR.test(v)),
      ip: single(params.get("ip"), isIp),
    },
    sort: sort === "viewed" ? "viewed" : "newest",
    feed: params.get("feed") === "for_you" || params.get("feed") === "trending"
      ? params.get("feed") as DiscoverQuery["feed"]
      : "latest",
  };
}

/**
 * `params` with Discover's keys replaced by `query`, defaults omitted and in
 * a fixed order, so one query has one spelling. Other keys are kept.
 */
export function writeDiscoverQuery(params: URLSearchParams, query: DiscoverQuery): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of KEYS) next.delete(key);

  const { q, filters, sort, feed } = query;
  if (q.trim()) next.set("q", q.trim());
  if (filters.recordType !== ALL_VALUE) next.set("type", filters.recordType);
  if (filters.colleges.length > 0) next.set("college", ids(filters.colleges.join(",")).join(","));
  if (filters.classifications.length > 0) {
    next.set("classification", ids(filters.classifications.join(",")).join(","));
  }
  if (filters.year !== ALL_VALUE) next.set("year", filters.year);
  if (filters.ip !== ALL_VALUE) next.set("ip", filters.ip);
  if (sort !== DEFAULT_QUERY.sort) next.set("sort", sort);
  if (feed !== DEFAULT_QUERY.feed) next.set("feed", feed);
  return next;
}

/** One string per query: what every page fetch is fenced by. */
export function discoverQueryKey(query: DiscoverQuery): string {
  return writeDiscoverQuery(new URLSearchParams(), query).toString();
}

/* ── Saved feeds (IR-577) ────────────────────────────────────────────────
   A saved feed is this same query under a name, so nothing below is a second
   filter representation: it is the URL spelling, with the tab left out. */

/**
 * `query` as a saved feed stores it: Discover's URL keys, ids sorted, the
 * default sort omitted. The tab is not stored (it is not a criterion), and
 * Trending, which is the catalogue by views, is saved as that sort.
 */
export function feedQueryOf(query: DiscoverQuery): FeedQuery {
  const sort = query.feed === "trending" ? "viewed" : query.sort;
  return Object.fromEntries(writeDiscoverQuery(new URLSearchParams(), { ...query, sort, feed: "latest" })) as FeedQuery;
}

function without(list: string, gone: number[]): string {
  return list.split(",").filter((id) => !gone.includes(Number(id))).join(",");
}

/**
 * The URL that opens `stored`. A taxonomy value the server reports stale is
 * left out, so it is never queried: the page holds the results back until the
 * reader corrects the feed, and nothing widens by itself.
 */
export function feedSearchParams(stored: FeedQuery, stale: FeedStale): URLSearchParams {
  const raw = new URLSearchParams();
  for (const [key, value] of Object.entries(stored)) {
    if (!value) continue;
    if (key === "type") {
      if (!stale.type?.includes(Number(value))) raw.set(key, value);
    } else if (key === "college" || key === "classification") {
      const kept = without(value, stale[key] ?? []);
      if (kept) raw.set(key, kept);
    } else {
      raw.set(key, value);
    }
  }
  return writeDiscoverQuery(new URLSearchParams(), parseDiscoverQuery(raw));
}

const entriesOf = (stored: FeedQuery) => JSON.stringify(Object.entries(stored).sort(([a], [b]) => (a < b ? -1 : 1)));

/** Are the filters on screen exactly the feed's own? */
export function sameFeedQuery(stored: FeedQuery, query: DiscoverQuery): boolean {
  const normal = feedQueryOf(parseDiscoverQuery(new URLSearchParams(stored as Record<string, string>)));
  return entriesOf(normal) === entriesOf(feedQueryOf(query));
}

export interface FeedLabelOptions {
  classifications: FilterOption[];
  colleges:        FilterOption[];
  recordTypes:     FilterOption[];
}

const UNAVAILABLE = "no longer available";

function labelled(list: string, options: FilterOption[]): string {
  return list
    .split(",")
    .map((id) => options.find((o) => o.value === id)?.label ?? (options.length ? UNAVAILABLE : id))
    .join(", ");
}

/** A feed's criteria in words, for the save form and the feed's own header. */
export function feedCriteria(stored: FeedQuery, options: FeedLabelOptions): string[] {
  const lines: string[] = [];
  if (stored.q) lines.push(`Keywords: ${stored.q}`);
  if (stored.classification) lines.push(`Areas: ${labelled(stored.classification, options.classifications)}`);
  if (stored.college) lines.push(`Colleges: ${labelled(stored.college, options.colleges)}`);
  if (stored.type) lines.push(`Type: ${labelled(stored.type, options.recordTypes)}`);
  if (stored.year) lines.push(`Year: ${stored.year}`);
  if (stored.ip) {
    lines.push(`Intellectual property: ${stored.ip === HAS_IP ? "any" : IP_TYPE_LABELS[stored.ip as keyof typeof IP_TYPE_LABELS] ?? stored.ip}`);
  }
  if (stored.sort) lines.push(`Sorted by: ${SORT_OPTIONS.find((o) => o.value === stored.sort)?.label ?? stored.sort}`);
  return lines;
}

/** The list endpoint's params for `query`, before paging. */
export function listParams(query: DiscoverQuery): Record<string, unknown> {
  const { q, filters, sort, feed } = query;
  const params: Record<string, unknown> = { ordering: feed === "trending" ? "-access_count" : ORDERING[sort] };

  if (q) params.search = q;
  if (filters.recordType !== ALL_VALUE) params.record_type = filters.recordType;
  if (filters.colleges.length > 0) params.college = filters.colleges.join(",");
  if (filters.classifications.length > 0) params.classification = filters.classifications.join(",");
  if (filters.year !== ALL_VALUE) {
    params.year_from = filters.year;
    params.year_to = filters.year;
  }
  if (filters.ip === HAS_IP) params.is_ip = true;
  else if (filters.ip !== ALL_VALUE) params.ip_type = filters.ip;

  return params;
}
