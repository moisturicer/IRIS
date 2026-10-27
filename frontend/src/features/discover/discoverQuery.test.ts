/**
 * Discover's one parsed query (IR-560): it round-trips through the URL, and an
 * invalid value falls back to that field's default instead of reaching the API.
 */
import { describe, expect, it } from "vitest";

import { DEFAULT_QUERY, parseDiscoverQuery, writeDiscoverQuery } from "./discoverQuery";

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
