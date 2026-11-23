import { describe, expect, it } from "vitest";

import { paramsForView, viewFromKey, viewFromParams, viewKey, type LibraryView } from "./libraryViews";

const read = (query: string, mayAuthor = true) => viewFromParams(new URLSearchParams(query), mayAuthor);

describe("My Library's address (IR-1311)", () => {
  it("keeps every value the tabs used, so old links open the same list", () => {
    expect(read("section=research")).toEqual({ kind: "research", filter: "all" });
    expect(read("section=saved")).toEqual({ kind: "saved" });
    expect(read("section=calls")).toEqual({ kind: "calls" });
    expect(read("section=downloads")).toEqual({ kind: "downloads" });
    // The Overview tab is gone: it lands on the default list.
    expect(read("section=overview")).toEqual({ kind: "research", filter: "all" });
    expect(read("section=overview", false)).toEqual({ kind: "saved" });
  });

  it("never opens a research list for a reader who cannot author", () => {
    for (const section of ["research", "waiting", "review", "drafts", "finished"]) {
      expect(read(`section=${section}`, false)).toEqual({ kind: "saved" });
    }
  });

  it("reads and writes every list, keeping Publish's parameter", () => {
    const views: LibraryView[] = [
      { kind: "research", filter: "waiting" }, { kind: "research", filter: "drafts" },
      { kind: "saved" }, { kind: "status", status: "reading" }, { kind: "folder", id: 3 },
      { kind: "history" }, { kind: "calls" }, { kind: "downloads" },
    ];
    for (const view of views) {
      const params = paramsForView(new URLSearchParams("publish=12"), view, true);
      expect(params.get("publish")).toBe("12");
      expect(viewFromParams(params, true)).toEqual(view);
      expect(viewFromKey(viewKey(view))).toEqual(view);
    }
  });

  it("writes no section for the default list, and drops a folder's id when leaving it", () => {
    const params = paramsForView(new URLSearchParams("section=folder&folder=3"), { kind: "research", filter: "all" }, true);
    expect(params.toString()).toBe("");
    expect(read("section=folder&folder=nope")).toEqual({ kind: "saved" });
  });
});
