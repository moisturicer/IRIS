/**
 * Discover's one parsed query (IR-560): it round-trips through the URL, and an
 * invalid value falls back to that field's default instead of reaching the API.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_QUERY, feedCriteria, feedQueryOf, feedSearchParams, parseDiscoverQuery, sameFeedQuery,
  writeDiscoverQuery,
} from "./discoverQuery";

const parse = (search: string) => parseDiscoverQuery(new URLSearchParams(search));

describe("parseDiscoverQuery", () => {
  it("reads every field", () => {
    expect(parse("q=rain&type=2&college=5,4&classification=7&year=2019&ip=patent&sort=viewed")).toEqual({
      q: "rain",
      filters: {
        recordType: "2",
        colleges: ["4", "5"],
        classifications: ["7"],
        year: "2019",
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
    ["year=19", "a malformed year"],
    ["ip=everything", "an unknown IP value"],
    ["college=x,", "college ids that are not ids"],
  ])("falls back to the default for %s (%s)", (search) => {
    expect(parse(search)).toEqual(DEFAULT_QUERY);
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

describe("writeDiscoverQuery", () => {
  it("round-trips: what it writes parses back to the same query", () => {
    const query = parse("q=rain&type=2&college=4,5&year=2019&ip=has_ip&sort=viewed");
    expect(parseDiscoverQuery(writeDiscoverQuery(new URLSearchParams(), query))).toEqual(query);
  });

  it("omits defaults, so the default query is an empty URL", () => {
    expect(writeDiscoverQuery(new URLSearchParams(), DEFAULT_QUERY).toString()).toBe("");
  });

  it("leaves keys it does not own, such as the Publish dialog's", () => {
    const written = writeDiscoverQuery(new URLSearchParams("publish=new&sort=bogus"), DEFAULT_QUERY);
    expect(written.toString()).toBe("publish=new");
  });
});

describe("saved feeds use Discover's own query (IR-577)", () => {
  it("stores a query in Discover's spelling, without the tab", () => {
    const query = parse("q=flood&classification=7,4&college=5&year=2018&ip=patent&type=2&sort=viewed&feed=for_you");

    expect(feedQueryOf(query)).toEqual({
      q: "flood", type: "2", college: "5", classification: "4,7", year: "2018", ip: "patent", sort: "viewed",
    });
  });

  it("saves Trending as most viewed and omits the default sort", () => {
    expect(feedQueryOf(parse("q=flood&feed=trending"))).toEqual({ q: "flood", sort: "viewed" });
    expect(feedQueryOf(parse("q=flood"))).toEqual({ q: "flood" });
  });

  it("opens a feed as the URL Discover would have written for it", () => {
    const params = feedSearchParams({ q: "flood", classification: "4,7", sort: "viewed" }, {});

    expect(params.toString()).toBe(writeDiscoverQuery(new URLSearchParams(), parse("q=flood&classification=4,7&sort=viewed")).toString());
    expect(params.get("feed")).toBeNull();
  });

  it("leaves a stale value out of the URL, so it is corrected rather than silently queried", () => {
    const stale = { classification: [7], college: [5] };

    const params = feedSearchParams({ q: "flood", classification: "4,7", college: "5" }, stale);

    expect(params.get("classification")).toBe("4");
    expect(params.has("college")).toBe(false);
    expect(params.get("q")).toBe("flood");
  });

  it("tells whether the filters on screen are the feed's own", () => {
    const stored = { q: "flood", classification: "4,7" };

    expect(sameFeedQuery(stored, parse("classification=7,4&q=flood"))).toBe(true);
    expect(sameFeedQuery(stored, parse("classification=4&q=flood"))).toBe(false);
    expect(sameFeedQuery(stored, parse("q=flood&classification=4,7&sort=viewed"))).toBe(false);
  });

  it("describes a feed in words, naming a value that no longer exists as unavailable", () => {
    const options = {
      classifications: [{ value: "4", label: "Civil Engineering" }],
      colleges: [{ value: "5", label: "College of Engineering" }],
      recordTypes: [{ value: "2", label: "Thesis" }],
    };

    expect(
      feedCriteria({ q: "flood", classification: "4,7", college: "5", type: "2", year: "2018", ip: "has_ip", sort: "viewed" }, options),
    ).toEqual([
      "Keywords: flood",
      "Areas: Civil Engineering, no longer available",
      "Colleges: College of Engineering",
      "Type: Thesis",
      "Year: 2018",
      "Intellectual property: any",
      "Sorted by: Most viewed",
    ]);
  });
});
