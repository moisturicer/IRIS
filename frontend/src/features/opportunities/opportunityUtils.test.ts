import { describe, expect, it } from "vitest";

import { TONES } from "@/components/ui/statusTones";
import type { Opportunity } from "@/types/opportunities";

import {
  EMPTY_DRAFT,
  checkDraft,
  countdown,
  deadlineGroup,
  inputFrom,
  serverErrors,
} from "./opportunityUtils";

const at = (days_left: number, is_closed = days_left < 0) =>
  ({ days_left, is_closed }) as Opportunity;

describe("deadlineGroup", () => {
  it.each([
    [0, "week"], [7, "week"], [8, "month"], [30, "month"], [31, "later"], [-1, "closed"],
  ] as const)("puts a call %i days out in %s", (days, group) => {
    expect(deadlineGroup(at(days))).toBe(group);
  });
});

describe("countdown", () => {
  it("says it in words and uses only the four tones", () => {
    expect(countdown(at(0))).toMatchObject({ label: "Due today", tone: "attention", className: TONES.attention });
    expect(countdown(at(1))).toMatchObject({ label: "1 day left", tone: "attention" });
    expect(countdown(at(7))).toMatchObject({ label: "7 days left", tone: "attention" });
    expect(countdown(at(21))).toMatchObject({ label: "21 days left", tone: "active" });
    expect(countdown(at(22))).toMatchObject({ label: "22 days left", tone: "quiet" });
    expect(countdown(at(-3))).toMatchObject({ label: "Closed", tone: "quiet" });
  });
});

describe("the form's draft", () => {
  it("names the seven required fields when they are empty", () => {
    expect(Object.keys(checkDraft(EMPTY_DRAFT)).sort()).toEqual(
      ["areas", "description", "due_date", "external_url", "location", "opportunity_type", "title"],
    );
  });

  it("sends an empty event date as none, and checks no date", () => {
    const base = {
      ...EMPTY_DRAFT, opportunity_type: "workshop" as const, title: "T", description: "A",
      due_date: "2026-11-01", location: "Online", areas: [1], external_url: "https://example.org",
    };
    // An end before its start is the poster's to fix (ADR-050 decision 5).
    expect(checkDraft({ ...base, start_date: "2027-03-05", end_date: "2027-03-01" })).toEqual({});
    expect(inputFrom(base)).toMatchObject({ start_date: null, end_date: null, areas: [1] });
  });
});

describe("serverErrors", () => {
  it("puts a field's message on the field and anything else on the form", () => {
    expect(serverErrors({ title: ["Too long."], detail: "Slow down.", posted_by: ["Nope."] })).toEqual({
      fields: { title: "Too long." },
      form: "Slow down. Nope.",
    });
  });

  it("tolerates a body that is not an object", () => {
    expect(serverErrors("Bad Request")).toEqual({ fields: {}, form: null });
  });
});
