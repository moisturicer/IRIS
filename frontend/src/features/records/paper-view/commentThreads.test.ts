import { describe, expect, it } from "vitest";

import type { PublicComment } from "@/types/records";

import { buildThreads, initials, relativeTime, truncateBody } from "./commentThreads";

function comment(id: number, overrides: Partial<PublicComment> = {}): PublicComment {
  return {
    id,
    author_name: `Reader ${id}`,
    body: `Body ${id}`,
    created_at: `2026-11-0${Math.min(id, 9)}T09:00:00Z`,
    edited_at: null,
    is_author: false,
    can_edit: false,
    can_report: true,
    reply_to: null,
    deletion_kind: null,
    ...overrides,
  };
}

const ids = (list: PublicComment[]) => list.map((item) => item.id);

describe("buildThreads", () => {
  it("groups replies under their top-level comment, oldest first", () => {
    const threads = buildThreads([
      comment(3, { reply_to: 1 }),
      comment(1),
      comment(2),
      comment(4, { reply_to: 2 }),
    ]);

    expect(threads.map((thread) => thread.root.id)).toEqual([1, 2]);
    expect(ids(threads[0].replies)).toEqual([3]);
    expect(ids(threads[1].replies)).toEqual([4]);
  });

  it("keeps a reply to a reply in the same thread", () => {
    const [thread] = buildThreads([comment(1), comment(2, { reply_to: 1 }), comment(3, { reply_to: 2 }), comment(4, { reply_to: 3 })]);

    expect(ids(thread.replies)).toEqual([2, 3, 4]);
  });

  it("orders top-level comments oldest first by default and newest first on request", () => {
    const list = [comment(2), comment(1), comment(3)];

    expect(buildThreads(list).map((thread) => thread.root.id)).toEqual([1, 2, 3]);
    expect(buildThreads(list, "newest").map((thread) => thread.root.id)).toEqual([3, 2, 1]);
  });

  it("keeps replies oldest first whichever way the top level is ordered", () => {
    const [thread] = buildThreads([comment(1), comment(3, { reply_to: 1 }), comment(2, { reply_to: 1 })], "newest");

    expect(ids(thread.replies)).toEqual([2, 3]);
  });

  it("keeps a deleted comment that has a live reply, so the thread keeps its context", () => {
    const [thread] = buildThreads([comment(1, { deletion_kind: "writer", body: null, author_name: null }), comment(2, { reply_to: 1 })]);

    expect(thread.root.id).toBe(1);
    expect(thread.root.deletion_kind).toBe("writer");
    expect(ids(thread.replies)).toEqual([2]);
  });

  it("keeps a deleted reply that has a live reply under it", () => {
    const [thread] = buildThreads([comment(1), comment(2, { reply_to: 1, deletion_kind: "moderator", body: null, author_name: null }), comment(3, { reply_to: 2 })]);

    expect(ids(thread.replies)).toEqual([2, 3]);
  });

  it("drops a deleted comment with nothing live beneath it", () => {
    const threads = buildThreads([
      comment(1, { deletion_kind: "writer", body: null, author_name: null }),
      comment(2),
      comment(3, { reply_to: 2, deletion_kind: "moderator", body: null, author_name: null }),
    ]);

    expect(threads.map((thread) => thread.root.id)).toEqual([2]);
    expect(threads[0].replies).toEqual([]);
  });

  it("drops a chain of deleted comments with no live comment at the end of it", () => {
    const threads = buildThreads([
      comment(1, { deletion_kind: "writer", body: null, author_name: null }),
      comment(2, { reply_to: 1, deletion_kind: "writer", body: null, author_name: null }),
    ]);

    expect(threads).toEqual([]);
  });

  it("shows a reply whose parent is missing as a top-level comment rather than losing it", () => {
    const threads = buildThreads([comment(2, { reply_to: 99 })]);

    expect(threads.map((thread) => thread.root.id)).toEqual([2]);
  });

  it("does not loop on a reply chain that points back at itself", () => {
    const threads = buildThreads([comment(1, { reply_to: 2 }), comment(2, { reply_to: 1 })]);

    expect(threads.flatMap((thread) => [thread.root.id, ...ids(thread.replies)]).sort()).toEqual([1, 2]);
  });
});

describe("relativeTime", () => {
  const now = Date.parse("2026-11-12T10:30:00+08:00");

  it("says just now for under a minute", () => {
    expect(relativeTime("2026-11-12T10:29:30+08:00", now)).toEqual({ short: "Just now", long: "just now" });
  });

  it("counts minutes, hours and days in a short form with a spoken one", () => {
    expect(relativeTime("2026-11-12T09:54:00+08:00", now)).toEqual({ short: "36m", long: "36 minutes ago" });
    expect(relativeTime("2026-11-11T23:01:00+08:00", now)).toEqual({ short: "11h", long: "11 hours ago" });
    expect(relativeTime("2026-11-11T09:30:00+08:00", now)).toEqual({ short: "1d", long: "1 day ago" });
    expect(relativeTime("2026-11-07T10:30:00+08:00", now)).toEqual({ short: "5d", long: "5 days ago" });
  });

  it("uses a date from a week on, and never a negative age", () => {
    expect(relativeTime("2026-10-01T10:30:00+08:00", now).short).toMatch(/Oct\s+1/);
    expect(relativeTime("2026-11-12T10:31:00+08:00", now).short).toBe("Just now");
  });

  it("returns an unreadable timestamp as it came", () => {
    expect(relativeTime("not a date", now)).toEqual({ short: "not a date", long: "not a date" });
  });
});

describe("initials", () => {
  it("takes the first and last name's first letters", () => {
    expect(initials("Lee Jasmin Adolfo")).toBe("LA");
    expect(initials("Ana")).toBe("A");
    expect(initials("Dr. Santos")).toBe("DS");
  });

  it("shows a question mark for a comment with no author", () => {
    expect(initials(null)).toBe("?");
    expect(initials("  ")).toBe("?");
  });
});

describe("truncateBody", () => {
  it("leaves a short body whole", () => {
    expect(truncateBody("Short", 300)).toEqual({ text: "Short", truncated: false });
  });

  it("cuts a long body at a word boundary and says it was cut", () => {
    const body = `${"word ".repeat(80)}end`;
    const cut = truncateBody(body, 300);

    expect(cut.truncated).toBe(true);
    expect(cut.text.length).toBeLessThanOrEqual(301);
    expect(cut.text.endsWith("…")).toBe(true);
    expect(cut.text).not.toMatch(/wor…$/);
  });
});
