import { IP_TYPE_LABELS } from "@/types/records";

import {
  EMPTY_FILTERS, HAS_IP, SORT_OPTIONS, endsBeforeItStarts, type DiscoverFilters, type DiscoverSort,
} from "./DiscoverFilterBar";
import { ALL_VALUE } from "./DiscoverFilterDropdown";
import { searchTerms } from "./searchTerms";

/**
 * Discover's query -- search text, filters and sort -- in one parsed shape
 * that round-trips through the URL (IR-560). The URL is the only copy, so Back,
 * reload and a copied link all restore the same catalogue view.
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

/**
 * How Discover is ordered, as the reader chooses it: one control for what were
 * the For you / Latest / Trending tabs and Latest's own Sort (IR-1187). It is
 * derived from `feed` and `sort`, so the URL keeps its spelling and a link to
 * an old tab lands on the matching order. Best is the For you feed (ADR-062).
 */
export type DiscoverOrder = "best" | "newest" | "viewed" | "trending";

/** Newest and Most viewed keep the catalogue sort's own labels, which a saved
 *  feed's "Sorted by" line also reads, so the two cannot drift apart. */
export const ORDER_OPTIONS: { value: DiscoverOrder; label: string }[] = [
  { value: "best", label: "Best" },
  ...SORT_OPTIONS.map((option) => ({ value: option.value as DiscoverSort, label: option.label })),
  { value: "trending", label: "Trending" },
];

export function orderOf(query: DiscoverQuery): DiscoverOrder {
  if (query.feed === "for_you") return "best";
  if (query.feed === "trending") return "trending";
  return query.sort;
}

/** `query` in `order`; its search and filters are left as they are. */
export function withOrder(query: DiscoverQuery, order: DiscoverOrder): DiscoverQuery {
  if (order === "best") return { ...query, feed: "for_you", sort: "newest" };
  if (order === "trending") return { ...query, feed: "trending", sort: "newest" };
  return { ...query, feed: "latest", sort: order };
}

/** The URL keys Discover owns. Any other key (`publish`) is left alone. */
const KEYS = ["q", "type", "college", "classification", "year_from", "year_to", "ip", "sort", "feed"] as const;
/** Keys Discover once wrote and no longer reads; removed, never carried along:
 *  the single `year` (IR-947) and an open saved feed's id, `myfeed` (IR-1189). */
const RETIRED_KEYS = ["year", "myfeed"] as const;

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

/** A from–to year range, either end open, the right way round (IR-947). */
function yearRange(params: URLSearchParams): { yearFrom: string; yearTo: string } {
  const from = single(params.get("year_from"), (v) => YEAR.test(v));
  const to = single(params.get("year_to"), (v) => YEAR.test(v));
  if (endsBeforeItStarts(from, to)) return { yearFrom: to, yearTo: from };
  return { yearFrom: from, yearTo: to };
}

export function parseDiscoverQuery(params: URLSearchParams): DiscoverQuery {
  const feed = params.get("feed") === "for_you" || params.get("feed") === "trending"
    ? params.get("feed") as DiscoverQuery["feed"]
    : "latest";
  // Only Latest has a sort of its own; a tab ignored it, so a sort beside a
  // tab is dropped and the order has one spelling (IR-1187).
  const sort = feed === "latest" && params.get("sort") === "viewed" ? "viewed" : "newest";
  return {
    q: (params.get("q") ?? "").trim(),
    filters: {
      recordType: single(params.get("type"), (v) => ID.test(v)),
      colleges: ids(params.get("college")),
      classifications: ids(params.get("classification")),
      ...yearRange(params),
      ip: single(params.get("ip"), isIp),
    },
    sort,
    feed,
  };
}

/**
 * `params` with Discover's keys replaced by `query`, defaults omitted and in
 * a fixed order, so one query has one spelling. Other keys are kept.
 */
export function writeDiscoverQuery(params: URLSearchParams, query: DiscoverQuery): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of [...KEYS, ...RETIRED_KEYS]) next.delete(key);

  const { q, filters, sort, feed } = query;
  if (q.trim()) next.set("q", q.trim());
  if (filters.recordType !== ALL_VALUE) next.set("type", filters.recordType);
  if (filters.colleges.length > 0) next.set("college", ids(filters.colleges.join(",")).join(","));
  if (filters.classifications.length > 0) {
    next.set("classification", ids(filters.classifications.join(",")).join(","));
  }
  if (filters.yearFrom !== ALL_VALUE) next.set("year_from", filters.yearFrom);
  if (filters.yearTo !== ALL_VALUE) next.set("year_to", filters.yearTo);
  if (filters.ip !== ALL_VALUE) next.set("ip", filters.ip);
  if (sort !== DEFAULT_QUERY.sort) next.set("sort", sort);
  if (feed !== DEFAULT_QUERY.feed) next.set("feed", feed);
  return next;
}

/** One string per query: what every page fetch is fenced by. */
export function discoverQueryKey(query: DiscoverQuery): string {
  return writeDiscoverQuery(new URLSearchParams(), query).toString();
}

/** The list endpoint's params for `query`, before paging. */
export function listParams(query: DiscoverQuery): Record<string, unknown> {
  const { q, filters, sort, feed } = query;
  // Trending is the server's own ordering: views gained in the last 30 days,
  // then all-time views, then newest (IR-369).
  const params: Record<string, unknown> = { ordering: feed === "trending" ? "trending" : ORDERING[sort] };

  // By word: the sentence's content words, not the phrase (IR-1095).
  if (q) params.search = searchTerms(q).join(" ");
  if (filters.recordType !== ALL_VALUE) params.record_type = filters.recordType;
  if (filters.colleges.length > 0) params.college = filters.colleges.join(",");
  if (filters.classifications.length > 0) params.classification = filters.classifications.join(",");
  if (filters.yearFrom !== ALL_VALUE) params.year_from = filters.yearFrom;
  if (filters.yearTo !== ALL_VALUE) params.year_to = filters.yearTo;
  if (filters.ip === HAS_IP) params.is_ip = true;
  else if (filters.ip !== ALL_VALUE) params.ip_type = filters.ip;

  return params;
}
