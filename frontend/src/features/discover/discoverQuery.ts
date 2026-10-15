import { IP_TYPE_LABELS } from "@/types/records";

import { EMPTY_FILTERS, HAS_IP, type DiscoverFilters, type DiscoverSort } from "./DiscoverFilterBar";
import { ALL_VALUE } from "./DiscoverFilterDropdown";

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
}

export const DEFAULT_QUERY: DiscoverQuery = { q: "", filters: EMPTY_FILTERS, sort: "newest" };

/** The URL keys Discover owns. Any other key (`publish`) is left alone. */
const KEYS = ["q", "type", "college", "classification", "year", "ip", "sort"] as const;

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
  };
}

/**
 * `params` with Discover's keys replaced by `query`, defaults omitted and in
 * a fixed order, so one query has one spelling. Other keys are kept.
 */
export function writeDiscoverQuery(params: URLSearchParams, query: DiscoverQuery): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of KEYS) next.delete(key);

  const { q, filters, sort } = query;
  if (q.trim()) next.set("q", q.trim());
  if (filters.recordType !== ALL_VALUE) next.set("type", filters.recordType);
  if (filters.colleges.length > 0) next.set("college", ids(filters.colleges.join(",")).join(","));
  if (filters.classifications.length > 0) {
    next.set("classification", ids(filters.classifications.join(",")).join(","));
  }
  if (filters.year !== ALL_VALUE) next.set("year", filters.year);
  if (filters.ip !== ALL_VALUE) next.set("ip", filters.ip);
  if (sort !== DEFAULT_QUERY.sort) next.set("sort", sort);
  return next;
}

/** One string per query: what every page fetch is fenced by. */
export function discoverQueryKey(query: DiscoverQuery): string {
  return writeDiscoverQuery(new URLSearchParams(), query).toString();
}

/** The list endpoint's params for `query`, before paging. */
export function listParams(query: DiscoverQuery): Record<string, unknown> {
  const { q, filters, sort } = query;
  const params: Record<string, unknown> = { ordering: ORDERING[sort] };

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
