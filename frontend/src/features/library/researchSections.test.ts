import { describe, expect, it } from "vitest";

import type { MyResearchItem } from "@/types/records";

import { groupResearch } from "./researchSections";

const item = (id: number, overrides: Partial<MyResearchItem>): MyResearchItem => ({
  id,
  title: `Record ${id}`,
  record_type_name: "Thesis / Research",
  authors: [],
  adviser_name: null,
  pipeline_status: "in_review",
  workflow_state: "in_review",
  workflow_state_label: "In review",
  holders: [],
  cleared_offices: [],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  ...overrides,
});

const adviser = { party: "adviser" as const, label: "Adviser" };
const itso = { party: "itso" as const, label: "ITSO" };
const rdco = { party: "rdco" as const, label: "RDCO Final" };

const ids = (sections: ReturnType<typeof groupResearch>) =>
  Object.fromEntries(sections.map((s) => [s.id, s.items.map((i) => i.id)]));

describe("groupResearch", () => {
  it("puts what waits on the owner first, whoever else holds it", () => {
    const sections = groupResearch([
      item(1, { holders: [itso] }),
      item(2, { workflow_state: "awaiting_resubmission", holders: [itso] }),
      item(3, { workflow_state: "awaiting_document", holders: [adviser] }),
    ]);

    expect(sections[0].id).toBe("waiting");
    expect(ids(sections)).toMatchObject({ waiting: [2, 3], offices: [1] });
  });

  it("groups review by the server's holders, the decider before the offices before the Adviser", () => {
    const sections = groupResearch([
      item(1, { holders: [adviser] }),
      item(2, { holders: [adviser, itso] }),
      item(3, { holders: [rdco] }),
      item(4, { holders: [] }),
    ]);

    expect(ids(sections)).toEqual({ adviser: [1], offices: [2], rdco: [3], review: [4] });
    expect(sections.map((s) => s.id)).toEqual(["adviser", "offices", "rdco", "review"]);
  });

  it("files drafts, finished, deletion and archived records by stored status", () => {
    const sections = groupResearch([
      item(1, { pipeline_status: "draft", workflow_state: "draft" }),
      item(2, { pipeline_status: "published", workflow_state: "published" }),
      item(3, { pipeline_status: "approved", workflow_state: "approved" }),
      item(4, { pipeline_status: "completed", workflow_state: "completed" }),
      item(5, { pipeline_status: "pending_delete", workflow_state: "pending_delete" }),
      item(6, { pipeline_status: "rejected", workflow_state: "rejected" }),
    ]);

    expect(ids(sections)).toEqual({ drafts: [1], finished: [2, 3, 4], deleting: [5], archived: [6] });
  });

  it("omits empty sections and keeps the server's order inside one", () => {
    const sections = groupResearch([item(9, { holders: [itso] }), item(4, { holders: [itso] })]);

    expect(sections).toHaveLength(1);
    expect(sections[0].items.map((i) => i.id)).toEqual([9, 4]);
  });
});
