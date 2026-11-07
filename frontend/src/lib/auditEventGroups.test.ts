import { describe, expect, it } from "vitest";
import { AUDIT_EVENT_GROUPS } from "@/types/audit";
import { groupAuditEventTypes, OTHER_GROUP } from "./auditEventGroups";

// The shape GET /audit/event-types/ returns (IR-913): the server's own labels.
const option = (type: string, label: string) => ({ type, label });

describe("groupAuditEventTypes", () => {
  it("puts each known type under its group, with the server's label", () => {
    const groups = groupAuditEventTypes([
      option("LOGIN", "Login (server wording)"),
      option("SUBMITTED", "Submitted"),
    ]);

    expect(groups).toEqual([
      { group: "Account", types: [option("LOGIN", "Login (server wording)")] },
      { group: "Workflow", types: [option("SUBMITTED", "Submitted")] },
    ]);
  });

  it("keeps the groups in the frontend's order, whatever order the server lists them in", () => {
    const groups = groupAuditEventTypes([option("SUBMITTED", "Submitted"), option("LOGIN", "Login")]);

    expect(groups.map((g) => g.group)).toEqual(["Account", "Workflow"]);
  });

  it("shows a type the frontend has never heard of under Other, last, so it can never be missing", () => {
    const groups = groupAuditEventTypes([
      option("A_BRAND_NEW_EVENT", "A Brand New Event"),
      option("LOGIN", "Login"),
    ]);

    expect(groups.map((g) => g.group)).toEqual(["Account", OTHER_GROUP]);
    expect(groups[1].types).toEqual([option("A_BRAND_NEW_EVENT", "A Brand New Event")]);
  });

  it("leaves out a group that has nothing in it, including Other", () => {
    const groups = groupAuditEventTypes([option("LOGIN", "Login")]);

    expect(groups.map((g) => g.group)).toEqual(["Account"]);
  });

  it("does not list a type the frontend still groups but the server no longer has", () => {
    const stillGrouped = Object.keys(AUDIT_EVENT_GROUPS.Account);
    expect(stillGrouped).toContain("PIN_GENERATED");

    const groups = groupAuditEventTypes([option("LOGIN", "Login")]);

    const listed = groups.flatMap((g) => g.types.map((t) => t.type));
    expect(listed).toEqual(["LOGIN"]);
  });

  it("returns nothing for an empty list", () => {
    expect(groupAuditEventTypes([])).toEqual([]);
  });
});
