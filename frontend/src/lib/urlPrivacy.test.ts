import { describe, expect, it } from "vitest";

import { DEFAULT_QUERY, writeDiscoverQuery } from "@/features/discover/discoverQuery";
import { citationHref, type AnswerTurn } from "@/lib/citedPage";

import allowed from "../../scripts/query-keys.json";

/**
 * No personal data in an address (IR-918), the builders' half. The source-wide
 * scan of every query-string key is scripts/url-privacy.test.mjs; it and this
 * file share the list of keys a person has decided are safe.
 */
const ALLOWED_KEYS = Object.keys(allowed.keys);

describe("builders that take structured input", () => {
  it("a citation address carries ids and numbers only, never the question or the quote", () => {
    const answer = { conversationId: 7, turnId: 9 } as AnswerTurn;
    const href = citationHref({ record_id: 12, page: 4, marker: 2 }, { origin: "paper-chat", answer });
    const url = new URL(href, "https://iris.example.edu");
    expect(url.pathname).toBe("/records/12");
    expect([...url.searchParams].length).toBeGreaterThan(0);
    for (const [key, value] of url.searchParams) {
      expect(ALLOWED_KEYS, key).toContain(key);
      expect(value, key).toMatch(/^(\d+|paper|page)$/);
    }
  });

  it("a Discover address holds only the filters the reader set, under allowed keys", () => {
    const params = writeDiscoverQuery(new URLSearchParams(), {
      ...DEFAULT_QUERY,
      q: "solar drying",
      filters: { ...DEFAULT_QUERY.filters, recordType: "3", colleges: ["1", "2"], year: "2025" },
      sort: "viewed",
    });
    expect([...params.keys()].length).toBeGreaterThan(0);
    for (const key of params.keys()) expect(ALLOWED_KEYS, key).toContain(key);
  });
});
