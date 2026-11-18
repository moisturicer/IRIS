/**
 * Discover's one parsed query (IR-560): it round-trips through the URL, and an
 * invalid value falls back to that field's default instead of reaching the API.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_QUERY, ORDER_OPTIONS, listParams, orderOf, parseDiscoverQuery, withOrder, writeDiscoverQuery,
} from "./discoverQuery";

const parse = (search: string) => parseDiscoverQuery(new URLSearchParams(search));

describe("parseDiscoverQuery", () => {
  it("reads every field", () => {
    expect(parse("q=rain&type=2&college=5,4&classification=7&year_from=2018&year_to=2021&ip=patent&sort=viewed")).toEqual({
      q: "rain",
      filters: {
        recordType: "2",
        colleges: ["4", "5"],
        classifications: ["7"],
        yearFrom: "2018",
        yearTo: "2021",
        ip: "patent",
      },
      sort: "viewed",
      feed: "latest",
    });
  });

  it("is the default for an empty URL", () => {
    expect(parse("")).toEqual(DEFAULT_QUERY);
  });

  it.each([
    ["sort=bogus", "an unknown sort"],
    ["type=thesis", "a non-numeric record type"],
    ["year_from=19", "a malformed from year"],
    ["year_to=20x1", "a malformed to year"],
    // IR-947: one year is From and To; the old single key is not read.
    ["year=2019", "the retired single-year key"],
    ["ip=everything", "an unknown IP value"],
    ["college=x,", "college ids that are not ids"],
  ])("falls back to the default for %s (%s)", (search) => {
    expect(parse(search)).toEqual(DEFAULT_QUERY);
  });

  it("reads an open-ended range from either end (IR-947)", () => {
    expect(parse("year_from=2018").filters).toMatchObject({ yearFrom: "2018", yearTo: "all" });
    expect(parse("year_to=2021").filters).toMatchObject({ yearFrom: "all", yearTo: "2021" });
  });

  it("puts a range written backwards the right way round", () => {
    expect(parse("year_from=2021&year_to=2018").filters).toMatchObject({ yearFrom: "2018", yearTo: "2021" });
  });

  it("keeps the valid ids in a list and drops the rest", () => {
    expect(parse("college=4,x,4,12").filters.colleges).toEqual(["4", "12"]);
  });

  it("accepts only the explicit feed modes", () => {
    expect(parse("feed=for_you").feed).toBe("for_you");
    expect(parse("feed=trending").feed).toBe("trending");
    expect(parse("feed=personalized")).toEqual(DEFAULT_QUERY);
  });
});

describe("one sort for Discover (IR-1187)", () => {
  it("offers Best, Newest, Most viewed and Trending, in that order", () => {
    expect(ORDER_OPTIONS.map((o) => o.label)).toEqual(["Best", "Newest", "Most viewed", "Trending"]);
  });

  it.each([
    ["", "newest"],
    ["sort=viewed", "viewed"],
    ["feed=latest", "newest"],
    ["feed=for_you", "best"],
    ["feed=trending", "trending"],
  ])("reads an old link %s as %s", (search, order) => {
    expect(orderOf(parse(search))).toBe(order);
  });

  it("lands an old tab link carrying a sort on the tab, the order it showed", () => {
    // The tab ignored the sort, so the link showed the tab's own order.
    expect(orderOf(parse("feed=trending&sort=viewed"))).toBe("trending");
    expect(orderOf(parse("feed=for_you&sort=viewed"))).toBe("best");
    expect(writeDiscoverQuery(new URLSearchParams(), parse("feed=trending&sort=viewed")).toString()).toBe("feed=trending");
  });

  it.each([
    ["best", { feed: "for_you", sort: "newest" }, { ordering: "-created_at" }],
    ["newest", { feed: "latest", sort: "newest" }, { ordering: "-created_at" }],
    ["viewed", { feed: "latest", sort: "viewed" }, { ordering: "-access_count" }],
    ["trending", { feed: "trending", sort: "newest" }, { ordering: "trending" }],
  ] as const)("asks for %s exactly as its tab or sort did", (order, shape, params) => {
    const query = withOrder(parse("sort=viewed&type=2"), order);
    expect(query).toMatchObject({ ...shape, filters: { recordType: "2" } });
    expect(listParams(query)).toMatchObject(params);
    expect(orderOf(parseDiscoverQuery(writeDiscoverQuery(new URLSearchParams(), query)))).toBe(order);
  });
});

describe("writeDiscoverQuery", () => {
  it("round-trips: what it writes parses back to the same query", () => {
    const query = parse("q=rain&type=2&college=4,5&year_from=2019&year_to=2019&ip=has_ip&sort=viewed");
    expect(parseDiscoverQuery(writeDiscoverQuery(new URLSearchParams(), query))).toEqual(query);
  });

  it("omits defaults, so the default query is an empty URL", () => {
    expect(writeDiscoverQuery(new URLSearchParams(), DEFAULT_QUERY).toString()).toBe("");
  });

  it("removes the retired single-year key rather than carrying it along (IR-947)", () => {
    expect(writeDiscoverQuery(new URLSearchParams("year=2026&q=rain"), parse("q=rain")).toString()).toBe("q=rain");
  });

  it("removes an old saved-feed id, keeping that link's filters (IR-1189)", () => {
    const old = new URLSearchParams("q=flood&classification=7&myfeed=5");
    expect(writeDiscoverQuery(old, parseDiscoverQuery(old)).toString()).toBe("q=flood&classification=7");
  });

    it("leaves keys it does not own, such as the Publish dialog's", () => {
    const written = writeDiscoverQuery(new URLSearchParams("publish=new&sort=bogus"), DEFAULT_QUERY);
    expect(written.toString()).toBe("publish=new");
  });
});

describe("a year range in the list request (IR-947)", () => {
  it("asks the list endpoint for each end the reader set, and only those", () => {
    const at = (search: string) => listParams(parse(search));

    expect(at("year_from=2018&year_to=2021")).toMatchObject({ year_from: "2018", year_to: "2021" });
    expect(at("year_from=2018")).toMatchObject({ year_from: "2018" });
    expect(at("year_from=2018")).not.toHaveProperty("year_to");
    expect(at("year_to=2021")).not.toHaveProperty("year_from");
    expect(at("")).not.toHaveProperty("year_from");
  });
});

describe("listParams: the search is by word (IR-1095)", () => {
  const search = (q: string) => listParams({ ...DEFAULT_QUERY, q }).search;

  it("asks for the content words of a sentence, without its punctuation", () => {
    expect(search("Can weather data forecast dengue?")).toBe("weather data forecast dengue");
  });

  it("leaves a plain word search as it was typed", () => {
    expect(search("dengue forecasting")).toBe("dengue forecasting");
  });

  it("sends no search when nothing was typed", () => {
    expect(listParams(DEFAULT_QUERY)).not.toHaveProperty("search");
  });

  it("keeps the URL's own text: the reader's sentence is not rewritten", () => {
    const query = parse("q=Can+weather+data+forecast+dengue%3F");
    expect(query.q).toBe("Can weather data forecast dengue?");
  });
});
