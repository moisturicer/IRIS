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
  it("names the four required fields when they are empty", () => {
    expect(Object.keys(checkDraft(EMPTY_DRAFT)).sort()).toEqual(
      ["due_date", "opportunity_type", "posting_office", "title"],
    );
  });

  it("refuses a ceiling that is not a number, and accepts one with commas", () => {
    const base = { ...EMPTY_DRAFT, opportunity_type: "funding_window" as const, title: "T", posting_office: "O", due_date: "2026-11-01" };
    expect(checkDraft({ ...base, funding_ceiling: "lots" }).funding_ceiling).toBeDefined();
    expect(checkDraft({ ...base, funding_ceiling: "150,000" })).toEqual({});
    expect(inputFrom({ ...base, funding_ceiling: "150,000" }).funding_ceiling).toBe("150000");
    expect(inputFrom({ ...base, funding_ceiling: " " }).funding_ceiling).toBeNull();
  });

  it("splits tags on commas and drops blanks", () => {
    expect(inputFrom({ ...EMPTY_DRAFT, tags: " AI , , Robotics," }).tags).toEqual(["AI", "Robotics"]);
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
